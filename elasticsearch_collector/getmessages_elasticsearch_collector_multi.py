#!/usr/bin/env python
"""
Multi-index ElasticSearch collector.

Forks the standard 8.x collector and fans out one PIT-paginated fetcher per
concrete index instead of opening a single PIT across a wildcard. Solves the
case where an API key has read access to *some* indices that match a pattern
but not all of them: a single multi-index PIT would 403 on the unauthorized
ones, while per-index PITs succeed independently.

Reuses everything from getmessages_elasticsearch_collector_8x except the
data-fetch coordinator (process_get_data) and main(). Parsing, sending,
config loading, logging, and signal handling are imported unchanged.
"""
import logging
import multiprocessing
import signal
import sys
import time
from multiprocessing import Process, Queue
from multiprocessing.pool import ThreadPool
from threading import Lock

import arrow
import requests
from urllib3.exceptions import InsecureRequestWarning

import getmessages_elasticsearch_collector_8x as base
from getmessages_elasticsearch_collector_8x import (
    CLOSED_MESSAGE,
    config_ini_path,
    get_agent_config_vars,
    get_cli_config_vars,
    get_es_connection,
    get_if_config_vars,
    listener_process,
    print_summary_info,
    process_build_buffer,
    process_parse_messages,
    query_messages_elasticsearch,
    worker_configurer,
    merge,
)


DEFAULT_MAX_INDEX_WORKERS = 5


def resolve_indices(logger, es_conn, pattern, headers):
    """Return the list of concrete indices the API key can read for a pattern.

    Uses _resolve/index, which is security-aware: indices the user lacks
    view_index_metadata on are silently dropped. Falls back to [pattern]
    on any failure so single-name configs keep working.
    """
    if not any(c in pattern for c in '*?,'):
        return [pattern]
    try:
        resolved = es_conn.transport.perform_request(
            'GET',
            f'/_resolve/index/{pattern}?expand_wildcards=open',
            headers=headers,
        )
        names = [i['name'] for i in resolved.get('indices', [])]
        if not names:
            logger.error(f"No authorized indices match pattern: {pattern}")
            return []

        # Try to find unauthorized indices via _cat/indices (requires monitor privilege).
        try:
            cat_response = es_conn.transport.perform_request(
                'GET',
                f'/_cat/indices/{pattern}?h=index&expand_wildcards=open',
                headers=headers,
            )
            all_indices = set(cat_response.strip().splitlines())
            unauthorized = sorted(all_indices - set(names))
            if unauthorized:
                logger.warning(
                    f"The following indices matched pattern '{pattern}' but are "
                    f"not authorized for this API key: {unauthorized}"
                )
        except Exception:
            pass  # monitor privilege not available, skip unauthorized logging

        logger.info(f"Pattern '{pattern}' resolved to {len(names)} authorized indices: {names}")
        return names
    except Exception as ex:
        logger.warning(f"index resolve failed, using raw pattern. {ex}")
        return [pattern]


def fetch_one_index(log_queue, cli_config_vars, if_config_vars, agent_config_vars,
                    messages, time_now, collector_id, index_name):
    """Per-index fetcher process. Opens a PIT on a single index, runs the
    same query/pagination logic as the standard collector, pushes parsed
    messages onto the shared queue, then exits. Does NOT enqueue
    CLOSED_MESSAGE - the coordinator does that once all fetchers are done.
    """
    worker_configurer(log_queue, cli_config_vars['log_level'])
    logger = logging.getLogger('worker')
    logger.info(f'[{index_name}] starting fetcher (collector {collector_id})')

    collector_count = cli_config_vars['collector']
    sampling_interval = if_config_vars['sampling_interval']
    collector_interval = sampling_interval // collector_count

    es_conn = get_es_connection(logger, agent_config_vars)
    if not es_conn:
        logger.error(f'[{index_name}] ES connection failed, skipping.')
        return

    custom_headers = agent_config_vars.get('headers') or None

    try:
        pit_response = es_conn.open_point_in_time(
            index=index_name, keep_alive="1m", headers=custom_headers
        )
        pit = pit_response['id']
    except Exception as ex:
        logger.error(f'[{index_name}] open PIT failed: {ex}')
        return

    timestamp_field = agent_config_vars['timestamp_field'].replace('_source.', '')

    def run_query(start_time, end_time):
        query_body = {
            "size": agent_config_vars['query_chunk_size'],
            "query": {
                "bool": {
                    "must": [
                        {
                            "range": {
                                timestamp_field: {
                                    "format": "epoch_second",
                                    'gte': start_time,
                                    'lt': end_time,
                                }
                            }
                        }
                    ],
                },
            },
            "pit": {'id': pit, 'keep_alive': '1m'},
            "sort": [{timestamp_field: {"order": "asc"}}],
        }
        if isinstance(agent_config_vars['query_json'], dict):
            merge(agent_config_vars['query_json'], query_body)
        logger.debug(f'[{index_name}] query: {query_body}')
        query_messages_elasticsearch(
            logger, cli_config_vars, if_config_vars, agent_config_vars, es_conn,
            query_body, messages, start_time * 1000, custom_headers,
        )

    try:
        if agent_config_vars['his_time_range']:
            for ts in range(agent_config_vars['his_time_range'][0],
                            agent_config_vars['his_time_range'][1],
                            sampling_interval):
                start = ts + collector_id * collector_interval
                run_query(start, start + collector_interval)
        else:
            offset = agent_config_vars['query_time_offset_seconds']
            start = time_now - offset - (collector_id + 1) * collector_interval
            run_query(start, start + collector_interval)
    except Exception as ex:
        logger.error(f'[{index_name}] fetcher error: {ex}')
    finally:
        try:
            es_conn.close_point_in_time(id=pit, headers=custom_headers)
        except Exception:
            pass
        logger.info(f'[{index_name}] fetcher done.')


def process_get_data_multi(log_queue, cli_config_vars, if_config_vars, agent_config_vars,
                           messages, worker_process, time_now, collector_id):
    """Coordinator: resolve the index pattern, fan out one fetcher process per
    authorized index in bounded chunks, then signal parser workers to stop.
    Drop-in replacement for base.process_get_data in this script's main().
    """
    worker_configurer(log_queue, cli_config_vars['log_level'])
    logger = logging.getLogger('worker')
    logger.info(f'multi-index coordinator starting (collector {collector_id})')

    es_conn = get_es_connection(logger, agent_config_vars)
    if not es_conn and collector_id == 0:
        logger.error('ES connection failed; aborting.')
        for _ in range(worker_process):
            messages.put(CLOSED_MESSAGE)
        messages.close()
        return

    custom_headers = agent_config_vars.get('headers') or None
    pattern = agent_config_vars['indeces']
    indices = resolve_indices(logger, es_conn, pattern, custom_headers)

    if not indices:
        for _ in range(worker_process):
            messages.put(CLOSED_MESSAGE)
        messages.close()
        return

    max_workers = int(agent_config_vars.get('max_index_workers') or DEFAULT_MAX_INDEX_WORKERS)
    logger.info(f'Fanning out across {len(indices)} indices, '
                f'{max_workers} concurrent fetchers.')

    for i in range(0, len(indices), max_workers):
        chunk = indices[i:i + max_workers]
        procs = []
        for idx in chunk:
            p = Process(
                target=fetch_one_index,
                args=(log_queue, cli_config_vars, if_config_vars, agent_config_vars,
                      messages, time_now, collector_id, idx),
            )
            p.daemon = True
            p.start()
            procs.append(p)
        for p in procs:
            p.join()

    for _ in range(worker_process):
        messages.put(CLOSED_MESSAGE)
    messages.close()
    logger.info('multi-index coordinator finished.')


def main():
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
    timer = arrow.utcnow().float_timestamp

    cli_config_vars = get_cli_config_vars()
    logging.captureWarnings(True)
    logging.getLogger('elasticsearch').setLevel(logging.WARNING)

    m = multiprocessing.Manager()
    log_queue = m.Queue()

    worker_configurer(log_queue, cli_config_vars['log_level'])
    logger = logging.getLogger('worker')

    config_file = config_ini_path(cli_config_vars)
    agent_config_vars = get_agent_config_vars(logger, config_file)
    if not agent_config_vars:
        time.sleep(1)
        sys.exit(1)

    if_config_vars = get_if_config_vars(logger, config_file, agent_config_vars)
    if not if_config_vars:
        time.sleep(1)
        sys.exit(1)

    if 'METRIC' in if_config_vars['project_type']:
        cli_config_vars['collector'] = 1

    listener = Process(target=listener_process, args=(log_queue, cli_config_vars, if_config_vars))
    listener.daemon = True
    listener.start()

    logger.info(f"Multi-index ES collector started with config: {config_file}")
    print_summary_info(logger, if_config_vars, agent_config_vars)

    messages = Queue()
    datas = Queue()
    processes = []
    worker_process = cli_config_vars['process']
    worker_timeout = cli_config_vars['timeout'] if cli_config_vars['timeout'] > 0 else None
    collector_process = cli_config_vars['collector']

    time_now = int(arrow.utcnow().float_timestamp)
    for collector_id in range(collector_process):
        d = Process(
            target=process_get_data_multi,
            args=(log_queue, cli_config_vars, if_config_vars, agent_config_vars,
                  messages, worker_process, time_now, collector_id),
        )
        d.daemon = True
        d.start()
        processes.append(d)

    for _ in range(worker_process):
        d = Process(
            target=process_parse_messages,
            args=(log_queue, cli_config_vars, if_config_vars, agent_config_vars, messages, datas),
        )
        d.daemon = True
        d.start()
        processes.append(d)

    def term(sig_num, addition):
        try:
            for p in processes:
                logger.info('process %d terminate' % p.pid)
                p.terminate()
            time.sleep(1)
            sys.exit(1)
        except Exception as e:
            logger.error(str(e))

    signal.signal(signal.SIGTERM, term)

    meta_info = {"projects": {}}
    project_create_lock = Lock()
    pool_map = ThreadPool(worker_process)
    pool_map.map_async(
        process_build_buffer,
        [(logger, cli_config_vars, if_config_vars, datas, meta_info, project_create_lock)
         for _ in range(worker_process)],
    )
    pool_map.close()
    pool_map.join()

    for p in processes:
        p.join(timeout=worker_timeout)

    logger.setLevel(logging.INFO)
    logger.info("Agent completed in {} seconds".format(arrow.utcnow().float_timestamp - timer))

    time.sleep(1)
    logging.getLogger('KILL').info('KILL')


if __name__ == "__main__":
    main()

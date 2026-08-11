#!/usr/bin/env python
import configparser
import http.client
import json
import logging
import multiprocessing
import os
import random
import re
import shlex
import signal
import socket
import sys
import threading
import time
import traceback
import urllib.parse
import warnings
from logging.handlers import QueueHandler, TimedRotatingFileHandler
from multiprocessing import Process, Queue
from multiprocessing.pool import ThreadPool
from optparse import OptionParser
from pathlib import Path
from pprint import pformat
from sys import getsizeof
from threading import Lock
from time import sleep

import arrow
import regex
import requests
from urllib3.exceptions import InsecureRequestWarning

import servicenow_auth

# NOTE: intentionally no logging.basicConfig() here. Worker processes attach a
# QueueHandler that forwards records to the listener process (which formats them).
# A basicConfig root StreamHandler would ALSO fire in each worker, printing every
# line a second time in the raw "INFO:worker:..." format.

"""
This agent queries ServiceNow (Table API) for ticket data and sends each
record to InsightFinder as a LOG entry.
"""

# declare a few vars
SPACES = regex.compile(r"\s+")
SLASHES = regex.compile(r"\/+")
UNDERSCORE = regex.compile(r"\_+")
COLONS = regex.compile(r"\:+")
LEFT_BRACE = regex.compile(r"\[")
RIGHT_BRACE = regex.compile(r"\]")
PERIOD = regex.compile(r"\.")
PIPE = regex.compile(r"\|+")
PROJECT_ALNUM = regex.compile(r"[@\._]+")
NON_ALNUM = regex.compile(r"[^a-zA-Z0-9]")
HOSTNAME = socket.gethostname().partition('.')[0]
ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
ATTEMPTS = 2
RETRY_WAIT_TIME_IN_SEC = 5
PARSE_DATA_LOG_COUNT = 5000
CLOSED_MESSAGE = "CLOSED_MESSAGE"
SESSION = requests.Session()  # used for the InsightFinder side only
LOG_DIR = "logs"
AGENT_LOG_FILE = "./logs/agent.log"

# --dump-file: guards concurrent writes from the sender ThreadPool's threads
# (all in one process, so a plain threading.Lock -- not a Manager lock -- is
# sufficient). See send_data_to_if().
DUMP_FILE_LOCK = Lock()

# ServiceNow-specific tuning. These are deliberately module constants, not
# config keys -- they are implementation details, not deployment decisions.
SNOW_TABLE_PATH = '/api/now/table/{}'
SYSPARM_DISPLAY_VALUE = 'all'
SYSPARM_EXCLUDE_REFERENCE_LINK = 'true'
SNOW_ORDERBY_TIEBREAK = 'sys_id'
SNOW_REQUEST_TIMEOUT = 120
SNOW_MAX_RETRIES = 4
SNOW_BACKOFF_BASE = 2
SNOW_BACKOFF_MAX = 60
MAX_SYSPARM_QUERY_LEN = 4000  # ServiceNow returns HTTP 414 well before this
RETRYABLE = {429, 500, 502, 503, 504}
SEEN_CAP = 200000  # in-run dedup set cap, see process_parse_messages

QUERY_SECTION_PREFIX = 'query:'
PER_QUERY_KEYS = (
    'sysparm_query', 'data_fields', 'timestamp_field', 'timestamp_format', 'timezone',
    'target_timestamp_timezone', 'instance_field', 'instance_field_regex',
    'instance_whitelist', 'default_instance_name', 'project_name',
)

# ServiceNow credentials come from the environment (a local .env file or real
# env vars/--env-file in Docker), never from config.ini -- so a config file
# can be safely shared/committed without exposing secrets. See
# load_dotenv_file() and get_agent_config_vars().
ENV_OAUTH_CLIENT_ID = 'SERVICENOW_OAUTH_CLIENT_ID'
ENV_OAUTH_CLIENT_SECRET = 'SERVICENOW_OAUTH_CLIENT_SECRET'
ENV_OAUTH_USERNAME = 'SERVICENOW_OAUTH_USERNAME'
ENV_OAUTH_PASSWORD = 'SERVICENOW_OAUTH_PASSWORD'
ENV_USERNAME = 'SERVICENOW_USERNAME'
ENV_PASSWORD = 'SERVICENOW_PASSWORD'
DOTENV_FILENAME = '.env'

# OAuth2 always uses the password grant against the fixed /oauth_token.do
# endpoint with no scope -- not configurable, since every known ServiceNow
# instance uses exactly this (client_credentials needs an OAuth Entity
# Profile most instances don't have enabled).
OAUTH_GRANT_TYPE = 'password'
OAUTH_TOKEN_PATH = '/oauth_token.do'

logCompressState = {}


def load_dotenv_file(path):
    """Loads KEY=VALUE lines from a .env file into os.environ, skipping blank
    lines and lines starting with '#'. A variable already present in the
    environment (e.g. set by `docker run -e`, `--env-file`, or the shell) is
    never overridden -- the file is a convenience default, not an
    override mechanism. Silently does nothing if the file doesn't exist,
    since a .env file is optional when credentials are supplied by the
    environment directly.
    """
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


##############################################
# ServiceNow query / time-window construction #
##############################################
def compute_window(sampling_interval, query_time_offset_seconds, time_now):
    """Returns (lower, upper) as a half-open window [lower, upper) in epoch
    seconds: exactly the last `sampling_interval` seconds back from now
    (offset by query_time_offset_seconds). No state is kept between runs --
    every run queries this same fixed-size window, driven entirely by
    config.ini and cron's schedule. Set run_interval == sampling_interval so
    consecutive runs' windows are contiguous with no gap or overlap."""
    upper = time_now - query_time_offset_seconds
    lower = upper - sampling_interval
    return lower, upper


def build_time_filter(field, lower_s, upper_s):
    """Half-open, timezone-free time filter. GlideDateTime(String) parses
    ServiceNow's internal format, which is always UTC -- so there is no
    session-timezone ambiguity to get wrong, unlike gs.dateGenerate(), which
    resolves against the integration user's timezone."""
    lo = arrow.get(lower_s).to('UTC').format('YYYY-MM-DD HH:mm:ss')
    hi = arrow.get(upper_s).to('UTC').format('YYYY-MM-DD HH:mm:ss')
    return ("{f}>=javascript:new GlideDateTime('{lo}')"
            "^{f}<javascript:new GlideDateTime('{hi}')").format(f=field, lo=lo, hi=hi)


def build_sysparm_query(user_query, time_filter, timestamp_field, tiebreak_field=SNOW_ORDERBY_TIEBREAK):
    """Appends the time filter and a total-order ORDERBY to the user's query.

    ORDERBY alone does not make offset paging safe -- rows inserted mid-
    pagination still shift every later page. It is safe here only because the
    window is bounded above: any record touched during pagination gets
    <timestamp_field> >= hi and drops out of the result set entirely.
    """
    parts = []
    if user_query:
        parts.append(user_query.strip('^'))
    parts.append(time_filter)
    q = '^'.join(p for p in parts if p)
    q += '^ORDERBY{}'.format(timestamp_field)
    if tiebreak_field and tiebreak_field != timestamp_field:
        q += '^ORDERBY{}'.format(tiebreak_field)
    return q


def _resolve_ref_value(display_value, value):
    """Picks between a ServiceNow reference field's display_value and value:
    display_value wins if it is non-null and non-empty; otherwise value if
    THAT is non-null and non-empty; otherwise display_value itself -- so a
    null display_value with an empty value resolves to null, and an empty
    display_value with a null value resolves to ''. Either way, when both
    are empty/null the field's own display_value nullness/emptiness wins,
    never value's."""
    if display_value not in (None, ''):
        return display_value
    if value not in (None, ''):
        return value
    return display_value


def normalize_record(row):
    """Collapses ServiceNow's {"display_value": ..., "value": ...} reference
    shape (returned because sysparm_display_value=all) to a single value per
    field via _resolve_ref_value(). Strips any residual `link`. Drops empty
    fields from the result."""
    out = {}
    for k, v in row.items():
        if isinstance(v, dict) and ('display_value' in v or 'value' in v):
            out[k] = _resolve_ref_value(v.get('display_value'), v.get('value'))
        elif isinstance(v, dict):
            out[k] = {kk: vv for kk, vv in v.items() if kk != 'link'}
        else:
            out[k] = v
    return {k: v for k, v in out.items() if v not in (None, '', [], {})}


def get_field(rec, path):
    """Looks up a ServiceNow field that may be a flat, dot-walked key (e.g.
    requesting sysparm_fields=cmdb_ci.name returns a key literally named
    "cmdb_ci.name") or, failing that, a genuinely nested path. safe_get()
    alone would mis-split the former."""
    if path in rec:
        return rec[path]
    return safe_get(rec, path.split('.'))


def derive_timestamp_ms(raw_row, norm_row, query, logger):
    """Always reads the raw .value, never .display_value: .value is
    ServiceNow's UTC internal format (YYYY-MM-DD HH:mm:ss); .display_value is
    rendered in the user's display format (e.g. 08-07-2026 06:14:22 on a US
    instance), which would parse to nonsense under timestamp_format."""
    field = query['timestamp_field']
    raw_val = raw_row.get(field)
    if isinstance(raw_val, dict):
        val = raw_val.get('value')
        if val in (None, ''):
            val = raw_val.get('display_value')
    else:
        val = raw_val if raw_val not in (None, '') else get_field(norm_row, field)

    if val in (None, ''):
        return None

    if isinstance(val, str) and val.isdigit():
        ts = int(val)
        return (ts * 1000 if len(val) <= 10 else ts) + query['target_timestamp_timezone_offset'] * 1000

    try:
        a = arrow.get(val, query['timestamp_format'], tzinfo=query['timezone'])
    except Exception:
        try:
            a = arrow.get(val)
        except Exception as e:
            logger.debug('Could not parse timestamp %r for query %s: %s', val, query['name'], e)
            return None
    return int(a.float_timestamp * 1000) + query['target_timestamp_timezone_offset'] * 1000


def _parse_retry_after(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _backoff(attempt):
    """Exponential backoff with jitter -- jitter matters because N collector
    processes hitting a 429 at the same moment must not retry in lockstep."""
    return min(SNOW_BACKOFF_BASE * (2 ** attempt), SNOW_BACKOFF_MAX) * (0.5 + random.random())


def snow_get(logger, session, url, params, query_name):
    """A retry wrapper for ServiceNow requests. Deliberately not the
    boilerplate send_request(): that helper sleeps a flat 5s, retries only
    twice, and retries every non-200 including 4xx -- so a 403 costs a
    10-second stall and a 429 gets a sleep that ignores Retry-After. Here:
    retry RETRYABLE with backoff+jitter, honor Retry-After on 429, re-auth
    exactly once on 401, fail fast on every other 4xx."""
    tried_reauth = False
    for attempt in range(SNOW_MAX_RETRIES + 1):
        try:
            r = session.get(url, params=params, timeout=SNOW_REQUEST_TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt >= SNOW_MAX_RETRIES:
                logger.error('query %s: giving up after %d attempts: %s', query_name, attempt + 1, e)
                return None
            wait = _backoff(attempt)
            logger.warning('query %s: %s, retrying in %.1fs', query_name, e, wait)
            time.sleep(wait)
            continue

        if r.status_code == 200:
            return r

        if r.status_code == 401 and getattr(session, 'servicenow_auth', None) and not tried_reauth:
            logger.info('query %s: HTTP 401, invalidating cached token and retrying once', query_name)
            session.servicenow_auth.invalidate()
            tried_reauth = True
            continue

        if r.status_code in RETRYABLE:
            if attempt >= SNOW_MAX_RETRIES:
                logger.error('query %s: HTTP %d after %d attempts', query_name, r.status_code, attempt + 1)
                return None
            retry_after = _parse_retry_after(r.headers.get('Retry-After'))
            wait = retry_after if retry_after is not None else _backoff(attempt)
            wait = min(wait, SNOW_BACKOFF_MAX)
            logger.warning('query %s: HTTP %d, sleeping %.1fs (Retry-After=%s)',
                           query_name, r.status_code, wait, r.headers.get('Retry-After'))
            time.sleep(wait)
            continue

        # non-retryable: 400/403/404/414, or a second 401
        logger.error('query %s: non-retryable HTTP %d: %s', query_name, r.status_code, r.text[:500])
        return None

    return None


def fetch_query(logger, session, agent_config_vars, query, lower_s, upper_s, messages):
    """Pages through one [query:NAME]'s results for the window [lower_s,
    upper_s) and pushes each raw record onto `messages`, tagged with the
    query it came from. Returns (rows_sent, completed)."""
    if lower_s >= upper_s:
        return 0, True

    url = agent_config_vars['base_url'] + SNOW_TABLE_PATH.format(query['table'])
    time_filter = build_time_filter(query['timestamp_field'], lower_s, upper_s)
    sysparm_query = build_sysparm_query(query['sysparm_query'], time_filter, query['timestamp_field'])

    if len(sysparm_query) > MAX_SYSPARM_QUERY_LEN:
        logger.warning(
            'query %s: sysparm_query is %d chars; ServiceNow may return HTTP 414. '
            'Shorten sysparm_query or split into two [query:NAME] sections.',
            query['name'], len(sysparm_query))

    base_params = {
        'sysparm_query': sysparm_query,
        'sysparm_display_value': SYSPARM_DISPLAY_VALUE,
        'sysparm_exclude_reference_link': SYSPARM_EXCLUDE_REFERENCE_LINK,
        'sysparm_limit': agent_config_vars['query_chunk_size'],
    }
    if query['data_fields']:
        # Always fetch sys_id/number/timestamp_field over the wire regardless
        # of what the user configured, so instance/timestamp derivation and
        # the always-injected output keys never silently break because a
        # column was left out of data_fields.
        fields = list(dict.fromkeys(query['data_fields'] + ['sys_id', 'number', query['timestamp_field']]))
        base_params['sysparm_fields'] = ','.join(fields)
    # blank data_fields intentionally omits sysparm_fields -- ServiceNow
    # returns every column on the record.

    offset = 0
    total = None
    sent = 0
    while True:
        params = dict(base_params, sysparm_offset=offset)
        r = snow_get(logger, session, url, params, query['name'])
        if r is None:
            return sent, False
        try:
            body = r.json()
        except ValueError:
            # a hibernating developer instance returns HTTP 200 with an HTML body
            logger.error('query %s: non-JSON response (hibernating instance?): %s',
                         query['name'], r.text[:200])
            return sent, False

        rows = body.get('result', [])
        if total is None:
            try:
                total = int(r.headers.get('X-Total-Count', 0) or 0)
            except ValueError:
                total = len(rows)
            logger.info('query %s: X-Total-Count=%d window=[%s,%s)',
                        query['name'], total, lower_s, upper_s)

        for row in rows:
            messages.put({'_query': query['name'], '_table': query['table'], '_row': row})
            sent += 1

        offset += len(rows)
        if not rows or len(rows) < agent_config_vars['query_chunk_size'] or (total and offset >= total):
            break

    return sent, True


def process_get_data(log_queue, cli_config_vars, if_config_vars, agent_config_vars, secrets_vars, messages,
                     worker_process, time_now, collector_id, token_shared_dict):
    worker_configurer(log_queue, cli_config_vars['log_level'])
    logger = logging.getLogger('worker')
    logger.info('Starting get data from ServiceNow on collector {} ...'.format(collector_id))

    collector_count = cli_config_vars['collector']
    queries = agent_config_vars['queries']
    # Fan out per query, not per time-slice: sys_updated_on has 1-second
    # resolution and ticket volume is 10^2-10^3/day, so slicing one window N
    # ways would just multiply requests. main() clamps collector_count to
    # len(queries), so every collector below gets at least one query, and one
    # query's table 403'ing does not affect the others.
    my_queries = queries[collector_id::collector_count]

    snow_cfg = dict(agent_config_vars)
    snow_cfg.update(secrets_vars)
    cache_key = servicenow_auth.make_cache_key(
        snow_cfg['base_url'], snow_cfg.get('oauth_grant_type', ''), snow_cfg.get('oauth_client_id', ''),
        snow_cfg.get('oauth_username', ''), os.path.basename(cli_config_vars['config']))
    token_store = servicenow_auth.TokenStore(agent_config_vars['state_dir'], cache_key,
                                             shared_dict=token_shared_dict)
    session = servicenow_auth.build_session(snow_cfg, token_store, logger)

    if agent_config_vars['his_time_range']:
        lo, hi = agent_config_vars['his_time_range']
        for q in my_queries:
            logger.info('Using historical time range for query %s: [%s, %s)', q['name'], lo, hi)
            sent, completed = fetch_query(logger, session, agent_config_vars, q, lo, hi, messages)
            logger.info('query %s: sent %d rows, completed=%s', q['name'], sent, completed)
    else:
        for q in my_queries:
            lower_s, upper_s = compute_window(
                if_config_vars['sampling_interval'], agent_config_vars['query_time_offset_seconds'], time_now)
            logger.info('query %s: window=[%s, %s)', q['name'], lower_s, upper_s)
            sent, completed = fetch_query(logger, session, agent_config_vars, q, lower_s, upper_s, messages)
            logger.info('query %s: sent %d rows, completed=%s', q['name'], sent, completed)

    # send close signal for each worker
    for i in range(0, worker_process):
        messages.put(CLOSED_MESSAGE)
    messages.close()

    logger.info('Finish getting data from ServiceNow on collector {}'.format(collector_id))


def process_parse_messages(log_queue, cli_config_vars, if_config_vars, agent_config_vars, messages, datas):
    worker_configurer(log_queue, cli_config_vars['log_level'])
    logger = logging.getLogger('worker')
    logger.debug('Started data parse process ......')

    log_compression_interval = if_config_vars['log_compression_interval']
    collector_process = cli_config_vars['collector']
    project_name = if_config_vars['project_name']
    queries_by_name = agent_config_vars['queries_by_name']

    # In-run dedup against paging overlap; capped so a large backfill can't
    # grow this unboundedly. Cross-run dedup state is deliberately not
    # persisted -- sys_id/sys_updated_on are always in the payload, so any
    # duplicate that does slip through (e.g. after a retried, partially-sent
    # page) is identifiable downstream.
    seen = set()

    count = 0
    collector_quit = 0
    while True:
        current_time = time.time()
        try:
            message = messages.get()
            if message == CLOSED_MESSAGE:
                collector_quit += 1
                if collector_quit >= collector_process:
                    logger.debug('All records parsed.')
                    break
                else:
                    continue

            last_log_time = logCompressState.get('_parse_messages')
            needs_log_data = False
            if cli_config_vars['testing'] and (
                    not last_log_time or current_time - last_log_time > log_compression_interval):
                needs_log_data = True
                logCompressState['_parse_messages'] = current_time
                logger.info('Raw data (before normalization):\n' + pformat(message))

            query = queries_by_name.get(message['_query'])
            if not query:
                continue
            raw_row = message['_row']
            norm_row = normalize_record(raw_row)

            # norm_row, not raw_row: with sysparm_display_value=all every
            # field -- including sys_id itself -- comes back as
            # {"display_value": ..., "value": ...}, which is unhashable and
            # would break the `in seen` set lookup below.
            dedup_key = (message['_query'], norm_row.get('sys_id'), get_field(norm_row, query['timestamp_field']))
            if dedup_key in seen:
                continue
            if len(seen) >= SEEN_CAP:
                logger.warning('Dedup set exceeded %d entries; clearing. Duplicate suppression is '
                               'best-effort for the remainder of this run.', SEEN_CAP)
                seen.clear()
            seen.add(dedup_key)

            timestamp = derive_timestamp_ms(raw_row, norm_row, query, logger)
            if timestamp is None:
                msg = 'query {}: record missing/unparseable {}'.format(message['_query'], query['timestamp_field'])
                last = logCompressState.get(msg)
                if not last or current_time - last > log_compression_interval:
                    logCompressState[msg] = current_time
                    logger.warning(msg)
                continue

            # instance: in LOG mode `tag` is the instance name. Priority list
            # (e.g. cmdb_ci.name, business_service.name, assignment_group.name)
            # tried in order, then default_instance_name.
            instance = None
            for field, pattern in query['instance_field_regex_compiled']:
                field_val = get_field(norm_row, field)
                if field_val:
                    if not isinstance(field_val, str):
                        field_val = str(field_val)
                    matches = pattern.search(field_val)
                    if matches:
                        instance = matches.groups()[0]
                        break
            if not instance:
                for field in query['instance_field']:
                    val = get_field(norm_row, field)
                    if val:
                        instance = val
                        break
            if not instance:
                instance = query['default_instance_name']

            if query['instance_whitelist_regex'] and not (instance and query['instance_whitelist_regex'].match(instance)):
                continue

            full_instance = make_safe_instance_string(instance)

            # data: blank data_fields -> the entire normalized record,
            # unfiltered (safe_get_data is skipped -- an empty field list
            # there would yield {}). Set -> only those fields.
            if query['data_fields']:
                data = safe_get_data(norm_row, query['data_fields'], logger)
                if data == "":
                    data = {}
            else:
                data = dict(norm_row)

            data['_query'] = message['_query']
            data['_table'] = message['_table']
            data.setdefault('sys_id', norm_row.get('sys_id'))
            data.setdefault('number', norm_row.get('number'))

            data_entry = prepare_data_entry(if_config_vars, str(int(timestamp)), data, None, full_instance)
            if data_entry:
                data_entry['project'] = query['project_name'] or project_name
                data_entry['data_size'] = getsizeof(str(data))
                if needs_log_data:
                    logger.info('Parsed data (sent to InsightFinder):\n' + pformat(data_entry))
                datas.put(data_entry)

        except Exception as e:
            msg = str(e)
            current_time = time.time()
            last_log_time = logCompressState.get(msg)
            if not last_log_time or current_time - last_log_time > log_compression_interval:
                logCompressState[msg] = current_time
                logger.warning('Error when parsing message, error:\n' + msg)
                logger.warning(traceback.format_exc())
            continue

        count += 1
        if count % PARSE_DATA_LOG_COUNT == 0:
            logger.debug('Parse {0} messages'.format(count))

    datas.put(CLOSED_MESSAGE)
    logger.info('Finish parsing {0} messages'.format(count))


def process_build_buffer(args):
    logger, c_config, if_config_vars, datas, meta_info, project_create_lock = args
    logger.info(f'Starting send messages to IF server in thread {threading.current_thread().ident}')

    # build buffer
    project_tracks = {}
    total_sent = 0
    while True:
        try:
            message = datas.get()

            # parser process is closed. process and threads is one2one mapping
            if message == CLOSED_MESSAGE:
                # last chunk
                for project in project_tracks.keys():
                    if len(project_tracks[project]['current_row']) > 0:
                        logger.debug('Sending last chunk')
                        send_data_to_if(logger, c_config, if_config_vars, project_tracks[project],
                                        project_tracks[project]['current_row'], project)
                        reset_track(project_tracks[project])
                break

            project = message.pop('project')

            # check and create project
            if not c_config['testing']:
                with project_create_lock:
                    if project not in meta_info['projects']:
                        check_success = check_project_exist(logger, if_config_vars, project, c_config)
                        if not check_success:
                            return
                        meta_info['projects'][project] = True

            if project not in project_tracks.keys():
                project_tracks[project] = {'current_row': [], 'line_count': 0, 'data_size': 0}
            project_tracks[project]['current_row'].append(message)
            project_tracks[project]['line_count'] += 1
            project_tracks[project]['data_size'] += message.pop('data_size')

            if project_tracks[project]['data_size'] >= if_config_vars['chunk_size']:
                logger.debug(f'Sending buffer chunk: {project_tracks[project]["data_size"]}')
                send_data_to_if(logger, c_config, if_config_vars, project_tracks[project],
                                project_tracks[project]['current_row'], project)
                reset_track(project_tracks[project])

            total_sent += 1

        except Exception as e:
            logger.warn('Failed to send data for IF server.\n{}'.format(e))
            logger.debug(traceback.format_exc())
            continue

    logger.info(f'Finish sending {total_sent} messages to IF server in thread {threading.current_thread().ident}')


##############################
# Config parsing (agent-side) #
##############################
def _strip_quotes(val):
    """Strips one matching pair of surrounding quotes, e.g. so
    `sysparm_query = "opened_byLIKEInsight Finder"` can be written for
    readability without the literal `"` characters ending up in the value
    sent to ServiceNow. Only strips a single matching pair -- ' or " -- and
    only when both ends match, so a value that isn't quoted, or that
    legitimately starts/ends with one quote character, is left alone."""
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
        return val[1:-1]
    return val


def _cfg(config_parser, section, key, fallback=''):
    if config_parser.has_section(section) and config_parser.has_option(section, key):
        val = config_parser.get(section, key)
        if val is not None and val.strip():
            return _strip_quotes(val.strip())
    return fallback


def _query_cfg(config_parser, section, key, fallback=''):
    """ per-query lookup, falling back to the [servicenow] default """
    val = _cfg(config_parser, section, key, fallback=None)
    if val is not None:
        return val
    return _cfg(config_parser, 'servicenow', key, fallback=fallback)


def _finish_query(logger, section_or_name, q):
    """Shared normalization for a query dict built from a [query:NAME]
    section."""
    q['data_fields'] = [x.strip() for x in q['data_fields'].split(',') if x.strip()]
    q['instance_field'] = [x.strip() for x in q['instance_field'].split(',') if x.strip()]
    q['timestamp_field'] = q['timestamp_field'] or 'sys_created_on'
    q['timestamp_format'] = q['timestamp_format'] or 'YYYY-MM-DD HH:mm:ss'
    q['timezone'] = q['timezone'] or 'UTC'

    q['target_timestamp_timezone'] = q['target_timestamp_timezone'] or 'UTC'
    try:
        q['target_timestamp_timezone_offset'] = int(
            arrow.now(q['target_timestamp_timezone']).utcoffset().total_seconds())
    except Exception:
        logger.error('Agent not correctly configured (%s target_timestamp_timezone). Using UTC.', section_or_name)
        q['target_timestamp_timezone'] = 'UTC'
        q['target_timestamp_timezone_offset'] = 0

    if q['instance_whitelist']:
        try:
            q['instance_whitelist_regex'] = regex.compile(q['instance_whitelist'])
        except Exception as e:
            logger.error('Agent not correctly configured (%s instance_whitelist): %s', section_or_name, e)
            return None
    else:
        q['instance_whitelist_regex'] = None

    # Compiled once here rather than per-record in process_parse_messages'
    # hot loop -- instance_whitelist_regex above already worked this way,
    # this just makes instance_field_regex consistent with it.
    q['instance_field_regex_compiled'] = []
    if q['instance_field_regex']:
        try:
            for field_regex in q['instance_field_regex'].split(','):
                field, pattern = field_regex.split('::')
                q['instance_field_regex_compiled'].append((field, regex.compile(pattern)))
        except Exception as e:
            logger.error('Agent not correctly configured (%s instance_field_regex): %s', section_or_name, e)
            return None

    q['project_name'] = make_safe_project_string(q['project_name']) if q['project_name'] else None
    return q


def _build_query_from_section(logger, config_parser, section):
    name = section[len(QUERY_SECTION_PREFIX):].strip()
    if not name:
        logger.error('Agent not correctly configured (empty query name in [%s]).', section)
        return None

    table = _cfg(config_parser, section, 'table')
    if not table:
        logger.error('Agent not correctly configured ([%s] table).', section)
        return None

    q = {'name': name, 'table': table}
    for key in PER_QUERY_KEYS:
        q[key] = _query_cfg(config_parser, section, key)

    return _finish_query(logger, '[{}]'.format(section), q)


def get_agent_config_vars(logger, config_ini):
    """Reads the [servicenow] connection settings and every [query:NAME]
    section. Returns (config_vars, secrets_vars) on success, or (False,
    None) on error.

    Secrets are returned separately from config_vars, and never merged into
    it, because print_summary_info() (boilerplate) dumps every key of
    agent_config_vars at DEBUG -- running with -v would otherwise print the
    decoded client secret or password.
    """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False, None

    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser(interpolation=None)
        config_parser.read_file(fp)

        if not config_parser.has_section('servicenow'):
            return config_error(logger, '[servicenow] section'), None

        base_url = _cfg(config_parser, 'servicenow', 'base_url').rstrip('/')
        if not base_url:
            return config_error(logger, 'base_url'), None

        auth_type = _cfg(config_parser, 'servicenow', 'auth_type', 'oauth2').lower()
        if auth_type not in ('oauth2', 'basic'):
            return config_error(logger, 'auth_type'), None

        # Credentials live in the environment (.env file or real env vars),
        # never in config.ini -- see load_dotenv_file() and the ENV_* constants.
        # OAuth always uses the password grant against the fixed
        # /oauth_token.do endpoint (OAUTH_GRANT_TYPE / OAUTH_TOKEN_PATH below)
        # -- client_credentials and a configurable token path/scope are not
        # supported; they're not needed against any known ServiceNow instance
        # and just add config surface for no benefit.
        secrets = {}
        if auth_type == 'basic':
            username = os.environ.get(ENV_USERNAME, '').strip()
            password = os.environ.get(ENV_PASSWORD, '').strip()
            if not username or not password:
                return config_error(logger, '{} or {} environment variable'.format(
                    ENV_USERNAME, ENV_PASSWORD)), None
            secrets['username'] = username
            secrets['password'] = password
        else:
            oauth_client_id = os.environ.get(ENV_OAUTH_CLIENT_ID, '').strip()
            oauth_client_secret = os.environ.get(ENV_OAUTH_CLIENT_SECRET, '').strip()
            oauth_username = os.environ.get(ENV_OAUTH_USERNAME, '').strip()
            oauth_password = os.environ.get(ENV_OAUTH_PASSWORD, '').strip()
            if not oauth_client_id or not oauth_client_secret or not oauth_username or not oauth_password:
                return config_error(logger, '{}, {}, {}, or {} environment variable'.format(
                    ENV_OAUTH_CLIENT_ID, ENV_OAUTH_CLIENT_SECRET, ENV_OAUTH_USERNAME, ENV_OAUTH_PASSWORD)), None
            secrets['oauth_client_id'] = oauth_client_id
            secrets['oauth_client_secret'] = oauth_client_secret
            secrets['oauth_username'] = oauth_username
            secrets['oauth_password'] = oauth_password

        verify_certs = _cfg(config_parser, 'servicenow', 'verify_certs', 'true').lower() != 'false'
        ca_certs = _cfg(config_parser, 'servicenow', 'ca_certs') or None

        proxies = {}
        agent_http_proxy = _cfg(config_parser, 'servicenow', 'agent_http_proxy')
        agent_https_proxy = _cfg(config_parser, 'servicenow', 'agent_https_proxy')
        if agent_http_proxy:
            proxies['http'] = agent_http_proxy
        if agent_https_proxy:
            proxies['https'] = agent_https_proxy

        query_chunk_size = _cfg(config_parser, 'servicenow', 'query_chunk_size', '1000')
        try:
            query_chunk_size = int(query_chunk_size)
        except ValueError:
            logger.error('Agent not correctly configured (query_chunk_size). Using 1000 by default.')
            query_chunk_size = 1000

        query_time_offset_seconds = _cfg(config_parser, 'servicenow', 'query_time_offset_seconds', '0')
        try:
            query_time_offset_seconds = int(query_time_offset_seconds)
        except ValueError:
            logger.error('Agent not correctly configured (query_time_offset_seconds). Using 0 by default.')
            query_time_offset_seconds = 0

        his_time_range_str = _cfg(config_parser, 'servicenow', 'his_time_range')
        his_time_range = None
        if his_time_range_str:
            try:
                parts = [x.strip() for x in his_time_range_str.split(',') if x.strip()]
                his_time_range = [int(arrow.get(x).float_timestamp) for x in parts]
                if len(his_time_range) != 2:
                    raise ValueError('expected two comma-separated timestamps')
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'his_time_range'), None

        # queries
        queries = []
        for section in config_parser.sections():
            if not section.startswith(QUERY_SECTION_PREFIX):
                continue
            q = _build_query_from_section(logger, config_parser, section)
            if q is None:
                return config_error(logger, section), None
            queries.append(q)

        if not queries:
            return config_error(logger, 'no [query:NAME] sections defined'), None

        names = [q['name'] for q in queries]
        if len(set(names)) != len(names):
            return config_error(logger, 'duplicate query names'), None

        config_vars = {
            'base_url': base_url,
            'auth_type': auth_type,
            'oauth_token_path': OAUTH_TOKEN_PATH,
            'oauth_grant_type': OAUTH_GRANT_TYPE,
            'verify_certs': verify_certs,
            'ca_certs': ca_certs,
            'proxies': proxies,
            'query_chunk_size': query_chunk_size,
            'query_time_offset_seconds': query_time_offset_seconds,
            'his_time_range': his_time_range,
            'queries': queries,
            'queries_by_name': {q['name']: q for q in queries},
            'state_dir': abs_path_from_cur('cache'),
            # forces get_if_config_vars() to require [insightfinder] project_name
            # instead of a project_field (this agent has no single project field --
            # each query already carries its own optional project override).
            'project_field': None,
        }
        return config_vars, secrets


#########################
#   START_BOILERPLATE   #
#########################
def get_if_config_vars(logger, config_ini, agent_config_vars):
    """ get config.ini vars """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False
    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)
        try:
            user_name = config_parser.get('insightfinder', 'user_name')
            license_key = config_parser.get('insightfinder', 'license_key')
            token = config_parser.get('insightfinder', 'token')
            project_name = config_parser.get('insightfinder', 'project_name')
            system_name = config_parser.get('insightfinder', 'system_name')
            project_type = config_parser.get('insightfinder', 'project_type').upper()
            containerize = config_parser.get('insightfinder', 'containerize').upper()
            enable_holistic_model = config_parser.get('insightfinder', 'enable_holistic_model').upper()
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            frequency_sampling_interval = config_parser.get('insightfinder', 'frequency_sampling_interval')
            run_interval = config_parser.get('insightfinder', 'run_interval')
            enable_log_rotation = config_parser.get('insightfinder', 'enable_log_rotation')
            log_backup_count = config_parser.get('insightfinder', 'log_compression_interval')
            log_compression_interval = config_parser.get('insightfinder', 'log_compression_interval')
            chunk_size_kb = config_parser.get('insightfinder', 'chunk_size_kb')
            if_url = config_parser.get('insightfinder', 'if_url')
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        # check required variables
        if len(user_name) == 0:
            return config_error(logger, 'user_name')
        if len(license_key) == 0:
            return config_error(logger, 'license_key')
        if not agent_config_vars['project_field'] and len(project_name) == 0:
            return config_error(logger, 'project_field or project_name')
        if len(project_type) == 0:
            return config_error(logger, 'project_type')

        if project_type not in {
            'METRIC',
            'METRICREPLAY',
            'LOG',
            'LOGREPLAY',
            'INCIDENT',
            'INCIDENTREPLAY',
            'ALERT',
            'ALERTREPLAY',
            'DEPLOYMENT',
            'DEPLOYMENTREPLAY',
            'TRACE',
            'TRACEREPLAY',
        }:
            return config_error(logger, 'project_type')
        is_replay = 'REPLAY' in project_type

        if len(sampling_interval) == 0:
            if 'METRIC' in project_type:
                return config_error(logger, 'sampling_interval')
            else:
                # set default for non-metric
                sampling_interval = 10

        if sampling_interval.endswith('s'):
            sampling_interval = int(sampling_interval[:-1])
        else:
            sampling_interval = int(sampling_interval) * 60
        if frequency_sampling_interval.endswith('s'):
            frequency_sampling_interval = int(frequency_sampling_interval[:-1])
        else:
            frequency_sampling_interval = int(frequency_sampling_interval) * 60

        if len(log_compression_interval) == 0:
            return config_error(logger, 'log_compression_interval')

        if log_compression_interval.endswith('s'):
            log_compression_interval = int(log_compression_interval[:-1])
        else:
            log_compression_interval = int(log_compression_interval) * 60

        if enable_log_rotation and enable_log_rotation.lower() == 'true':
            enable_log_rotation = True
        else:
            enable_log_rotation = False

        if log_backup_count:
            log_backup_count = int(log_backup_count)
        else:
            log_backup_count = 0

        if len(run_interval) == 0:
            return config_error(logger, 'run_interval')

        if run_interval.endswith('s'):
            run_interval = int(run_interval[:-1])
        else:
            run_interval = int(run_interval) * 60

        # defaults
        if len(chunk_size_kb) == 0:
            chunk_size_kb = 2048  # 2MB chunks by default
        if len(if_url) == 0:
            if_url = 'https://app.insightfinder.com'

        # set IF proxies
        if_proxies = dict()
        if len(if_http_proxy) > 0:
            if_proxies['http'] = if_http_proxy
        if len(if_https_proxy) > 0:
            if_proxies['https'] = if_https_proxy

        config_vars = {
            'user_name': user_name,
            'license_key': license_key,
            'token': token,
            'project_name': project_name,
            'system_name': system_name,
            'project_type': project_type,
            'containerize': True if containerize == 'YES' else False,
            'enable_holistic_model': True if enable_holistic_model == 'TRUE' else False,
            'sampling_interval': int(sampling_interval),  # as seconds
            'frequency_sampling_interval': int(frequency_sampling_interval),  # as seconds
            'log_compression_interval': int(log_compression_interval),  # as seconds
            'enable_log_rotation': enable_log_rotation,
            'log_backup_count': log_backup_count,
            'run_interval': int(run_interval),  # as seconds
            'chunk_size': int(chunk_size_kb) * 1024,  # as bytes
            'if_url': if_url,
            'if_proxies': if_proxies,
            'is_replay': is_replay
        }

        return config_vars


def config_ini_path(cli_config_vars):
    return abs_path_from_cur(cli_config_vars['config'])


def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))


def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    parser.add_option('-c', '--config', action='store', dest='config', default=abs_path_from_cur('conf.d/config.ini'),
                      help='Path to the config file to use. Defaults to {}'.format(
                          abs_path_from_cur('conf.d/config.ini')))
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data).' +
                           ' Automatically turns on verbose logging')
    parser.add_option('-p', '--process', action='store', dest='process', default=1,
                      help='Number of processes for each agent to use for multithreading')
    parser.add_option('--timeout', action='store', dest='timeout', default=60,
                      help='Seconds of timeout for all worker processes')
    parser.add_option('-l', '--collector', action='store', dest='collector', default=4,
                      help='Number of processes for each agent to use to collect data from ServiceNow, '
                           'one query per collector')
    parser.add_option('--dump-file', action='store', dest='dump_file', default=None,
                      help='Testing only: write every entry that would be sent to InsightFinder to '
                           'this file, as JSON lines (one {eventId, tag, data} object per line). '
                           'The file is truncated at the start of each run. Combine with -t to '
                           'inspect the payload schema without actually sending data.')
    (options, args) = parser.parse_args()

    config_vars = {
        'config': options.config if os.path.isfile(options.config) else abs_path_from_cur('conf.d/config.ini'),
        'testing': False,
        'log_level': logging.INFO,
        'process': int(options.process),
        'timeout': int(options.timeout),
        'collector': int(options.collector),
        'dump_file': options.dump_file,
    }

    if options.testing:
        config_vars['testing'] = True

    if options.verbose:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING

    return config_vars


def config_error(logger, setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(
        info))
    return False


def safe_get(dct, keys):
    for key in keys:
        try:
            dct = dct[key]
        except KeyError:
            return None
    return dct


def flatten_json(y):
    out = {}

    def flatten(x, name=''):
        if type(x) is dict:
            for a in x:
                flatten(x[a], name + a + '.')
        elif type(x) is list:
            i = 0
            for a in x:
                flatten(a, name + str(i) + '.')
                i += 1
        else:
            out[name[:-1]] = x

    flatten(y)
    return out


def match_patterns(target, patterns):
    for pattern in patterns:
        if pattern.startswith('/') and pattern.endswith('/'):
            if regex.match(pattern[1:-1], target):
                return True
        else:
            if pattern == target:
                return True
    return False


def safe_get_data(dct, keys, logger):
    if not keys:
        return dct

    data = {}
    no_value_ct = 0  # count of empty values
    for key in keys:
        named_key = key.split('::')
        try:
            if len(named_key) > 1:
                try:
                    data[named_key[0]] = json.loads(dct[named_key[1]])
                except Exception:
                    data[named_key[0]] = dct[named_key[1]]
            else:
                try:
                    data[named_key[0]] = json.loads(dct[named_key[0]])
                except Exception:
                    data[named_key[0]] = dct[named_key[0]]
        except KeyError:
            logger.debug('safe_get_data key error, key={}'.format(key))
            no_value_ct += 1
            continue

    # If all keys don't have data
    if no_value_ct == len(keys):
        return ""

    return data


def prepare_data_entry(if_config_vars, timestamp, data, component_name, instance_name):
    """ creates the log entry """
    entry = dict()
    entry['data'] = data
    if 'INCIDENT' in if_config_vars['project_type'] or 'DEPLOYMENT' in if_config_vars['project_type']:
        entry['timestamp'] = timestamp
        entry['instanceName'] = instance_name
    elif 'METRIC' in if_config_vars['project_type']:
        entry['timestamp'] = timestamp
        entry['componentName'] = component_name
        entry['instanceName'] = instance_name
    else:  # LOG or ALERT
        entry['eventId'] = timestamp
        entry['tag'] = instance_name
    return entry


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    return getsizeof(json.dumps(json_data))


def make_safe_project_string(project):
    """ make a safe project name string """
    # strip underscores
    project = PIPE.sub('', project)
    project = PROJECT_ALNUM.sub('-', project)
    return project


def make_safe_component_string(component):
    """ make a safe component name string"""
    if not component:
        return None

    # strip underscores
    component = UNDERSCORE.sub('.', component)
    component = COLONS.sub('-', component)
    return component


def make_safe_instance_string(instance, device=''):
    """ make a safe instance name string, concatenated with device if appropriate """
    if not instance:
        instance = 'unknown'

    # strip underscores
    instance = UNDERSCORE.sub('.', instance)
    instance = COLONS.sub('-', instance)

    # remove leading special characters (hyphens, underscores, etc.)
    instance = re.sub(r'^[-_\W]+', '', instance)

    # if there's a device, concatenate it to the instance with an underscore
    if device:
        instance = '{}_{}'.format(make_safe_instance_string(device), instance)
    return instance


def make_safe_metric_key(metric):
    """ make safe string already handles this """
    metric = LEFT_BRACE.sub('(', metric)
    metric = RIGHT_BRACE.sub(')', metric)
    metric = PERIOD.sub('/', metric)
    return metric


def make_safe_string(string):
    """
    Take a single string and return the same string with spaces, slashes,
    underscores, and non-alphanumeric characters subbed out.
    """
    string = SPACES.sub('-', string)
    string = SLASHES.sub('.', string)
    string = UNDERSCORE.sub('.', string)
    string = NON_ALNUM.sub('', string)
    return string


def merge(source, destination):
    """
    run me with nosetests --with-doctest file.py

    >>> a = { 'first' : { 'all_rows' : { 'pass' : 'dog', 'number' : '1' } } }
    >>> b = { 'first' : { 'all_rows' : { 'fail' : 'cat', 'number' : '5' } } }
    >>> merge(b, a) == { 'first' : { 'all_rows' : { 'pass' : 'dog', 'fail' : 'cat', 'number' : '5' } } }
    True
    """
    for key, value in source.items():
        if isinstance(value, dict):
            # get node or create one
            node = destination.setdefault(key, {})
            merge(value, node)
        else:
            destination[key] = value

    return destination


def format_command(cmd):
    if not isinstance(cmd, (list, tuple)):  # no sets, as order matters
        cmd = shlex.split(cmd)
    return list(cmd)


def set_logger_config(level):
    """ set up logging according to the defined log level """
    # Get the root logger
    logger_obj = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger_obj.setLevel(level)
    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
    # create a logging format
    formatter = logging.Formatter(
        '{ts} [pid {pid}] {lvl} {mod}.{func}():{line} {msg}'.format(
            ts='%(asctime)s',
            pid='%(process)d',
            lvl='%(levelname)-8s',
            mod='%(module)s',
            func='%(funcName)s',
            line='%(lineno)d',
            msg='%(message)s'),
        ISO8601[0])
    logging_handler_out.setFormatter(formatter)
    logger_obj.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.INFO)
    logger_obj.addHandler(logging_handler_err)
    return logger_obj


def print_summary_info(logger, if_config_vars, agent_config_vars):
    # info to be sent to IF
    post_data_block = '\nIF settings:'
    for ik, iv in sorted(if_config_vars.items()):
        post_data_block += '\n\t{}: {}'.format(ik, iv)
    logger.debug(post_data_block)

    # variables from agent-specific config
    agent_data_block = '\nAgent settings:'
    for jk, jv in sorted(agent_config_vars.items()):
        agent_data_block += '\n\t{}: {}'.format(jk, jv)
    logger.debug(agent_data_block)


def reset_track(track):
    """ reset the track global for the next chunk """
    track['current_row'] = []
    track['line_count'] = 0
    track['data_size'] = 0


################################
# Functions to send data to IF #
################################
def send_data_to_if(logger, c_config, if_config_vars, track, chunk_metric_data, project):
    timeout = None
    if c_config:
        timeout = c_config['timeout'] if c_config['timeout'] > 0 else None

    send_data_time = time.time()

    data_to_post = initialize_api_post_data(logger, if_config_vars, project)
    data_to_post[get_data_field_from_project_type(if_config_vars)] = json.dumps(chunk_metric_data)
    post_url = urllib.parse.urljoin(if_config_vars['if_url'], get_api_from_project_type(if_config_vars))

    logger.debug('First:\n' + str(chunk_metric_data[0]))
    logger.debug('Last:\n' + str(chunk_metric_data[-1]))
    logger.debug('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
    logger.debug('Total Lines: ' + str(track['line_count']))

    # --dump-file: write the exact entries that would be POSTed to
    # InsightFinder (one JSON object per line) for schema inspection.
    # Independent of -t/--testing -- combine both to inspect without sending.
    if c_config.get('dump_file'):
        with DUMP_FILE_LOCK:
            with open(c_config['dump_file'], 'a') as f:
                for entry in chunk_metric_data:
                    f.write(json.dumps(entry) + '\n')
        logger.info('Dumped %d entries to %s', len(chunk_metric_data), c_config['dump_file'])

    # do not send if only testing
    if c_config['testing']:
        return

    logger.info('Total Lines: ' + str(len(chunk_metric_data)))
    logger.info('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
    logger.debug(data_to_post)

    send_request(logger, post_url, 'POST', 'Could not send request to IF',
                str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.', data=data_to_post,
                verify=False, proxies=if_config_vars['if_proxies'], timeout=timeout)

    logger.info('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def send_request(logger, url, mode='GET', failure_message='Failure!', success_message='Success!',
                 **request_passthrough):
    """ sends a request to the given url. Used for the InsightFinder side
    only -- ServiceNow requests go through snow_get(), which has real
    Retry-After/backoff/401 handling that this simple loop lacks. """
    req = SESSION.get
    if mode.upper() == 'POST':
        req = SESSION.post

    req_num = 0
    for req_num in range(ATTEMPTS):
        try:
            response = req(url, **request_passthrough)
            if response.status_code == http.client.OK:
                return response
            else:
                logger.warning(failure_message)
                logger.info('Response Code: {}\nTEXT: {}'.format(
                    response.status_code, response.text))
        except requests.exceptions.Timeout:
            logger.exception('Timed out. Reattempting...')
            continue
        except requests.exceptions.TooManyRedirects:
            logger.exception('Too many redirects.')
            break
        except requests.exceptions.RequestException as e:
            logger.exception('Exception ' + str(e))
            break

        time.sleep(RETRY_WAIT_TIME_IN_SEC)

    logger.error('Failed! Gave up after {} attempts.'.format(req_num + 1))
    return -1


def get_data_type_from_project_type(if_config_vars):
    """ use project type to determine data type """
    if 'METRIC' in if_config_vars['project_type']:
        return 'Metric'
    elif 'ALERT' in if_config_vars['project_type']:
        return 'Log'
    elif 'INCIDENT' in if_config_vars['project_type']:
        return 'Incident'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'Deployment'
    elif 'TRACE' in if_config_vars['project_type']:
        return 'Trace'
    else:  # LOG
        return 'Log'


def get_insight_agent_type_from_project_type(if_config_vars):
    if 'containerize' in if_config_vars and if_config_vars['containerize']:
        if 'METRIC' in if_config_vars['project_type']:
            if if_config_vars['is_replay']:
                return 'containerReplay'
            else:
                return 'containerStreaming'
        else:
            if if_config_vars['is_replay']:
                return 'ContainerHistorical'
            else:
                return 'ContainerCustom'
    elif if_config_vars['is_replay']:
        if 'METRIC' in if_config_vars['project_type']:
            return 'MetricFile'
        else:
            return 'LogFile'
    else:
        return 'Custom'


def get_agent_type_from_project_type(if_config_vars):
    """ use project type to determine agent type """
    if 'METRIC' in if_config_vars['project_type']:
        if if_config_vars['is_replay']:
            return 'MetricFileReplay'
        else:
            return 'CUSTOM'
    elif if_config_vars['is_replay']:
        return 'LogFileReplay'
    else:
        return 'LogStreaming'
    # INCIDENT and DEPLOYMENT don't use this


def get_data_field_from_project_type(if_config_vars):
    """ use project type to determine which field to place data in """
    if 'INCIDENT' in if_config_vars['project_type']:
        return 'incidentData'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'deploymentData'
    else:  # METRIC, LOG, ALERT
        return 'metricData'


def get_api_from_project_type(if_config_vars):
    """ use project type to determine which API to post to """
    if 'INCIDENT' in if_config_vars['project_type']:
        return '/api/v1/incidentdatareceive'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return '/api/v1/deploymentEventReceive'
    else:  # METRIC, LOG, ALERT
        return '/api/v1/customprojectrawdata'


def initialize_api_post_data(logger, if_config_vars, project):
    """ set up the unchanging portion of this """
    to_send_data_dict = dict()
    to_send_data_dict['userName'] = if_config_vars['user_name']
    to_send_data_dict['licenseKey'] = if_config_vars['license_key']
    to_send_data_dict['projectName'] = project or if_config_vars['project_name']
    to_send_data_dict['instanceName'] = HOSTNAME
    to_send_data_dict['agentType'] = get_agent_type_from_project_type(if_config_vars)
    if 'METRIC' in if_config_vars['project_type'] and 'sampling_interval' in if_config_vars:
        to_send_data_dict['samplingInterval'] = str(if_config_vars['sampling_interval'])
    logger.debug(to_send_data_dict)
    return to_send_data_dict


def check_project_exist(logger, if_config_vars, project, c_config):
    timeout = None
    if c_config:
        timeout = c_config['timeout'] if c_config['timeout'] > 0 else None

    is_project_exist = False
    try:
        logger.info(f'Starting check project: {project or if_config_vars["project_name"]}')
        params = {
            'operation': 'check',
            'userName': if_config_vars['user_name'],
            'licenseKey': if_config_vars['license_key'],
            'projectName': project or if_config_vars['project_name'],
        }
        url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
        response = send_request(logger, url, 'POST', data=params, verify=False, proxies=if_config_vars['if_proxies'],
                                timeout=5)
        if response == -1:
            logger.error(f'Check project error: {project or if_config_vars["project_name"]}')
        else:
            result = response.json()
            if result['success'] is False or result['isProjectExist'] is False:
                logger.error(f'Check project error: {project or if_config_vars["project_name"]}')
            else:
                is_project_exist = True
                logger.info(f'Check project success: {project or if_config_vars["project_name"]}')

    except Exception as e:
        logger.error(e)
        logger.error(f'Check project error: {project or if_config_vars["project_name"]}')

    create_project_sucess = False
    if not is_project_exist:
        try:
            logger.info(f'Starting add project: {project or if_config_vars["project_name"]}')
            params = {
                'operation': 'create',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': project or if_config_vars['project_name'],
                'systemName': if_config_vars['system_name'] or project or if_config_vars['project_name'],
                'instanceType': 'PrivateCloud',
                'projectCloudType': 'PrivateCloud',
                'dataType': get_data_type_from_project_type(if_config_vars),
                'insightAgentType': get_insight_agent_type_from_project_type(if_config_vars),
                'samplingInterval': int(if_config_vars['frequency_sampling_interval'] / 60),
                'samplingIntervalInSeconds': if_config_vars['frequency_sampling_interval'],
                'projectModelFlag': if_config_vars['enable_holistic_model'],
            }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'], timeout=5)
            if response == -1:
                logger.error(f'Check project error: {project or if_config_vars["project_name"]}')
            else:
                result = response.json()
                if result['success'] is False:
                    logger.error(f'Check project error: {project or if_config_vars["project_name"]}')
                else:
                    create_project_sucess = True
                    logger.info(f'Check project success: {project or if_config_vars["project_name"]}')

        except Exception as e:
            logger.error(e)
            logger.error(f'Check project error: {project or if_config_vars["project_name"]}')

    if create_project_sucess:
        # if create project is success, sleep 10s and check again
        time.sleep(10)
        try:
            logger.info(f'Starting check project: {project or if_config_vars["project_name"]}')
            params = {
                'operation': 'check',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': project or if_config_vars['project_name'],
            }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'], timeout=timeout)
            if response == -1:
                logger.error(f'Check project error: {project or if_config_vars["project_name"]}')
            else:
                result = response.json()
                if result['success'] is False or result['isProjectExist'] is False:
                    logger.error(f'Check project error: {project or if_config_vars["project_name"]}')
                else:
                    is_project_exist = True
                    logger.info(f'Check project success: {project or if_config_vars["project_name"]}')

        except Exception as e:
            logger.error(e)
            logger.error(f'Check project error: {project or if_config_vars["project_name"]}')

    return is_project_exist


def listener_configurer(c_config, if_config_vars):
    # Get config file name
    config_name = os.path.basename(c_config['config'])
    level = c_config['log_level']
    enable_log_rotation = if_config_vars.get('enable_log_rotation')
    log_backup_count = if_config_vars.get('log_backup_count')

    # create a logging format
    formatter = logging.Formatter(
        '{ts} [{cfg}] [pid {pid}] {lvl} {mod}.{func}():{line} | {msg}'.format(
            ts='%(asctime)s',
            cfg=config_name,
            pid='%(process)d',
            lvl='%(levelname)-8s',
            mod='%(module)s',
            func='%(funcName)s',
            line='%(lineno)d',
            msg='%(message)s'),
        ISO8601[0])

    # Get the root logger
    root = logging.getLogger()
    root.setLevel(level)
    # Drop any handlers inherited from the parent (e.g. the QueueHandler) so the
    # listener doesn't re-enqueue records it is meant to emit.
    for hdlr in list(root.handlers):
        root.removeHandler(hdlr)

    if enable_log_rotation:
        # create log output folder if not exists
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
        handler = TimedRotatingFileHandler(AGENT_LOG_FILE, when='MIDNIGHT', backupCount=log_backup_count)
        handler.setFormatter(formatter)
        root.addHandler(handler)
    else:
        # stdout gets DEBUG/INFO only; stderr gets WARNING+. The stdout filter keeps
        # a single record from printing on both streams (which doubled warnings/errors).
        logging_handler_out = logging.StreamHandler(sys.stdout)
        logging_handler_out.setLevel(logging.DEBUG)
        logging_handler_out.addFilter(lambda r: r.levelno < logging.WARNING)
        logging_handler_out.setFormatter(formatter)
        root.addHandler(logging_handler_out)

        logging_handler_err = logging.StreamHandler(sys.stderr)
        logging_handler_err.setLevel(logging.WARNING)
        logging_handler_err.setFormatter(formatter)
        root.addHandler(logging_handler_err)


def listener_process(q, c_config, if_config_vars):
    listener_configurer(c_config, if_config_vars)
    while True:
        try:
            while not q.empty():
                try:
                    record = q.get()

                    if not record:
                        continue

                    if record.name == 'KILL':
                        return

                    logger = logging.getLogger(record.name)
                    logger.handle(record)
                except Exception as e:
                    # if exception raise, the main process quit, so the listener process should quit too
                    return
        except Exception as e:
            return
        sleep(1)


def worker_configurer(q, level):
    root = logging.getLogger()
    # Drop any handlers inherited from the parent process (forked children already
    # carry the parent's QueueHandler); otherwise each record is enqueued - and so
    # printed - more than once.
    for hdlr in list(root.handlers):
        root.removeHandler(hdlr)
    root.addHandler(QueueHandler(q))  # the one handler each worker needs
    root.setLevel(level)


#######################
#   END_BOILERPLATE   #
#######################
def main():
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
    timer = arrow.utcnow().float_timestamp

    # Load credentials from <agent_dir>/.env, if present, before anything
    # reads os.environ. Real env vars (docker -e / --env-file / the shell)
    # always take priority over the file -- see load_dotenv_file().
    load_dotenv_file(abs_path_from_cur(DOTENV_FILENAME))

    # get config
    cli_config_vars = get_cli_config_vars()

    # logger queue, must use Manager().Queue() because agent may use pool create process
    m = multiprocessing.Manager()
    log_queue = m.Queue()

    # set logger
    worker_configurer(log_queue, cli_config_vars['log_level'])
    logger = logging.getLogger('worker')

    # --dump-file: truncate/create once per run, before any sender thread
    # appends to it, so repeated runs don't accumulate stale entries.
    if cli_config_vars.get('dump_file'):
        open(cli_config_vars['dump_file'], 'w').close()
        logger.info('Dumping every entry sent to InsightFinder to %s', cli_config_vars['dump_file'])

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)

    # get config file
    logger.info("Get Config File")
    config_file = config_ini_path(cli_config_vars)
    agent_config_vars, secrets_vars = get_agent_config_vars(logger, config_file)
    if not agent_config_vars:
        time.sleep(1)
        sys.exit(1)

    logger.info("Get IF Config Vars")
    if_config_vars = get_if_config_vars(logger, config_file, agent_config_vars)
    if not if_config_vars:
        time.sleep(1)
        sys.exit(1)

    if 'LOG' not in if_config_vars['project_type']:
        logger.error('This agent only supports project_type = LOG or LOGREPLAY. Got: {}'.format(
            if_config_vars['project_type']))
        time.sleep(1)
        sys.exit(1)

    # one query per collector; never spawn more collectors than there are
    # queries to run (mirrors how the ES template forces collector=1 for METRIC)
    queries = agent_config_vars['queries']
    cli_config_vars['collector'] = max(1, min(cli_config_vars['collector'], len(queries)))

    logger.info("Start listener process")
    listener = Process(target=listener_process, args=(log_queue, cli_config_vars, if_config_vars))
    listener.daemon = True
    listener.start()

    logger.info(cli_data_block)
    logger.info("Process start with config: {}".format(config_file))
    print_summary_info(logger, if_config_vars, agent_config_vars)

    # Cross-process shared OAuth token cache, so a sibling collector's
    # refresh-on-401 is picked up by the others.
    token_shared_dict = m.dict()

    # Warm the OAuth token once before forking, so steady-state runs make
    # zero token calls (disk cache hit) instead of one per collector process.
    if agent_config_vars['auth_type'] == 'oauth2':
        try:
            snow_cfg = dict(agent_config_vars)
            snow_cfg.update(secrets_vars)
            token_cache_key = servicenow_auth.make_cache_key(
                snow_cfg['base_url'], snow_cfg.get('oauth_grant_type', ''), snow_cfg.get('oauth_client_id', ''),
                snow_cfg.get('oauth_username', ''), os.path.basename(config_file))
            pre_fork_store = servicenow_auth.TokenStore(agent_config_vars['state_dir'], token_cache_key,
                                                        shared_dict=token_shared_dict)
            servicenow_auth.ServiceNowAuth(snow_cfg, pre_fork_store, logger).ensure_token()
        except servicenow_auth.AuthError as e:
            logger.error('Could not acquire an OAuth token: {}'.format(e))
            time.sleep(1)
            sys.exit(1)

    # start run
    # raw data
    messages = Queue()
    # parsed data
    datas = Queue()
    # all processes
    processes = []
    worker_process = cli_config_vars['process']
    worker_timeout = cli_config_vars['timeout'] if cli_config_vars['timeout'] > 0 else None
    collector_process = cli_config_vars['collector']

    # collector processes
    time_now = int(arrow.utcnow().float_timestamp)
    for collector_id in range(collector_process):
        d = Process(target=process_get_data,
                    args=(log_queue, cli_config_vars, if_config_vars, agent_config_vars, secrets_vars, messages,
                          worker_process, time_now, collector_id, token_shared_dict))
        d.daemon = True
        d.start()
        processes.append(d)

    # parser process
    for x in range(worker_process):
        d = Process(target=process_parse_messages,
                    args=(log_queue, cli_config_vars, if_config_vars, agent_config_vars, messages, datas))
        d.daemon = True
        d.start()
        processes.append(d)

    def term(sig_num, addtion):
        try:
            for p in processes:
                logger.info('process %d terminate' % p.pid)
                p.terminate()

            logger.info("Process is done with config: {}".format(config_file))
            time.sleep(1)
            sys.exit(1)
        except Exception as e:
            logger.error(str(e))

    signal.signal(signal.SIGTERM, term)

    # build ThreadPool to send data
    meta_info = {"projects": {}}
    project_create_lock = Lock()
    pool_map = ThreadPool(worker_process)
    pool_map.map_async(process_build_buffer,
                       [(logger, cli_config_vars, if_config_vars, datas, meta_info, project_create_lock)
                        for i in range(worker_process)])
    pool_map.close()
    pool_map.join()

    # clear all process
    for p in processes:
        logger.debug("Wait for worker {} to finish.".format(p.pid))
        p.join(timeout=worker_timeout)

    # Set logging to INFO to print end of agent
    logger.setLevel(logging.INFO)
    logger.info("Agent completed in {} seconds".format(arrow.utcnow().float_timestamp - timer))

    # send kill signal
    time.sleep(1)
    kill_logger = logging.getLogger('KILL')
    kill_logger.info('KILL')


if __name__ == "__main__":
    main()

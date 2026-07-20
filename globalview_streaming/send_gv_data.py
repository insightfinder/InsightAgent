#!/usr/bin/env python
"""
GlobalView -> InsightFinder log-streaming collector.

Fetches the GlobalView anomaly timeline for a system from the InsightFinder
backend (`GET /api/v2/timeline`) and streams each timeline record into an
InsightFinder LOG project (`POST /api/v1/customprojectrawdata`).

Each timeline record is turned into one log entry that preserves the instance
name and component name exactly as reported by GlobalView, and carries the
anomaly score and priority level in the log payload.
"""

import configparser
import glob
import http.client
import json
import logging
import os
import socket
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from optparse import OptionParser
from sys import getsizeof

import requests
from urllib3.exceptions import InsecureRequestWarning

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HOSTNAME = socket.gethostname().partition('.')[0]
ATTEMPTS = 2
RETRY_WAIT_TIME_IN_SEC = 5
SESSION = requests.Session()

# GlobalView timeline endpoint on the InsightFinder backend.
TIMELINE_API = '/api/v2/timeline'

# The backend serialises IncidentPriorityLevel using @SerializedName("1".."5").
# Map those to human-readable names so the log payload carries both.
PRIORITY_LEVEL_NAMES = {
    '1': 'CRITICAL',
    '2': 'HIGH',
    '3': 'MODERATE',
    '4': 'LOW',
    '5': 'PLANNING',
}

# Fields copied from each timeline record into the log `data` payload, in
# addition to the required anomalyScore / priorityLevel.
CONTEXT_FIELDS = (
    'type',
    'patternName',
    'projectName',
    'zoneName',
    'status',
    'isIncident',
    'isPrediction',
    'timestamp',
    'endTime',
)


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------
def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))


def config_error(logger, setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(info))
    return False


def get_cli_config_vars():
    """ get CLI options """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    parser.add_option('-c', '--config', action='store', dest='config',
                      default=abs_path_from_cur('conf.d'),
                      help='Path to a config .ini file, or a directory of .ini files '
                           '(each is processed in turn). Defaults to the conf.d directory.')
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Testing mode: fetch and parse, but do not send data to IF.')
    parser.add_option('--timeout', action='store', dest='timeout', default=60,
                      help='Seconds of timeout for requests')
    (options, args) = parser.parse_args()

    config_vars = {
        'config': options.config,
        'testing': bool(options.testing),
        'log_level': logging.INFO,
        'timeout': int(options.timeout),
    }
    if options.verbose:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING
    return config_vars


def resolve_config_files(config_path):
    """ resolve the -c value to a list of .ini files (single file or a directory) """
    if config_path and os.path.isfile(config_path):
        return [config_path]
    if config_path and os.path.isdir(config_path):
        return sorted(glob.glob(os.path.join(config_path, '*.ini')))
    # fall back to the conf.d directory next to this script
    return sorted(glob.glob(abs_path_from_cur('conf.d/*.ini')))


def get_agent_config_vars(logger, config_ini):
    """ parse the [globalview] section """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False
    config_parser = configparser.ConfigParser()
    with open(config_ini) as fp:
        config_parser.read_file(fp)
    try:
        gv_url = config_parser.get('globalview', 'gv_url').strip()
        gv_user_name = config_parser.get('globalview', 'gv_user_name').strip()
        gv_license_key = config_parser.get('globalview', 'gv_license_key').strip()
        gv_system_name = config_parser.get('globalview', 'gv_system_name').strip()
        timeline_event_type = config_parser.get('globalview', 'timeline_event_type').strip()
        predict = config_parser.get('globalview', 'predict').strip()
        timeline_source = config_parser.get('globalview', 'timeline_source').strip().lower()
        query_time_offset_seconds = config_parser.get('globalview', 'query_time_offset_seconds').strip()
        his_time_range = config_parser.get('globalview', 'his_time_range').strip()
        verify_certs = config_parser.get('globalview', 'verify_certs').strip()
        only_start_in_window = config_parser.get('globalview', 'only_start_in_window',
                                                 fallback='true').strip()
        agent_http_proxy = config_parser.get('globalview', 'agent_http_proxy').strip()
        agent_https_proxy = config_parser.get('globalview', 'agent_https_proxy').strip()
    except configparser.NoOptionError as cp_noe:
        logger.error(cp_noe)
        return config_error(logger)

    if not gv_url:
        return config_error(logger, 'gv_url')
    if not gv_user_name:
        return config_error(logger, 'gv_user_name')
    if not gv_license_key:
        return config_error(logger, 'gv_license_key')
    if not gv_system_name:
        return config_error(logger, 'gv_system_name')

    if timeline_source not in ('raw', 'consolidated', 'both'):
        timeline_source = 'raw'

    # optional history window
    his_time_config = None
    if his_time_range:
        try:
            start_raw, end_raw = [x.strip() for x in his_time_range.split(',')]
            his_time_config = (_parse_utc_to_ms(start_raw), _parse_utc_to_ms(end_raw))
        except Exception:
            logger.error('Invalid his_time_range, expected "start,end" in UTC. Ignoring.')
            his_time_config = None

    agent_proxies = dict()
    if agent_http_proxy:
        agent_proxies['http'] = agent_http_proxy
    if agent_https_proxy:
        agent_proxies['https'] = agent_https_proxy

    return {
        'gv_url': gv_url,
        'gv_user_name': gv_user_name,
        'gv_license_key': gv_license_key,
        'gv_system_name': gv_system_name,
        'timeline_event_type': timeline_event_type or None,
        'predict': predict.lower() == 'true',
        'timeline_source': timeline_source,
        'query_time_offset_seconds': int(query_time_offset_seconds) if query_time_offset_seconds else 0,
        'his_time_range': his_time_config,
        'verify_certs': verify_certs.lower() != 'false',
        'only_start_in_window': only_start_in_window.lower() != 'false',
        'agent_proxies': agent_proxies,
    }


def get_if_config_vars(logger, config_ini):
    """ parse the [insightfinder] section (target LOG project) """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False
    config_parser = configparser.ConfigParser()
    with open(config_ini) as fp:
        config_parser.read_file(fp)
    try:
        user_name = config_parser.get('insightfinder', 'user_name')
        license_key = config_parser.get('insightfinder', 'license_key')
        project_name = config_parser.get('insightfinder', 'project_name')
        system_name = config_parser.get('insightfinder', 'system_name')
        project_type = config_parser.get('insightfinder', 'project_type').upper()
        sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
        run_interval = config_parser.get('insightfinder', 'run_interval')
        chunk_size_kb = config_parser.get('insightfinder', 'chunk_size_kb')
        if_url = config_parser.get('insightfinder', 'if_url')
        if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
        if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
    except configparser.NoOptionError as cp_noe:
        logger.error(cp_noe)
        return config_error(logger)

    if len(user_name) == 0:
        return config_error(logger, 'user_name')
    if len(license_key) == 0:
        return config_error(logger, 'license_key')
    if len(project_name) == 0:
        return config_error(logger, 'project_name')
    if project_type not in ('LOG', 'LOGREPLAY', 'ALERT', 'ALERTREPLAY'):
        # This collector streams anomaly records as logs/alerts only.
        return config_error(logger, 'project_type (must be log/logreplay/alert/alertreplay)')
    is_replay = 'REPLAY' in project_type

    sampling_interval = int(sampling_interval[:-1]) if sampling_interval.endswith('s') \
        else int(sampling_interval) * 60

    if len(run_interval) == 0:
        return config_error(logger, 'run_interval')
    run_interval = int(run_interval[:-1]) if run_interval.endswith('s') else int(run_interval) * 60

    if len(chunk_size_kb) == 0:
        chunk_size_kb = 2048
    if len(if_url) == 0:
        if_url = 'https://app.insightfinder.com'

    if_proxies = dict()
    if len(if_http_proxy) > 0:
        if_proxies['http'] = if_http_proxy
    if len(if_https_proxy) > 0:
        if_proxies['https'] = if_https_proxy

    return {
        'user_name': user_name,
        'license_key': license_key,
        'project_name': project_name,
        'system_name': system_name,
        'project_type': project_type,
        'sampling_interval': int(sampling_interval),
        'run_interval': int(run_interval),
        'chunk_size': int(chunk_size_kb) * 1024,
        'if_url': if_url,
        'if_proxies': if_proxies,
        'is_replay': is_replay,
    }


def _parse_utc_to_ms(value):
    """ parse 'YYYY-MM-DD HH:MM:SS' (UTC) to epoch millis """
    dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


# ---------------------------------------------------------------------------
# GlobalView fetch
# ---------------------------------------------------------------------------
def get_query_window(logger, agent_config_vars, if_config_vars):
    """ return (start_ms, end_ms) for this run """
    if agent_config_vars['his_time_range']:
        start_ms, end_ms = agent_config_vars['his_time_range']
        logger.info('History mode window: {} - {}'.format(start_ms, end_ms))
        return start_ms, end_ms
    now_ms = int(time.time() * 1000)
    end_ms = now_ms - agent_config_vars['query_time_offset_seconds'] * 1000
    start_ms = end_ms - if_config_vars['run_interval'] * 1000
    logger.info('Live mode window: {} - {}'.format(start_ms, end_ms))
    return start_ms, end_ms


def fetch_timeline(logger, c_config, agent_config_vars, start_ms, end_ms):
    """ GET the GlobalView timeline for the configured system """
    url = urllib.parse.urljoin(agent_config_vars['gv_url'], TIMELINE_API)
    headers = {
        'X-User-Name': agent_config_vars['gv_user_name'],
        'X-License-Key': agent_config_vars['gv_license_key'],
    }
    params = {
        'systemName': agent_config_vars['gv_system_name'],
        'startTime': start_ms,
        'endTime': end_ms,
        'predict': 'true' if agent_config_vars['predict'] else 'false',
    }
    if agent_config_vars['timeline_event_type']:
        params['timelineEventType'] = agent_config_vars['timeline_event_type']

    timeout = c_config['timeout'] if c_config['timeout'] > 0 else None
    response = send_request(logger, url, 'GET', 'Could not fetch GlobalView timeline',
                            'Fetched GlobalView timeline', headers=headers, params=params,
                            verify=agent_config_vars['verify_certs'],
                            proxies=agent_config_vars['agent_proxies'], timeout=timeout)
    if response == -1:
        return []

    try:
        payload = response.json()
    except ValueError:
        logger.error('GlobalView timeline response is not valid JSON.')
        return []

    records = []
    seen_ids = set()
    source = agent_config_vars['timeline_source']
    lists_to_read = []
    if source in ('raw', 'both'):
        lists_to_read.append('timelineList')
    if source in ('consolidated', 'both'):
        lists_to_read.append('consolidatedTimelineList')

    for key in lists_to_read:
        for record in payload.get(key) or []:
            rid = record.get('id')
            # dedup by id when merging both lists
            if source == 'both' and rid is not None:
                if rid in seen_ids:
                    continue
                seen_ids.add(rid)
            records.append(record)

    logger.info('GlobalView returned {} timeline record(s).'.format(len(records)))
    return records


def filter_records_to_window(logger, records, start_ms, end_ms):
    """
    Keep only records whose start time (`timestamp`, i.e. getStartTimestamp) falls
    inside the query window [start_ms, end_ms). GlobalView loads incidents at day
    granularity and reports each incident's earliest (consolidated) start time, so
    without this filter records outside the window leak in and long-running
    incidents get re-sent every run. Inclusive start / exclusive end means back-to-
    back windows never overlap, so each start time lands in exactly one run.
    """
    kept = []
    dropped = 0
    for record in records:
        ts = record.get('timestamp')
        if ts is None or not (start_ms <= int(ts) < end_ms):
            dropped += 1
            continue
        kept.append(record)
    logger.info('Kept {} record(s) with start time in window, dropped {} outside.'.format(
        len(kept), dropped))
    return kept


# ---------------------------------------------------------------------------
# Timeline record -> IF log entry
# ---------------------------------------------------------------------------
def build_log_entry(logger, record):
    """
    Convert one GlobalView TimelineBase record into an IF log raw-data entry.
    Instance and component names are preserved verbatim. The log payload carries
    the anomaly score and priority level.
    """
    instance_name = record.get('instanceName')
    timestamp = record.get('timestamp')
    if not instance_name or not timestamp:
        logger.debug('Skipping record without instanceName/timestamp: {}'.format(record))
        return None

    priority_level = record.get('priorityLevel')
    priority_level = str(priority_level) if priority_level is not None else None

    data = {
        'anomalyScore': record.get('anomalyScore'),
        'priorityLevel': priority_level,
        'priorityLevelName': PRIORITY_LEVEL_NAMES.get(priority_level, priority_level),
    }
    for field in CONTEXT_FIELDS:
        if field in record and record.get(field) is not None:
            data[field] = record.get(field)

    entry = {
        'eventId': int(timestamp),
        'tag': instance_name,
        'data': data,
    }
    # componentName is a first-class key of the IF log raw-data format, so the
    # component name from GlobalView is preserved as-is.
    component_name = record.get('componentName')
    if component_name:
        entry['componentName'] = component_name
    return entry


# ---------------------------------------------------------------------------
# Send to InsightFinder
# ---------------------------------------------------------------------------
def get_json_size_bytes(json_data):
    return getsizeof(json.dumps(json_data))


def initialize_api_post_data(logger, if_config_vars):
    to_send_data_dict = dict()
    to_send_data_dict['userName'] = if_config_vars['user_name']
    to_send_data_dict['licenseKey'] = if_config_vars['license_key']
    to_send_data_dict['projectName'] = if_config_vars['project_name']
    to_send_data_dict['instanceName'] = HOSTNAME
    to_send_data_dict['agentType'] = 'LogFileReplay' if if_config_vars['is_replay'] else 'LogStreaming'
    logger.debug(to_send_data_dict)
    return to_send_data_dict


def send_data_to_if(logger, c_config, if_config_vars, chunk_data):
    """ POST one chunk of log entries to /api/v1/customprojectrawdata """
    if not chunk_data:
        return
    send_data_time = time.time()

    data_to_post = initialize_api_post_data(logger, if_config_vars)
    data_to_post['metricData'] = json.dumps(chunk_data)
    post_url = urllib.parse.urljoin(if_config_vars['if_url'], '/api/v1/customprojectrawdata')

    logger.debug('First:\n' + str(chunk_data[0]))
    logger.debug('Last:\n' + str(chunk_data[-1]))
    logger.info('Total Lines: ' + str(len(chunk_data)))
    logger.info('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))

    if c_config['testing']:
        logger.info('Testing mode: not sending data to IF.')
        return

    send_request(logger, post_url, 'POST', 'Could not send request to IF',
                 str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.',
                 data=data_to_post, verify=False, proxies=if_config_vars['if_proxies'])
    logger.info('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def send_and_reset(logger, c_config, if_config_vars, buffer):
    if buffer['entries']:
        send_data_to_if(logger, c_config, if_config_vars, buffer['entries'])
    buffer['entries'] = []
    buffer['size'] = 0


def send_request(logger, url, mode='GET', failure_message='Failure!', success_message='Success!',
                 **request_passthrough):
    """ sends a request to the given url with retries """
    req = SESSION.post if mode.upper() == 'POST' else SESSION.get
    req_num = 0
    for req_num in range(ATTEMPTS):
        try:
            response = req(url, **request_passthrough)
            if response.status_code == http.client.OK:
                logger.info(success_message)
                return response
            else:
                logger.warning(failure_message)
                logger.info('Response Code: {}\nTEXT: {}'.format(response.status_code, response.text))
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


def check_project_exist(logger, c_config, if_config_vars):
    """ check the target LOG project exists, create it if not """
    project_name = if_config_vars['project_name']
    url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
    is_project_exist = False
    try:
        logger.info('Starting check project: {}'.format(project_name))
        params = {
            'operation': 'check',
            'userName': if_config_vars['user_name'],
            'licenseKey': if_config_vars['license_key'],
            'projectName': project_name,
        }
        response = send_request(logger, url, 'POST', data=params, verify=False,
                                proxies=if_config_vars['if_proxies'], timeout=5)
        if response != -1:
            result = response.json()
            is_project_exist = bool(result.get('success')) and bool(result.get('isProjectExist'))
    except Exception as e:
        logger.error(e)

    if is_project_exist:
        logger.info('Project exists: {}'.format(project_name))
        return True

    created = False
    try:
        logger.info('Creating project: {}'.format(project_name))
        params = {
            'operation': 'create',
            'userName': if_config_vars['user_name'],
            'licenseKey': if_config_vars['license_key'],
            'projectName': project_name,
            'systemName': if_config_vars['system_name'] or project_name,
            'instanceType': 'PrivateCloud',
            'projectCloudType': 'PrivateCloud',
            'dataType': 'Log',
            'insightAgentType': 'LogFile' if if_config_vars['is_replay'] else 'Custom',
            'samplingInterval': int(if_config_vars['sampling_interval'] / 60),
            'samplingIntervalInSeconds': if_config_vars['sampling_interval'],
            'projectModelFlag': False,
        }
        response = send_request(logger, url, 'POST', data=params, verify=False,
                                proxies=if_config_vars['if_proxies'], timeout=5)
        if response != -1:
            created = bool(response.json().get('success'))
    except Exception as e:
        logger.error(e)

    if created:
        time.sleep(10)
        try:
            params = {
                'operation': 'check',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': project_name,
            }
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'], timeout=5)
            if response != -1:
                result = response.json()
                is_project_exist = bool(result.get('success')) and bool(result.get('isProjectExist'))
        except Exception as e:
            logger.error(e)

    return is_project_exist


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def set_logger_config(level):
    logger_obj = logging.getLogger('globalview_streaming')
    logger_obj.setLevel(level)
    logger_obj.handlers = []
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [pid %(process)d] %(levelname)-8s %(module)s.%(funcName)s():%(lineno)d %(message)s'))
    logger_obj.addHandler(handler)
    logger_obj.propagate = False
    return logger_obj


def print_summary_info(logger, if_config_vars, agent_config_vars):
    block = '\nIF settings:'
    for k, v in sorted(if_config_vars.items()):
        if k in ('license_key',):
            v = '***'
        block += '\n\t{}: {}'.format(k, v)
    block += '\nGlobalView settings:'
    for k, v in sorted(agent_config_vars.items()):
        if k == 'gv_license_key':
            v = '***'
        block += '\n\t{}: {}'.format(k, v)
    logger.debug(block)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def process_config(logger, config_ini, c_config):
    """ run one full fetch -> transform -> send cycle for a single config file """
    cfg_name = os.path.basename(config_ini)
    start_time = time.time()
    logger.info('===== Processing config: {} ====='.format(cfg_name))

    agent_config_vars = get_agent_config_vars(logger, config_ini)
    if not agent_config_vars:
        logger.error('[{}] Skipping: invalid [globalview] config.'.format(cfg_name))
        return
    if_config_vars = get_if_config_vars(logger, config_ini)
    if not if_config_vars:
        logger.error('[{}] Skipping: invalid [insightfinder] config.'.format(cfg_name))
        return

    print_summary_info(logger, if_config_vars, agent_config_vars)

    # make sure the target LOG project exists before streaming
    if not c_config['testing']:
        if not check_project_exist(logger, c_config, if_config_vars):
            logger.error('[{}] Skipping: target project does not exist and could not be '
                         'created.'.format(cfg_name))
            return

    # fetch the timeline for this run's window
    start_ms, end_ms = get_query_window(logger, agent_config_vars, if_config_vars)
    records = fetch_timeline(logger, c_config, agent_config_vars, start_ms, end_ms)
    if agent_config_vars['only_start_in_window']:
        records = filter_records_to_window(logger, records, start_ms, end_ms)

    # transform + chunk + send
    buffer = {'entries': [], 'size': 0}
    sent = 0
    skipped = 0
    for record in records:
        entry = build_log_entry(logger, record)
        if entry is None:
            skipped += 1
            continue
        entry_size = get_json_size_bytes(entry)
        if buffer['size'] + entry_size >= if_config_vars['chunk_size'] and buffer['entries']:
            send_and_reset(logger, c_config, if_config_vars, buffer)
        buffer['entries'].append(entry)
        buffer['size'] += entry_size
        sent += 1
    send_and_reset(logger, c_config, if_config_vars, buffer)

    logger.info('[{}] Streamed {} record(s), skipped {}. Config run time: {} seconds.'.format(
        cfg_name, sent, skipped, round(time.time() - start_time, 2)))


def main():
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
    overall_start = time.time()

    c_config = get_cli_config_vars()
    logger = set_logger_config(c_config['log_level'])

    config_files = resolve_config_files(c_config['config'])
    if not config_files:
        logger.error('No config .ini files found at {}. Exiting...'.format(c_config['config']))
        sys.exit(1)
    logger.info('Found {} config file(s): {}'.format(
        len(config_files), ', '.join(os.path.basename(f) for f in config_files)))

    for config_ini in config_files:
        try:
            process_config(logger, config_ini, c_config)
        except Exception as e:
            # one bad config must not stop the others
            logger.exception('Unhandled error processing {}: {}'.format(
                os.path.basename(config_ini), e))

    logger.info('Processed {} config file(s). Total run time: {} seconds.'.format(
        len(config_files), round(time.time() - overall_start, 2)))


if __name__ == '__main__':
    main()

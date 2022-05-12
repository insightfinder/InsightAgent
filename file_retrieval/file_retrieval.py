#!/usr/bin/env python
import configparser
import json
import logging
import os
import regex
import socket
import sys
import time
import pytz
import arrow
import urllib.parse
import http.client
import requests
import shlex
import traceback
import glob
from time import sleep
from sys import getsizeof
from optparse import OptionParser
from logging.handlers import QueueHandler
import multiprocessing
from multiprocessing.pool import ThreadPool
from multiprocessing import Pool, TimeoutError

import arrow
import requests
import subprocess

"""
This script gathers data to send to Insightfinder
"""

# declare a few vars
TRUE = regex.compile(r"T(RUE)?", regex.IGNORECASE)
FALSE = regex.compile(r"F(ALSE)?", regex.IGNORECASE)
SPACES = regex.compile(r"\s+")
SLASHES = regex.compile(r"\/+")
UNDERSCORE = regex.compile(r"\_+")
COLONS = regex.compile(r"\:+")
LEFT_BRACE = regex.compile(r"\[")
RIGHT_BRACE = regex.compile(r"\]")
PERIOD = regex.compile(r"\.")
COMMA = regex.compile(r"\,")
NON_ALNUM = regex.compile(r"[^a-zA-Z0-9]")
FORMAT_STR = regex.compile(r"{(.*?)}")
STRIP_PORT = regex.compile(r"(.*):\d+")
HOSTNAME = socket.gethostname().partition('.')[0]
ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
JSON_LEVEL_DELIM = '.'
CSV_DELIM = r",|\t"
ATTEMPTS = 3
RETRY_WAIT_TIME_IN_SEC = 30
CACHE_NAME = 'cache.db'


def start_data_processing(logger, c_config, if_config_vars, agent_config_vars, log_buffer, track, time_now):
    logger.info('Started......')

    logger.debug('Using current time for streaming data')

    # build query
    data = query_messages(logger, if_config_vars, agent_config_vars)
    parse_messages(logger, if_config_vars, agent_config_vars, log_buffer, track, data)

    logger.info('Closed......')


def query_messages(logger, if_config_vars, agent_config_vars):
    logger.info('Starting exec shell command')

    data = []
    try:
        ret = subprocess.check_output(agent_config_vars['scan_command'], shell=True)
        ret = ret.decode('utf-8')
        data = ret.split('\n')
    except Exception as e:
        logger.error("Run command error: {}".format(agent_config_vars['scan_command']))
        logger.error(e)

    data = [f for f in data if f.strip()]
    return data


def parse_messages(logger, if_config_vars, agent_config_vars, log_buffer, track, result):
    count = 0
    logger.info('Reading {} messages'.format(len(result)))

    for file in result:
        try:
            logger.debug(file)

            if not os.path.exists(file):
                continue

            message = {}

            # get file info
            # parse file name
            _, f_name = os.path.split(file)
            if agent_config_vars['file_name_regex']:
                matches = agent_config_vars['file_name_regex'].match(f_name)
                if matches:
                    message.update(matches.groupdict() or dict)

            # parse file content
            if agent_config_vars['file_content_regex']:
                with open(file, 'r') as f:
                    content = f.read()
                    matches = agent_config_vars['file_content_regex'].match(content)
                    if matches:
                        message.update(matches.groupdict() or dict)

            # get timestamp
            timestamp = message.get(agent_config_vars['timestamp_field'])
            if not timestamp:
                continue
            if agent_config_vars['timestamp_format']:
                timestamp = int(arrow.get(timestamp, agent_config_vars['timestamp_format']).float_timestamp * 1000)
            else:
                timestamp = int(arrow.get(timestamp).float_timestamp * 1000)
            # set offset for timestamp
            timestamp += agent_config_vars['target_timestamp_timezone'] * 1000
            timestamp = str(timestamp)

            instance = message.get(
                agent_config_vars['instance_field'][0] if agent_config_vars['instance_field'] and len(
                    agent_config_vars['instance_field']) > 0 else 'instance')
            if not instance:
                continue
            # filter by instance whitelist
            if agent_config_vars['instance_whitelist_regex'] \
                    and not agent_config_vars['instance_whitelist_regex'].match(instance):
                continue

            # add device info if has
            device = None
            device_field = agent_config_vars['device_field']
            if device_field and len(device_field) > 0:
                devices = [message.get(d) for d in device_field]
                devices = [d for d in devices if d]
                device = devices[0] if len(devices) > 0 else None
            full_instance = make_safe_instance_string(instance, device)

            # get data from data_fields
            data = {}
            for data_field in agent_config_vars['data_fields']:
                if data_field in message.keys():
                    data_val = message.get(data_field)
                    data[data_field] = data_val

            # build log entry
            entry = prepare_log_entry(if_config_vars, str(int(timestamp)), data, full_instance)
            log_buffer['buffer_logs'].append(entry)

        except Exception as e:
            logger.warning('Error when parsing message')
            logger.warning(e)
            logger.debug(traceback.format_exc())
            continue

        track['entry_count'] += 1
        count += 1
        if count % 1000 == 0:
            logger.info('Parse {0} messages'.format(count))
    logger.info('Parse {0} messages'.format(count))


def get_agent_config_vars(logger, config_ini):
    """ Read and parse config.ini """
    """ get config.ini vars """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False
    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)

        instance_whitelist_regex = None
        try:
            # agent settings
            agent_config = {}

            # only keep settings with values
            agent_kwargs = {k: v for (k, v) in list(agent_config.items()) if v}

            scan_command = config_parser.get('agent', 'scan_command')
            file_name_regex = config_parser.get('agent', 'file_name_regex')
            file_content_regex = config_parser.get('agent', 'file_content_regex')
            data_fields = config_parser.get('agent', 'data_fields')

            # message parsing
            data_fields = config_parser.get('agent', 'data_fields', raw=True)
            timestamp_format = config_parser.get('agent', 'timestamp_format', raw=True)
            timezone = config_parser.get('agent', 'timezone') or 'UTC'
            timestamp_field = config_parser.get('agent', 'timestamp_field', raw=True)
            target_timestamp_timezone = config_parser.get('agent', 'target_timestamp_timezone',
                                                          raw=True) or 'UTC'
            component_field = config_parser.get('agent', 'component_field', raw=True)
            instance_field = config_parser.get('agent', 'instance_field', raw=True)
            instance_whitelist = config_parser.get('agent', 'instance_whitelist')
            device_field = config_parser.get('agent', 'device_field', raw=True)

            # proxies
            agent_http_proxy = config_parser.get('agent', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('agent', 'agent_https_proxy')

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        # required
        if len(scan_command) == 0:
            return config_error(logger, 'scan_command')
        if len(file_name_regex) != 0:
            try:
                file_name_regex = regex.compile(file_name_regex)
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'file_name_regex')
        else:
            return config_error(logger, 'file_name_regex')
        if len(file_content_regex) != 0:
            try:
                file_content_regex = regex.compile(file_content_regex)
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'file_content_regex')

        if timezone:
            if timezone not in pytz.all_timezones:
                return config_error(logger, 'timezone')
            else:
                timezone = pytz.timezone(timezone)
        if len(target_timestamp_timezone) != 0:
            target_timestamp_timezone = int(arrow.now(target_timestamp_timezone).utcoffset().total_seconds())
        else:
            return config_error(logger, 'target_timestamp_timezone')
        if len(instance_whitelist) != 0:
            try:
                instance_whitelist_regex = regex.compile(instance_whitelist)
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'instance_whitelist')

        data_fields = [x.strip() for x in data_fields.split(',') if x.strip()]
        instance_fields = [x.strip() for x in instance_field.split(',') if x.strip()]
        device_fields = [x.strip() for x in device_field.split(',') if x.strip()]

        # proxies
        agent_proxies = dict()
        if len(agent_http_proxy) > 0:
            agent_proxies['http'] = agent_http_proxy
        if len(agent_https_proxy) > 0:
            agent_proxies['https'] = agent_https_proxy

        # add parsed variables to a global
        config_vars = {
            'agent_kwargs': agent_kwargs,
            'scan_command': scan_command,
            'file_name_regex': file_name_regex,
            'file_content_regex': file_content_regex,
            'data_fields': data_fields,
            'timestamp_format': timestamp_format,
            'timezone': timezone,
            'timestamp_field': timestamp_field,
            'target_timestamp_timezone': target_timestamp_timezone,
            'component_field': component_field,
            'instance_field': instance_fields,
            "instance_whitelist_regex": instance_whitelist_regex,
            'device_field': device_fields,
            'proxies': agent_proxies,
        }

        return config_vars


#########################
#   START_BOILERPLATE   #
#########################
def get_if_config_vars(logger, config_ini):
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
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            run_interval = config_parser.get('insightfinder', 'run_interval')
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
        if len(project_name) == 0:
            return config_error(logger, 'project_name')
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
            'sampling_interval': int(sampling_interval),  # as seconds
            'run_interval': int(run_interval),  # as seconds
            'chunk_size': int(chunk_size_kb) * 1024,  # as bytes
            'if_url': if_url,
            'if_proxies': if_proxies,
            'is_replay': is_replay
        }

        return config_vars


def config_ini_path():
    return abs_path_from_cur(cli_config_vars['config'])


def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))


def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    """
    """
    parser.add_option('-c', '--config', action='store', dest='config', default=abs_path_from_cur('conf.d'),
                      help='Path to the config files to use. Defaults to {}'.format(abs_path_from_cur('conf.d')))
    parser.add_option('-p', '--processes', action='store', dest='processes', default=multiprocessing.cpu_count() * 4,
                      help='Number of processes to run')
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data).' +
                           ' Automatically turns on verbose logging')
    parser.add_option('--timeout', action='store', dest='timeout', default=5,
                      help='Minutes of timeout for all processes')
    (options, args) = parser.parse_args()

    config_vars = {
        'config': options.config if os.path.isdir(options.config) else abs_path_from_cur('conf.d'),
        'processes': int(options.processes),
        'testing': False,
        'log_level': logging.INFO,
        'timeout': int(options.timeout) * 60,
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


def prepare_log_entry(if_config_vars, timestamp, data, instanceName):
    """ creates the log entry """
    entry = dict()
    entry['data'] = data
    if 'INCIDENT' in if_config_vars['project_type'] or 'DEPLOYMENT' in if_config_vars['project_type']:
        entry['timestamp'] = timestamp
        entry['instanceName'] = instanceName
    else:  # LOG or ALERT
        entry['eventId'] = timestamp
        entry['tag'] = instanceName
    return entry


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    # return len(bytearray(json.dumps(json_data)))
    return getsizeof(json.dumps(json_data))


def make_safe_instance_string(instance, device=''):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', instance)
    instance = COLONS.sub('-', instance)
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


def initialize_data_gathering(logger, c_config, if_config_vars, agent_config_vars, time_now):
    log_buffer = dict()
    track = dict()
    reset_log_buffer(log_buffer)
    reset_track(track)
    track['chunk_count'] = 0
    track['entry_count'] = 0

    start_data_processing(logger, c_config, if_config_vars, agent_config_vars, log_buffer, track, time_now)

    # clear log buffer when data processing end
    clear_log_buffer(logger, c_config, if_config_vars, log_buffer, track)

    logger.info('Total chunks created: ' + str(track['chunk_count']))
    logger.info('Total {} entries: {}'.format(
        if_config_vars['project_type'].lower(), track['entry_count']))


def clear_log_buffer(logger, c_config, if_config_vars, log_buffer, track):
    # move all buffer data to current data, and send
    buffer_values = log_buffer['buffer_logs']

    count = 0
    for row in buffer_values:
        track['current_row'].append(row)
        count += 1
        track['line_count'] += 1
        if count % 500 == 0 or get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
            logger.debug('Sending buffer chunk')
            send_data_wrapper(logger, c_config, if_config_vars, track)

    # last chunk
    if len(track['current_row']) > 0:
        logger.debug('Sending last chunk')
        send_data_wrapper(logger, c_config, if_config_vars, track)

    reset_log_buffer(log_buffer)


def reset_log_buffer(log_buffer):
    log_buffer['buffer_logs'] = []


def reset_track(track):
    """ reset the track global for the next chunk """
    track['start_time'] = time.time()
    track['line_count'] = 0
    track['current_row'] = []
    track['component_map_list'] = []


################################
# Functions to send data to IF #
################################
def send_data_wrapper(logger, c_config, if_config_vars, track):
    """ wrapper to send data """
    logger.debug('--- Chunk creation time: {} seconds ---'.format(
        round(time.time() - track['start_time'], 2)))
    send_data_to_if(logger, c_config, if_config_vars, track, track['current_row'])
    track['chunk_count'] += 1
    reset_track(track)


def send_data_to_if(logger, c_config, if_config_vars, track, chunk_metric_data):
    send_data_time = time.time()

    # prepare data for metric/log streaming agent
    data_to_post = initialize_api_post_data(logger, if_config_vars)
    if 'DEPLOYMENT' in if_config_vars['project_type'] or 'INCIDENT' in if_config_vars['project_type']:
        for chunk in chunk_metric_data:
            chunk['data'] = json.dumps(chunk['data'])
    data_to_post[get_data_field_from_project_type(if_config_vars)] = json.dumps(chunk_metric_data)

    # add component mapping to the post data
    track['component_map_list'] = list({v['instanceName']: v for v in track['component_map_list']}.values())
    data_to_post['instanceMetaData'] = json.dumps(track['component_map_list'] or [])

    logger.debug('First:\n' + str(chunk_metric_data[0]))
    logger.debug('Last:\n' + str(chunk_metric_data[-1]))
    logger.info('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
    logger.info('Total Lines: ' + str(track['line_count']))

    # do not send if only testing
    if c_config['testing']:
        return

    # send the data
    post_url = urllib.parse.urljoin(if_config_vars['if_url'], get_api_from_project_type(if_config_vars))
    send_request(logger, post_url, 'POST', 'Could not send request to IF',
                 str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.',
                 data=data_to_post, verify=False, proxies=if_config_vars['if_proxies'])
    logger.info('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def send_request(logger, url, mode='GET', failure_message='Failure!', success_message='Success!',
                 **request_passthrough):
    """ sends a request to the given url """
    # determine if post or get (default)
    req = requests.get
    if mode.upper() == 'POST':
        req = requests.post

    req_num = 0
    for req_num in range(ATTEMPTS):
        try:
            response = req(url, **request_passthrough)
            if response.status_code == http.client.OK:
                return response
            else:
                logger.warn(failure_message)
                logger.info('Response Code: {}\nTEXT: {}'.format(
                    response.status_code, response.text))
        # handle various exceptions
        except requests.exceptions.Timeout:
            logger.exception('Timed out. Reattempting...')
            continue
        except requests.exceptions.TooManyRedirects:
            logger.exception('Too many redirects.')
            break
        except requests.exceptions.RequestException as e:
            logger.exception('Exception ' + str(e))
            break

        # retry after sleep
        time.sleep(RETRY_WAIT_TIME_IN_SEC)

    logger.error('Failed! Gave up after {} attempts.'.format(req_num + 1))
    return -1


def get_data_type_from_project_type(if_config_vars):
    """ use project type to determine data type """
    if 'METRIC' in if_config_vars['project_type']:
        return 'Metric'
    elif 'ALERT' in if_config_vars['project_type']:
        return 'Alert'
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
    # incident uses a different API endpoint
    if 'INCIDENT' in if_config_vars['project_type']:
        return 'incidentData'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'deploymentData'
    else:  # MERTIC, LOG, ALERT
        return 'metricData'


def get_api_from_project_type(if_config_vars):
    """ use project type to determine which API to post to """
    # incident uses a different API endpoint
    if 'INCIDENT' in if_config_vars['project_type']:
        return 'incidentdatareceive'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'deploymentEventReceive'
    else:  # MERTIC, LOG, ALERT
        return 'customprojectrawdata'


def initialize_api_post_data(logger, if_config_vars):
    """ set up the unchanging portion of this """
    to_send_data_dict = dict()
    to_send_data_dict['userName'] = if_config_vars['user_name']
    to_send_data_dict['licenseKey'] = if_config_vars['license_key']
    to_send_data_dict['projectName'] = if_config_vars['project_name']
    to_send_data_dict['instanceName'] = HOSTNAME
    to_send_data_dict['agentType'] = get_agent_type_from_project_type(if_config_vars)
    if 'METRIC' in if_config_vars['project_type'] and 'sampling_interval' in if_config_vars:
        to_send_data_dict['samplingInterval'] = str(if_config_vars['sampling_interval'])
    logger.debug(to_send_data_dict)
    return to_send_data_dict


def check_project_exist(logger, if_config_vars):
    is_project_exist = False
    try:
        logger.info('Starting check project: ' + if_config_vars['project_name'])
        params = {
            'operation': 'check',
            'userName': if_config_vars['user_name'],
            'licenseKey': if_config_vars['license_key'],
            'projectName': if_config_vars['project_name'],
        }
        url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
        response = send_request(logger, url, 'POST', data=params, verify=False, proxies=if_config_vars['if_proxies'])
        if response == -1:
            logger.error('Check project error: ' + if_config_vars['project_name'])
        else:
            result = response.json()
            if result['success'] is False or result['isProjectExist'] is False:
                logger.error('Check project error: ' + if_config_vars['project_name'])
            else:
                is_project_exist = True
                logger.info('Check project success: ' + if_config_vars['project_name'])

    except Exception as e:
        logger.error(e)
        logger.error('Check project error: ' + if_config_vars['project_name'])

    create_project_sucess = False
    if not is_project_exist:
        try:
            logger.info('Starting add project: ' + if_config_vars['project_name'])
            params = {
                'operation': 'create',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': if_config_vars['project_name'],
                'systemName': if_config_vars['system_name'] or if_config_vars['project_name'],
                'instanceType': '',
                'projectCloudType': 'Shadow',
                'dataType': get_data_type_from_project_type(if_config_vars),
                'insightAgentType': get_insight_agent_type_from_project_type(if_config_vars),
                'samplingInterval': int(if_config_vars['sampling_interval'] / 60),
                'samplingIntervalInSeconds': if_config_vars['sampling_interval'],
            }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'])
            if response == -1:
                logger.error('Add project error: ' + if_config_vars['project_name'])
            else:
                result = response.json()
                if result['success'] is False:
                    logger.error('Add project error: ' + if_config_vars['project_name'])
                else:
                    create_project_sucess = True
                    logger.info('Add project success: ' + if_config_vars['project_name'])

        except Exception as e:
            logger.error(e)
            logger.error('Add project error: ' + if_config_vars['project_name'])

    if create_project_sucess:
        # if create project is success, sleep 10s and check again
        time.sleep(10)
        try:
            logger.info('Starting check project: ' + if_config_vars['project_name'])
            params = {
                'operation': 'check',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': if_config_vars['project_name'],
            }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'])
            if response == -1:
                logger.error('Check project error: ' + if_config_vars['project_name'])
            else:
                result = response.json()
                if result['success'] is False or result['isProjectExist'] is False:
                    logger.error('Check project error: ' + if_config_vars['project_name'])
                else:
                    is_project_exist = True
                    logger.info('Check project success: ' + if_config_vars['project_name'])

        except Exception as e:
            logger.error(e)
            logger.error('Check project error: ' + if_config_vars['project_name'])

    return is_project_exist


def listener_configurer():
    """ set up logging according to the defined log level """
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

    # Get the root logger
    root = logging.getLogger()
    # No level or filter logic applied - just do it!
    # root.setLevel(level)

    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
    logging_handler_out.setFormatter(formatter)
    root.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logging_handler_err.setFormatter(formatter)
    root.addHandler(logging_handler_err)


def listener_process(q):
    listener_configurer()
    while True:
        while not q.empty():
            record = q.get()

            if record.name == 'KILL':
                return

            logger = logging.getLogger(record.name)
            logger.handle(record)
        sleep(1)


def worker_configurer(q, level):
    h = QueueHandler(q)  # Just the one handler needed
    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(level)


def worker_process(args):
    (config_file, c_config, time_now, q) = args

    # start sub process
    worker_configurer(q, c_config['log_level'])
    logger = logging.getLogger('worker')
    logger.info("Setup logger in PID {}".format(os.getpid()))
    logger.info("Process start with config: {}".format(config_file))

    if_config_vars = get_if_config_vars(logger, config_file)
    if not if_config_vars:
        return
    agent_config_vars = get_agent_config_vars(logger, config_file)
    if not agent_config_vars:
        return
    print_summary_info(logger, if_config_vars, agent_config_vars)

    if not c_config['testing']:
        # check project name first
        check_success = check_project_exist(logger, if_config_vars)
        if not check_success:
            return

    # start run
    initialize_data_gathering(logger, c_config, if_config_vars, agent_config_vars, time_now)

    logger.info("Process is done with config: {}".format(config_file))
    return True


if __name__ == "__main__":
    # get config
    cli_config_vars = get_cli_config_vars()

    # logger
    m = multiprocessing.Manager()
    queue = m.Queue()
    listener = multiprocessing.Process(
        target=listener_process, args=(queue,))
    listener.start()

    # set up main logger following example from work_process
    worker_configurer(queue, cli_config_vars['log_level'])
    main_logger = logging.getLogger('main')

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)
    main_logger.info(cli_data_block)

    # get all config files
    files_path = os.path.join(cli_config_vars['config'], "*.ini")
    config_files = glob.glob(files_path)

    # get args
    utc_time_now = int(arrow.utcnow().float_timestamp)
    arg_list = [(f, cli_config_vars, utc_time_now, queue) for f in config_files]

    # start sub process by pool
    pool = Pool(cli_config_vars['processes'])
    pool_result = pool.map_async(worker_process, arg_list)
    pool.close()

    # wait 5 minutes for every worker to finish
    pool_result.wait(timeout=cli_config_vars['timeout'])

    try:
        results = pool_result.get(timeout=1)
        pool.join()
    except TimeoutError:
        main_logger.error("We lacked patience and got a multiprocessing.TimeoutError")
        pool.terminate()

    # end
    main_logger.info("Now the pool is closed and no longer available")

    # send kill signal
    time.sleep(1)
    kill_logger = logging.getLogger('KILL')
    kill_logger.info('KILL')
    listener.join()

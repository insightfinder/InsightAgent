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
from itertools import chain
from optparse import OptionParser
from logging.handlers import QueueHandler
import multiprocessing
from multiprocessing.pool import ThreadPool
from multiprocessing import Pool, TimeoutError

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


def start_data_processing(logger, c_config, if_config_vars, agent_config_vars, metric_buffer, track, time_now):
    logger.info('Started......')

    # build ThreadPool
    pool_map = ThreadPool(agent_config_vars['thread_pool'])

    # build request headers
    api_key = agent_config_vars['api_key']
    headers = {
        "Accept": "application/json",
        "Authorization": "ExtraHop apikey=" + api_key
    }

    metric_query_params = agent_config_vars['metric_query_params']
    device_ip_list = agent_config_vars['device_ip_list'] or []

    # merge all device ip list
    for param in metric_query_params:
        ips = param.get('device_ip_list') or []
        device_ip_list.extend(ips)
    device_ip_list = list(set(device_ip_list))

    # get devices list and id maps
    devices_ids = []
    devices_ids_map = {}
    devices_ips_map = {}
    url = urllib.parse.urljoin(agent_config_vars['host'], '/api/v1/devices')
    result_list = []
    if device_ip_list:
        def query_devices(args):
            ip, params = args
            logger.debug('Starting query device ip: {}'.format(ip))
            data = []
            try:
                # execute sql string
                response = send_request(url, headers=headers, params=params, verify=False,
                                        proxies=agent_config_vars['proxies'])
                if response != -1:
                    result = response.json()
                    data = result or []
            except Exception as e:
                logger.error(e)
                logger.error('Query device error: ' + ip)
            return data

        params_list = [(ip, {
            "search_type": 'ip address',
            "value": ip
        }) for ip in device_ip_list]
        results = pool_map.map(query_devices, params_list)
        result_list = list(chain(*results))
    else:
        params = {
            "search_type": 'any',
        }
        try:
            # execute sql string
            response = send_request(url, headers=headers, params=params, verify=False,
                                    proxies=agent_config_vars['proxies'])
            if response != -1:
                result = response.json()
                result_list = result or []
        except Exception as e:
            logger.error(e)
            logger.error('Query device list error')

    # parse device list
    for device in result_list:
        device_id = device['id']
        devices_ids.append(device_id)
        devices_ids_map[device_id] = device['ipaddr4']
        devices_ips_map[device['ipaddr4']] = device_id

    # filter devices ids
    if len(devices_ids) == 0:
        logger.error('Devices list is empty')
        return

    # parse sql string by params
    logger.debug('history range config: {}'.format(agent_config_vars['his_time_range']))
    if agent_config_vars['his_time_range']:
        logger.debug('Using time range for replay data')
        for timestamp in range(agent_config_vars['his_time_range'][0],
                               agent_config_vars['his_time_range'][1],
                               if_config_vars['sampling_interval']):
            start_time = timestamp
            end_time = timestamp + if_config_vars['sampling_interval']

            params = build_query_params(logger, if_config_vars, agent_config_vars, headers, devices_ips_map,
                                        devices_ids, metric_query_params, start_time, end_time)
            results = pool_map.map(query_messages_extrahop, params)
            result_list = list(chain(*results))
            parse_messages_extrahop(logger, if_config_vars, agent_config_vars, metric_buffer, track, result_list,
                                    devices_ids_map)

            # clear metric buffer when piece of time range end
            clear_metric_buffer(logger, c_config, if_config_vars, metric_buffer, track)
    else:
        logger.debug('Using current time for streaming data')
        start_time = time_now - if_config_vars['sampling_interval']
        end_time = time_now

        params = build_query_params(logger, if_config_vars, agent_config_vars, headers, devices_ips_map, devices_ids,
                                    metric_query_params, start_time, end_time)
        results = pool_map.map(query_messages_extrahop, params)
        result_list = list(chain(*results))
        parse_messages_extrahop(logger, if_config_vars, agent_config_vars, metric_buffer, track, result_list,
                                devices_ids_map)

    logger.info('Closed......')


def build_query_params(logger, if_config_vars, agent_config_vars, headers, devices_ips_map, devices_ids,
                       metric_query_params, start_time, end_time):
    params = []
    for metric_query in metric_query_params:
        device_ip_list = metric_query['device_ip_list']
        current_devices_ids = devices_ids
        if device_ip_list and len(device_ip_list) > 0:
            current_devices_ids = [devices_ips_map.get(ip) for ip in device_ip_list if devices_ips_map.get(ip)]

        for metric_obj in metric_query['metric_specs']:
            metric = metric_obj['name']
            metric_specs = [metric_obj]
            params.append((
                logger, if_config_vars, agent_config_vars,
                metric,
                headers,
                {
                    "from": start_time * 1000,
                    "until": end_time * 1000,
                    "metric_category": metric_query["metric_category"],
                    "metric_specs": metric_specs,
                    "object_type": agent_config_vars['object_type'],
                    "object_ids": current_devices_ids,
                    "cycle": metric_query['cycle'] or 'auto',
                }
            ))
    return params


def query_messages_extrahop(args):
    logger, if_config_vars, agent_config_vars, metric, headers, params = args
    logger.info('Starting query metrics with params: {}'.format(str(json.dumps(params))))

    data = []
    try:
        # execute sql string
        url = urllib.parse.urljoin(agent_config_vars['host'], '/api/v1/metrics')
        response = send_request(url, mode='POST', headers=headers, data=json.dumps(params), verify=False,
                                proxies=agent_config_vars['proxies'])
        if response == -1:
            logger.error('Query metrics error')
        else:
            result = response.json()
            # Check the result is Dict, and has field stats
            data = result["stats"] or []

    except Exception as e:
        logger.error(e)

    # add metric name in the value
    data = [{**item, 'metric_name': metric, } for item in data]

    return data


def parse_messages_extrahop(logger, if_config_vars, agent_config_vars, metric_buffer, track, result, devices_ids_map):
    count = 0
    logger.info('Reading {} messages'.format(len(result)))

    for message in result:
        try:
            logger.debug(message)

            date_field = message.get('metric_name')

            instance = message.get(
                agent_config_vars['instance_field'][0] if agent_config_vars['instance_field'] and len(
                    agent_config_vars['instance_field']) > 0 else 'oid')
            instance = devices_ids_map.get(instance, instance)

            # filter by instance whitelist
            if agent_config_vars['instance_whitelist_regex'] \
                    and not agent_config_vars['instance_whitelist_regex'].match(instance):
                continue

            # timestamp should be misc unit
            timestamp = message.get(
                agent_config_vars['timestamp_field'][0] if agent_config_vars['timestamp_field'] else 'time')

            # set offset for timestamp
            timestamp += agent_config_vars['target_timestamp_timezone'] * 1000
            timestamp = str(timestamp)

            # get values with different format
            values = message.get('values')
            if len(values) == 0:
                continue
            value_val = values[0]
            if isinstance(value_val, list):
                for value_item in value_val:
                    data_value = value_item['value']
                    key_meta_data = value_item['key'] or {}

                    # add device info if has
                    device = None
                    device_field = agent_config_vars['device_field']
                    if device_field and len(device_field) > 0:
                        devices = [key_meta_data.get(d) for d in device_field]
                        devices = [d for d in devices if d]
                        device = devices[0] if len(devices) > 0 else None
                    full_instance = make_safe_instance_string(instance, device)

                    # get component, and build component instance map info
                    component_map = None
                    if agent_config_vars['component_field']:
                        component = key_meta_data.get(agent_config_vars['component_field'])
                        if component:
                            component_map = {"instanceName": full_instance, "componentName": component}

                    key = '{}-{}'.format(timestamp, full_instance)
                    if key not in metric_buffer['buffer_dict']:
                        metric_buffer['buffer_dict'][key] = {"timestamp": timestamp, "component_map": component_map}

                    metric_key = '{}[{}]'.format(date_field, full_instance)
                    metric_buffer['buffer_dict'][key][metric_key] = str(data_value)

            else:
                data_value = value_val

                # add device info if has
                device = None
                device_field = agent_config_vars['device_field']
                if device_field and len(device_field) > 0:
                    devices = [message.get(d) for d in device_field]
                    devices = [d for d in devices if d]
                    device = devices[0] if len(devices) > 0 else None
                full_instance = make_safe_instance_string(instance, device)

                # get component, and build component instance map info
                component_map = None
                if agent_config_vars['component_field']:
                    component = message.get(agent_config_vars['component_field'])
                    if component:
                        component_map = {"instanceName": full_instance, "componentName": component}

                key = '{}-{}'.format(timestamp, full_instance)
                if key not in metric_buffer['buffer_dict']:
                    metric_buffer['buffer_dict'][key] = {"timestamp": timestamp, "component_map": component_map}

                metric_key = '{}[{}]'.format(date_field, full_instance)
                metric_buffer['buffer_dict'][key][metric_key] = str(data_value)

        except Exception as e:
            logger.warn('Error when parsing message')
            logger.warn(e)
            logger.debug(traceback.format_exc())
            continue

        track['entry_count'] += 1
        count += 1
        if count % 1000 == 0:
            logger.info('Parse {0} messages'.format(count))
    logger.info('Parse {0} messages'.format(count))


def get_agent_config_vars(logger, config_ini):
    """ Read and parse config.ini """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False
    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)

        extrahop_kwargs = {}
        host = None
        api_key = None
        metric_query_params = None
        device_ip_list = None
        object_type = None
        his_time_range = None

        instance_whitelist_regex = None
        try:
            # extrahop settings
            extrahop_config = {}
            # only keep settings with values
            extrahop_kwargs = {k: v for (k, v) in list(extrahop_config.items()) if v}

            host = config_parser.get('extrahop', 'host')
            api_key = config_parser.get('extrahop', 'api_key')

            object_type = config_parser.get('extrahop', 'object_type')
            device_ip_list = config_parser.get('extrahop', 'device_ip_list')
            metric_query_params = config_parser.get('extrahop', 'metric_query_params')

            # time range
            his_time_range = config_parser.get('extrahop', 'his_time_range')

            # proxies
            agent_http_proxy = config_parser.get('extrahop', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('extrahop', 'agent_https_proxy')

            # message parsing
            data_format = config_parser.get('extrahop', 'data_format').upper()
            component_field = config_parser.get('extrahop', 'component_field', raw=True)
            instance_field = config_parser.get('extrahop', 'instance_field', raw=True)
            instance_whitelist = config_parser.get('extrahop', 'instance_whitelist')
            device_field = config_parser.get('extrahop', 'device_field', raw=True)
            timestamp_field = config_parser.get('extrahop', 'timestamp_field', raw=True) or 'timestamp'
            target_timestamp_timezone = config_parser.get('extrahop', 'target_timestamp_timezone', raw=True) or 'UTC'
            timestamp_format = config_parser.get('extrahop', 'timestamp_format', raw=True)
            timezone = config_parser.get('extrahop', 'timezone') or 'UTC'
            thread_pool = config_parser.get('extrahop', 'thread_pool', raw=True)

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        # handle boolean setting

        # handle required arrays
        if not host:
            return config_error(logger, 'host')
        if not api_key:
            return config_error(logger, 'api_key')
        if not object_type:
            return config_error(logger, 'object_type')
        if device_ip_list:
            device_ip_list = [ip.strip() for ip in device_ip_list.split(',') if ip.strip()]
        if metric_query_params:
            try:
                metric_query_params = eval(metric_query_params)
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'metric_query_params')
        else:
            return config_error(logger, 'metric_query_params')
        if not isinstance(metric_query_params, list):
            return config_error(logger, 'metric_query_params')
        for param in metric_query_params:
            if param.get('device_ip_list') and not isinstance(param['device_ip_list'], list):
                return config_error(logger, 'metric_query_params->device_ip_list')

        if len(instance_whitelist) != 0:
            try:
                instance_whitelist_regex = regex.compile(instance_whitelist)
            except Exception:
                return config_error(logger, 'instance_whitelist')

        if len(his_time_range) != 0:
            his_time_range = [x.strip() for x in his_time_range.split(',') if x.strip()]
            his_time_range = [int(arrow.get(x).float_timestamp) for x in his_time_range]

        if len(target_timestamp_timezone) != 0:
            target_timestamp_timezone = int(arrow.now(target_timestamp_timezone).utcoffset().total_seconds())
        else:
            return config_error(logger, 'target_timestamp_timezone')

        if timezone:
            if timezone not in pytz.all_timezones:
                return config_error(logger, 'timezone')
            else:
                timezone = pytz.timezone(timezone)

        # data format
        if data_format in {'JSON',
                           'JSONTAIL',
                           'AVRO',
                           'XML'}:
            pass
        else:
            return config_error(logger, 'data_format')

        # proxies
        agent_proxies = dict()
        if len(agent_http_proxy) > 0:
            agent_proxies['http'] = agent_http_proxy
        if len(agent_https_proxy) > 0:
            agent_proxies['https'] = agent_https_proxy

        # fields
        instance_fields = [x.strip() for x in instance_field.split(',') if x.strip()]
        device_fields = [x.strip() for x in device_field.split(',') if x.strip()]
        timestamp_fields = timestamp_field.split(',')

        if len(thread_pool) != 0:
            thread_pool = int(thread_pool)
        else:
            thread_pool = 20

        # add parsed variables to a global
        config_vars = {
            'extrahop_kwargs': extrahop_kwargs,
            'host': host,
            'api_key': api_key,
            'object_type': object_type,
            'device_ip_list': device_ip_list,
            'metric_query_params': metric_query_params,

            'his_time_range': his_time_range,

            'proxies': agent_proxies,
            'data_format': data_format,
            'component_field': component_field,
            'instance_field': instance_fields,
            "instance_whitelist_regex": instance_whitelist_regex,
            'device_field': device_fields,
            'timestamp_field': timestamp_fields,
            'target_timestamp_timezone': target_timestamp_timezone,
            'timezone': timezone,
            'timestamp_format': timestamp_format,
            'thread_pool': thread_pool,
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
            'DEPLOYMENTREPLAY'
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
            'project_type': project_type,
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


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    # return len(bytearray(json.dumps(json_data)))
    return getsizeof(json.dumps(json_data))


def make_safe_instance_string(instance, device=''):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', str(instance))
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


def format_command(cmd):
    if not isinstance(cmd, (list, tuple)):  # no sets, as order matters
        cmd = shlex.split(cmd)
    return list(cmd)


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
    metric_buffer = dict()
    track = dict()
    reset_metric_buffer(metric_buffer)
    reset_track(track)
    track['chunk_count'] = 0
    track['entry_count'] = 0

    start_data_processing(logger, c_config, if_config_vars, agent_config_vars, metric_buffer, track, time_now)

    # clear metric buffer when data processing end
    clear_metric_buffer(logger, c_config, if_config_vars, metric_buffer, track)

    logger.info('Total chunks created: ' + str(track['chunk_count']))
    logger.info('Total {} entries: {}'.format(
        if_config_vars['project_type'].lower(), track['entry_count']))


def clear_metric_buffer(logger, c_config, if_config_vars, metric_buffer, track):
    # move all buffer data to current data, and send
    buffer_values = list(metric_buffer['buffer_dict'].values())

    count = 0
    for row in buffer_values:
        # pop component map info
        component_map = row.pop('component_map')
        if component_map:
            track['component_map_list'].append(component_map)

        track['current_row'].append(row)
        count += 1
        if count % 100 == 0 or get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
            logger.debug('Sending buffer chunk')
            send_data_wrapper()

    # last chunk
    if len(track['current_row']) > 0:
        logger.debug('Sending last chunk')
        send_data_wrapper()

    reset_metric_buffer(metric_buffer)


def reset_metric_buffer(metric_buffer):
    metric_buffer['buffer_key_list'] = []
    metric_buffer['buffer_ts_list'] = []
    metric_buffer['buffer_dict'] = {}

    metric_buffer['buffer_collected_list'] = []
    metric_buffer['buffer_collected_dict'] = {}


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
    reset_track()


def send_data_to_if(logger, c_config, if_config_vars, track, chunk_metric_data):
    send_data_time = time.time()

    # prepare data for metric streaming agent
    data_to_post = initialize_api_post_data()
    if 'DEPLOYMENT' in if_config_vars['project_type'] or 'INCIDENT' in if_config_vars['project_type']:
        for chunk in chunk_metric_data:
            chunk['data'] = json.dumps(chunk['data'])
    data_to_post[get_data_field_from_project_type()] = json.dumps(chunk_metric_data)

    # add component mapping to the post data
    track['component_map_list'] = list({v['instanceName']: v for v in track['component_map_list']}.values())
    data_to_post['instanceMetaData'] = json.dumps(track['component_map_list'] or [])

    logger.debug('First:\n' + str(chunk_metric_data[0]))
    logger.debug('Last:\n' + str(chunk_metric_data[-1]))
    logger.info('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
    logger.info('Total Lines: ' + str(track['line_count']))

    # do not send if only testing
    if cli_config_vars['testing']:
        return

    # send the data
    post_url = urllib.parse.urljoin(if_config_vars['if_url'], get_api_from_project_type())
    send_request(logger, post_url, 'POST', 'Could not send request to IF',
                 str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.',
                 data=data_to_post, verify=False, proxies=if_config_vars['if_proxies'])
    logger.info('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def send_request(logger, url, mode='GET', failure_message='Failure!', success_message='Success!',
                 **request_passthrough):
    """ sends a request to the given url """
    # determine if post or get (default)
    requests.packages.urllib3.disable_warnings()
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
    to_send_data_dict['agentType'] = get_agent_type_from_project_type()
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
                'instanceType': 'PrivateCloud',
                'projectCloudType': 'PrivateCloud',
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


def listener_process(q, c_config):
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
        target=listener_process, args=(queue, cli_config_vars))
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

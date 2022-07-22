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

    # get servers
    servers = agent_config_vars['servers']

    # filter servers
    if len(servers) == 0:
        logger.error('Server list is empty')
        return

    metric_path = agent_config_vars['metric_path']

    # get instances
    instances = agent_config_vars['instances']
    # filter instances
    if len(instances) == 0:
        logger.error('Instance list is empty')
        return

    # get metrics
    metrics = agent_config_vars['metrics']
    # filter metrics
    if len(metrics) == 0:
        logger.error('Metric list is empty')
        return

    # parse sql string by params
    pool_map = ThreadPool(agent_config_vars['thread_pool'])
    logger.debug('history range config: {}'.format(agent_config_vars['his_time_range']))
    if agent_config_vars['his_time_range']:
        logger.debug('Using time range for replay data')
        for timestamp in range(agent_config_vars['his_time_range'][0],
                               agent_config_vars['his_time_range'][1],
                               if_config_vars['sampling_interval']):
            start_time = timestamp
            end_time = timestamp + if_config_vars['sampling_interval']

            params = []
            for server in servers:
                for ins in instances:
                    for m in metrics:
                        target = metric_path.format(region=agent_config_vars['region'], env=agent_config_vars['env'],
                                                    system=agent_config_vars['system'], instance=ins, metric=m)
                        params.append((logger, if_config_vars, agent_config_vars, server[1], server[0], ins, m, {
                            'format': agent_config_vars['data_format'].lower(),
                            'target': target,
                            'from': start_time,
                            'until': end_time,
                            # 'from': arrow.get(start_time).format('HH:mm_YYYYMMDD'),
                            # 'until': arrow.get(end_time).format('HH:mm_YYYYMMDD'),
                        }))
            results = pool_map.map(query_messages_osmosys, params)
            result_list = list(chain(*results))
            parse_messages_osmosys(logger, if_config_vars, agent_config_vars, metric_buffer, track, result_list)

            # clear metric buffer when piece of time range end
            clear_metric_buffer(logger, c_config, if_config_vars, metric_buffer, track)
    else:
        logger.debug('Using current time for streaming data')
        start_time = time_now - if_config_vars['sampling_interval']
        end_time = time_now

        params = []
        for server in servers:
            for ins in instances:
                for m in metrics:
                    target = metric_path.format(region=agent_config_vars['region'], env=agent_config_vars['env'],
                                                system=agent_config_vars['system'], instance=ins, metric=m)
                    params.append((logger, if_config_vars, agent_config_vars, server[1], server[0], ins, m, {
                        'format': agent_config_vars['data_format'].lower(),
                        'target': target,
                        'from': start_time,
                        'until': end_time,
                        # 'from': arrow.get(start_time).format('HH:mm_YYYYMMDD'),
                        # 'until': arrow.get(end_time).format('HH:mm_YYYYMMDD'),
                    }))
        results = pool_map.map(query_messages_osmosys, params)
        result_list = list(chain(*results))
        parse_messages_osmosys(logger, if_config_vars, agent_config_vars, metric_buffer, track, result_list)

    logger.info('Closed......')


def query_messages_osmosys(args):
    logger, if_config_vars, agent_config_vars, server, server_name, instance, metric, params = args
    logger.info('Starting query server name | metric: {} | {}'.format(server_name, metric))

    data = []
    try:
        # execute sql string
        url = urllib.parse.urljoin(server, 'render')
        response = send_request(url, params=params, proxies=agent_config_vars['proxies'])
        if response == -1:
            logger.error('Query metric error: ' + metric)
        else:
            result = response.json()

            # make the real data has correct format, the results should be a list<object>
            # Example: data = [{'time': 1624435839000, 'metric': 'test_metric', 'data': '1.01'}]
            data = result or []

    except Exception as e:
        logger.error(e)
        logger.error('Query metric error: ' + metric)

    # add metric name in the value
    data = [{**item, 'query_server_name': server_name, 'query_instance_name': instance, 'query_metric_name': metric, }
            for item in data]

    return data


def parse_messages_osmosys(logger, if_config_vars, agent_config_vars, metric_buffer, track, result):
    count = 0
    logger.info('Reading {} messages'.format(len(result)))

    for message in result:
        try:
            logger.debug(message)

            # get metric name in response, parse metric path
            metric = message.get('target')
            metric = metric.split('.')
            metric = metric[6:]
            date_field = '.'.join(metric)

            # filter by metric whitelist
            if agent_config_vars['metrics_whitelist_regex'] \
                    and not agent_config_vars['metrics_whitelist_regex'].match(date_field):
                continue

            # get instance name
            instance = message.get(
                agent_config_vars['instance_field'][0] if agent_config_vars['instance_field'] and len(
                    agent_config_vars['instance_field']) > 0 else 'query_instance_name')

            # filter by instance whitelist
            if agent_config_vars['instance_whitelist_regex'] \
                    and not agent_config_vars['instance_whitelist_regex'].match(instance):
                continue

            # add device info if has
            device = None
            device_field = agent_config_vars['device_field']
            if device_field and len(device_field) > 0:
                device = message.get(agent_config_vars['device_field'][0])
            full_instance = make_safe_instance_string(instance, device)

            # get component, and build component instance map info
            component_map = None
            if agent_config_vars['component_field']:
                component = message.get(agent_config_vars['component_field'])
                if component:
                    component_map = {"instanceName": full_instance, "componentName": component}

            # time and value in the datapoints
            datapoints = message.get('datapoints', [])
            for item in datapoints:
                # timestamp should be misc unit
                timestamp = item[1] * 1000
                data_value = item[0]

                # set offset for timestamp
                timestamp += agent_config_vars['target_timestamp_timezone'] * 1000
                timestamp = str(timestamp)

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

        osmosys_kwargs = {}
        servers = None
        metric_path = ''
        instances = None
        metrics = None
        metrics_whitelist = None
        region = '*'
        env = '*'
        system = '*'
        his_time_range = None

        metrics_whitelist_regex = None
        instance_whitelist_regex = None
        try:
            # osmosys settings
            osmosys_config = {}
            # only keep settings with values
            osmosys_kwargs = {k: v for (k, v) in list(osmosys_config.items()) if v}

            # handle boolean setting

            # handle required arrays
            if len(config_parser.get('osmosys', 'osmosys_servers')) != 0:
                osmosys_servers = config_parser.get('osmosys', 'osmosys_servers')
                servers = [[s.strip() for s in x.strip().split(',') if s.strip()] for x in osmosys_servers.split(';') if
                           x.strip()]
            else:
                return config_error(logger, 'osmosys_servers')
            for server in servers:
                if len(server) != 2:
                    return config_error(logger, 'osmosys_servers')

            metric_path = config_parser.get('osmosys', 'metric_path')
            instances = config_parser.get('osmosys', 'instances')
            metrics = config_parser.get('osmosys', 'metrics')
            metrics_whitelist = config_parser.get('osmosys', 'metrics_whitelist')
            region = config_parser.get('osmosys', 'region') or '*'
            env = config_parser.get('osmosys', 'env') or '*'
            system = config_parser.get('osmosys', 'system') or '*'

            # time range
            his_time_range = config_parser.get('osmosys', 'his_time_range')

            # proxies
            agent_http_proxy = config_parser.get('osmosys', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('osmosys', 'agent_https_proxy')

            # message parsing
            data_format = config_parser.get('osmosys', 'data_format').upper()
            component_field = config_parser.get('osmosys', 'component_field', raw=True)
            instance_field = config_parser.get('osmosys', 'instance_field', raw=True)
            instance_whitelist = config_parser.get('osmosys', 'instance_whitelist')
            device_field = config_parser.get('osmosys', 'device_field', raw=True)
            timestamp_field = config_parser.get('osmosys', 'timestamp_field', raw=True) or 'timestamp'
            target_timestamp_timezone = config_parser.get('osmosys', 'target_timestamp_timezone', raw=True) or 'UTC'
            timestamp_format = config_parser.get('osmosys', 'timestamp_format', raw=True)
            timezone = config_parser.get('osmosys', 'timezone') or 'UTC'
            data_fields = config_parser.get('osmosys', 'data_fields', raw=True)
            thread_pool = config_parser.get('osmosys', 'thread_pool', raw=True)

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        if len(metric_path) == 0:
            return config_error(logger, 'metric_path')
        # instances
        if len(instances) != 0:
            instances = [x.strip() for x in instances.split(',') if x.strip()]
        else:
            return config_error(logger, 'instances')
        # metrics
        if len(metrics) != 0:
            metrics = [x.strip() for x in metrics.split(',') if x.strip()]
        else:
            return config_error(logger, 'metrics')

        if len(metrics_whitelist) != 0:
            try:
                metrics_whitelist_regex = regex.compile(metrics_whitelist)
            except Exception:
                return config_error(logger, 'metrics_whitelist')
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
        if len(data_fields) != 0:
            data_fields = data_fields.split(',')
            for instance_field in instance_fields:
                if instance_field in data_fields:
                    data_fields.pop(data_fields.index(instance_field))
            for device_field in device_fields:
                if device_field in data_fields:
                    data_fields.pop(data_fields.index(device_field))
            for timestamp_field in timestamp_fields:
                if timestamp_field in data_fields:
                    data_fields.pop(data_fields.index(timestamp_field))

        if len(thread_pool) != 0:
            thread_pool = int(thread_pool)
        else:
            thread_pool = 20

        # add parsed variables to a global
        config_vars = {
            'osmosys_kwargs': osmosys_kwargs,
            'servers': servers,
            'metric_path': metric_path,
            'instances': instances,
            'metrics': metrics,
            'metrics_whitelist_regex': metrics_whitelist_regex,
            'region': region,
            'env': env,
            'system': system,
            'his_time_range': his_time_range,

            'proxies': agent_proxies,
            'data_format': data_format,
            'component_field': component_field,
            'instance_field': instance_fields,
            "instance_whitelist_regex": instance_whitelist_regex,
            'device_field': device_fields,
            'data_fields': data_fields,
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

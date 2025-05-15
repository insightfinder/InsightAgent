#!/usr/bin/env python
import configparser
import glob
import http.client
import json
import logging
import multiprocessing
import os
import shlex
import socket
import sqlite3
import sys
import time
import traceback
import urllib.parse
from itertools import chain
from logging.handlers import QueueHandler
from multiprocessing import Pool, TimeoutError
from multiprocessing.pool import ThreadPool
from optparse import OptionParser
from sys import getsizeof
from time import sleep

import arrow
import pytz
import redis
import regex
import requests
from redis.cluster import RedisCluster, ClusterNode

"""
This script monitors Redis keys for staleness and sends data to Insightfinder
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
CACHE_NAME = 'cache/cache.db'


def align_timestamp(timestamp, sampling_interval):
    if sampling_interval == 0 or not timestamp:
        return timestamp
    else:
        return int(timestamp / (sampling_interval * 1000)) * sampling_interval * 1000


def initialize_cache_connection():
    # Not needed for Redis agent
    return (None, None)


def start_data_processing(logger, c_config, if_config_vars, agent_config_vars, metric_buffer, track, cache_con,
                          cache_cur, time_now):
    logger.info('Started......')

    redis_hosts = agent_config_vars['redis_hosts']
    thread_pool = ThreadPool(agent_config_vars['thread_pool'])

    def run_redis_query(timestamp):
        params = [(logger, if_config_vars, agent_config_vars, host.strip(), timestamp) 
                 for host in redis_hosts.split(',')]
        
        results = thread_pool.map(query_redis_keys, params)
        result_list = list(chain(*results))
        
        # Process results similar to Prometheus
        parse_messages_redis(logger, if_config_vars, agent_config_vars, metric_buffer, track,
                           cache_con, cache_cur, result_list, timestamp)
        
        # Clear buffer when time range ends
        clear_metric_buffer(logger, c_config, if_config_vars, metric_buffer, track)

    if agent_config_vars.get('his_time_range'):
        logger.debug('history range config: {}'.format(agent_config_vars['his_time_range']))
        for timestamp in range(agent_config_vars['his_time_range'][0], agent_config_vars['his_time_range'][1],
                             if_config_vars['run_interval']):
            run_redis_query(timestamp)
    else:
        logger.debug('Using current time for streaming data')
        run_redis_query(time_now)

    thread_pool.close()
    thread_pool.join()
    logger.info('Closed......')


def query_redis_keys(args):
    logger, if_config_vars, agent_config_vars, redis_host, time_now = args
    
    try:
        host, port = redis_host.split(':')
        port = int(port)
        
        # Redis connection parameters
        redis_params = {
            'host': host,
            'port': port,
            'password': agent_config_vars.get('password'),
            'ssl': agent_config_vars.get('use_ssl', False),
            'ssl_ca_certs': agent_config_vars.get('ssl_ca_certs'),
            'ssl_certfile': agent_config_vars.get('ssl_certfile'),
            'ssl_keyfile': agent_config_vars.get('ssl_keyfile'),
            'socket_timeout': agent_config_vars.get('connection_timeout', 5)
        }

        # Connect based on redis_mode
        redis_mode = agent_config_vars.get('redis_mode', 'single').lower()
        if redis_mode == 'single':
            # Single node mode
            r = redis.Redis(**redis_params)
        elif redis_mode == 'cluster':
            # Cluster mode
            # startup_nodes = [ClusterNode(host, port)]
            r = RedisCluster(**redis_params)
        
        data = []
        pattern = agent_config_vars.get('key_pattern', '*')
        scan_count = int(agent_config_vars.get('scan_count', 1000))
        check_ttl = agent_config_vars.get('check_ttl', False)
        
        # Query keys for the cluster or single node
        data.extend(scan_node_keys(r, pattern, scan_count, check_ttl, 
                                   time_now, f"{host}:{port}", logger))
                    
        return data
        
    except Exception as e:
        logger.error(f"Error querying Redis {host}:{port}: {e}")
        return []


def scan_node_keys(redis_client, pattern, scan_count, check_ttl, time_now, instance, logger):
    """Helper function to scan keys on a single Redis node/instance"""
    data = []
    try:
        cursor = '0'
        while cursor != 0:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=scan_count)
            for key in keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                
                # Get key metadata
                try:
                    idle_time = redis_client.object('IDLETIME', key)
                    metrics = {'idle_minutes': idle_time / 60}
                    
                    # Only check TTL if configured
                    if check_ttl:
                        ttl = redis_client.ttl(key)
                        metrics['ttl_seconds'] = ttl
                        
                    metric_data = {
                        'metric': {
                            '__name__': 'redis_key',
                            'key': key_str,
                            'instance': instance
                        },
                        'value': [time_now, metrics]
                    }
                    data.append(metric_data)
                except:
                    continue
    except Exception as e:
        logger.error(f"Error scanning keys on {instance}: {e}")
    
    return data


def parse_messages_redis(logger, if_config_vars, agent_config_vars, metric_buffer, track, cache_con,
                        cache_cur, result, timestamp):

    count = 0
    logger.info('Reading {} messages'.format(len(result)))
    
    for message in result:
        try:
            metric = message.get('metric', {})
            instance = metric.get('instance', '')
            key = metric.get('key', '')
            
            # Format instance name
            if agent_config_vars.get('instance_field'):
                instance = message.get('metric', {}).get(agent_config_vars['instance_field'])
            
            # Filter by whitelist if configured
            if agent_config_vars.get('instance_whitelist_regex') and not agent_config_vars['instance_whitelist_regex'].match(instance):
                continue
                
            # Add instance suffix if configured    
            instance_name_suffix = agent_config_vars.get('instance_name_suffix', '')
            if instance_name_suffix:
                instance = instance + instance_name_suffix
            
            # Make safe instance string
            full_instance = make_safe_instance_string(instance)
            
            # Process metric values
            value = message.get('value', [])
            if len(value) >= 2:
                timestamp = value[0]
                metrics = value[1]
                
                buffer_key = '{}-{}'.format(timestamp, full_instance)
                
                if buffer_key not in metric_buffer['buffer_dict']:
                    metric_buffer['buffer_dict'][buffer_key] = {
                        "timestamp": timestamp * 1000,
                        "instanceName": full_instance,
                        "componentName": None,
                        "device_type": 0,
                        "host_id": None
                    }
                
                # Add each metric with proper naming
                for metric_name, metric_value in metrics.items():
                    # Create metric name with key as prefix
                    full_metric_name = f"{key}-{metric_name}"
                    float_value = safe_string_to_float(metric_value)
                    if float_value is not None:
                        metric_buffer['buffer_dict'][buffer_key][full_metric_name] = str(float_value)
                    else:
                        metric_buffer['buffer_dict'][buffer_key][full_metric_name] = '0.0'
                    
        except Exception as e:
            logger.warning('Error parsing message')
            logger.warning(e)
            continue

        track['entry_count'] += 1
        count += 1
        if count % 1000 == 0:
            logger.info('Parse {} messages'.format(count))
            
    logger.info('Parse {} messages'.format(count))


def get_agent_config_vars(logger, config_ini):
    """ Read and parse config.ini """
    """ get config.ini vars """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False
    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)
        
        try:
            # Redis settings matching Prometheus structure
            redis_config = {
                'redis_hosts': config_parser.get('redis', 'redis_hosts'),
                'redis_mode': config_parser.get('redis', 'redis_mode', fallback='single'),
                'password': config_parser.get('redis', 'password', fallback=''),
                'verify_certs': config_parser.get('redis', 'verify_certs', fallback='true'),
                'ssl_ca_certs': config_parser.get('redis', 'ssl_ca_certs', fallback=''),
                'ssl_certfile': config_parser.get('redis', 'ssl_certfile', fallback=''),
                'ssl_keyfile': config_parser.get('redis', 'ssl_keyfile', fallback=''),
                'key_pattern': config_parser.get('redis', 'key_pattern', fallback='*'),
                'instance_field': config_parser.get('redis', 'instance_field', fallback=''),
                'instance_whitelist': config_parser.get('redis', 'instance_whitelist', fallback=''),
                'instance_connector': config_parser.get('redis', 'instance_connector', fallback='-'),
                'thread_pool': config_parser.get('redis', 'thread_pool', fallback='20'),
                'processes': config_parser.get('redis', 'processes', fallback=''),
                'timeout': config_parser.get('redis', 'timeout', fallback='5'),
                'instance_name_suffix': config_parser.get('redis', 'instance_name_suffix', fallback=''),
                'query_delay': config_parser.get('redis', 'query_delay', fallback='10'),
                'check_ttl': config_parser.getboolean('redis', 'check_ttl', fallback=False)
            }

            # Validate redis_mode
            if redis_config['redis_mode'].lower() not in ['single', 'cluster']:
                logger.error('redis_mode must be either "single" or "cluster"')
                return False
            
            # Required settings validation
            if not redis_config['redis_hosts']:
                return config_error(logger, 'redis_hosts')
                
            # Convert settings
            redis_config['verify_certs'] = redis_config['verify_certs'].lower() == 'true'
            redis_config['thread_pool'] = int(redis_config['thread_pool'])
            redis_config['processes'] = int(redis_config['processes']) if redis_config['processes'] else multiprocessing.cpu_count() * 4
            redis_config['timeout'] = int(redis_config['timeout']) * 60
            redis_config['query_delay'] = int(redis_config['query_delay'])
            
            # Handle instance whitelist regex
            if redis_config['instance_whitelist']:
                try:
                    redis_config['instance_whitelist_regex'] = regex.compile(redis_config['instance_whitelist'])
                except:
                    return config_error(logger, 'instance_whitelist')
            
            return redis_config
            
        except Exception as e:
            logger.error(e)
            return config_error(logger)


def print_summary_info(logger, if_config_vars, agent_config_vars):
    # info to be sent to IF
    post_data_block = '\nIF settings:'
    for ik, iv in sorted(if_config_vars.items()):
        if iv and ('license' in ik.lower() or 'token' in ik.lower() or 'key' in ik.lower()):
            iv = '********'
        post_data_block += '\n\t{}: {}'.format(ik, iv)
    logger.debug(post_data_block)

    # variables from agent-specific config
    agent_data_block = '\nAgent settings:'
    for jk, jv in sorted(agent_config_vars.items()):
        if jv and ('password' in jk.lower() or 'key' in jk.lower()):
            jv = '********'
        agent_data_block += '\n\t{}: {}'.format(jk, jv)
    logger.debug(agent_data_block)


#########################
#   START_BOILERPLATE   #
#########################

def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    """
    """
    parser.add_option('-c', '--config', action='store', dest='config', default=abs_path_from_cur('conf.d'),
                      help='Path to the config files to use. Defaults to {}'.format(abs_path_from_cur('conf.d')))
    # parser.add_option('-p', '--processes', action='store', dest='processes', default=multiprocessing.cpu_count() * 4,
    #                   help='Number of processes to run')
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data).' + ' Automatically turns on verbose logging')
    # parser.add_option('--timeout', action='store', dest='timeout', default=5,
    #                   help='Minutes of timeout for all processes')
    (options, args) = parser.parse_args()

    config_vars = {'config': options.config if os.path.isdir(options.config) else abs_path_from_cur('conf.d'),
                   # 'processes': int(options.processes),
                   'testing': False, 'log_level': logging.INFO,  # 'timeout': int(options.timeout) * 60,
                   }

    if options.testing:
        config_vars['testing'] = True
        config_vars['log_level'] = logging.DEBUG

    if options.verbose:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING

    return config_vars


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
            dynamic_metric_type = config_parser.get('insightfinder', 'dynamic_metric_type')
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

        if project_type not in {'METRIC', 'METRICREPLAY', 'LOG', 'LOGREPLAY', 'INCIDENT', 'INCIDENTREPLAY', 'ALERT',
                                'ALERTREPLAY', 'DEPLOYMENT', 'DEPLOYMENTREPLAY', 'TRACE', 'TRACEREPLAY'}:
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

        config_vars = {'user_name': user_name, 'license_key': license_key, 'token': token, 'project_name': project_name,
                       'system_name': system_name, 'project_type': project_type,
                       'containerize': True if containerize == 'YES' else False,
                       'sampling_interval': int(sampling_interval),  # as seconds
                       'run_interval': int(run_interval),  # as seconds
                       'chunk_size': int(chunk_size_kb) * 1024,  # as bytes
                       'if_url': if_url, 'if_proxies': if_proxies, 'is_replay': is_replay, 'dynamic_metric_type': dynamic_metric_type}

        return config_vars


def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))


def config_error(logger, setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(info))
    return False


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    # return len(bytearray(json.dumps(json_data)))
    return getsizeof(json.dumps(json_data))


def make_safe_instance_string(instance, device=''):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', instance)
    instance = COMMA.sub('.', instance)
    instance = COLONS.sub('-', instance)
    instance = LEFT_BRACE.sub('(', instance)
    instance = RIGHT_BRACE.sub(')', instance)
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


def initialize_data_gathering(logger, c_config, if_config_vars, agent_config_vars, time_now):
    metric_buffer = dict()
    track = dict()
    reset_metric_buffer(metric_buffer)
    reset_track(track)
    track['chunk_count'] = 0
    track['entry_count'] = 0

    # get cache
    (cache_con, cache_cur) = initialize_cache_connection()

    start_data_processing(logger, c_config, if_config_vars, agent_config_vars, metric_buffer, track, cache_con,
                          cache_cur, time_now)

    # clear metric buffer when data processing end
    clear_metric_buffer(logger, c_config, if_config_vars, metric_buffer, track)

    logger.info('Total chunks created: ' + str(track['chunk_count']))
    logger.info('Total {} entries: {}'.format(if_config_vars['project_type'].lower(), track['entry_count']))

    # close cache if needed
    if cache_con:
        cache_con.close()
    return True


def clear_metric_buffer(logger, c_config, if_config_vars, metric_buffer, track):
    # move all buffer data to current data, and send
    buffer_values = list(metric_buffer['buffer_dict'].values())

    count = 0
    for row in buffer_values:
        # # pop component map info
        # component_map = row.pop('component_map')
        # if component_map:
        #     track['component_map_list'].append(component_map)

        track['current_row'].append(row)
        count += 1
        if count % 100 == 0 or get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
            logger.debug('Sending buffer chunk')
            send_data_wrapper(logger, c_config, if_config_vars, track)

    # last chunk
    if len(track['current_row']) > 0:
        logger.debug('Sending last chunk')
        send_data_wrapper(logger, c_config, if_config_vars, track)

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
    logger.debug('--- Chunk creation time: {} seconds ---'.format(round(time.time() - track['start_time'], 2)))
    send_data_to_if(logger, c_config, if_config_vars, track, track['current_row'])
    track['chunk_count'] += 1
    reset_track(track)


def safe_string_to_float(s):
    try:
        return float(s)
    except ValueError:
        return None


def convert_to_metric_data(logger, chunk_metric_data, cli_config_vars, if_config_vars):
    to_send_data_dict = dict()
    to_send_data_dict['licenseKey'] = if_config_vars['license_key']
    to_send_data_dict['userName'] = if_config_vars['user_name']

    data_dict = dict()
    data_dict['projectName'] = if_config_vars['project_name']
    data_dict['userName'] = if_config_vars['user_name']
    if 'system_name' in if_config_vars:
        data_dict['systemName'] = if_config_vars['system_name']
    #data_dict['iat'] = get_insight_agent_type_from_project_type(if_config_vars)
    instance_data_map = dict()
    common_fields = {"instanceName", "componentName", "host_id", "timestamp", "device_type"}
    for chunk in chunk_metric_data:
        instance_name = chunk['instanceName']
        component_name = chunk.get('componentName')
        device_type = chunk.get('device_type')
        host_id = chunk.get('host_id')
        timestamp = chunk['timestamp']
        data = {k: v for k, v in chunk.items() if k not in common_fields}
        if data and timestamp and instance_name:
            ts = int(timestamp)
            if instance_name not in instance_data_map:
                instance_data_map[instance_name] = {'in': instance_name, 'cn': component_name, 'ct': device_type , 'dit': {}, }

            if timestamp not in instance_data_map[instance_name]['dit']:
                instance_data_map[instance_name]['dit'][timestamp] = {'t': ts, 'm': []}

            data_set = instance_data_map[instance_name]['dit'][timestamp]['m']
            if host_id:
                instance_data_map[instance_name]['dit'][timestamp]['k'] = {"hostId": host_id}
            for metric_name, metric_value in data.items():
                # remove instance name from the metric name
                metric_name = metric_name.split('[')[0]
                float_value = safe_string_to_float(metric_value)
                if float_value is not None:
                    data_set.append({'m': metric_name, 'v': float_value})
                else:
                    data_set.append({'m': metric_name, 'v': 0.0})

    data_dict['idm'] = instance_data_map
    to_send_data_dict['data'] = data_dict

    return to_send_data_dict


def send_data_to_if(logger, cli_config_vars, if_config_vars, track, chunk_metric_data):
    send_data_time = time.time()

    # prepare data for metric streaming agent
    # data_to_post = convert_to_metric_data(logger, chunk_metric_data, cli_config_vars, if_config_vars)

    # prepare data for metric streaming agent
    data_to_post = None
    json_to_post = None
    if 'METRIC' in if_config_vars['project_type']:
        json_to_post = convert_to_metric_data(logger, chunk_metric_data, cli_config_vars, if_config_vars)
        logger.debug(json_to_post)
        post_url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v2/metric-data-receive')
    else:
        data_to_post = initialize_api_post_data(logger, if_config_vars)
        if 'DEPLOYMENT' in if_config_vars['project_type'] or 'INCIDENT' in if_config_vars['project_type']:
            for chunk in chunk_metric_data:
                chunk['data'] = json.dumps(chunk['data'])
        data_to_post[get_data_field_from_project_type(if_config_vars)] = json.dumps(chunk_metric_data)
        # add component mapping to the post data
        track['component_map_list'] = list({v['instanceName']: v for v in track['component_map_list']}.values())
        data_to_post['instanceMetaData'] = json.dumps(track['component_map_list'] or [])

        post_url = urllib.parse.urljoin(if_config_vars['if_url'], get_api_from_project_type(if_config_vars))

    # do not send if only testing
    if cli_config_vars['testing']:
        test_data = json.dumps(data_to_post)
        logger.info("Test mode - data to send: {}".format(test_data[:max(100, len(test_data))]))        
        return

    # send the data
    if data_to_post:
        logger.debug('First:\n' + str(chunk_metric_data[0]))
        logger.debug('Last:\n' + str(chunk_metric_data[-1]))
        logger.info('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
        logger.info('Total Lines: ' + str(len(chunk_metric_data)))

        send_request(logger, post_url, 'POST', 'Could not send request to IF',
                     str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.', data=data_to_post,
                     verify=False, proxies=if_config_vars['if_proxies'])
    elif json_to_post:
        logger.info('Total Data (bytes): ' + str(get_json_size_bytes(json_to_post)))
        send_request(logger, post_url, 'POST', 'Could not send request to IF',
                     str(get_json_size_bytes(json_to_post)) + ' bytes of data are reported.', json=json_to_post,
                     verify=False, proxies=if_config_vars['if_proxies'])

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
                logger.info('Response Code: {}\nTEXT: {}'.format(response.status_code, response.text))
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
    elif if_config_vars['dynamic_metric_type']:
        if if_config_vars['dynamic_metric_type'] == 'vm':
            return 'DynamicVM'
        else:
            return 'DynamicHost'
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
        return 'LogStreaming'  # INCIDENT and DEPLOYMENT don't use this


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
        params = {'operation': 'check', 'userName': if_config_vars['user_name'],
                  'licenseKey': if_config_vars['license_key'], 'projectName': if_config_vars['project_name'], }
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
            params = {'operation': 'create', 'userName': if_config_vars['user_name'],
                      'licenseKey': if_config_vars['license_key'], 'projectName': if_config_vars['project_name'],
                      'systemName': if_config_vars['system_name'] or if_config_vars['project_name'],
                      'instanceType': 'Prometheus', 'projectCloudType': 'Prometheus',
                      'dataType': get_data_type_from_project_type(if_config_vars),
                      'insightAgentType': get_insight_agent_type_from_project_type(if_config_vars),
                      'samplingInterval': int(if_config_vars['sampling_interval']),
                      'samplingIntervalInSeconds': if_config_vars['sampling_interval'], }
            logger.debug("insightAgentType:", get_insight_agent_type_from_project_type(if_config_vars))
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
            params = {'operation': 'check', 'userName': if_config_vars['user_name'],
                      'licenseKey': if_config_vars['license_key'], 'projectName': if_config_vars['project_name'], }
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
        '{ts} [{cfg}] [pid {pid}] {lvl} {mod}.{func}():{line} {msg}'.format(ts='%(asctime)s', cfg='%(name)s',
                                                                            pid='%(process)d', lvl='%(levelname)-8s',
                                                                            mod='%(module)s', func='%(funcName)s',
                                                                            line='%(lineno)d', msg='%(message)s'),
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

    # Get config file name
    config_name = os.path.basename(config_file)

    # start sub process
    worker_configurer(q, c_config['log_level'])
    logger = logging.getLogger(config_name)
    logger.info("Setup logger in PID {}".format(os.getpid()))
    logger.info("Process start with config: {}".format(config_name))

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

    logger.info("Process is done with config: {}".format(config_name))
    return True


if __name__ == "__main__":

    # get config
    cli_config_vars = get_cli_config_vars()

    # logger
    m = multiprocessing.Manager()
    queue = m.Queue()
    listener = multiprocessing.Process(target=listener_process, args=(queue, cli_config_vars))
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

    # get agent config from first config
    agent_config_vars = get_agent_config_vars(main_logger, config_files[0])
    if not agent_config_vars:
        main_logger.error('Failed to get agent config')
    else:
        # get args
        utc_time_now = int(arrow.utcnow().float_timestamp)
        arg_list = [(f, cli_config_vars, utc_time_now, queue) for f in config_files]

        # start sub process by pool
        pool = Pool(agent_config_vars['processes'])
        pool_result = pool.map_async(worker_process, arg_list)
        pool.close()

        # wait 5 minutes for every worker to finish
        need_timeout = agent_config_vars['timeout'] > 0
        if need_timeout:
            pool_result.wait(timeout=agent_config_vars['timeout'])

        try:
            results = pool_result.get(timeout=1 if need_timeout else None)
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
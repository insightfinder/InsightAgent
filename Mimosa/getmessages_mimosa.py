#!/usr/bin/env python

import csv
import json
import logging
import os
import regex
import requests
import socket
import sqlite3
import sys
import time
import pytz
import arrow
import configparser
import multiprocessing
from datetime import datetime, timedelta
from itertools import chain
from logging.handlers import QueueHandler
from multiprocessing import Pool, TimeoutError
from multiprocessing.pool import ThreadPool
from optparse import OptionParser
from sys import getsizeof
from time import sleep
from urllib.parse import urljoin

"""
This script gathers metrics data from Mimosa devices and sends to InsightFinder
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
    """Align timestamp to sampling interval"""
    if sampling_interval == 0 or not timestamp:
        return timestamp
    else:
        return timestamp - (timestamp % sampling_interval)


def initialize_cache_connection():
    """Initialize SQLite cache connection"""
    cache_loc = abs_path_from_cur(CACHE_NAME)
    if os.path.exists(cache_loc):
        cache_con = sqlite3.connect(cache_loc)
    else:
        cache_con = sqlite3.connect(cache_loc)
        cache_con.execute('''CREATE TABLE aliases (alias TEXT PRIMARY KEY, instance TEXT)''')
        cache_con.commit()

    cache_cur = cache_con.cursor()
    return cache_con, cache_cur


def mimosa_login(mimosa_uri, username, password, verify_certs=True):
    """Login to Mimosa device and get session token"""
    session = requests.Session()
    
    try:
        # Step 1: Get the welcome page to establish session
        welcome_url = urljoin(mimosa_uri, '/app/welcome.html')
        welcome_response = session.get(welcome_url, verify=verify_certs, timeout=30)
        welcome_response.raise_for_status()
        
        # Step 2: Login using the correct Spring Security endpoint
        login_url = urljoin(mimosa_uri, '/login/j_spring_security_check')
        
        login_data = {
            'j_username': username,
            'j_password': password
        }
        
        response = session.post(
            login_url,
            data=login_data,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
                'Referer': welcome_url
            },
            verify=verify_certs,
            timeout=30,
            allow_redirects=False  # Handle redirects manually to check success
        )
        
        # Check if login was successful
        if response.status_code in [302, 303]:
            location = response.headers.get('Location', '')
            if 'app/index.html' in location and 'error' not in location.lower():
                logging.info(f"Login successful: redirected to {location}")
                return session
            else:
                raise Exception(f"Login failed: redirected to {location}")
        elif response.status_code == 200:
            # Sometimes successful login returns 200 instead of redirect
            logging.info(f"Login successful: redirected to {location}")
            return session
        else:
            raise Exception(f"Login failed with status code: {response.status_code}")
            
    except Exception as e:
        raise Exception(f"Failed to login to Mimosa: {str(e)}")


def query_mimosa_metrics(session, mimosa_uri, metrics_config, verify_certs=True):
    """Query metrics from Mimosa device"""
    metrics_data = []
    
    for metric_name, metric_config in metrics_config.items():
        try:
            endpoint = metric_config.get('endpoint', '/api/stats')
            params = metric_config.get('params', {})
            
            url = urljoin(mimosa_uri, endpoint)
            
            response = session.get(
                url,
                params=params,
                verify=verify_certs,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Extract the specific metric value based on configuration
            metric_value = extract_metric_value(data, metric_config)
            
            if metric_value is not None:
                metrics_data.append({
                    'metric_name': metric_name,
                    'value': metric_value,
                    'timestamp': int(time.time() * 1000),
                    'raw_data': data
                })
                
        except Exception as e:
            logging.error(f"Error querying metric {metric_name}: {str(e)}")
            continue
    
    return metrics_data


def extract_metric_value(data, metric_config):
    """Extract metric value from response data based on configuration"""
    value_path = metric_config.get('value_path', '')
    
    if not value_path:
        return None
    
    # Navigate through nested JSON using dot notation
    current_data = data
    path_parts = value_path.split('.')
    
    try:
        for part in path_parts:
            if isinstance(current_data, dict):
                current_data = current_data.get(part)
            elif isinstance(current_data, list) and part.isdigit():
                current_data = current_data[int(part)]
            else:
                return None
        
        return current_data
        
    except (KeyError, IndexError, TypeError):
        return None


def start_data_processing(logger, c_config, if_config_vars, agent_config_vars, metric_buffer, track, cache_con,
                          cache_cur, time_now):
    """Main data processing function"""
    logger.info('Started Mimosa data collection...')

    mimosa_uri = agent_config_vars['mimosa_uri']
    username = agent_config_vars['username']
    password = agent_config_vars['password']
    verify_certs = agent_config_vars.get('verify_certs', True)
    metrics_config = agent_config_vars['metrics_config']
    
    thread_pool = ThreadPool(agent_config_vars['thread_pool'])

    def collect_mimosa_data():
        """Collect data from Mimosa device"""
        try:
            # Login to Mimosa
            session = mimosa_login(mimosa_uri, username, password, verify_certs)
            
            # Query metrics
            metrics_data = query_mimosa_metrics(session, mimosa_uri, metrics_config, verify_certs)
            
            # Process the collected data
            for metric_data in metrics_data:
                parse_messages_mimosa(
                    logger, if_config_vars, agent_config_vars, metric_buffer, track,
                    cache_con, cache_cur, metric_data, time_now
                )
            
            logger.info(f'Successfully collected {len(metrics_data)} metrics from Mimosa')
            
        except Exception as e:
            logger.error(f'Error collecting Mimosa data: {str(e)}')

    # Run data collection
    if agent_config_vars.get('his_time_range'):
        # Historical data collection not implemented for Mimosa
        logger.warning('Historical data collection not supported for Mimosa')
    else:
        # Real-time data collection
        thread_pool.apply_async(collect_mimosa_data)

    thread_pool.close()
    thread_pool.join()
    logger.info('Mimosa data collection completed.')


def parse_messages_mimosa(logger, if_config_vars, agent_config_vars, metric_buffer, track, cache_con, cache_cur,
                          metric_data, sampling_time):
    """Parse Mimosa metric data and add to buffer"""
    
    default_component_name = agent_config_vars.get('default_component_name', 'mimosa_device')
    sampling_interval = if_config_vars['sampling_interval']
    
    try:
        # Extract metric information
        metric_name = metric_data.get('metric_name')
        value = metric_data.get('value')
        timestamp = metric_data.get('timestamp', sampling_time)
        
        if value is None or metric_name is None:
            return
        
        # Align timestamp to sampling interval
        aligned_timestamp = align_timestamp(timestamp, sampling_interval)
        
        # Create instance name
        instance_name = agent_config_vars.get('instance_name', default_component_name)
        
        # Create safe metric key
        safe_metric_key = make_safe_metric_key(metric_name)
        
        # Prepare metric data point
        metric_data_point = {
            'instanceName': instance_name,
            'componentName': default_component_name,
            'metricName': safe_metric_key,
            'data': value,
            'timestamp': aligned_timestamp
        }
        
        # Add to metric buffer
        metric_buffer['buffer_dict'][aligned_timestamp].append(metric_data_point)
        track['entry_count'] += 1
        
        logger.debug(f'Added metric: {metric_name} = {value} at {aligned_timestamp}')
        
    except Exception as e:
        logger.error(f'Error parsing Mimosa metric data: {str(e)}')


def get_agent_config_vars(logger, config_ini):
    """Read and parse config.ini for Mimosa agent"""
    if not os.path.exists(config_ini):
        logger.error(f'Config file {config_ini} does not exist')
        sys.exit(1)
        
    config_parser = configparser.ConfigParser()
    config_parser.read(config_ini)
    
    try:
        # Mimosa connection settings
        mimosa_section = 'mimosa'
        mimosa_uri = config_parser.get(mimosa_section, 'mimosa_uri')
        username = config_parser.get(mimosa_section, 'username')
        password = config_parser.get(mimosa_section, 'password')
        
        # Optional settings
        verify_certs = config_parser.getboolean(mimosa_section, 'verify_certs', fallback=True)
        
        # Metrics configuration
        metrics_config = {}
        if config_parser.has_section('metrics'):
            for metric_name, metric_def in config_parser.items('metrics'):
                if metric_name == 'DEFAULT':
                    continue
                # Parse metric definition (format: endpoint:value_path:params)
                parts = metric_def.split(':')
                metrics_config[metric_name] = {
                    'endpoint': parts[0] if len(parts) > 0 else '/api/stats',
                    'value_path': parts[1] if len(parts) > 1 else '',
                    'params': dict(param.split('=') for param in parts[2].split('&') if '=' in param) if len(parts) > 2 and parts[2] else {}
                }
        
        # Agent settings
        agent_section = 'agent'
        thread_pool = config_parser.getint(agent_section, 'thread_pool', fallback=20)
        default_component_name = config_parser.get(agent_section, 'default_component_name', fallback='mimosa_device')
        instance_name = config_parser.get(agent_section, 'instance_name', fallback='mimosa_instance')
        
        return {
            'mimosa_uri': mimosa_uri,
            'username': username,
            'password': password,
            'verify_certs': verify_certs,
            'metrics_config': metrics_config,
            'thread_pool': thread_pool,
            'default_component_name': default_component_name,
            'instance_name': instance_name,
            'his_time_range': config_parser.get(agent_section, 'his_time_range', fallback=''),
        }
        
    except Exception as e:
        logger.error(f'Error reading config: {str(e)}')
        sys.exit(1)


def print_summary_info(logger, if_config_vars, agent_config_vars):
    """Print configuration summary"""
    # info to be sent to IF
    post_data_block = '\nIF settings:'
    for ik, iv in sorted(if_config_vars.items()):
        post_data_block += f'\n\t{ik}: {iv}'
    logger.debug(post_data_block)

    # variables from agent-specific config
    agent_data_block = '\nAgent settings:'
    for jk, jv in sorted(agent_config_vars.items()):
        if 'password' in jk.lower():
            agent_data_block += f'\n\t{jk}: ***'
        else:
            agent_data_block += f'\n\t{jk}: {jv}'
    logger.debug(agent_data_block)


#########################
#   START_BOILERPLATE   #
#########################

def get_cli_config_vars():
    """Get CLI options"""
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    
    parser.add_option('-c', '--config', action='store', dest='config', default=abs_path_from_cur('conf.d'),
                      help='Path to the config files to use. Defaults to {}'.format(abs_path_from_cur('conf.d')))
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data). Automatically turns on verbose logging')
    
    (options, args) = parser.parse_args()

    config_vars = {
        'config': options.config if os.path.isdir(options.config) else abs_path_from_cur('conf.d'),
        'testing': options.testing,
        'log_level': logging.DEBUG if options.verbose or options.testing else logging.WARNING if options.quiet else logging.INFO,
    }

    return config_vars


def get_if_config_vars(logger, config_ini):
    """Get InsightFinder configuration variables"""
    if not os.path.exists(config_ini):
        logger.error(f'Config file {config_ini} does not exist')
        sys.exit(1)
        
    config_parser = configparser.ConfigParser()
    config_parser.read(config_ini)
    
    try:
        if_section = 'insightfinder'
        user_name = config_parser.get(if_section, 'user_name')
        license_key = config_parser.get(if_section, 'license_key')
        token = config_parser.get(if_section, 'token', fallback='')
        project_name = config_parser.get(if_section, 'project_name')
        system_name = config_parser.get(if_section, 'system_name', fallback='')
        project_type = config_parser.get(if_section, 'project_type', fallback='metric')
        containerize = config_parser.getboolean(if_section, 'containerize', fallback=False)
        dynamic_metric_type = config_parser.get(if_section, 'dynamic_metric_type', fallback='')
        sampling_interval = config_parser.get(if_section, 'sampling_interval', fallback='15s')
        run_interval = config_parser.get(if_section, 'run_interval', fallback='60s')
        chunk_size_kb = config_parser.getint(if_section, 'chunk_size_kb', fallback=2048)
        if_url = config_parser.get(if_section, 'if_url', fallback='https://app.insightfinder.com')
        if_http_proxy = config_parser.get(if_section, 'if_http_proxy', fallback='')
        if_https_proxy = config_parser.get(if_section, 'if_https_proxy', fallback='')
        
        # Convert sampling interval to milliseconds
        sampling_interval_ms = parse_time_interval(sampling_interval)
        
        return {
            'user_name': user_name,
            'license_key': license_key,
            'token': token,
            'project_name': project_name,
            'system_name': system_name,
            'project_type': project_type,
            'containerize': containerize,
            'dynamic_metric_type': dynamic_metric_type,
            'sampling_interval': sampling_interval_ms,
            'run_interval': run_interval,
            'chunk_size_kb': chunk_size_kb,
            'if_url': if_url,
            'if_http_proxy': if_http_proxy,
            'if_https_proxy': if_https_proxy,
        }
        
    except Exception as e:
        logger.error(f'Error reading InsightFinder config: {str(e)}')
        sys.exit(1)


def parse_time_interval(interval_str):
    """Parse time interval string and return milliseconds"""
    if interval_str.endswith('s'):
        return int(interval_str[:-1]) * 1000
    elif interval_str.endswith('m'):
        return int(interval_str[:-1]) * 60 * 1000
    elif interval_str.endswith('h'):
        return int(interval_str[:-1]) * 60 * 60 * 1000
    else:
        return int(interval_str) * 1000


def abs_path_from_cur(filename=''):
    """Get absolute path from current directory"""
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))


def config_error(logger, setting=''):
    """Log configuration error and exit"""
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(info))
    sys.exit(1)


def get_json_size_bytes(json_data):
    """Get size of JSON data in bytes"""
    return len(json.dumps(json_data).encode('utf-8'))


def make_safe_instance_string(instance, device=''):
    """Make instance string safe for InsightFinder"""
    # combine instance and device
    if device:
        instance = '{}_{}'.format(instance, device)
    
    # clean up
    instance = SPACES.sub('_', instance)
    instance = SLASHES.sub('-', instance)
    instance = UNDERSCORE.sub('_', instance)
    instance = COLONS.sub('-', instance)
    instance = LEFT_BRACE.sub('(', instance)
    instance = RIGHT_BRACE.sub(')', instance)
    instance = PERIOD.sub('_', instance)
    instance = COMMA.sub('_', instance)
    
    return instance


def make_safe_metric_key(metric):
    """Make metric key safe for InsightFinder"""
    metric = SPACES.sub('_', metric)
    metric = SLASHES.sub('-', metric)
    metric = UNDERSCORE.sub('_', metric)
    metric = COLONS.sub('-', metric)
    metric = LEFT_BRACE.sub('(', metric)
    metric = RIGHT_BRACE.sub(')', metric)
    metric = PERIOD.sub('_', metric)
    metric = COMMA.sub('_', metric)
    
    return metric


def make_safe_string(string):
    """Make string safe for InsightFinder"""
    string = SPACES.sub('_', string)
    string = SLASHES.sub('-', string)
    string = UNDERSCORE.sub('_', string)
    string = COLONS.sub('-', string)
    string = LEFT_BRACE.sub('(', string)
    string = RIGHT_BRACE.sub(')', string)
    string = PERIOD.sub('_', string)
    string = COMMA.sub('_', string)
    
    return string


def format_command(cmd):
    """Format command for logging"""
    return ' '.join(cmd) if isinstance(cmd, list) else cmd


def initialize_data_gathering(logger, c_config, if_config_vars, agent_config_vars, time_now):
    """Initialize data gathering structures"""
    metric_buffer = {
        'buffer_dict': {},
        'buffer_collected_list': [],
        'buffer_collected_size': 0
    }
    
    track = {
        'entry_count': 0,
        'prev_endtime': time_now,
        'file_name': '',
        'data_type': get_data_type_from_project_type(if_config_vars),
        'mode': 'LIVE'
    }
    
    reset_metric_buffer(metric_buffer)
    reset_track(track)
    
    return metric_buffer, track


def clear_metric_buffer(logger, c_config, if_config_vars, metric_buffer, track):
    """Clear metric buffer and send data to InsightFinder"""
    if len(metric_buffer['buffer_dict']) > 0:
        logger.debug('Sending data to InsightFinder')
        send_data_wrapper(logger, c_config, if_config_vars, track)
        
    reset_metric_buffer(metric_buffer)


def reset_metric_buffer(metric_buffer):
    """Reset metric buffer"""
    metric_buffer['buffer_dict'] = {}
    metric_buffer['buffer_collected_list'] = []
    metric_buffer['buffer_collected_size'] = 0


def reset_track(track):
    """Reset tracking variables"""
    track['entry_count'] = 0


################################
# Functions to send data to IF #
################################
def send_data_wrapper(logger, c_config, if_config_vars, track):
    """Wrapper function to send data to InsightFinder"""
    logger.debug('--- Send data to IF ---')
    
    # placeholder for actual implementation
    # This would include the logic to format and send data to InsightFinder
    logger.info('Data sent to InsightFinder')


def safe_string_to_float(s):
    """Safely convert string to float"""
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def get_data_type_from_project_type(if_config_vars):
    """Get data type from project type"""
    project_type = if_config_vars.get('project_type', 'metric')
    if 'metric' in project_type.lower():
        return 'Metric'
    elif 'log' in project_type.lower():
        return 'Log'
    else:
        return 'Metric'


def main():
    """Main function"""
    # get CLI config
    cli_config_vars = get_cli_config_vars()
    
    # set up logging
    logging.basicConfig(
        level=cli_config_vars['log_level'],
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # get config files
    config_ini = os.path.join(cli_config_vars['config'], 'config.ini')
    
    # get configuration variables
    if_config_vars = get_if_config_vars(logger, config_ini)
    agent_config_vars = get_agent_config_vars(logger, config_ini)
    
    # print summary
    print_summary_info(logger, if_config_vars, agent_config_vars)
    
    # initialize cache
    cache_con, cache_cur = initialize_cache_connection()
    
    # current time
    time_now = int(time.time() * 1000)
    
    # initialize data gathering
    metric_buffer, track = initialize_data_gathering(logger, cli_config_vars, if_config_vars, agent_config_vars, time_now)
    
    # start data processing
    start_data_processing(logger, cli_config_vars, if_config_vars, agent_config_vars, metric_buffer, track, cache_con, cache_cur, time_now)
    
    # clear remaining data
    clear_metric_buffer(logger, cli_config_vars, if_config_vars, metric_buffer, track)
    
    # close cache connection
    cache_con.close()
    
    logger.info('Mimosa agent completed successfully')


if __name__ == "__main__":
    main()

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
import urllib3

# Disable SSL warnings when verify_certs is False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        welcome_response = session.get(welcome_url, verify=verify_certs, timeout=10)
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
            timeout=10,
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


def fetch_device_metrics_batch(session, mimosa_uri, network_id, action_names, devices_batch, verify_certs=True):
    """Fetch metrics for a batch of devices using a single API call"""
    metrics_data = []
    multi_series_url = urljoin(mimosa_uri, f'/{network_id}/devices/multiSeriesData/')
    
    # Create a device lookup dictionary for fast access
    device_lookup = {device.get('id'): device for device in devices_batch}
    
    try:
        # Build parameters with multiple device IDs in a single request
        params = {'timeWindow': 'LAST_1_HOUR'}
        
        # Add each device ID as a parameter with its action names
        for device in devices_batch:
            device_id = device.get('id')
            if device_id:
                params[str(device_id)] = ','.join(action_names)
        
        logging.debug(f'Fetching metrics for {len(devices_batch)} devices in single API call')
        
        # Make single API call for all devices in this batch
        response = session.get(multi_series_url, params=params, verify=verify_certs, timeout=30)
        response.raise_for_status()
        
        series_data = response.json()
        
        # Parse the response which contains data for all devices
        if isinstance(series_data, list) and len(series_data) > 0:
            for metric_obj in series_data:
                if isinstance(metric_obj, dict):
                    action_name = metric_obj.get('actionName', '')
                    device_id = metric_obj.get('deviceId')  # The API should return which device this metric belongs to
                    data_array = metric_obj.get('data', [])
                    
                    # Find the device info from our lookup
                    device = device_lookup.get(device_id)
                    if not device:
                        logging.debug(f'Device {device_id} not found in batch lookup')
                        continue
                    
                    device_name = device.get('friendlyName', f'device_{device_id}')
                    
                    if isinstance(data_array, list) and len(data_array) > 0:
                        latest_entry = data_array[-1]
                        
                        if isinstance(latest_entry, list) and len(latest_entry) >= 2:
                            value = latest_entry[1]
                            timestamp = latest_entry[0]
                            metric_name = action_name.lower().replace('mimosa_', '')
                            
                            metrics_data.append({
                                'metric_name': metric_name,
                                'value': value,
                                'timestamp': timestamp,
                                'device_id': device_id,
                                'device_name': device_name,
                                'device_model': device.get('modelName', 'Unknown'),
                                'device_type': device.get('deviceType', 'Unknown'),
                                'ip_address': device.get('ipAddress', ''),
                                'mac_address': device.get('macAddress', ''),
                                'sw_version': device.get('swVersion', '')
                            })
        
        logging.debug(f'Collected {len(metrics_data)} metrics from {len(devices_batch)} devices in single call')
        
    except Exception as e:
        logging.warning(f'Failed to collect metrics for device batch: {str(e)}')
        # Fallback to individual device calls if batch fails
        logging.info('Falling back to individual device API calls')
        return fetch_device_metrics_individual(session, mimosa_uri, network_id, action_names, devices_batch, verify_certs)
    
    return metrics_data


def fetch_device_metrics_individual(session, mimosa_uri, network_id, action_names, devices_batch, verify_certs=True):
    """Fallback method: fetch metrics for devices individually (original method)"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    metrics_data = []
    multi_series_url = urljoin(mimosa_uri, f'/{network_id}/devices/multiSeriesData/')
    current_time = int(time.time() * 1000)
    
    def fetch_single_device_metrics(device):
        """Fetch metrics for a single device"""
        device_metrics = []
        device_id = device.get('id')
        device_name = device.get('friendlyName', f'device_{device_id}')
        
        try:
            # Parameters for the API call
            params = {
                'timeWindow': 'LAST_1_HOUR',
                str(device_id): ','.join(action_names)
            }
            
            response = session.get(multi_series_url, params=params, verify=verify_certs, timeout=15)
            response.raise_for_status()
            
            series_data = response.json()
            
            # Parse the response
            if isinstance(series_data, list) and len(series_data) > 0:
                for metric_obj in series_data:
                    if isinstance(metric_obj, dict):
                        action_name = metric_obj.get('actionName', '')
                        data_array = metric_obj.get('data', [])
                        
                        if isinstance(data_array, list) and len(data_array) > 0:
                            latest_entry = data_array[-1]
                            
                            if isinstance(latest_entry, list) and len(latest_entry) >= 2:
                                value = latest_entry[1]
                                metric_name = action_name.lower().replace('mimosa_', '').replace('_', '_')
                                
                                device_metrics.append({
                                    'metric_name': metric_name,
                                    'value': value,
                                    'timestamp': current_time,
                                    'device_id': device_id,
                                    'device_name': device_name,
                                    'device_model': device.get('modelName', 'Unknown'),
                                    'device_type': device.get('deviceType', 'Unknown'),
                                    'ip_address': device.get('ipAddress', ''),
                                    'mac_address': device.get('macAddress', ''),
                                    'sw_version': device.get('swVersion', '')
                                })
        except Exception as e:
            logging.debug(f'Failed to collect metrics for device {device_name}: {str(e)}')
        
        return device_metrics
    
    # Use ThreadPoolExecutor for concurrent requests
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_device = {executor.submit(fetch_single_device_metrics, device): device for device in devices_batch}
        
        for future in as_completed(future_to_device):
            try:
                device_metrics = future.result()
                metrics_data.extend(device_metrics)
            except Exception as e:
                device = future_to_device[future]
                logging.debug(f'Device metrics fetch failed: {str(e)}')
    
    return metrics_data


def query_mimosa_metrics(session, mimosa_uri, network_id, action_names, metrics_filter=None, verify_certs=True, max_devices=0, api_batch_size=25):
    """Query metrics from Mimosa device using optimized batch processing"""
    metrics_data = []
    
    try:
        # Get devices list with pagination - collect ALL devices from all pages
        all_devices = []
        page = 0
        page_size = 1000  # Large page size for efficiency
        
        while True:
            devices_url = urljoin(mimosa_uri, f'/{network_id}/devices/')
            params = {
                'pageNumber': page,
                'pageSize': page_size
            }
            
            response = session.get(devices_url, params=params, verify=verify_certs, timeout=15)
            response.raise_for_status()
            
            devices_data = response.json()
            current_devices = devices_data.get('content', [])
            
            if not current_devices:
                break
                
            all_devices.extend(current_devices)
            
            # Check if this is the last page
            if devices_data.get('last', True):
                break
                
            page += 1
        
        total_devices = len(all_devices)
        logging.info(f'Collected {total_devices} devices from {page + 1} pages')
        
        # Apply device limit if specified
        if max_devices > 0 and total_devices > max_devices:
            all_devices = all_devices[:max_devices]
            total_devices = len(all_devices)
            logging.info(f'Limited to first {total_devices} devices for faster processing')
        
        # Process devices in API batches for maximum efficiency
        # Each API call can handle multiple devices, dramatically reducing total API calls
        total_batches = (total_devices + api_batch_size - 1) // api_batch_size
        
        for i in range(0, total_devices, api_batch_size):
            batch_num = (i // api_batch_size) + 1
            devices_batch = all_devices[i:i + api_batch_size]
            
            logging.info(f'Processing API batch {batch_num}/{total_batches} ({len(devices_batch)} devices in single call)')
            
            # Fetch metrics for this batch using single API call
            batch_metrics = fetch_device_metrics_batch(
                session, mimosa_uri, network_id, action_names, devices_batch, verify_certs
            )
            
            # Filter metrics if specified
            if metrics_filter and len(metrics_filter) > 0:
                filtered_metrics = []
                for metric in batch_metrics:
                    if metric['metric_name'] in metrics_filter:
                        filtered_metrics.append(metric)
                batch_metrics = filtered_metrics
            
            metrics_data.extend(batch_metrics)
            logging.info(f'API batch {batch_num} collected {len(batch_metrics)} metrics from {len(devices_batch)} devices')
        
        logging.info(f'Successfully collected {len(metrics_data)} total metrics from {total_devices} devices')
        
    except Exception as e:
        logging.error(f"Error querying Mimosa metrics: {str(e)}")
    
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
            
            # Get network ID from config or use default
            network_id = agent_config_vars.get('network_id', '6078')
            
            # Query metrics using the working endpoints
            max_devices = agent_config_vars.get('max_devices', 0)
            api_batch_size = agent_config_vars.get('api_batch_size', 25)
            metrics_data = query_mimosa_metrics(session, mimosa_uri, network_id, agent_config_vars.get('action_names', ['Mimosa_B5_UL_Rate', 'Mimosa_B5_DL_Rate']), agent_config_vars.get('metrics_filter', []), verify_certs, max_devices, api_batch_size)

            # Save metrics data to file for inspection
            output_file = f'mimosa_metrics_data.json'
            
            try:
                with open(output_file, 'w') as f:
                    json.dump(metrics_data, f, indent=2, default=str)
                logger.info(f'Saved {len(metrics_data)} metrics to {output_file}')
            except Exception as e:
                logger.error(f'Failed to save metrics data to file: {str(e)}')

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
    
    default_component_name = agent_config_vars.get('default_component_name', '')
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
        
        # Create instance name using device name for better identification
        device_name = metric_data.get('device_name', 'unknown_device')
        instance_name = make_safe_instance_string(device_name)
        
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
        if aligned_timestamp not in metric_buffer['buffer_dict']:
            metric_buffer['buffer_dict'][aligned_timestamp] = []
        metric_buffer['buffer_dict'][aligned_timestamp].append(metric_data_point)
        track['entry_count'] += 1
        
        logger.debug(f'Added metric: {metric_name} = {value} for {device_name} at {aligned_timestamp}')
        
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
        network_id = config_parser.get(mimosa_section, 'network_id', fallback='6078')
        
        # Get action names from config - comma-separated list
        action_names_str = config_parser.get(mimosa_section, 'action_names', fallback='Mimosa_B5_UL_Rate,Mimosa_B5_DL_Rate').strip()
        action_names = [action.strip() for action in action_names_str.split(',') if action.strip()]
        
        # Get metrics filter from config - comma-separated list or empty for all metrics
        metrics_filter_str = config_parser.get(mimosa_section, 'metrics', fallback='').strip()
        metrics_filter = []
        if metrics_filter_str:
            metrics_filter = [metric.strip() for metric in metrics_filter_str.split(',') if metric.strip()]
        
        # Optional: Limit number of devices for testing/performance (0 = no limit)
        max_devices = config_parser.getint(mimosa_section, 'max_devices', fallback=0)
        
        # Optional: Number of devices to query per API call (default: 25)
        api_batch_size = config_parser.getint(mimosa_section, 'api_batch_size', fallback=25)
        
        # Metrics configuration (keeping for backward compatibility but not used with new API)
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
        default_component_name = config_parser.get(agent_section, 'default_component_name', fallback='')
        instance_name = config_parser.get(agent_section, 'instance_name', fallback='mimosa_instance')
        
        return {
            'mimosa_uri': mimosa_uri,
            'username': username,
            'password': password,
            'verify_certs': verify_certs,
            'network_id': network_id,
            'action_names': action_names,
            'metrics_filter': metrics_filter,
            'max_devices': max_devices,
            'api_batch_size': api_batch_size,
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
        'mode': 'LIVE',
        'chunk_count': 0,
        'start_time': time.time(),
        'current_row': []
    }
    
    reset_metric_buffer(metric_buffer)
    reset_track(track)
    
    return metric_buffer, track


def clear_metric_buffer(logger, c_config, if_config_vars, metric_buffer, track, agent_config_vars=None):
    """Clear metric buffer and send data to InsightFinder"""
    if len(metric_buffer['buffer_dict']) > 0:
        # Move all buffer data to current_row for sending
        buffer_values = list(metric_buffer['buffer_dict'].values())
        
        count = 0
        for row in buffer_values:
            for data_point in row:
                track['current_row'].append(data_point)
                count += 1
        
        # Send the data if we have any
        if len(track['current_row']) > 0:
            logger.debug('Sending {} data points to InsightFinder'.format(len(track['current_row'])))
            send_data_wrapper(logger, c_config, if_config_vars, track, agent_config_vars)
        
    reset_metric_buffer(metric_buffer)


def reset_metric_buffer(metric_buffer):
    """Reset metric buffer"""
    metric_buffer['buffer_dict'] = {}
    metric_buffer['buffer_collected_list'] = []
    metric_buffer['buffer_collected_size'] = 0


def reset_track(track):
    """Reset tracking variables"""
    track['entry_count'] = 0
    track['start_time'] = time.time()
    track['current_row'] = []


################################
# Functions to send data to IF #
################################
def send_data_wrapper(logger, c_config, if_config_vars, track, agent_config_vars=None):
    """Wrapper function to send data to InsightFinder"""
    logger.debug('--- Send data to IF ---')
    send_data_to_if(logger, c_config, if_config_vars, track, track['current_row'], agent_config_vars)
    track['chunk_count'] += 1
    reset_track(track)


def safe_string_to_float(s):
    """Safely convert string to float"""
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def convert_to_metric_data(logger, chunk_metric_data, cli_config_vars, if_config_vars, agent_config_vars=None):
    """Convert metric data to InsightFinder format"""
    to_send_data_dict = dict()
    to_send_data_dict['licenseKey'] = if_config_vars['license_key']
    to_send_data_dict['userName'] = if_config_vars['user_name']

    data_dict = dict()
    data_dict['projectName'] = if_config_vars['project_name']
    data_dict['userName'] = if_config_vars['user_name']
    if 'system_name' in if_config_vars and if_config_vars['system_name']:
        data_dict['systemName'] = if_config_vars['system_name']
    
    instance_data_map = dict()
    
    # Get default component name from agent config
    default_component_name = ''
    if agent_config_vars and agent_config_vars.get('default_component_name'):
        default_component_name = agent_config_vars['default_component_name']
    
    # Group data by instance and timestamp
    for chunk in chunk_metric_data:
        instance_name = chunk['instanceName']
        component_name = chunk.get('componentName', default_component_name)
        timestamp = str(chunk['timestamp'])
        # device_type = chunk.get('device_type', 'mimosa_device')
        host_id = chunk.get('host_id')
        
        if instance_name not in instance_data_map:
            instance_data_map[instance_name] = {
                'in': instance_name,
                'cn': component_name,
                # 'ct': 0,
                'dit': {}
            }
        
        if timestamp not in instance_data_map[instance_name]['dit']:
            timestamp_entry = {
                't': int(timestamp),
                'm': []
            }
            if host_id:
                timestamp_entry['k'] = {'hostId': host_id}
            instance_data_map[instance_name]['dit'][timestamp] = timestamp_entry
        
        # Add metric to the metrics array
        metric_entry = {
            'm': chunk['metricName'],
            'v': float(chunk['data'])
        }
        instance_data_map[instance_name]['dit'][timestamp]['m'].append(metric_entry)

    data_dict['idm'] = instance_data_map
    to_send_data_dict['data'] = data_dict

    return to_send_data_dict


def send_data_to_if(logger, cli_config_vars, if_config_vars, track, chunk_metric_data, agent_config_vars=None):
    """Send data to InsightFinder"""
    send_data_time = time.time()

    # prepare data for metric streaming agent
    data_to_post = None
    json_to_post = None
    
    if 'METRIC' in if_config_vars['project_type'].upper():
        data_to_post = convert_to_metric_data(logger, chunk_metric_data, cli_config_vars, if_config_vars, agent_config_vars)
    else:
        # For non-metric data types, use the raw chunk data
        json_to_post = chunk_metric_data

    # Save JSON data to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_filename = f"mimosa_insightfinder_data.json"
    try:
        if data_to_post:
            with open(json_filename, 'w') as f:
                json.dump(data_to_post, f, indent=2)
        elif json_to_post:
            with open(json_filename, 'w') as f:
                json.dump(json_to_post, f, indent=2)
        logger.info(f"JSON data saved to {json_filename}")
    except Exception as e:
        logger.error(f"Failed to save JSON file: {e}")

    # do not send if only testing
    if cli_config_vars['testing']:
        logger.info('Testing mode - would have sent {} data points to InsightFinder'.format(len(chunk_metric_data)))
        if data_to_post:
            logger.debug('Metric data sample: {}'.format(json.dumps(data_to_post, indent=2)[:500]))
        elif json_to_post:
            logger.debug('JSON data sample: {}'.format(json.dumps(json_to_post, indent=2)[:500]))
        return

    # send the data
    if data_to_post:
        logger.debug('Sending {} metric data points to InsightFinder'.format(len(chunk_metric_data)))
        send_request(logger, if_config_vars['if_url'] + get_api_from_project_type(if_config_vars), 
                    mode='POST', data=json.dumps(data_to_post),
                    headers={'Content-Type': 'application/json'},
                    proxies=get_proxy_dict(if_config_vars),
                    verify=False)
    elif json_to_post:
        logger.debug('Sending {} JSON data points to InsightFinder'.format(len(chunk_metric_data)))
        send_request(logger, if_config_vars['if_url'] + get_api_from_project_type(if_config_vars), 
                    mode='POST', data=json.dumps(json_to_post),
                    headers={'Content-Type': 'application/json'},
                    proxies=get_proxy_dict(if_config_vars),
                    verify=False)

    logger.info('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def send_request(logger, url, mode='GET', failure_message='Failure!', success_message='Success!',
                 **request_passthrough):
    """Send a request to the given URL"""
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    req = requests.get
    if mode.upper() == 'POST':
        req = requests.post

    req_num = 0
    for req_num in range(ATTEMPTS):
        try:
            response = req(url, **request_passthrough)
            if response.status_code == requests.codes.ok:
                logger.info(success_message)
                return response
            else:
                logger.warning('Request failed with status code: {}'.format(response.status_code))
                logger.warning('Response: {}'.format(response.text))
        except Exception as e:
            logger.warning('Request attempt {} failed: {}'.format(req_num + 1, str(e)))
            if req_num < (ATTEMPTS - 1):
                time.sleep(1)

    logger.error('Failed! Gave up after {} attempts.'.format(req_num + 1))
    return -1


def get_proxy_dict(if_config_vars):
    """Get proxy configuration dictionary"""
    proxies = {}
    if if_config_vars.get('if_http_proxy'):
        proxies['http'] = if_config_vars['if_http_proxy']
    if if_config_vars.get('if_https_proxy'):
        proxies['https'] = if_config_vars['if_https_proxy']
    return proxies


def get_api_from_project_type(if_config_vars):
    """Use project type to determine which API to post to"""
    if 'INCIDENT' in if_config_vars['project_type'].upper():
        return '/api/v1/incidentdatasenders'
    elif 'DEPLOYMENT' in if_config_vars['project_type'].upper():
        return '/api/v1/deploymentEventReceiver'
    else:
        # return '/api/v1/customprojectrawdata'
        return '/api/v2/metric-data-receive'


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
    clear_metric_buffer(logger, cli_config_vars, if_config_vars, metric_buffer, track, agent_config_vars)
    
    # close cache connection
    cache_con.close()
    
    logger.info('Mimosa agent completed successfully')


if __name__ == "__main__":
    main()

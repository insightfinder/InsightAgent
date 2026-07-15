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
from urllib.parse import quote, urljoin
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
    if sampling_interval == 0 or not timestamp:
        return timestamp
    else:
        return int(timestamp / (sampling_interval * 1000)) * sampling_interval * 1000


def save_failed_devices_log(failed_devices):
    """Save failed device metrics to JSON file for review"""
    if not failed_devices:
        return
    
    filename = 'mimosa_failed_devices.json'
    
    try:
        # Load existing failures if file exists
        existing_failures = []
        
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    existing_data = json.load(f)
                    if isinstance(existing_data, dict) and 'detailed_failures' in existing_data:
                        existing_failures = existing_data['detailed_failures']
                    elif isinstance(existing_data, list):
                        existing_failures = existing_data
            except:
                existing_failures = []
        
        # Combine existing and new failures
        all_failures = existing_failures + failed_devices
        
        # Create summary statistics
        current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        failure_summary = {
            'last_updated': current_timestamp,
            'total_failed_requests': len(all_failures),
            'unique_devices': len(set(f['device_id'] for f in all_failures)),
            'unique_metrics': len(set(f['metric_name'] for f in all_failures)),
            'failure_reasons': {},
            'failed_devices_by_name': {},
            'failed_metrics_by_type': {}
        }
        
        # Analyze failure patterns
        for failure in all_failures:
            reason = failure['failure_reason']
            device_name = failure['device_name']
            metric_name = failure['metric_name']
            
            # Count failure reasons
            failure_summary['failure_reasons'][reason] = failure_summary['failure_reasons'].get(reason, 0) + 1
            
            # Count failures by device
            if device_name not in failure_summary['failed_devices_by_name']:
                failure_summary['failed_devices_by_name'][device_name] = {
                    'device_id': failure['device_id'],
                    'failure_count': 0,
                    'failed_metrics': []
                }
            failure_summary['failed_devices_by_name'][device_name]['failure_count'] += 1
            if metric_name not in failure_summary['failed_devices_by_name'][device_name]['failed_metrics']:
                failure_summary['failed_devices_by_name'][device_name]['failed_metrics'].append(metric_name)
            
            # Count failures by metric type
            failure_summary['failed_metrics_by_type'][metric_name] = failure_summary['failed_metrics_by_type'].get(metric_name, 0) + 1
        
        # Save complete failure log to single file
        failure_log = {
            'summary': failure_summary,
            'detailed_failures': all_failures
        }
        
        # Save to single consolidated file
        with open(filename, 'w') as f:
            json.dump(failure_log, f, indent=2, default=str)
        
        logging.info(f'Updated failure log with {len(failed_devices)} new failures in {filename}')
        logging.info(f'Total tracked failures: {len(all_failures)} ({failure_summary["unique_devices"]} devices, {failure_summary["unique_metrics"]} metrics)')
        
    except Exception as e:
        logging.error(f'Failed to save device failure log: {str(e)}')


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


#########################
#    DEVICE LOOKUP      #
#########################

DEVICE_LOOKUP_PATH = 'devicelookup.json'
DEVICE_LOOKUP_REFRESH_HOURS = 24
# module-level cache: mac(lower) -> device info dict
DEVICE_LOOKUP = {}


def load_device_lookup(logger):
    """Load devicelookup.json from disk into DEVICE_LOOKUP; returns entry count."""
    global DEVICE_LOOKUP
    path = abs_path_from_cur(DEVICE_LOOKUP_PATH)
    if not os.path.exists(path):
        DEVICE_LOOKUP = {}
        return 0
    try:
        with open(path) as f:
            DEVICE_LOOKUP = json.load(f)
        logger.info(f'DeviceLookup: loaded {len(DEVICE_LOOKUP)} entries from disk')
        return len(DEVICE_LOOKUP)
    except Exception as e:
        logger.warning(f'DeviceLookup: failed to load {path}: {e}')
        DEVICE_LOOKUP = {}
        return 0


def device_lookup_is_stale():
    """Return True if devicelookup.json is missing or older than refresh interval."""
    path = abs_path_from_cur(DEVICE_LOOKUP_PATH)
    if not os.path.exists(path):
        return True
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    return age_hours >= DEVICE_LOOKUP_REFRESH_HOURS


def _lookup_device_by_identifier(identifier, api_key, base_url, timeout, max_retry):
    """Query the Asset Registry API for a single identifier (MAC, IP, name,
    serial, object key, or Jira ID — the endpoint accepts any of them).
    Returns the device dict on match, None on 404/error."""
    if not identifier:
        return None
    url = f'{base_url}/devices/{quote(str(identifier), safe="")}'
    headers = {'X-API-Key': api_key, 'Accept': 'application/json'}
    for attempt in range(max_retry):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                continue
            return resp.json()
        except Exception:
            if attempt < max_retry - 1:
                time.sleep(0.5)
    return None


def _lookup_device(identifiers, api_key, base_url, timeout, max_retry):
    """Try each identifier in priority order; first match wins.
    Mirrors the mimosa agent's MAC -> serial -> name fallback chain."""
    for ident in identifiers:
        raw = _lookup_device_by_identifier(ident, api_key, base_url, timeout, max_retry)
        if raw:
            return raw
    return None


def _extract_device_info(raw):
    """Parse device inventory API response into the fields we need."""
    meta = raw.get('meta') or {}
    model = raw.get('model') or {}
    manufacturer = model.get('manufacturer') or meta.get('manufacturer') or 'NONE'
    device_class = model.get('device_class') or 'NONE'
    return {
        'mac_address': raw.get('mac_address') or '',
        'serial_number': raw.get('serial_number') or '',
        'object_key': raw.get('object_key') or '',
        'name': raw.get('name') or '',
        'venue': meta.get('venue') or '',
        'component_name': f'{manufacturer}-{device_class}',
        'ip_address': raw.get('ip_address') or '',
    }


def normalize_mac_identifier(mac):
    """Mirror the mimosa/zabbix agents' MAC normalization: replace ':'
    with '-', trim leading/trailing '-', trim whitespace, and require at
    least one alphanumeric character. No case conversion — the original
    casing is preserved so the same physical device produces the same
    instance identifier across agents."""
    if not mac:
        return ''
    converted = mac.strip().replace(':', '-').strip('-').strip()
    if not converted or not any(c.isalnum() for c in converted):
        return ''
    return converted


def normalize_serial_identifier(serial):
    """Mirror the mimosa/zabbix agents' serial normalization: trim
    whitespace and require at least one alphanumeric character."""
    if not serial:
        return ''
    serial = serial.strip()
    if not serial or not any(c.isalnum() for c in serial):
        return ''
    return serial


def _inventory_api_is_healthy(logger, base_url, timeout):
    """Quick health check against the device inventory API before a bulk refresh."""
    try:
        resp = requests.get(f'{base_url}/health', timeout=timeout)
        if resp.status_code == 200:
            return True
        logger.warning(f'DeviceLookup: health check returned HTTP {resp.status_code}')
    except Exception as e:
        logger.warning(f'DeviceLookup: health check failed: {e}')
    return False


def refresh_device_lookup(logger, devices, agent_config_vars):
    """Query the Asset Registry API for all devices (20 concurrent) and save to disk.
    Each device is looked up by MAC -> serial -> name (first match wins); the result is
    cached under the device's lowercased MAC so parse_messages_mimosa can retrieve it.
    If the API is unreachable, keeps the existing lookup (devices fall back to UNKNOWN zone etc.)."""
    global DEVICE_LOOKUP
    api_key = agent_config_vars.get('device_inventory_api_key', '')
    base_url = agent_config_vars.get('device_inventory_base_url', '')
    if not api_key or not base_url:
        logger.warning('DeviceLookup: device_inventory_api_key/base_url not configured, skipping refresh')
        return
    timeout = agent_config_vars.get('device_inventory_timeout_sec', 5)
    max_retry = agent_config_vars.get('device_inventory_max_retry', 2)

    # fast-fail: skip the whole refresh if the API is down, keep existing cache
    if not _inventory_api_is_healthy(logger, base_url, timeout):
        logger.warning('DeviceLookup: inventory API unreachable, keeping existing lookup '
                       f'({len(DEVICE_LOOKUP)} entries); unmatched devices will use fallback values')
        return

    # dedup devices by MAC; each entry keeps its identifiers for the fallback chain
    uniq = {}
    for d in devices:
        mac = (d.get('mac_address') or '').strip()
        if not mac:
            continue
        uniq[mac.lower()] = {
            'mac': mac.lower(),
            'ip': (d.get('ip_address') or '').strip(),
            'name': (d.get('device_name') or '').strip(),
            'serial': (d.get('serial_number') or '').strip(),
        }
    device_list = list(uniq.values())
    logger.info(f'DeviceLookup: refreshing {len(device_list)} devices (concurrency=20)...')
    start_time = time.time()

    def _lookup_one(dev):
        # Priority chain mirrors the mimosa agent: MAC -> serial -> name
        raw = _lookup_device([dev['mac'], dev['serial'], dev['name']], api_key, base_url, timeout, max_retry)
        return dev['mac'], raw

    new_lookup = {}
    found = 0
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=20) as executor:
        for mac_key, raw in executor.map(_lookup_one, device_list):
            if raw:
                new_lookup[mac_key] = _extract_device_info(raw)
                found += 1

    elapsed = round(time.time() - start_time, 1)
    logger.info(f'DeviceLookup: done - {found} found, {len(device_list) - found} not found, elapsed={elapsed}s')

    # safety: if nothing was found but we had a non-empty cache, the API likely failed
    # mid-run — keep the old cache instead of wiping it
    if found == 0 and DEVICE_LOOKUP:
        logger.warning('DeviceLookup: refresh found 0 devices, keeping previous '
                       f'{len(DEVICE_LOOKUP)} entries')
        return

    # atomic write: tmp file + replace
    path = abs_path_from_cur(DEVICE_LOOKUP_PATH)
    tmp = path + '.tmp'
    try:
        with open(tmp, 'w') as f:
            json.dump(new_lookup, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning(f'DeviceLookup: failed to save to disk: {e}')

    DEVICE_LOOKUP = new_lookup


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


def fetch_device_metrics_batch(session, mimosa_uri, network_id, action_names, devices_batch, verify_certs=True, data_points_count=1):
    """Fetch metrics for a batch of devices using a single API call"""
    metrics_data = []
    failed_devices = []
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

        # Track which devices we got data for
        devices_with_data = set()
        
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
                        devices_with_data.add(device_id)
                        # Get the latest N data points based on data_points_count
                        num_points = min(data_points_count, len(data_array))
                        latest_entries = data_array[-num_points:]  # Get last N entries
                        
                        # Process each data point
                        for entry in latest_entries:
                            if isinstance(entry, list) and len(entry) >= 2:
                                value = entry[1]
                                timestamp = entry[0]
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
                                    'serial_number': device.get('serialNumber', ''),
                                    'sw_version': device.get('swVersion', '')
                                })
                    else:
                        # Track devices/metrics with no data
                        failed_devices.append({
                            'device_id': device_id,
                            'device_name': device_name,
                            'metric_name': action_name,
                            'failure_reason': 'No data returned for metric',
                            'timestamp': int(time.time() * 1000),
                            'device_model': device.get('modelName', 'Unknown'),
                            'device_type': device.get('deviceType', 'Unknown'),
                            'ip_address': device.get('ipAddress', ''),
                            'mac_address': device.get('macAddress', ''),
                            'sw_version': device.get('swVersion', '')
                        })
        
        # Track devices that had no data at all
        for device in devices_batch:
            device_id = device.get('id')
            if device_id not in devices_with_data:
                device_name = device.get('friendlyName', f'device_{device_id}')
                for action_name in action_names:
                    failed_devices.append({
                        'device_id': device_id,
                        'device_name': device_name,
                        'metric_name': action_name,
                        'failure_reason': 'No data returned for device',
                        'timestamp': int(time.time() * 1000),
                        'device_model': device.get('modelName', 'Unknown'),
                        'device_type': device.get('deviceType', 'Unknown'),
                        'ip_address': device.get('ipAddress', ''),
                        'mac_address': device.get('macAddress', ''),
                        'sw_version': device.get('swVersion', '')
                    })
        
        logging.debug(f'Collected {len(metrics_data)} metrics from {len(devices_batch)} devices in single call')
        if failed_devices:
            logging.debug(f'Found {len(failed_devices)} failed metric requests in batch')
        
    except Exception as e:
        # Track batch failure for all devices/metrics
        for device in devices_batch:
            device_id = device.get('id')
            device_name = device.get('friendlyName', f'device_{device_id}')
            for action_name in action_names:
                failed_devices.append({
                    'device_id': device_id,
                    'device_name': device_name,
                    'metric_name': action_name,
                    'failure_reason': f'Batch API call failed: {str(e)}',
                    'timestamp': int(time.time() * 1000),
                    'device_model': device.get('modelName', 'Unknown'),
                    'device_type': device.get('deviceType', 'Unknown'),
                    'ip_address': device.get('ipAddress', ''),
                    'mac_address': device.get('macAddress', ''),
                    'sw_version': device.get('swVersion', '')
                })
        
        logging.warning(f'Failed to collect metrics for device batch: {str(e)}')
        # Fallback to individual device calls if batch fails
        logging.info('Falling back to individual device API calls')
        individual_metrics, individual_failures = fetch_device_metrics_individual(session, mimosa_uri, network_id, action_names, devices_batch, verify_certs, data_points_count)
        
        # Save failures from both batch and individual attempts
        save_failed_devices_log(failed_devices + individual_failures)
        return individual_metrics
    
    # Save any failures from successful batch
    if failed_devices:
        save_failed_devices_log(failed_devices)
    
    return metrics_data


def fetch_device_metrics_individual(session, mimosa_uri, network_id, action_names, devices_batch, verify_certs=True, data_points_count=1):
    """Fallback method: fetch metrics for devices individually (original method)"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    metrics_data = []
    failed_devices = []
    multi_series_url = urljoin(mimosa_uri, f'/{network_id}/devices/multiSeriesData/')
    current_time = int(time.time() * 1000)
    
    def fetch_single_metric_for_device(device, action_name):
        """Fetch a single metric for a single device (ultimate fallback)"""
        device_metrics = []
        device_failures = []
        device_id = device.get('id')
        device_name = device.get('friendlyName', f'device_{device_id}')
        
        try:
            # Parameters for single metric API call
            params = {
                'timeWindow': 'LAST_1_HOUR',
                str(device_id): action_name
            }
            
            response = session.get(multi_series_url, params=params, verify=verify_certs, timeout=10)
            response.raise_for_status()
            
            series_data = response.json()
            
            # Parse the response for single metric
            if isinstance(series_data, list) and len(series_data) > 0:
                for metric_obj in series_data:
                    if isinstance(metric_obj, dict):
                        returned_action_name = metric_obj.get('actionName', '')
                        data_array = metric_obj.get('data', [])
                        
                        if returned_action_name == action_name and isinstance(data_array, list) and len(data_array) > 0:
                            # Get the latest N data points based on data_points_count
                            num_points = min(data_points_count, len(data_array))
                            latest_entries = data_array[-num_points:]  # Get last N entries
                            
                            # Process each data point
                            for entry in latest_entries:
                                if isinstance(entry, list) and len(entry) >= 2:
                                    value = entry[1]
                                    timestamp = entry[0]
                                    metric_name = action_name.lower().replace('mimosa_', '').replace('_', '_')
                                    
                                    device_metrics.append({
                                        'metric_name': metric_name,
                                        'value': value,
                                        'timestamp': timestamp,
                                        'device_id': device_id,
                                        'device_name': device_name,
                                        'device_model': device.get('modelName', 'Unknown'),
                                        'device_type': device.get('deviceType', 'Unknown'),
                                        'ip_address': device.get('ipAddress', ''),
                                        'mac_address': device.get('macAddress', ''),
                                        'serial_number': device.get('serialNumber', ''),
                                        'sw_version': device.get('swVersion', '')
                                    })
                            return device_metrics, device_failures
            
            # If we get here, no data was returned
            device_failures.append({
                'device_id': device_id,
                'device_name': device_name,
                'metric_name': action_name,
                'failure_reason': 'No data returned for single metric call',
                'timestamp': current_time,
                'device_model': device.get('modelName', 'Unknown'),
                'device_type': device.get('deviceType', 'Unknown'),
                'ip_address': device.get('ipAddress', ''),
                'mac_address': device.get('macAddress', ''),
                'sw_version': device.get('swVersion', '')
            })
                    
        except Exception as e:
            logging.debug(f'Failed to collect single metric {action_name} for device {device_name}: {str(e)}')
            device_failures.append({
                'device_id': device_id,
                'device_name': device_name,
                'metric_name': action_name,
                'failure_reason': f'Single metric API call failed: {str(e)}',
                'timestamp': current_time,
                'device_model': device.get('modelName', 'Unknown'),
                'device_type': device.get('deviceType', 'Unknown'),
                'ip_address': device.get('ipAddress', ''),
                'mac_address': device.get('macAddress', ''),
                'sw_version': device.get('swVersion', '')
            })
        
        return device_metrics, device_failures
    
    def fetch_single_device_metrics(device):
        """Fetch metrics for a single device"""
        device_metrics = []
        device_failures = []
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
            
            # Track which metrics we got data for
            metrics_with_data = set()
            
            # Parse the response
            if isinstance(series_data, list) and len(series_data) > 0:
                for metric_obj in series_data:
                    if isinstance(metric_obj, dict):
                        action_name = metric_obj.get('actionName', '')
                        data_array = metric_obj.get('data', [])
                        
                        if isinstance(data_array, list) and len(data_array) > 0:
                            metrics_with_data.add(action_name)
                            # Get the latest N data points based on data_points_count
                            num_points = min(data_points_count, len(data_array))
                            latest_entries = data_array[-num_points:]  # Get last N entries
                            
                            # Process each data point
                            for entry in latest_entries:
                                if isinstance(entry, list) and len(entry) >= 2:
                                    value = entry[1]
                                    timestamp = entry[0]
                                    metric_name = action_name.lower().replace('mimosa_', '').replace('_', '_')
                                    
                                    device_metrics.append({
                                        'metric_name': metric_name,
                                        'value': value,
                                        'timestamp': timestamp,
                                        'device_id': device_id,
                                        'device_name': device_name,
                                        'device_model': device.get('modelName', 'Unknown'),
                                        'device_type': device.get('deviceType', 'Unknown'),
                                        'ip_address': device.get('ipAddress', ''),
                                        'mac_address': device.get('macAddress', ''),
                                        'serial_number': device.get('serialNumber', ''),
                                        'sw_version': device.get('swVersion', '')
                                    })
                        else:
                            # Track metric with no data
                            device_failures.append({
                                'device_id': device_id,
                                'device_name': device_name,
                                'metric_name': action_name,
                                'failure_reason': 'No data returned for metric (individual call)',
                                'timestamp': current_time,
                                'device_model': device.get('modelName', 'Unknown'),
                                'device_type': device.get('deviceType', 'Unknown'),
                                'ip_address': device.get('ipAddress', ''),
                                'mac_address': device.get('macAddress', ''),
                                'sw_version': device.get('swVersion', '')
                            })
            
            # Check if we got any data at all - if not, try individual metric calls
            if len(device_metrics) == 0:
                logging.debug(f'No metrics collected for device {device_name}, trying individual metric calls')
                # Try each metric individually as ultimate fallback
                for action_name in action_names:
                    single_metrics, single_failures = fetch_single_metric_for_device(device, action_name)
                    device_metrics.extend(single_metrics)
                    device_failures.extend(single_failures)
                
                # If we got some metrics from individual calls, remove the bulk failure entries
                if len(device_metrics) > 0:
                    # Remove previous failure entries for metrics that we successfully collected individually
                    successful_metrics = set(m['metric_name'] for m in device_metrics)
                    device_failures = [f for f in device_failures if f['metric_name'].lower().replace('mimosa_', '').replace('_', '_') not in successful_metrics]
            else:
                # Track missing metrics only (we got some data from the bulk call)
                for action_name in action_names:
                    if action_name not in metrics_with_data:
                        device_failures.append({
                            'device_id': device_id,
                            'device_name': device_name,
                            'metric_name': action_name,
                            'failure_reason': 'Metric not returned by API (individual call)',
                            'timestamp': current_time,
                            'device_model': device.get('modelName', 'Unknown'),
                            'device_type': device.get('deviceType', 'Unknown'),
                            'ip_address': device.get('ipAddress', ''),
                            'mac_address': device.get('macAddress', ''),
                            'sw_version': device.get('swVersion', '')
                        })
                    
        except Exception as e:
            logging.debug(f'Failed to collect metrics for device {device_name}: {str(e)}')
            # Try individual metric calls as fallback when device call completely fails
            logging.debug(f'Trying individual metric calls for device {device_name} after bulk failure')
            try:
                for action_name in action_names:
                    single_metrics, single_failures = fetch_single_metric_for_device(device, action_name)
                    device_metrics.extend(single_metrics)
                    device_failures.extend(single_failures)
            except Exception as e2:
                logging.debug(f'Individual metric calls also failed for device {device_name}: {str(e2)}')
                # Track all metrics as failed for this device
                for action_name in action_names:
                    device_failures.append({
                        'device_id': device_id,
                        'device_name': device_name,
                        'metric_name': action_name,
                        'failure_reason': f'All API calls failed: {str(e)} / {str(e2)}',
                        'timestamp': current_time,
                        'device_model': device.get('modelName', 'Unknown'),
                        'device_type': device.get('deviceType', 'Unknown'),
                        'ip_address': device.get('ipAddress', ''),
                        'mac_address': device.get('macAddress', ''),
                        'sw_version': device.get('swVersion', '')
                    })
        
        return device_metrics, device_failures
    
    # Use ThreadPoolExecutor for concurrent requests
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_device = {executor.submit(fetch_single_device_metrics, device): device for device in devices_batch}
        
        for future in as_completed(future_to_device):
            try:
                device_metrics, device_failures = future.result()
                metrics_data.extend(device_metrics)
                failed_devices.extend(device_failures)
            except Exception as e:
                device = future_to_device[future]
                logging.debug(f'Device metrics fetch failed: {str(e)}')
                # Track all metrics as failed for this device
                device_id = device.get('id')
                device_name = device.get('friendlyName', f'device_{device_id}')
                for action_name in action_names:
                    failed_devices.append({
                        'device_id': device_id,
                        'device_name': device_name,
                        'metric_name': action_name,
                        'failure_reason': f'Future execution failed: {str(e)}',
                        'timestamp': current_time,
                        'device_model': device.get('modelName', 'Unknown'),
                        'device_type': device.get('deviceType', 'Unknown'),
                        'ip_address': device.get('ipAddress', ''),
                        'mac_address': device.get('macAddress', ''),
                        'sw_version': device.get('swVersion', '')
                    })
    
    # Save individual call failures
    if failed_devices:
        save_failed_devices_log(failed_devices)
        logging.debug(f'Individual calls: {len(failed_devices)} failed metric requests')
    
    return metrics_data, failed_devices


def query_mimosa_metrics(session, mimosa_uri, network_id, action_names, verify_certs=True, max_devices=0, api_batch_size=25, data_points_count=1):
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
                session, mimosa_uri, network_id, action_names, devices_batch, verify_certs, data_points_count
            )
            
            metrics_data.extend(batch_metrics)
            logging.info(f'API batch {batch_num} collected {len(batch_metrics)} metrics from {len(devices_batch)} devices')
        
        logging.info(f'Successfully collected {len(metrics_data)} total metrics from {total_devices} devices')
        
    except Exception as e:
        logging.error(f"Error querying Mimosa metrics: {str(e)}")
    
    return metrics_data

def start_data_processing(logger, c_config, if_config_vars, agent_config_vars, metric_buffer, track, cache_con,
                          cache_cur, time_now):
    """Main data processing function"""
    logger.info('Started Mimosa data collection...')

    mimosa_uri = agent_config_vars['mimosa_uri']
    username = agent_config_vars['username']
    password = agent_config_vars['password']
    verify_certs = agent_config_vars.get('verify_certs', True)
    
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
            data_points_count = agent_config_vars.get('data_points_count', 1)
            metrics_data = query_mimosa_metrics(session, mimosa_uri, network_id, agent_config_vars.get('action_names', ['Mimosa_B5_UL_Rate', 'Mimosa_B5_DL_Rate']), verify_certs, max_devices, api_batch_size, data_points_count)

            # Save metrics data to file for inspection
            output_file = f'mimosa_metrics_data.json'
            
            try:
                with open(output_file, 'w') as f:
                    json.dump(metrics_data, f, indent=2, default=str)
                logger.info(f'Saved {len(metrics_data)} metrics to {output_file}')
            except Exception as e:
                logger.error(f'Failed to save metrics data to file: {str(e)}')

            # Refresh device lookup (MAC -> IP -> name against Asset Registry) if stale, then load
            load_device_lookup(logger)
            if device_lookup_is_stale() or not DEVICE_LOOKUP:
                refresh_device_lookup(logger, metrics_data, agent_config_vars)

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
    
    # default_component_name is the fallback componentName when the device
    # inventory lookup misses (mirrors the mimosa/zabbix agents'
    # "AP-<Manufacturer>" fallback convention).
    default_component_name = agent_config_vars.get('default_component_name', 'AP-Mimosa')
    default_display_name = agent_config_vars.get('default_display_name', 'UNKNOWN')
    sampling_interval = if_config_vars['sampling_interval']

    try:
        # Extract metric information
        metric_name = metric_data.get('metric_name')
        value = metric_data.get('value')
        timestamp = metric_data.get('timestamp', sampling_time)
        ipAddress = metric_data.get('ip_address', '')
        device_name = metric_data.get('device_name', '')

        if value is None or metric_name is None:
            return

        # Align timestamp to sampling interval
        aligned_timestamp = align_timestamp(timestamp, sampling_interval)

        mac_address = metric_data.get('mac_address', '')
        dev_info = DEVICE_LOOKUP.get(mac_address.lower(), {}) if mac_address else {}

        # Instance name priority (matches the zabbix agent's device-inventory rules):
        # MAC(inventory) > serial(inventory) > object_key(inventory) > device_name (Mimosa's own).
        inv_mac = normalize_mac_identifier(dev_info.get('mac_address'))
        inv_serial = normalize_serial_identifier(dev_info.get('serial_number'))

        if inv_mac:
            instance_name = 'MAC ' + inv_mac
        elif inv_serial:
            instance_name = 'SERIAL ' + inv_serial
        elif dev_info.get('object_key'):
            instance_name = 'JIRAKEY ' + dev_info['object_key']
        elif metric_data.get('device_name'):
            instance_name = str(metric_data['device_name'])
        else:
            # device not in inventory (or inventory record has no usable
            # identifier) — skip it, do not report to InsightFinder
            return

        # Underscores/colons are not safe instance-identifier characters — normalize to dashes
        instance_name = instance_name.replace('_', '-').replace(':', '-')

        # Display name: inventory name > fallback — sent to InsightFinder as-is, no cleanup
        display_name = metric_data.get('device_name') or dev_info.get('name') or default_display_name

        # Component name: inventory manufacturer-device_class (exclude NONE-NONE) > fallback
        component_name = default_component_name
        if dev_info.get('component_name') and dev_info['component_name'] != 'NONE-NONE':
            component_name = dev_info['component_name']

        # Zone: inventory meta.venue > empty
        zone = dev_info.get('venue') or ''

        # IP: devicelookup > Mimosa API
        if dev_info.get('ip_address'):
            ipAddress = dev_info['ip_address']

        # Create safe metric key
        safe_metric_key = make_safe_metric_key(metric_name)

        # Prepare metric data point
        metric_data_point = {
            'instanceName': instance_name,
            'displayName': display_name,
            'componentName': component_name,
            'zone': zone,
            'metricName': safe_metric_key,
            'data': value,
            'timestamp': timestamp,
            'ipAddress': ipAddress,
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
        
        # Optional: Limit number of devices for testing/performance (0 = no limit)
        max_devices = config_parser.getint(mimosa_section, 'max_devices', fallback=0)
        
        # Optional: Number of devices to query per API call (default: 25)
        api_batch_size = config_parser.getint(mimosa_section, 'api_batch_size', fallback=25)
        
        # Optional: Number of data points to collect per metric (default: 1 - latest only)
        data_points_count = config_parser.getint(mimosa_section, 'data_points_count', fallback=1)
        
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
        default_display_name = config_parser.get(agent_section, 'default_display_name', fallback='UNKNOWN')
        instance_name = config_parser.get(agent_section, 'instance_name', fallback='mimosa_instance')

        # Device Inventory API settings (for MAC -> serial/venue/component lookup)
        device_inventory_api_key = config_parser.get(agent_section, 'device_inventory_api_key', fallback='')
        device_inventory_base_url = config_parser.get(agent_section, 'device_inventory_base_url', fallback='')
        device_inventory_timeout_sec = config_parser.getint(agent_section, 'device_inventory_timeout_sec', fallback=5)
        device_inventory_max_retry = config_parser.getint(agent_section, 'device_inventory_max_retry', fallback=2)

        return {
            'mimosa_uri': mimosa_uri,
            'username': username,
            'password': password,
            'verify_certs': verify_certs,
            'network_id': network_id,
            'action_names': action_names,
            'max_devices': max_devices,
            'api_batch_size': api_batch_size,
            'data_points_count': data_points_count,
            'metrics_config': metrics_config,
            'thread_pool': thread_pool,
            'default_component_name': default_component_name,
            'default_display_name': default_display_name,
            'instance_name': instance_name,
            'device_inventory_api_key': device_inventory_api_key,
            'device_inventory_base_url': device_inventory_base_url,
            'device_inventory_timeout_sec': device_inventory_timeout_sec,
            'device_inventory_max_retry': device_inventory_max_retry,
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
    data_dict['iat'] = 'Custom'
    if if_config_vars.get('sampling_interval'):
        data_dict['si'] = str(int(if_config_vars['sampling_interval'] / 1000))  # ms -> seconds
    
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
        ipAddress = chunk.get('ipAddress', '')
        display_name = chunk.get('displayName', '')
        zone = chunk.get('zone', '')

        if instance_name not in instance_data_map:
            # build instance metadata string (im): idn=display name, cn=component, i=ip, z=zone
            im_data = {}
            if display_name:
                im_data['idn'] = display_name
            if component_name:
                im_data['cn'] = component_name
            if ipAddress:
                im_data['i'] = ipAddress
            if zone:
                im_data['z'] = zone

            instance_data_map[instance_name] = {
                'in': instance_name,
                'cn': component_name,
                'i': ipAddress,
                'dit': {}
            }
            if im_data:
                instance_data_map[instance_name]['im'] = json.dumps(im_data)
        
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
    
    # NOTE: instance metadata is carried in the 'im' field of the v2 payload (like zabbix-ap).
    # The separate agent-upload-instancemetadata call is disabled: it only sent
    # instanceName+ipAddress with override=true, wiping display name/component/zone.


def send_instance_metadata(logger, if_config_vars, data_to_post, agent_config_vars=None):
    """Send instance metadata to InsightFinder after data upload"""
    try:
        # Extract instance metadata from the sent data
        instance_metadata_list = []
        
        if 'data' in data_to_post and 'idm' in data_to_post['data']:
            instance_data_map = data_to_post['data']['idm']
            
            for instance_key, instance_info in instance_data_map.items():
                instance_name = instance_info.get('in', '')  # instanceName
                ip_address = instance_info.get('i', '')  # ipAddress (used as componentName)
                
                if instance_name:
                    metadata_entry = {
                        'instanceName': instance_name,
                        'ipAddress': ip_address if ip_address else ''
                    }
                    instance_metadata_list.append(metadata_entry)
        
        if not instance_metadata_list:
            logger.debug('No instance metadata to send')
            return
        
        # Save metadata to file for debugging
        metadata_filename = 'mimosa_instance_metadata.json'
        try:
            with open(metadata_filename, 'w') as f:
                json.dump(instance_metadata_list, f, indent=2)
            logger.info(f"Instance metadata saved to {metadata_filename}")
        except Exception as e:
            logger.error(f"Failed to save metadata file: {e}")
        
        # Build the metadata API URL
        metadata_url = (
            f"{if_config_vars['if_url']}/api/v1/agent-upload-instancemetadata"
            f"?userName={if_config_vars['user_name']}"
            f"&licenseKey={if_config_vars['license_key']}"
            f"&projectName={if_config_vars['project_name']}"
            f"&override=true"
        )
        
        logger.info(f'Sending instance metadata for {len(instance_metadata_list)} instances')
        
        # Send the metadata request
        response = send_request(
            logger, 
            metadata_url,
            mode='POST',
            data=json.dumps(instance_metadata_list),
            headers={'Content-Type': 'application/json'},
            proxies=get_proxy_dict(if_config_vars),
            verify=False,
            success_message='Instance metadata uploaded successfully',
            failure_message='Failed to upload instance metadata'
        )
        
        if response != -1:
            logger.info('Instance metadata sent successfully')
        else:
            logger.warning('Failed to send instance metadata')
            
    except Exception as e:
        logger.error(f'Error sending instance metadata: {str(e)}')


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


def check_and_create_project(logger, if_config_vars):
    """Check if the project exists in InsightFinder; create it (with system) if not.
    Mirrors the mimosa Go agent's IsProjectExist/CreateProject logic."""
    if_url = if_config_vars['if_url']
    project_endpoint = urljoin(if_url, '/api/v1/check-and-add-custom-project')
    project_name = if_config_vars['project_name']
    system_name = if_config_vars.get('system_name') or project_name

    check_form = {
        'operation': 'check',
        'userName': if_config_vars['user_name'],
        'licenseKey': if_config_vars['license_key'],
        'projectName': project_name,
        'systemName': system_name,
    }

    try:
        resp = requests.post(project_endpoint, data=check_form, verify=False, timeout=30)
        if resp.status_code != 200:
            logger.error(f'Project check failed with status: {resp.status_code}')
            return False
        check_result = resp.json()
    except Exception as e:
        logger.error(f'Failed to check project existence: {e}')
        return False

    if not check_result.get('success', check_result.get('isSuccess', False)):
        logger.error(f'Project check failed: {check_result.get("message", "")}')
        return False

    if check_result.get('isProjectExist', False):
        logger.info(f"Project '{project_name}' exists in InsightFinder")
        return True

    logger.info(f"Project '{project_name}' does not exist, creating...")

    sampling_interval_sec = int(if_config_vars.get('sampling_interval', 60000) / 1000) or 60
    create_form = {
        'operation': 'create',
        'userName': if_config_vars['user_name'],
        'licenseKey': if_config_vars['license_key'],
        'projectName': project_name,
        'systemName': system_name,
        'instanceType': 'OnPremise',
        'projectCloudType': 'OnPremise',
        'dataType': get_data_type_from_project_type(if_config_vars),
        'insightAgentType': 'Custom',
        'samplingInterval': sampling_interval_sec,
        'samplingIntervalInSeconds': sampling_interval_sec,
    }

    try:
        resp = requests.post(project_endpoint, params=create_form, verify=False, timeout=30)
        if resp.status_code != 200:
            logger.error(f'Project creation failed with status: {resp.status_code}, response: {resp.text}')
            return False
        create_result = resp.json()
        if create_result.get('success', create_result.get('isSuccess', False)):
            logger.info(f"Project '{project_name}' created successfully in system '{system_name}'")
            return True
        logger.error(f'Project creation failed: {create_result.get("message", "")}')
        return False
    except Exception as e:
        logger.error(f'Failed to create project: {e}')
        return False


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

    # ensure project (and system) exist in InsightFinder before sending data
    if not cli_config_vars['testing']:
        if not check_and_create_project(logger, if_config_vars):
            logger.error('Failed to create/verify InsightFinder project, exiting')
            sys.exit(1)

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

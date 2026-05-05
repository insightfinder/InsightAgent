#!/usr/bin/env python3
import configparser
import glob
import http.client
import json
import logging
import multiprocessing
import os
import regex
import socket
import sys
import time
import traceback
import urllib.parse
from logging.handlers import QueueHandler
from multiprocessing import Pool, TimeoutError
from optparse import OptionParser
from time import sleep

import arrow
import pytz
import pymssql
import requests

from pymssql import ProgrammingError
from datetime import datetime
from decimal import Decimal

"""
This script gathers data to send to Insightfinder
"""

# module-level constants
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
HOSTNAME = socket.gethostname().partition('.')[0]
ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
ATTEMPTS = 3


def start_data_processing(logger, if_config_vars, agent_config_vars, metric_buffer, track):
    conn = pymssql.connect(**agent_config_vars['mssql_kwargs'])
    cursor = conn.cursor()
    logger.info('Connected to MSSQL')

    agent_config_vars.setdefault('instance_map', {})
    agent_config_vars.setdefault('device_map', {})

    # load instance mapping
    if agent_config_vars['instance_map_conn']:
        try:
            sql_str = "select * from {}".format(agent_config_vars['instance_map_conn']['instance_map_table'])
            cursor.execute(sql_str)
            instance_map = {}
            for message in cursor:
                id_str = str(message[agent_config_vars['instance_map_conn']['instance_map_id_field']])
                name_str = str(message[agent_config_vars['instance_map_conn']['instance_map_name_field']])
                instance_map[id_str] = name_str
            agent_config_vars['instance_map'] = instance_map
        except ProgrammingError as e:
            logger.error('Instance map query error: {}'.format(e))

    # resolve table list
    table_list = []
    if agent_config_vars['table_list'].startswith('sql:'):
        try:
            sql_str = agent_config_vars['table_list'].split('sql:')[1]
            cursor.execute(sql_str)
            for message in cursor:
                table_list.append(str(message['name']))
        except ProgrammingError as e:
            logger.error('Table list query error: {}'.format(e))
    else:
        table_list = [x.strip() for x in agent_config_vars['table_list'].split(',') if x.strip()]

    if len(table_list) == 0:
        logger.error('Table list is empty')
        cursor.close()
        conn.close()
        return

    # load device mapping
    if agent_config_vars['device_map_conn']:
        try:
            map_info = agent_config_vars['device_map_conn']
            sql_str = "select * from {}".format(map_info['device_map_table'])
            cursor.execute(sql_str)
            device_map = {}
            for message in cursor:
                id_str = str(message[map_info['device_map_id_field']])
                name_str = str(message[map_info['device_map_name_field']])
                device_map[id_str] = name_str
            agent_config_vars['device_map'] = device_map
        except ProgrammingError as e:
            logger.error('Device map query error: {}'.format(e))

    sql = agent_config_vars['sql']
    sql = sql.replace('\n', ' ').replace('"""', '')

    if agent_config_vars['sql_config']:
        logger.debug('Using hist time range for replay data')
        for timestamp in range(agent_config_vars['sql_config']['hist_time_range'][0],
                               agent_config_vars['sql_config']['hist_time_range'][1],
                               agent_config_vars['sql_config']['hist_batch_interval']):
            for table in table_list:
                sql_str = sql
                start_time = arrow.get(timestamp).format(agent_config_vars['timestamp_format'])
                end_time = arrow.get(
                    timestamp + agent_config_vars['sql_config']['hist_batch_interval']).format(
                    agent_config_vars['timestamp_format'])
                sql_str = sql_str.replace('{{table}}', table)
                sql_str = sql_str.replace('{{timestamp_field}}', agent_config_vars['timestamp_field'][0])
                sql_str = sql_str.replace('{{start_time}}', start_time)
                sql_str = sql_str.replace('{{end_time}}', end_time)
                query_messages_mssql(logger, if_config_vars, agent_config_vars, metric_buffer, track, cursor, sql_str)

            clear_metric_buffer(logger, if_config_vars, metric_buffer, track)
    else:
        logger.debug('Using current time for streaming data')
        for table in table_list:
            sql_str = sql
            start_time = arrow.get(
                arrow.utcnow().float_timestamp - agent_config_vars['query_window'] * 60,
                tzinfo=agent_config_vars['timezone'].zone).format(agent_config_vars['timestamp_format'])
            end_time = arrow.get(
                arrow.utcnow().float_timestamp,
                tzinfo=agent_config_vars['timezone'].zone).format(agent_config_vars['timestamp_format'])
            sql_str = sql_str.replace('{{table}}', table)
            sql_str = sql_str.replace('{{timestamp_field}}', agent_config_vars['timestamp_field'][0])
            sql_str = sql_str.replace('{{start_time}}', start_time)
            sql_str = sql_str.replace('{{end_time}}', end_time)
            query_messages_mssql(logger, if_config_vars, agent_config_vars, metric_buffer, track, cursor, sql_str)

    cursor.close()
    conn.close()
    logger.info('Disconnected from MSSQL')


def query_messages_mssql(logger, if_config_vars, agent_config_vars, metric_buffer, track, cursor, sql_str):
    try:
        logger.info('Executing SQL: {}'.format(sql_str))
        cursor.execute(sql_str)
        parse_messages_mssql(logger, if_config_vars, agent_config_vars, metric_buffer, track, cursor)
    except ProgrammingError as e:
        logger.error('SQL execute error: {}'.format(e))


def parse_messages_mssql(logger, if_config_vars, agent_config_vars, metric_buffer, track, cursor):
    count = 0
    message_list = cursor.fetchall()
    logger.info('Reading {} messages'.format(len(message_list)))

    for message in message_list:
        try:
            timestamp = message[agent_config_vars['timestamp_field'][0]]
            if isinstance(timestamp, datetime):
                timestamp = int(arrow.get(timestamp, tzinfo=agent_config_vars['timezone'].zone).float_timestamp * 1000)
            else:
                timestamp = int(arrow.get(timestamp, tzinfo=agent_config_vars['timezone'].zone).float_timestamp * 1000)

            timestamp += int(agent_config_vars['target_timestamp_timezone'] * 1000)
            timestamp = str(timestamp)

            instance = str(message[agent_config_vars['instance_field'][0]])
            instance = agent_config_vars['instance_map'].get(instance, instance)

            full_instance = instance
            device_field = agent_config_vars['device_field']
            device_field = list(set(device_field) & set(message.keys()))
            if device_field:
                device = str(message[device_field[0]])
                device = agent_config_vars['device_map'].get(device, device)
                device = device.replace('_', '-').replace('.', '-')
                full_instance = '{}_{}'.format(device, instance)

            key = '{}-{}'.format(timestamp, full_instance)

            if 'METRIC' in if_config_vars['project_type']:
                if key not in metric_buffer['buffer_dict']:
                    metric_buffer['buffer_dict'][key] = {'timestamp': timestamp, 'instanceName': full_instance}

                metric_name_field = agent_config_vars['metric_name_field']
                if metric_name_field:
                    metric_name = str(message[metric_name_field])
                    value_field = agent_config_vars['data_fields'][0]
                    data_value = message[value_field]
                    if isinstance(data_value, Decimal):
                        data_value = str(data_value)
                    metric_buffer['buffer_dict'][key]['{}[{}]'.format(metric_name, full_instance)] = str(data_value)
                else:
                    setting_values = agent_config_vars['data_fields'] or list(message.keys())
                    setting_values = list(set(setting_values) & set(message.keys()))
                    for data_field in setting_values:
                        data_value = message[data_field]
                        if isinstance(data_value, Decimal):
                            data_value = str(data_value)
                        metric_buffer['buffer_dict'][key]['{}[{}]'.format(data_field, full_instance)] = str(data_value)
            else:
                setting_values = agent_config_vars['data_fields'] or list(message.keys())
                setting_values = list(set(setting_values) & set(message.keys()))
                data = {}
                for data_field in setting_values:
                    data_value = message[data_field]
                    if isinstance(data_value, Decimal):
                        data_value = str(data_value)
                    elif isinstance(data_value, datetime):
                        data_value = str(data_value)
                    data[data_field] = data_value
                metric_buffer['buffer_dict'][key] = {
                    'eventId': timestamp,
                    'tag': full_instance,
                    'data': data,
                }

        except Exception as e:
            logger.warning('Error parsing message: {}'.format(e))
            logger.debug(traceback.format_exc())
            continue

        track['entry_count'] += 1
        count += 1
        if count % 1000 == 0:
            logger.info('Parsed {} messages'.format(count))
    logger.info('Parsed {} messages'.format(count))


def get_agent_config_vars(logger, config_file):
    if not os.path.exists(config_file):
        logger.error('No config file found: {}'.format(config_file))
        return False

    config_parser = configparser.ConfigParser()
    config_parser.read(config_file)

    mssql_kwargs = {}
    table_list = ''
    instance_map_conn = None
    device_map_conn = None
    sql = None
    sql_config = None

    try:
        mssql_config = {
            'charset': 'utf8',
            'as_dict': True,
            'timeout': int(config_parser.get('mssql', 'timeout') or '0'),
            'login_timeout': int(config_parser.get('mssql', 'login_timeout') or '60'),
            'appname': config_parser.get('mssql', 'appname', fallback=''),
            'port': config_parser.get('mssql', 'port'),
        }
        mssql_kwargs = {k: v for (k, v) in mssql_config.items() if v}

        if len(config_parser.get('mssql', 'host')) != 0:
            mssql_kwargs['host'] = config_parser.get('mssql', 'host')
        else:
            return config_error(logger, 'host')
        if len(config_parser.get('mssql', 'user')) != 0:
            mssql_kwargs['user'] = config_parser.get('mssql', 'user')
        else:
            return config_error(logger, 'user')
        if len(config_parser.get('mssql', 'password')) != 0:
            mssql_kwargs['password'] = config_parser.get('mssql', 'password')
        else:
            return config_error(logger, 'password')
        if len(config_parser.get('mssql', 'database')) != 0:
            mssql_kwargs['database'] = config_parser.get('mssql', 'database')
        else:
            return config_error(logger, 'database')

        if len(config_parser.get('mssql', 'table_list')) != 0:
            table_list = config_parser.get('mssql', 'table_list')
        else:
            return config_error(logger, 'table_list')

        if len(config_parser.get('mssql', 'instance_map_table')) != 0 \
                and len(config_parser.get('mssql', 'instance_map_id_field')) != 0 \
                and len(config_parser.get('mssql', 'instance_map_name_field')) != 0:
            instance_map_conn = {
                'instance_map_table': config_parser.get('mssql', 'instance_map_table'),
                'instance_map_id_field': config_parser.get('mssql', 'instance_map_id_field'),
                'instance_map_name_field': config_parser.get('mssql', 'instance_map_name_field'),
            }

        if len(config_parser.get('mssql', 'device_map_table')) != 0 \
                and len(config_parser.get('mssql', 'device_map_id_field')) != 0 \
                and len(config_parser.get('mssql', 'device_map_name_field')) != 0:
            device_map_conn = {
                'device_map_table': config_parser.get('mssql', 'device_map_table'),
                'device_map_id_field': config_parser.get('mssql', 'device_map_id_field'),
                'device_map_name_field': config_parser.get('mssql', 'device_map_name_field'),
            }

        if len(config_parser.get('mssql', 'sql')) != 0:
            sql = config_parser.get('mssql', 'sql')
        else:
            return config_error(logger, 'sql')

        if len(config_parser.get('mssql', 'hist_time_range')) != 0 \
                and len(config_parser.get('mssql', 'hist_batch_interval')) != 0:
            try:
                hist_time_range = [x.strip() for x in config_parser.get('mssql', 'hist_time_range').split(',') if x.strip()]
                hist_time_range = [int(arrow.get(x).float_timestamp) for x in hist_time_range]
                hist_batch_interval = int(config_parser.get('mssql', 'hist_batch_interval'))
                sql_config = {
                    'hist_time_range': hist_time_range,
                    'hist_batch_interval': hist_batch_interval,
                }
            except Exception as e:
                logger.debug(e)
                return config_error(logger, 'hist_time_range|hist_batch_interval')

        agent_http_proxy = config_parser.get('mssql', 'agent_http_proxy')
        agent_https_proxy = config_parser.get('mssql', 'agent_https_proxy')

        data_format = config_parser.get('mssql', 'data_format').upper()
        instance_field = config_parser.get('mssql', 'instance_field', raw=True)
        device_field = config_parser.get('mssql', 'device_field', raw=True)
        timestamp_field = config_parser.get('mssql', 'timestamp_field', raw=True) or 'timestamp'
        target_timestamp_timezone = config_parser.get('mssql', 'target_timestamp_timezone', raw=True) or 'UTC'
        timestamp_format = config_parser.get('mssql', 'timestamp_format', raw=True)
        timezone = config_parser.get('mssql', 'timezone') or 'UTC'
        data_fields = config_parser.get('mssql', 'data_fields', raw=True)
        metric_name_field = config_parser.get('mssql', 'metric_name_field', raw=True, fallback='')
        query_window = int(config_parser.get('mssql', 'query_window', fallback='') or 10)

    except configparser.NoOptionError as cp_noe:
        logger.error(cp_noe)
        return config_error(logger)

    timestamp_format = timestamp_format.strip() or 'epoch'

    if len(target_timestamp_timezone) != 0:
        target_timestamp_timezone = arrow.now(target_timestamp_timezone).utcoffset().total_seconds()
    else:
        return config_error(logger, 'target_timestamp_timezone')

    if timezone:
        if timezone not in pytz.all_timezones:
            return config_error(logger, 'timezone')
        else:
            timezone = pytz.timezone(timezone)

    if data_format not in {'JSON', 'JSONTAIL', 'AVRO', 'XML'}:
        return config_error(logger, 'data_format')

    agent_proxies = {}
    if len(agent_http_proxy) > 0:
        agent_proxies['http'] = agent_http_proxy
    if len(agent_https_proxy) > 0:
        agent_proxies['https'] = agent_https_proxy

    instance_fields = instance_field.split(',')
    device_fields = device_field.split(',')
    timestamp_fields = timestamp_field.split(',')
    if len(data_fields) != 0:
        data_fields = data_fields.split(',')
        for f in instance_fields + device_fields + timestamp_fields:
            if f in data_fields:
                data_fields.remove(f)

    return {
        'mssql_kwargs': mssql_kwargs,
        'table_list': table_list,
        'instance_map_conn': instance_map_conn,
        'device_map_conn': device_map_conn,
        'sql': sql,
        'sql_config': sql_config,
        'proxies': agent_proxies,
        'data_format': data_format,
        'instance_field': instance_fields,
        'device_field': device_fields,
        'data_fields': data_fields,
        'metric_name_field': metric_name_field,
        'query_window': query_window,
        'timestamp_field': timestamp_fields,
        'target_timestamp_timezone': target_timestamp_timezone,
        'timezone': timezone,
        'timestamp_format': timestamp_format,
    }


def get_if_config_vars(logger, config_file):
    if not os.path.exists(config_file):
        logger.error('No config file found: {}'.format(config_file))
        return False

    config_parser = configparser.ConfigParser()
    config_parser.read(config_file)

    try:
        user_name = config_parser.get('insightfinder', 'user_name')
        license_key = config_parser.get('insightfinder', 'license_key')
        project_name = config_parser.get('insightfinder', 'project_name')
        project_type = config_parser.get('insightfinder', 'project_type').upper()
        sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
        chunk_size_kb = config_parser.get('insightfinder', 'chunk_size_kb')
        if_url = config_parser.get('insightfinder', 'if_url')
        if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
        if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
        containerize = config_parser.get('insightfinder', 'containerize', fallback='').upper() in ('TRUE', '1', 'YES')
    except configparser.NoOptionError as cp_noe:
        logger.error(cp_noe)
        return config_error(logger)

    if len(user_name) == 0:
        return config_error(logger, 'user_name')
    if len(license_key) == 0:
        return config_error(logger, 'license_key')
    if len(project_name) == 0:
        return config_error(logger, 'project_name')
    if project_type not in {'METRIC', 'LOG'}:
        return config_error(logger, 'project_type')

    if len(sampling_interval) == 0:
        if 'METRIC' in project_type:
            return config_error(logger, 'sampling_interval')
        else:
            sampling_interval = 10

    if sampling_interval.endswith('s'):
        sampling_interval = int(sampling_interval[:-1])
    else:
        sampling_interval = int(sampling_interval) * 60

    if len(chunk_size_kb) == 0:
        chunk_size_kb = 2048
    if len(if_url) == 0:
        if_url = 'https://app.insightfinder.com'

    if_proxies = {}
    if len(if_http_proxy) > 0:
        if_proxies['http'] = if_http_proxy
    if len(if_https_proxy) > 0:
        if_proxies['https'] = if_https_proxy

    return {
        'user_name': user_name,
        'license_key': license_key,
        'project_name': project_name,
        'project_type': project_type,
        'sampling_interval': int(sampling_interval),
        'chunk_size': int(chunk_size_kb) * 1024,
        'if_url': if_url,
        'if_proxies': if_proxies,
        'containerize': containerize,
    }


def initialize_data_gathering(logger, if_config_vars, agent_config_vars):
    metric_buffer = {}
    track = {}
    reset_metric_buffer(metric_buffer)
    reset_track(track)
    track['chunk_count'] = 0
    track['entry_count'] = 0

    start_data_processing(logger, if_config_vars, agent_config_vars, metric_buffer, track)

    clear_metric_buffer(logger, if_config_vars, metric_buffer, track)

    logger.info('Total chunks created: {}'.format(track['chunk_count']))
    logger.info('Total {} entries: {}'.format(if_config_vars['project_type'].lower(), track['entry_count']))


def clear_metric_buffer(logger, if_config_vars, metric_buffer, track):
    buffer_values = list(metric_buffer['buffer_dict'].values())

    count = 0
    for row in buffer_values:
        track['current_row'].append(row)
        count += 1
        if count % 100 == 0 and get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
            logger.debug('Sending buffer chunk')
            send_data_wrapper(logger, if_config_vars, track)

    if len(track['current_row']) > 0:
        logger.debug('Sending last chunk')
        send_data_wrapper(logger, if_config_vars, track)

    reset_metric_buffer(metric_buffer)


def reset_metric_buffer(metric_buffer):
    metric_buffer['buffer_key_list'] = []
    metric_buffer['buffer_ts_list'] = []
    metric_buffer['buffer_dict'] = {}
    metric_buffer['buffer_collected_list'] = []
    metric_buffer['buffer_collected_dict'] = {}


def reset_track(track):
    track['start_time'] = time.time()
    track['line_count'] = 0
    track['current_row'] = []


def send_data_wrapper(logger, if_config_vars, track):
    logger.debug('--- Chunk creation time: {} seconds ---'.format(round(time.time() - track['start_time'], 2)))
    send_data_to_if(logger, if_config_vars, track['current_row'])
    track['chunk_count'] += 1
    reset_track(track)


def safe_string_to_float(s):
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def convert_to_metric_data(if_config_vars, chunk_metric_data):
    to_send_data_dict = {
        'licenseKey': if_config_vars['license_key'],
        'userName': if_config_vars['user_name'],
    }
    data_dict = {
        'projectName': if_config_vars['project_name'],
        'userName': if_config_vars['user_name'],
    }

    common_fields = {'instanceName', 'timestamp'}
    instance_data_map = {}

    for chunk in chunk_metric_data:
        instance_name = chunk.get('instanceName')
        timestamp = chunk.get('timestamp')
        data = {k: v for k, v in chunk.items() if k not in common_fields}

        if data and timestamp and instance_name:
            ts = int(float(timestamp))
            if instance_name not in instance_data_map:
                instance_data_map[instance_name] = {'in': instance_name, 'dit': {}}

            if timestamp not in instance_data_map[instance_name]['dit']:
                instance_data_map[instance_name]['dit'][timestamp] = {'t': ts, 'm': []}

            data_set = instance_data_map[instance_name]['dit'][timestamp]['m']
            for metric_name, metric_value in data.items():
                metric_name = metric_name.split('[')[0]
                float_value = safe_string_to_float(metric_value)
                data_set.append({'m': metric_name, 'v': float_value if float_value is not None else 0.0})

    data_dict['idm'] = instance_data_map
    to_send_data_dict['data'] = data_dict
    return to_send_data_dict


def send_data_to_if(logger, if_config_vars, chunk_metric_data):
    send_data_time = time.time()

    if 'METRIC' in if_config_vars['project_type']:
        json_to_post = convert_to_metric_data(if_config_vars, chunk_metric_data)
        post_url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v2/metric-data-receive')
        logger.info('Total Data (bytes): {}'.format(get_json_size_bytes(json_to_post)))
        send_request(logger, post_url, 'POST', 'Could not send request to IF',
                     '{} bytes reported.'.format(get_json_size_bytes(json_to_post)),
                     json=json_to_post, verify=False, proxies=if_config_vars['if_proxies'])
    else:
        data_to_post = initialize_api_post_data(if_config_vars)
        data_to_post['metricData'] = json.dumps(chunk_metric_data)
        post_url = urllib.parse.urljoin(if_config_vars['if_url'], get_api_from_project_type(if_config_vars))
        logger.info('Total Data (bytes): {}'.format(get_json_size_bytes(data_to_post)))
        send_request(logger, post_url, 'POST', 'Could not send request to IF',
                     '{} bytes reported.'.format(get_json_size_bytes(data_to_post)),
                     data=data_to_post, verify=False, proxies=if_config_vars['if_proxies'])

    logger.info('--- Send data time: {} seconds ---'.format(round(time.time() - send_data_time, 2)))


def send_request(logger, url, mode='GET', failure_message='Failure!', success_message='Success!',
                 **request_passthrough):
    requests.packages.urllib3.disable_warnings()
    req = requests.post if mode.upper() == 'POST' else requests.get

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

    logger.error('Failed! Gave up after {} attempts.'.format(req_num + 1))
    return -1


def get_agent_type_from_project_type(if_config_vars):
    if if_config_vars.get('containerize'):
        return 'containerStreaming' if 'METRIC' in if_config_vars['project_type'] else 'containerCustom'
    return 'CUSTOM' if 'METRIC' in if_config_vars['project_type'] else 'LogStreaming'


def get_api_from_project_type(if_config_vars):
    if 'METRIC' in if_config_vars['project_type']:
        return 'api/v2/metric-data-receive'
    return '/api/v1/customprojectrawdata'


def initialize_api_post_data(if_config_vars):
    to_send_data_dict = {
        'userName': if_config_vars['user_name'],
        'licenseKey': if_config_vars['license_key'],
        'projectName': if_config_vars['project_name'],
        'instanceName': HOSTNAME,
        'agentType': get_agent_type_from_project_type(if_config_vars),
    }
    if 'METRIC' in if_config_vars['project_type'] and 'sampling_interval' in if_config_vars:
        to_send_data_dict['samplingInterval'] = str(if_config_vars['sampling_interval'])
    return to_send_data_dict


def get_json_size_bytes(json_data):
    return len(json.dumps(json_data).encode('utf-8'))


def config_error(logger, setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(info))
    return False


def print_summary_info(logger, if_config_vars, agent_config_vars):
    post_data_block = '\nIF settings:'
    for ik, iv in sorted(if_config_vars.items()):
        post_data_block += '\n\t{}: {}'.format(ik, iv)
    logger.debug(post_data_block)

    agent_data_block = '\nAgent settings:'
    for jk, jv in sorted(agent_config_vars.items()):
        agent_data_block += '\n\t{}: {}'.format(jk, jv)
    logger.debug(agent_data_block)


#########################
#   MULTIPROCESSING     #
#########################

def listener_configurer():
    formatter = logging.Formatter(
        '%(asctime)s [%(name)s] [pid %(process)d] %(levelname)-8s %(module)s.%(funcName)s():%(lineno)d %(message)s',
        ISO8601[0])
    root = logging.getLogger()
    handler_out = logging.StreamHandler(sys.stdout)
    handler_out.setLevel(logging.DEBUG)
    handler_out.setFormatter(formatter)
    root.addHandler(handler_out)
    handler_err = logging.StreamHandler(sys.stderr)
    handler_err.setLevel(logging.WARNING)
    handler_err.setFormatter(formatter)
    root.addHandler(handler_err)


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
    h = QueueHandler(q)
    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(level)


def worker_process(args):
    config_file, c_config, q = args

    config_name = os.path.basename(config_file)
    worker_configurer(q, c_config['log_level'])
    logger = logging.getLogger(config_name)
    logger.info('Process start with config: {}'.format(config_name))

    if_config_vars = get_if_config_vars(logger, config_file)
    if not if_config_vars:
        return

    agent_config_vars = get_agent_config_vars(logger, config_file)
    if not agent_config_vars:
        return

    print_summary_info(logger, if_config_vars, agent_config_vars)

    if c_config['testing']:
        logger.info('TEST MODE — skipping data send')
        return

    initialize_data_gathering(logger, if_config_vars, agent_config_vars)
    logger.info('Process done with config: {}'.format(config_name))
    return True


def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))


def get_cli_config_vars():
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    parser.add_option('-c', '--config', action='store', dest='config', default=abs_path_from_cur('conf.d'),
                      help='Path to the conf.d directory containing *.ini config files. '
                           'Defaults to {}'.format(abs_path_from_cur('conf.d')))
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data)')
    (options, args) = parser.parse_args()

    config_vars = {
        'config': options.config if os.path.isdir(options.config) else abs_path_from_cur('conf.d'),
        'testing': options.testing,
        'log_level': logging.INFO,
    }

    if options.verbose:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING

    return config_vars


if __name__ == '__main__':
    c_config = get_cli_config_vars()

    m = multiprocessing.Manager()
    queue = m.Queue()
    listener = multiprocessing.Process(target=listener_process, args=(queue,))
    listener.start()

    worker_configurer(queue, c_config['log_level'])
    main_logger = logging.getLogger('main')

    config_files = glob.glob(os.path.join(c_config['config'], '*.ini'))
    if not config_files:
        main_logger.error('No *.ini files found in: {}'.format(c_config['config']))
        sys.exit(1)

    main_logger.info('Found {} config file(s): {}'.format(len(config_files), config_files))

    arg_list = [(f, c_config, queue) for f in config_files]
    pool = Pool(len(config_files))
    pool_result = pool.map_async(worker_process, arg_list)
    pool.close()

    try:
        results = pool_result.get(timeout=600)
        pool.join()
    except TimeoutError:
        main_logger.error('Timed out waiting for workers')
        pool.terminate()

    main_logger.info('All workers complete')

    time.sleep(1)
    kill_logger = logging.getLogger('KILL')
    kill_logger.info('KILL')
    listener.join()

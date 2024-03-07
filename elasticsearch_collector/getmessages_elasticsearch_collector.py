#!/usr/bin/env python
import configparser
import http.client
import json
import logging
import math
import multiprocessing
import os
import shlex
import signal
import socket
import sys
import threading
import time
import re
import traceback
import urllib.parse
from logging.handlers import QueueHandler, TimedRotatingFileHandler
from multiprocessing import Process, Queue
from multiprocessing.pool import ThreadPool
from optparse import OptionParser
from sys import getsizeof
from threading import Lock
from time import sleep

import arrow
import pytz
import regex
import requests
from elasticsearch import Elasticsearch
from urllib3.exceptions import InsecureRequestWarning
from pprint import pformat
from pathlib import Path

import logging

logging.basicConfig(level=logging.INFO)

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
PIPE = regex.compile(r"\|+")
PROJECT_ALNUM = regex.compile(r"[@\._]+")
NON_ALNUM = regex.compile(r"[^a-zA-Z0-9]")
FORMAT_STR = regex.compile(r"{(.*?)}")
STRIP_PORT = regex.compile(r"(.*):\d+")
HOSTNAME = socket.gethostname().partition('.')[0]
ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
JSON_LEVEL_DELIM = '.'
CSV_DELIM = r",|\t"
ATTEMPTS = 3
RETRY_WAIT_TIME_IN_SEC = 30
BUFFER_CHECK_COUNT = 1000
PARSE_DATA_LOG_COUNT = 5000
CLOSED_MESSAGE = "CLOSED_MESSAGE"
SESSION = requests.Session()
LOG_DIR = "logs"
AGENT_LOG_FILE = "./logs/agent.log"

logCompressState = {}


def align_timestamp(timestamp, sampling_interval):
    if sampling_interval == 0 or not timestamp:
        return timestamp
    else:
        return math.floor(timestamp / (sampling_interval * 1000)) * sampling_interval * 1000


def safe_string_to_float(s):
    try:
        return float(s)
    except ValueError:
        return None


def process_get_data(log_queue, cli_config_vars, if_config_vars, agent_config_vars, messages, worker_process,
                     time_now, collector_id):
    worker_configurer(log_queue, cli_config_vars['log_level'])
    logger = logging.getLogger('worker')
    logger.info('Starting get data from ElasticSearch on collector {} ...'.format(collector_id))

    collector_count = cli_config_vars['collector']
    sampling_interval = if_config_vars['sampling_interval']
    collector_interval = sampling_interval // collector_count

    # get conn
    es_conn = get_es_connection(logger, agent_config_vars)

    # only close the worker process on the failure of the first collector
    if not es_conn and collector_id == 0:
        config_error(logger, 'ElasticSearch connection error')
        # # send close single for each worker
        for i in range(0, worker_process):
            messages.put(CLOSED_MESSAGE)
        messages.close()
        logger.error("Failed to get data from ElasticSearch caused by connection issue.")
        time.sleep(1)
        return False

    # pit used
    pit = None
    try:
        pit_response = es_conn.open_point_in_time(index=agent_config_vars['indeces'], keep_alive="1m")
        pit = pit_response['id']
    except Exception as ex:
        logger.error("ElasticSearch open PIT failed. \n{}".format(str(ex)))
        # send close single for each worker
        for i in range(0, worker_process):
            messages.put(CLOSED_MESSAGE)
        messages.close()
        logger.error("Failed to get data from ElasticSearch")
        sleep(1)
        return False

    # time query
    timestamp_field = agent_config_vars['timestamp_field']
    timestamp_field = timestamp_field.replace('_source.', '')

    # parse sql string by params
    logger.debug('history range config: {}'.format(agent_config_vars['his_time_range']))
    if agent_config_vars['his_time_range']:
        logger.debug('Using time range for replay data')
        for timestamp in range(agent_config_vars['his_time_range'][0],
                               agent_config_vars['his_time_range'][1],
                               if_config_vars['sampling_interval']):
            start_time = timestamp + (collector_id + 1) * collector_interval
            end_time = start_time + collector_interval

            # build query
            query_body = {
                "size": agent_config_vars['query_chunk_size'],
                "query": {
                    "bool": {
                        "must": [
                            {
                                "range": {
                                    timestamp_field: {
                                        "format": "epoch_second",
                                        'gte': start_time,
                                        'lt': end_time
                                    }
                                }
                            }
                        ],
                    },
                },
                "pit": {'id': pit, 'keep_alive': '1m'},
                "sort": [
                    {timestamp_field: {"order": "asc"}}
                ]
            }

            # add user-defined query
            if isinstance(agent_config_vars['query_json'], dict):
                merge(agent_config_vars['query_json'], query_body)

            logger.info('Getting data from ElasticSearch with query:' + str(query_body))

            # build query with chunk
            query_messages_elasticsearch(logger, cli_config_vars, if_config_vars, agent_config_vars, es_conn,
                                         query_body, messages, start_time * 1000)

    else:
        logger.info('Using current time for streaming data on collector {} ...'.format(collector_id))

        start_time = time_now - (collector_id + 1) * collector_interval
        end_time = start_time + collector_interval

        # build query
        query_body = {
            "size": agent_config_vars['query_chunk_size'],
            "query": {
                "bool": {
                    "must": [
                        {
                            "range": {
                                timestamp_field: {
                                    "format": "epoch_second",
                                    'gte': start_time,
                                    'lt': end_time
                                }
                            }
                        }
                    ],
                },
            },
            "pit": {'id': pit, 'keep_alive': '1m'},
            "sort": [
                {timestamp_field: {"order": "asc"}}
            ]
        }

        # add user-defined query
        if isinstance(agent_config_vars['query_json'], dict):
            merge(agent_config_vars['query_json'], query_body)

        logger.info('Getting data from ElasticSearch with query:' + str(query_body))

        # build query with chunk
        query_messages_elasticsearch(logger, cli_config_vars, if_config_vars, agent_config_vars, es_conn, query_body,
                                     messages, start_time * 1000)

    # send close single for each worker
    for i in range(0, worker_process):
        messages.put(CLOSED_MESSAGE)
    messages.close()

    logger.info('Finish getting data from ElasticSearch')


def get_es_connection(logger, agent_config_vars):
    """ Try to connect to es """
    hosts = build_es_connection_hosts(logger, agent_config_vars)
    try:
        return Elasticsearch(hosts)
    except Exception as e:
        logger.error('Could not contact ElasticSearch with provided configuration.')
        logger.error(e)
        return False


def build_es_connection_hosts(logger, agent_config_vars):
    """ Build array of host dicts """
    hosts = []
    for uri in agent_config_vars['es_uris']:
        host = agent_config_vars['elasticsearch_kwargs'].copy()

        # parse uri for overrides
        uri = urllib.parse.urlparse(uri)
        host['host'] = uri.hostname or uri.path
        host['port'] = uri.port or host['port']
        host['http_auth'] = '{}:{}'.format(uri.username, uri.password) if uri.username and uri.password else host.get(
            'http_auth')
        if uri.scheme == 'https':
            host['use_ssl'] = True

        # add ssl info
        if len(agent_config_vars['elasticsearch_kwargs']) != 0:
            host.update(agent_config_vars['elasticsearch_kwargs'])
        hosts.append(host)
    logger.debug(hosts)
    return hosts


def query_messages_elasticsearch(logger, cli_config_vars, if_config_vars, agent_config_vars, es_conn, query_body,
                                 messages, sampling_timestamp):
    is_metric = 'METRIC' in if_config_vars['project_type']
    logger.debug('Starting query server es')

    # get total number of messages
    try:
        response = es_conn.search(body=query_body, ignore_unavailable=False, )
    except Exception as e:
        logger.error('Query log error.\n{}'.format(str(e)))
        return

    # validate successes
    if 'error' in response:
        logger.error('Query es error: ' + str(response))
        return

    logger.debug('Query result:\n' + str(response))

    hits_data = response.get('hits', {}).get('hits', [])
    aggs_data = response.get('aggregations', {})

    if is_metric:
        if len(hits_data) == 0 and len(aggs_data) == 0:
            logger.info('No data found in hits or aggregations')
            return
    else:
        if len(hits_data) == 0:
            logger.info('No data found in hits')
            return

    # if it's metric data, put all data into one message
    metric_message = []
    if is_metric:
        for item in hits_data:
            metric_message.append(item)

        if len(aggs_data) > 0:
            metric_message.append({"_aggregations": aggs_data, 'sampling_timestamp': sampling_timestamp})
    else:
        for item in hits_data:
            messages.put(item)

    if len(hits_data) == 0:
        if len(metric_message) > 0:
            messages.put(metric_message)
        return

    # next query
    last_time = response.get('hits').get('hits')[-1].get('sort')
    pit = response.get('pit_id')
    while len(hits_data) >= agent_config_vars['query_chunk_size']:
        try:
            query_body["search_after"] = last_time
            query_body['pit']['id'] = pit
            response = es_conn.search(
                body=query_body,
                ignore_unavailable=False,
            )

            if 'error' in response:
                logger.error('Query es error: ' + str(response))
                return
            else:
                hits_data = response.get('hits', {}).get('hits', [])
                aggs_data = response.get('aggregations', {})

                if is_metric:
                    if len(hits_data) == 0 or len(aggs_data) == 0:
                        logger.info('No data found in hits or aggregations')
                        return
                else:
                    if len(hits_data) == 0:
                        logger.info('No data found in hits')
                        return

                if is_metric:
                    for item in hits_data:
                        metric_message.append(item)

                    if len(aggs_data) > 0:
                        metric_message.append({"_aggregations": aggs_data, "sampling_timestamp": sampling_timestamp})
                else:
                    for item in hits_data:
                        messages.put(item)

                # next query
                last_time = response.get('hits').get('hits')[-1].get('sort')
                pit = response.get('pit_id')

        except Exception as e:
            logger.error('Query log error.\n{}'.format(str(e)))
            return

    if len(metric_message) > 0:
        messages.put(metric_message)


def process_parse_messages(log_queue, cli_config_vars, if_config_vars, agent_config_vars, messages, datas):
    worker_configurer(log_queue, cli_config_vars['log_level'])
    logger = logging.getLogger('worker')
    logger.debug('Started data parse process ......')

    log_compression_interval = if_config_vars['log_compression_interval']
    collector_process = cli_config_vars['collector']
    is_metric = 'METRIC' in if_config_vars['project_type']
    sampling_interval = if_config_vars['sampling_interval']

    project_name = if_config_vars['project_name']
    timestamp_timezone = agent_config_vars['target_timestamp_timezone'] * 1000

    document_root_field = agent_config_vars['document_root_field']
    component_field = agent_config_vars['component_field']
    default_component_name = agent_config_vars['default_component_name']
    default_instance_name = agent_config_vars['default_instance_name']
    aggregation_data_fields = agent_config_vars['aggregation_data_fields']

    count = 0
    collector_quit = 0
    while True:
        current_time = time.time()
        try:
            message = messages.get()
            if message == CLOSED_MESSAGE:
                collector_quit += 1
                if collector_quit >= collector_process:
                    logger.debug('All logs parsed.')
                    break
                else:
                    continue

            last_log_time = logCompressState.get('_parse_messages')
            needs_log_data = False
            if cli_config_vars['testing'] and (
                    not last_log_time or current_time - last_log_time > log_compression_interval):
                needs_log_data = True
                logCompressState['_parse_messages'] = current_time
                logger.info('Raw data:\n' + pformat(message))

            if not isinstance(message, list):
                data_messages_list = [message]
            else:
                data_messages_list = message

            metric_data_entries = []

            for data_message in data_messages_list:

                # get source
                message_source = data_message.get(document_root_field, {}) if document_root_field else data_message
                aggs_data = data_message.get('_aggregations', {})
                project = project_name

                if len(message_source) > 0:
                    # get project
                    if agent_config_vars['project_field']:
                        project = message_source.get(agent_config_vars['project_field'])
                        if not project:
                            continue
                        # filter by project whitelist
                        if agent_config_vars['project_whitelist_regex'] \
                                and not agent_config_vars['project_whitelist_regex'].match(project):
                            continue
                        project = make_safe_project_string(project)

                    # get timestamp
                    timestamp_field = agent_config_vars['timestamp_field']
                    timestamp_field = timestamp_field.split('.')
                    timestamp = safe_get(message_source, timestamp_field)
                    if timestamp.isnumeric():
                        timestamp = int(timestamp)
                    else:
                        timestamp = int(arrow.get(timestamp).float_timestamp)
                    # check whether timestamp is epoch second or epoch millisecond
                    if len(str(timestamp)) == 10:
                        timestamp *= 1000

                    # set offset for timestamp
                    timestamp += timestamp_timezone
                    if is_metric:
                        timestamp = str(align_timestamp(timestamp, sampling_interval))
                    else:
                        timestamp = str(timestamp)

                    # get component name
                    component_name = None
                    component_field = component_field if component_field and len(component_field) > 0 else None
                    if component_field:
                        component_field = component_field.split('.')
                        component_name = safe_get(message_source, component_field)
                        component_name = make_safe_instance_string(component_name)

                    if not component_name and default_component_name:
                        component_name = make_safe_instance_string(default_component_name)

                    # get instance name
                    instance = None
                    # If the instance_field_regex is set, then grab the first capture group to match and set as instance
                    # syntax:  <field1 >::<regex1>,<field2>::<regex2>
                    instance_field_regex = agent_config_vars['instance_field_regex']
                    if instance_field_regex:
                        field_regex_list = instance_field_regex.split(',')
                        for field_regex in field_regex_list:
                            field_regex_vals = field_regex.split('::')
                            if len(field_regex_vals) > 1:
                                field_val = safe_get(message_source, field_regex_vals[0].split('.'))
                                if field_val and field_regex_vals[1]:
                                    if not isinstance(field_val, str):
                                        field_val = str(field_val)
                                    re = regex.compile(field_regex_vals[1])
                                    matches = re.search(field_val)
                                    if matches:
                                        instance = matches.groups()[0]
                                        break

                    if not instance:
                        instance_field = agent_config_vars['instance_field'][0] if agent_config_vars[
                                                                                       'instance_field'] and len(
                            agent_config_vars['instance_field']) > 0 else 'agent.hostname'
                        instance_field = instance_field.split('.')
                        instance = safe_get(message_source, instance_field)

                    # filter by instance whitelist
                    if agent_config_vars['instance_whitelist_regex'] \
                            and not agent_config_vars['instance_whitelist_regex'].match(instance):
                        continue

                    # add device info if has
                    device = None
                    device_field = agent_config_vars['device_field'][0] if agent_config_vars['device_field'] and len(
                        agent_config_vars['device_field']) > 0 else ''
                    if device_field and len(device_field) > 0:
                        device_field = device_field.split('.')
                        device = safe_get(message_source, device_field)
                    if agent_config_vars['device_field_regex']:
                        matches = agent_config_vars['device_field_regex'].match(device)
                        if not matches or 'device' not in matches.groupdict().keys():
                            logger.debug('Parse message failed with device_field_regex: {}'.format(device))
                            continue
                        device = matches.group('device')
                    full_instance = make_safe_instance_string(instance, device)

                    # get data
                    data_entry = None
                    if is_metric:
                        data_fields = agent_config_vars['data_fields'] if agent_config_vars['data_fields'] and len(
                            agent_config_vars['data_fields']) > 0 else []
                        data = safe_get_metric_data(message_source, data_fields, logger)
                        if bool(data):
                            # build metric entry
                            data_entry = prepare_data_entry(if_config_vars, str(int(timestamp)), data, component_name,
                                                            full_instance)
                    else:
                        data_fields = agent_config_vars['data_fields'] if agent_config_vars['data_fields'] and len(
                            agent_config_vars['data_fields']) > 0 else None
                        data = safe_get_data(message_source, data_fields, logger)

                        # build log entry
                        data_entry = prepare_data_entry(if_config_vars, str(int(timestamp)), data, component_name,
                                                        full_instance)

                    if data_entry:
                        data_entry['project'] = project
                        data_entry['data_size'] = getsizeof(str(data))
                        if needs_log_data:
                            logger.info('Parsed data:\n' + pformat(data_entry))

                        if is_metric:
                            metric_data_entries.append(data_entry)
                        else:
                            datas.put(data_entry)

                if is_metric and len(aggs_data) > 0:
                    timestamp = data_message.get('sampling_timestamp', 0)

                    component_name = None
                    full_instance = None
                    if default_component_name:
                        component_name = make_safe_instance_string(default_component_name)

                    if default_instance_name:
                        full_instance = make_safe_instance_string(default_instance_name)

                    if full_instance and timestamp:
                        data = {}
                        for key, value in aggs_data.items():
                            val = safe_get_metric_value(value, aggregation_data_fields, logger)
                            metric_name = make_safe_metric_key(key)
                            if val is not None:
                                data[metric_name] = val

                        timestamp = str(align_timestamp(timestamp, sampling_interval))
                        if bool(data):
                            # build metric entry
                            data_entry = prepare_data_entry(if_config_vars, str(int(timestamp)), data, component_name,
                                                            full_instance)
                            if data_entry:
                                data_entry['project'] = project
                                data_entry['data_size'] = getsizeof(str(data))
                                metric_data_entries.append(data_entry)

            # merge metric data
            metric_data_dict = {}
            for metric_data_entry in metric_data_entries:
                timestamp = metric_data_entry['timestamp']
                project = metric_data_entry['project']
                component_name = metric_data_entry['componentName']
                data_size = metric_data_entry['data_size']
                if not component_name:
                    component_name = ''
                instance_name = metric_data_entry['instanceName']
                key = project + '_' + component_name + '_' + instance_name + '_' + timestamp
                data = metric_data_entry.get('data')
                if key not in metric_data_dict:
                    metric_data_dict[key] = {
                        'timestamp': timestamp,
                        'project': project,
                        'componentName': component_name,
                        'instanceName': instance_name,
                        'data': data,
                        'data_size': data_size
                    }
                else:
                    metric_data_dict[key]['data'].update(data)
                    metric_data_dict[key]['data_size'] += data_size

            for key, metric_data in metric_data_dict.items():
                datas.put(metric_data)

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
                            sys.exit(1)
                        meta_info['projects'][project] = True

            if project not in project_tracks.keys():
                project_tracks[project] = {'current_row': [], 'line_count': 0, 'data_size': 0}
            project_tracks[project]['current_row'].append(message)
            project_tracks[project]['line_count'] += 1
            project_tracks[project]['data_size'] += message.pop('data_size')

            # check the buffer every BUFFER_CHECK_COUNT lines
            if project_tracks[project]['line_count'] % BUFFER_CHECK_COUNT == 0 \
                    and project_tracks[project]['data_size'] >= if_config_vars['chunk_size']:
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


def get_agent_config_vars(logger, config_ini):
    """ Read and parse config.ini """
    """ get config.ini vars """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False
    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)

        elasticsearch_kwargs = {}
        es_uris = None
        query_json = None
        query_chunk_size = None
        indeces = None
        his_time_range = None

        project_whitelist_regex = None
        instance_whitelist_regex = None
        try:
            # elasticsearch settings
            elasticsearch_config = {
                'port': config_parser.get('elasticsearch', 'port'),
                'http_auth': config_parser.get('elasticsearch', 'http_auth'),
                'use_ssl': config_parser.get('elasticsearch', 'use_ssl'),
                'ssl_version': config_parser.get('elasticsearch', 'ssl_version'),
                'ssl_assert_hostname': config_parser.get('elasticsearch', 'ssl_assert_hostname'),
                'ssl_assert_fingerprint': config_parser.get('elasticsearch', 'ssl_assert_fingerprint'),
                'verify_certs': config_parser.get('elasticsearch', 'verify_certs'),
                'ca_certs': config_parser.get('elasticsearch', 'ca_certs'),
                'client_cert': config_parser.get('elasticsearch', 'client_cert'),
                'client_key': config_parser.get('elasticsearch', 'client_key')
            }

            # only keep settings with values
            elasticsearch_kwargs = {k: v for (k, v) in list(elasticsearch_config.items()) if v}

            # handle boolean setting
            use_ssl = elasticsearch_kwargs.get('use_ssl')
            if use_ssl and use_ssl.lower() == 'true':
                elasticsearch_kwargs['use_ssl'] = True

            ssl_assert_hostname = elasticsearch_kwargs.get('ssl_assert_hostname')
            if ssl_assert_hostname and ssl_assert_hostname.lower() == 'true':
                elasticsearch_kwargs['ssl_assert_hostname'] = True

            ssl_assert_fingerprint = elasticsearch_kwargs.get('ssl_assert_fingerprint')
            if ssl_assert_fingerprint and ssl_assert_fingerprint.lower() == 'true':
                elasticsearch_kwargs['ssl_assert_fingerprint'] = True

            verify_certs = elasticsearch_kwargs.get('verify_certs')
            if verify_certs and verify_certs.lower() == 'true':
                elasticsearch_kwargs['verify_certs'] = True
            else:
                elasticsearch_kwargs['verify_certs'] = False

            es_uris = config_parser.get('elasticsearch', 'es_uris')
            query_json_str = config_parser.get('elasticsearch', 'query_json')
            query_json_file = config_parser.get('elasticsearch', 'query_json_file')
            query_chunk_size = config_parser.get('elasticsearch', 'query_chunk_size')
            indeces = config_parser.get('elasticsearch', 'indeces')

            # time range
            his_time_range = config_parser.get('elasticsearch', 'his_time_range')

            # proxies
            agent_http_proxy = config_parser.get('elasticsearch', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('elasticsearch', 'agent_https_proxy')

            # logs
            project_field = config_parser.get('elasticsearch', 'project_field')
            project_whitelist = config_parser.get('elasticsearch', 'project_whitelist')

            # message parsing
            document_root_field = config_parser.get('elasticsearch', 'document_root_field', raw=True)
            component_field = config_parser.get('elasticsearch', 'component_field', raw=True)
            default_component_name = config_parser.get('elasticsearch', 'default_component_name', raw=True)
            instance_field = config_parser.get('elasticsearch', 'instance_field', raw=True)
            instance_field_regex = config_parser.get('elasticsearch', 'instance_field_regex', raw=True)
            instance_whitelist = config_parser.get('elasticsearch', 'instance_whitelist')
            default_instance_name = config_parser.get('elasticsearch', 'default_instance_name', raw=True)
            device_field = config_parser.get('elasticsearch', 'device_field', raw=True)
            device_field_regex = config_parser.get('elasticsearch', 'device_field_regex', raw=True)
            timestamp_field = config_parser.get('elasticsearch', 'timestamp_field', raw=True) or '@timestamp'
            target_timestamp_timezone = config_parser.get('elasticsearch', 'target_timestamp_timezone',
                                                          raw=True) or 'UTC'
            timestamp_format = config_parser.get('elasticsearch', 'timestamp_format', raw=True)
            timezone = config_parser.get('elasticsearch', 'timezone') or 'UTC'
            data_fields = config_parser.get('elasticsearch', 'data_fields', raw=True)
            aggregation_data_fields = config_parser.get('elasticsearch', 'aggregation_data_fields', raw=True)

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        if len(project_whitelist) != 0:
            try:
                project_whitelist_regex = regex.compile(project_whitelist)
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'project_whitelist')

        # uris required
        if len(es_uris) != 0:
            es_uris = [x.strip() for x in es_uris.split(',') if x.strip()]
        else:
            return config_error(logger, 'es_uris')

        query_json = None
        if len(query_json_file) != 0:
            try:
                json_path = os.path.join(os.path.dirname(config_ini), query_json_file)
                with open(json_path, 'r') as json_path:
                    query_json = json.load(json_path)
            except Exception as ex:
                logger.error(ex)
                return config_error(logger, 'query_json_file')
        else:
            if len(query_json_str) != 0:
                try:
                    query_json = json.loads(query_json)
                except Exception as e:
                    logger.error('Agent not correctly configured (query_json). Dropping.')

        if len(query_chunk_size) != 0:
            try:
                query_chunk_size = int(query_chunk_size)
            except Exception as e:
                logger.error('Agent not correctly configured (query_chunk_size). Use 5000 by default.')
                query_chunk_size = 5000

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

        # proxies
        agent_proxies = dict()
        if len(agent_http_proxy) > 0:
            agent_proxies['http'] = agent_http_proxy
        if len(agent_https_proxy) > 0:
            agent_proxies['https'] = agent_https_proxy

        # fields
        project_field = project_field.strip() if project_field else None
        if document_root_field == '""':
            document_root_field = None
        else:
            document_root_field = document_root_field.strip() if document_root_field else '_source'
        component_field = component_field.strip() if component_field else None
        default_component_name = default_component_name.strip() if default_component_name else None
        instance_fields = [x.strip() for x in instance_field.split(',') if x.strip()]
        default_instance_name = default_instance_name.strip() if default_instance_name else None
        device_fields = [x.strip() for x in device_field.split(',') if x.strip()]
        if len(data_fields) != 0:
            data_fields = data_fields.split(',')
            for instance_field in instance_fields:
                if instance_field in data_fields:
                    data_fields.pop(data_fields.index(instance_field))
            for device_field in device_fields:
                if device_field in data_fields:
                    data_fields.pop(data_fields.index(device_field))
            if timestamp_field in data_fields:
                data_fields.pop(data_fields.index(timestamp_field))

        if len(aggregation_data_fields) != 0:
            aggregation_data_fields = aggregation_data_fields.split(',')
        else:
            aggregation_data_fields = ['doc_count']

        if len(instance_field_regex) != 0:
            try:
                for field_regex in instance_field_regex.split(','):
                    re = field_regex.split('::')[1]
                    regex.compile(re)
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'instance_field_regex')

        if len(device_field_regex) != 0:
            try:
                device_field_regex = regex.compile(device_field_regex)
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'device_field_regex')

        # add parsed variables to a global
        config_vars = {
            'elasticsearch_kwargs': elasticsearch_kwargs,
            'es_uris': es_uris,
            'query_json': query_json,
            'query_chunk_size': query_chunk_size,
            'indeces': indeces,
            'his_time_range': his_time_range,
            'project_field': project_field,
            'project_whitelist_regex': project_whitelist_regex,
            'document_root_field': document_root_field,
            'component_field': component_field,
            'default_component_name': default_component_name,
            'instance_field': instance_fields,
            'instance_field_regex': instance_field_regex,
            'instance_whitelist_regex': instance_whitelist_regex,
            'default_instance_name': default_instance_name,
            'device_field': device_fields,
            'device_field_regex': device_field_regex,
            'data_fields': data_fields,
            'aggregation_data_fields': aggregation_data_fields,
            'timestamp_field': timestamp_field,
            'target_timestamp_timezone': target_timestamp_timezone,
            'timezone': timezone,
            'timestamp_format': timestamp_format,
            'proxies': agent_proxies,
        }

        return config_vars


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
    """
    """
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
    parser.add_option('-p', '--process', action='store', dest='process', default=2,
                      help='Number of processes for each agent to use for multithreading')
    parser.add_option('--timeout', action='store', dest='timeout', default=5 * 60,
                      help='Seconds of timeout for all worker processes')
    parser.add_option('-l', '--collector', action='store', dest='collector', default=5,
                      help='Number of processes for each agent to collect data from elastic search')
    (options, args) = parser.parse_args()

    config_vars = {
        'config': options.config if os.path.isfile(options.config) else abs_path_from_cur('conf.d/config.ini'),
        'testing': False,
        'log_level': logging.INFO,
        'process': int(options.process),
        'timeout': int(options.timeout),
        'collector': int(options.collector)
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


def safe_get_metric_value(dct, keys, logger):
    # flatten multiple level dict object into key value and ignore string values
    flat_json = flatten_json(dct)
    filtered_json = {k: v for k, v in flat_json.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}

    val = None

    if keys:
        for key in keys:
            for k, v in filtered_json.items():
                if match_patterns(k, [key]):
                    val = v
                    break
            if val:
                break
    return val


def safe_get_metric_data(dct, keys, logger):
    # flatten multiple level dict object into key value and ignore string values
    flat_json = flatten_json(dct)
    filtered_json = {k: v for k, v in flat_json.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}

    if keys:
        filtered_json = {k: v for k, v in filtered_json.items() if match_patterns(k, keys)}

    return filtered_json


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
                except:
                    data[named_key[0]] = dct[named_key[1]]
            else:
                try:
                    data[named_key[0]] = json.loads(dct[named_key[0]])
                except:
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
    # return len(bytearray(json.dumps(json_data)))
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
def convert_to_metric_data(logger, chunk_metric_data, if_config_vars):
    to_send_data_dict = dict()
    to_send_data_dict['licenseKey'] = if_config_vars['license_key']
    to_send_data_dict['userName'] = if_config_vars['user_name']

    data_dict = dict()
    data_dict['projectName'] = if_config_vars['project_name']
    data_dict['userName'] = if_config_vars['user_name']
    if 'system_name' in if_config_vars:
        data_dict['systemName'] = if_config_vars['system_name']
    data_dict['iat'] = get_agent_type_from_project_type(if_config_vars)
    if 'sampling_interval' in if_config_vars:
        data_dict['si'] = str(if_config_vars['sampling_interval'])

    instance_data_map = dict()
    for chunk in chunk_metric_data:
        instance_name = chunk['instanceName']
        component_name = chunk.get('componentName')
        timestamp = chunk['timestamp']
        data = chunk['data']
        if data and timestamp and instance_name:
            ts = int(timestamp)
            if instance_name not in instance_data_map:
                instance_data_map[instance_name] = {'in': instance_name, 'cn': component_name, 'dit': {}, }

            if timestamp not in instance_data_map[instance_name]['dit']:
                instance_data_map[instance_name]['dit'][timestamp] = {'t': ts, 'm': []}

            data_set = instance_data_map[instance_name]['dit'][timestamp]['m']
            for metric_name, metric_value in data.items():
                float_value = safe_string_to_float(metric_value)
                if float_value is not None:
                    data_set.append({'m': metric_name, 'v': float_value})
                else:
                    data_set.append({'m': metric_name, 'v': 0.0})

    data_dict['idm'] = instance_data_map
    to_send_data_dict['data'] = data_dict

    return to_send_data_dict


def send_data_to_if(logger, c_config, if_config_vars, track, chunk_metric_data, project):
    timeout = None
    if c_config:
        timeout = c_config['timeout'] if c_config['timeout'] > 0 else None

    send_data_time = time.time()

    # prepare data for metric/log streaming agent
    data_to_post = None
    json_to_post = None
    if 'METRIC' in if_config_vars['project_type']:
        json_to_post = convert_to_metric_data(logger, chunk_metric_data, if_config_vars)
        logger.debug(json_to_post)
        post_url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v2/metric-data-receive')
    else:
        data_to_post = initialize_api_post_data(logger, if_config_vars, project)
        if 'DEPLOYMENT' in if_config_vars['project_type'] or 'INCIDENT' in if_config_vars['project_type']:
            for chunk in chunk_metric_data:
                chunk['data'] = json.dumps(chunk['data'])
        data_to_post[get_data_field_from_project_type(if_config_vars)] = json.dumps(chunk_metric_data)
        logger.debug(data_to_post)
        post_url = urllib.parse.urljoin(if_config_vars['if_url'], get_api_from_project_type(if_config_vars))

    logger.debug('First:\n' + str(chunk_metric_data[0]))
    logger.debug('Last:\n' + str(chunk_metric_data[-1]))
    logger.debug('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
    logger.debug('Total Lines: ' + str(track['line_count']))

    # do not send if only testing
    if c_config['testing']:
        return

    logger.debug('First:\n' + str(chunk_metric_data[0]))
    logger.debug('Last:\n' + str(chunk_metric_data[-1]))
    logger.info('Total Lines: ' + str(len(chunk_metric_data)))

    # send the data
    if data_to_post:
        logger.info('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
        logger.debug(data_to_post)

        send_request(logger, post_url, 'POST', 'Could not send request to IF',
                     str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.', data=data_to_post,
                     verify=False, proxies=if_config_vars['if_proxies'])
    elif json_to_post:
        logger.info('Total Data (bytes): ' + str(get_json_size_bytes(json_to_post)))
        logger.debug(json_to_post)
        send_request(logger, post_url, 'POST', 'Could not send request to IF',
                     str(get_json_size_bytes(json_to_post)) + ' bytes of data are reported.', json=json_to_post,
                     verify=False, proxies=if_config_vars['if_proxies'])

    logger.debug('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def send_request(logger, url, mode='GET', failure_message='Failure!', success_message='Success!',
                 **request_passthrough):
    """ sends a request to the given url """
    # determine if post or get (default)
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
                                timeout=timeout)
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
                                    proxies=if_config_vars['if_proxies'], timeout=timeout)
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

    if enable_log_rotation:
        # create log output folder if not exists
        Path(LOG_DIR).mkdir(parents=True, exist_ok=True)
        handler = TimedRotatingFileHandler(AGENT_LOG_FILE, when='MIDNIGHT', backupCount=log_backup_count)
        handler.setFormatter(formatter)
        root.addHandler(handler)
    else:
        # route INFO and DEBUG logging to stdout from stderr
        logging_handler_out = logging.StreamHandler(sys.stdout)
        logging_handler_out.setLevel(logging.DEBUG)
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
    h = QueueHandler(q)  # Just the one handler needed
    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(level)


def main():
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
    timer = arrow.utcnow().float_timestamp

    # get config
    cli_config_vars = get_cli_config_vars()

    # capture warnings to logging system
    logging.captureWarnings(True)

    # change elasticsearch logger level
    es_logger = logging.getLogger('elasticsearch')
    es_logger.setLevel(logging.WARNING)

    # logger queue, must use Manager().Queue() because agent may use pool create process
    m = multiprocessing.Manager()
    log_queue = m.Queue()

    # set logger
    worker_configurer(log_queue, cli_config_vars['log_level'])
    logger = logging.getLogger('worker')

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)

    # get config file
    logger.info("Get Config File")
    config_file = config_ini_path(cli_config_vars)
    agent_config_vars = get_agent_config_vars(logger, config_file)
    if not agent_config_vars:
        time.sleep(1)
        sys.exit(1)

    logger.info("Get IF Config Vars")
    if_config_vars = get_if_config_vars(logger, config_file, agent_config_vars)
    if not if_config_vars:
        time.sleep(1)
        sys.exit(1)

    if 'METRIC' in if_config_vars['project_type']:
        cli_config_vars['collector'] = 1

    logger.info("Start listener process")
    listener = Process(target=listener_process, args=(log_queue, cli_config_vars, if_config_vars))
    listener.daemon = True
    listener.start()

    logger.info(cli_data_block)
    logger.info("Process start with config: {}".format(config_file))
    print_summary_info(logger, if_config_vars, agent_config_vars)

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
                    args=(log_queue, cli_config_vars, if_config_vars, agent_config_vars, messages, worker_process,
                          time_now, collector_id))
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

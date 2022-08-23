#!/usr/bin/env python
import configparser
import json
import logging
import os
import queue
import socket
import sys
import time
import urllib.parse
import http.client
import shlex
import traceback
import signal
from sys import getsizeof
from optparse import OptionParser
from threading import Thread, Lock
from logging.handlers import QueueHandler
import multiprocessing
from multiprocessing import Process, Queue

import arrow
import pytz
import regex
import requests
from kafka import KafkaConsumer

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
HOSTNAME = socket.gethostname().partition('.')[0]
ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
JSON_LEVEL_DELIM = '.'
CSV_DELIM = r",|\t"
ATTEMPTS = 3


def process_get_data(log_queue, cli_config_vars, if_config_vars, agent_config_vars, messages):
    worker_configurer(log_queue, cli_config_vars['log_level'])
    logger = logging.getLogger('worker')
    logger.info('Started data consumer process ......')
    consumer = KafkaConsumer(**agent_config_vars['kafka_kwargs'])
    if len(consumer.topics()) == 0:
        config_error(logger, 'kafka connection error')
        sys.exit(1)
    # subscribe to given topics
    consumer.subscribe(agent_config_vars['topics'])
    while True:
        try:
            msg_pack = consumer.poll(timeout_ms=10)

            if not msg_pack:
                logger.info('No data received, waiting...')
                time.sleep(20)
                continue

            for tp, msgs in msg_pack.items():
                for msg in msgs:
                    msg_value = msg.value
                    if isinstance(msg_value, bytes):
                        msg_value = msg_value.decode("utf-8")
                    if agent_config_vars['initial_filter'] \
                            and not agent_config_vars['initial_filter'].search(msg_value):
                        continue
                    messages.put(msg_value)

        except Exception as e:
            # Handle any exception here
            logger.error('Error when poll messages')
            logger.error(e)
            logger.debug(traceback.format_exc())

    logger.info('Closed data process......')


def process_parse_messages(log_queue, cli_config_vars, if_config_vars, agent_config_vars, messages, project_mapping_dict, datas):
    worker_configurer(log_queue, cli_config_vars['log_level'])
    logger = logging.getLogger('worker')
    logger.info('Started data parse process ......')

    count = 0
    while True:
        try:
            msg_value = messages.get()
            logger.debug(msg_value)

            message = {}
            if agent_config_vars['raw_regex']:
                matches = agent_config_vars['raw_regex'].match(msg_value)
                if not matches:
                    logger.debug('Parse message failed with raw_regex: {}'.format(msg_value))
                    continue
                message = matches.groupdict()
            else:
                message = json.loads(msg_value)
            # get project
            project = if_config_vars['project_name']
            system_name = if_config_vars['system_name']
            if agent_config_vars['project_field']:
                project = message.get(agent_config_vars['project_field'])
                if not project:
                    continue
                # filter by project whitelist
                if agent_config_vars['project_whitelist_regex'] \
                        and not agent_config_vars['project_whitelist_regex'].match(project):
                    continue
                project = make_safe_project_string(project, project_mapping_dict, agent_config_vars['project_separator'])

            # instance name
            instance = 'Application'
            instance_field = agent_config_vars['instance_field']
            if instance_field and len(instance_field) > 0:
                instances = [message.get(d) for d in instance_field if message.get(d)]
                instance = '-'.join(instances) if len(instances) > 0 else None
            # filter by instance whitelist
            if agent_config_vars['instance_whitelist_regex'] \
                    and not agent_config_vars['instance_whitelist_regex'].match(instance):
                continue

            # add device info if has
            device = None
            device_field = agent_config_vars['device_field']
            if device_field and len(device_field) > 0:
                devices = [message.get(d) for d in device_field if message.get(d)]
                device = '-'.join(devices) if len(devices) > 0 else None
            full_instance = make_safe_instance_string(instance, device)

            # get timestamp
            timestamp = message.get(agent_config_vars['timestamp_field'][0])
            timestamp = int(timestamp) if len(str(timestamp)) > 10 else int(timestamp) * 1000
            # set offset for timestamp
            timestamp += agent_config_vars['target_timestamp_timezone'] * 1000
            timestamp = str(timestamp)

            # metric name
            for field in agent_config_vars['metric_fields']:
                data_field = field
                data_value = message.get(field)
                if field.find("::") != -1:
                    metric_name, metric_value = field.split('::')
                    data_field = message.get(metric_name)
                    data_value = message.get(metric_value)
                if not data_field:
                    continue

                # filter by metric whitelist
                if agent_config_vars['metric_whitelist_regex'] \
                        and not agent_config_vars['metric_whitelist_regex'].match(data_field):
                    continue

                metric_key = '{}[{}]'.format(data_field, full_instance)
                if isinstance(project, dict):
                    for key, value in project.items():
                        datas.put({
                            'project': value['custom_project'],
                            'system_name': value['custom_system'] or system_name,
                            'timestamp': timestamp,
                            'full_instance': full_instance,
                            'metric_key': metric_key,
                            'value': str(data_value)
                        })
                else:
                    datas.put({
                        'project': project,
                        'system_name': system_name,
                        'timestamp': timestamp,
                        'full_instance': full_instance,
                        'metric_key': metric_key,
                        'value': str(data_value)
                    })

        except Exception as e:
            logger.warn('Error when parsing message')
            logger.warn(e)
            logger.debug(traceback.format_exc())
            continue

        count += 1
        if count % 1000 == 0:
            logger.info('Parse {0} messages'.format(count))
    logger.info('Parse {0} messages'.format(count))


def process_build_buffer(logger, c_config, if_config_vars, agent_config_vars, datas):
    lock = Lock()
    metric_buffer = {}

    # check buffer and send data
    loop_thead = Thread(target=func_check_buffer,
                        args=(lock, metric_buffer, logger, c_config, if_config_vars, agent_config_vars))
    loop_thead.setDaemon(True)
    loop_thead.start()

    # build buffer
    while True:
        try:
            message = datas.get()
            project = message['project']
            system_name = message['system_name']
            timestamp = message['timestamp']
            full_instance = message['full_instance']
            metric_key = message['metric_key']
            value = message['value']
            if lock.acquire():
                # build buffer dict
                if project not in metric_buffer:
                    metric_buffer[project] = {'buffer_dict': {}, "times": []}
                if timestamp not in metric_buffer[project]['buffer_dict']:
                    metric_buffer[project]['buffer_dict'][timestamp] = {}
                    metric_buffer[project]['times'].append(timestamp)
                if full_instance not in metric_buffer[project]['buffer_dict'][timestamp]:
                    metric_buffer[project]['buffer_dict'][timestamp][full_instance] = {"timestamp": timestamp}
                metric_buffer[project]['buffer_dict'][timestamp][full_instance][metric_key] = value
                metric_buffer[project]['buffer_dict'][timestamp][full_instance]['system_name'] = system_name
                lock.release()

        except Exception as e:
            logger.warn('Error when build buffer message')
            logger.warn(e)
            logger.debug(traceback.format_exc())
            continue


def func_check_buffer(lock, metric_buffer, logger, c_config, if_config_vars, agent_config_vars):
    while True:
        buffer_check_thead = Thread(target=check_buffer,
                                    args=(
                                        lock, metric_buffer, logger, c_config, if_config_vars,
                                        agent_config_vars))
        buffer_check_thead.start()
        buffer_check_thead.join()
        time.sleep(min(60, if_config_vars['sampling_interval']))


def check_buffer(lock, metric_buffer, logger, c_config, if_config_vars, agent_config_vars):
    utc_time_now = arrow.utcnow().float_timestamp
    logger.info('Start clear buffer: {}'.format(arrow.get(utc_time_now).format()))

    clear_time = utc_time_now - agent_config_vars['buffer_sampling_interval_multiple'] * if_config_vars[
        'sampling_interval']
    clear_time *= 1000
    # empty data to send
    project_data_map = {}
    if lock.acquire():
        for project, buffer in metric_buffer.items():
            if project not in project_data_map:
                project_data_map[project] = []

            buffer_times = []
            for timestamp in buffer['times']:
                if int(timestamp) >= clear_time:
                    buffer_times.append(timestamp)
                else:
                    buffer_dict_time = buffer['buffer_dict'].pop(timestamp)
                    buffer_values = list(buffer_dict_time.values())
                    project_data_map[project].extend(buffer_values)
            # reset times
            buffer['times'] = buffer_times
        lock.release()

    # send data
    for project, buffer in project_data_map.items():
        # check project name first
        if len(buffer) <= 0:
            continue
        check_success = check_project_exist(logger, if_config_vars, project, buffer[0]['system_name'])
        if not check_success:
            sys.exit(1)

        track = {'current_row': [], 'line_count': 0}
        for row in buffer:
            track['current_row'].append(row)
            track['line_count'] += 1
            if get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
                logger.debug('Sending buffer chunk')
                send_data_to_if(logger, c_config, if_config_vars, track, track['current_row'], project)
                reset_track(track)

        # last chunk
        if len(track['current_row']) > 0:
            logger.debug('Sending last chunk')
            send_data_to_if(logger, c_config, if_config_vars, track, track['current_row'], project)
            reset_track(track)


def get_multiple_kafka_info(logger, kafka_config, if_config_vars):
    if not os.path.exists(kafka_config):
        logger.error('No config file found. Exiting...')
        return False
    with open(kafka_config) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)
        try:
            kafka_info = {}
            topics = []
            # agent settings
            kafka_config = {
                # hardcoded
                'api_version': (0, 9),
                'auto_offset_reset': 'latest',
                'consumer_timeout_ms': 30 * if_config_vars['sampling_interval'] * 1000 if 'METRIC' in if_config_vars[
                    'project_type'] or 'LOG' in if_config_vars['project_type'] else None,

                # consumer settings
                'bootstrap_servers': config_parser.get('agent', 'bootstrap_servers'),
                'group_id': config_parser.get('agent', 'group_id'),
                'client_id': config_parser.get('agent', 'client_id'),

                # SSL
                'security_protocol': 'SSL' if config_parser.get('agent', 'security_protocol') == 'SSL' else 'PLAINTEXT',
                'ssl_context': config_parser.get('agent', 'ssl_context'),
                'ssl_cafile': config_parser.get('agent', 'ssl_cafile'),
                'ssl_certfile': config_parser.get('agent', 'ssl_certfile'),
                'ssl_keyfile': config_parser.get('agent', 'ssl_keyfile'),
                'ssl_password': config_parser.get('agent', 'ssl_password'),
                'ssl_crlfile': config_parser.get('agent', 'ssl_crlfile'),
                'ssl_ciphers': config_parser.get('agent', 'ssl_ciphers'),
                'ssl_check_hostname': config_parser.get('agent', 'ssl_check_hostname'),

                # SASL
                'sasl_mechanism': config_parser.get('agent', 'sasl_mechanism'),
                'sasl_plain_username': config_parser.get('agent', 'sasl_plain_username'),
                'sasl_plain_password': config_parser.get('agent', 'sasl_plain_password'),
                'sasl_kerberos_service_name': config_parser.get('agent', 'sasl_kerberos_service_name'),
                'sasl_kerberos_domain_name': config_parser.get('agent', 'sasl_kerberos_domain_name'),
                'sasl_oauth_token_provider': config_parser.get('agent', 'sasl_oauth_token_provider')
            }
            # only keep settings with values
            kafka_kwargs = {k: v for (k, v) in list(kafka_config.items()) if v}

            # handle boolean setting
            if kafka_kwargs.get('ssl_check_hostname'):
                kafka_kwargs['ssl_check_hostname'] = kafka_kwargs['ssl_check_hostname'].lower() == 'true'
            else:
                kafka_kwargs['ssl_check_hostname'] = False

            # handle required arrays
            # bootstrap serverss
            if len(kafka_kwargs.get('bootstrap_servers')) != 0:
                kafka_kwargs['bootstrap_servers'] = [x.strip() for x in kafka_kwargs['bootstrap_servers'].split(',') if
                                                     x.strip()]
            else:
                return config_error(logger, 'bootstrap_servers')
            # group_id
            if len(kafka_kwargs.get('group_id')) != 0:
                kafka_kwargs['group_id'] = kafka_kwargs['group_id'].strip()
            else:
                return config_error(logger, 'group_id')
            # topics
            if len(config_parser.get('agent', 'topics')) != 0:
                topics = [x.strip() for x in config_parser.get('agent', 'topics').split(',') if x.strip()]
            else:
                return config_error(logger, 'topics')
            partitions = config_parser.get('agent', 'partitions') or multiprocessing.cpu_count()
            return {'kafka_kwargs': kafka_kwargs, 'topics': topics, 'partitions': partitions}
        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)


def get_agent_config_vars(logger, config_ini, if_config_vars):
    """ Read and parse config.ini """
    """ get config.ini vars """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False
    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)
        try:
            # kafka config file
            kafka_connect_file = config_parser.get('agent', 'kafka_connect_file').split(',')

            project_whitelist_regex = None
            metric_whitelist_regex = None
            instance_whitelist_regex = None
            # metrics
            initial_filter = config_parser.get('agent', 'initial_filter')
            raw_regex = config_parser.get('agent', 'raw_regex')

            project_field = config_parser.get('agent', 'project_field')
            project_whitelist = config_parser.get('agent', 'project_whitelist')
            project_map_id = config_parser.get('agent', 'project_map_id')
            project_separator = config_parser.get('agent', 'project_separator')

            metric_fields = config_parser.get('agent', 'metric_fields')
            metrics_whitelist = config_parser.get('agent', 'metrics_whitelist')

            # message parsing
            timezone = config_parser.get('agent', 'timezone') or 'UTC'
            timestamp_field = config_parser.get('agent', 'timestamp_field', raw=True) or 'timestamp'
            target_timestamp_timezone = config_parser.get('agent', 'target_timestamp_timezone', raw=True) or 'UTC'
            component_field = config_parser.get('agent', 'component_field', raw=True)
            instance_field = config_parser.get('agent', 'instance_field', raw=True)
            instance_whitelist = config_parser.get('agent', 'instance_whitelist')
            device_field = config_parser.get('agent', 'device_field', raw=True)
            buffer_sampling_interval_multiple = config_parser.get('agent', 'buffer_sampling_interval_multiple')

            # proxies
            agent_http_proxy = config_parser.get('agent', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('agent', 'agent_https_proxy')

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        if len(project_whitelist) != 0:
            try:
                project_whitelist_regex = regex.compile(project_whitelist)
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'project_whitelist')

        # metrics
        if len(raw_regex) != 0:
            try:
                raw_regex = regex.compile(raw_regex)
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'raw_regex')

        if len(initial_filter) != 0:
            try:
                initial_filter = regex.compile(initial_filter)
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'initial_filter')

        if len(metrics_whitelist) != 0:
            try:
                metric_whitelist_regex = regex.compile(metrics_whitelist)
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'metrics_whitelist')

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

        if len(metric_fields) == 0:
            return config_error(logger, 'metric_fields')

        # fields
        project_field = project_field.strip() if project_field.strip() else None
        metric_fields = [x.strip() for x in metric_fields.split(',') if x.strip()]
        timestamp_fields = [x.strip() for x in timestamp_field.split(',') if x.strip()]
        instance_fields = [x.strip() for x in instance_field.split(',') if x.strip()]
        device_fields = [x.strip() for x in device_field.split(',') if x.strip()]
        buffer_sampling_interval_multiple = int(
            buffer_sampling_interval_multiple.strip()) if buffer_sampling_interval_multiple.strip() else 2

        # proxies
        agent_proxies = dict()
        if len(agent_http_proxy) > 0:
            agent_proxies['http'] = agent_http_proxy
        if len(agent_https_proxy) > 0:
            agent_proxies['https'] = agent_https_proxy

        # add parsed variables to a global
        config_vars = {
            'kafka_kwargs': '',
            'topics': '',
            'kafka_connect_file': kafka_connect_file,
            'initial_filter': initial_filter,
            'raw_regex': raw_regex,
            'project_field': project_field,
            'project_whitelist_regex': project_whitelist_regex,
            'project_separator': project_separator,
            'metric_whitelist_regex': metric_whitelist_regex,
            'project_map_id': project_map_id,
            'metric_fields': metric_fields,
            'timezone': timezone,
            'timestamp_field': timestamp_fields,
            'target_timestamp_timezone': target_timestamp_timezone,
            'component_field': component_field,
            'instance_field': instance_fields,
            "instance_whitelist_regex": instance_whitelist_regex,
            'device_field': device_fields,
            'buffer_sampling_interval_multiple': buffer_sampling_interval_multiple,
            'proxies': agent_proxies,
        }

        return config_vars


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
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data).' +
                           ' Automatically turns on verbose logging')
    (options, args) = parser.parse_args()

    config_vars = {
        'config': options.config if os.path.isdir(options.config) else abs_path_from_cur('conf.d'),
        'testing': False,
        'log_level': logging.INFO,
    }

    if options.testing:
        config_vars['testing'] = True

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
        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        # check required variables
        if len(user_name) == 0:
            return config_error(logger, 'user_name')
        if len(license_key) == 0:
            return config_error(logger, 'license_key')
        # if len(project_name) == 0:
        #     return config_error(logger, 'project_name')
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
            'TRAVEREPLAY'
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


def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))


def config_error(logger, setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(
        info))
    return False


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    # return len(bytearray(json.dumps(json_data)))
    return getsizeof(json.dumps(json_data))


def make_safe_project_string(project, project_mapping_dict, project_separator):
    """ make a safe project name string """
    # strip underscores
    # project = PIPE.sub('', project)
    # project = PROJECT_ALNUM.sub('-', project)
    project_list = project.split(project_separator)[1:-1]
    project_dict = dict()
    for every_project in project_list:
        if every_project in project_mapping_dict:
            project_dict[every_project] = {'custom_project': project_mapping_dict[every_project]['custom_project'], 'custom_system': project_mapping_dict[every_project]['custom_system']}
        else:
            project_dict[every_project] = {'custom_project': every_project, 'custom_system': ''}
    return project_dict


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


def reset_track(track):
    """ reset the track global for the next chunk """
    track['current_row'] = []
    track['line_count'] = 0


################################
# Functions to send data to IF #
################################
def send_data_to_if(logger, c_config, if_config_vars, track, chunk_metric_data, project):
    send_data_time = time.time()

    # prepare data for metric streaming agent
    data_to_post = initialize_api_post_data(logger, if_config_vars, project)
    if 'DEPLOYMENT' in if_config_vars['project_type'] or 'INCIDENT' in if_config_vars['project_type']:
        for chunk in chunk_metric_data:
            chunk['data'] = json.dumps(chunk['data'])
    data_to_post[get_data_field_from_project_type(if_config_vars)] = json.dumps(chunk_metric_data)

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


def check_project_exist(logger, if_config_vars, project, system_name):
    is_project_exist = False
    try:
        logger.info('Starting check project: ' + if_config_vars['project_name'])
        params = {
            'operation': 'check',
            'userName': if_config_vars['user_name'],
            'licenseKey': if_config_vars['license_key'],
            'projectName': project or if_config_vars['project_name'],
        }
        url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
        response = send_request(logger, url, 'POST', data=params, verify=False, proxies=if_config_vars['if_proxies'])
        if response == -1:
            logger.error('Check project error: ' + params['projectName'])
        else:
            result = response.json()
            if result['success'] is False or result['isProjectExist'] is False:
                logger.error('Check project error: ' + params['projectName'])
            else:
                is_project_exist = True
                logger.info('Check project success: ' + params['projectName'])

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
                'projectName': project or if_config_vars['project_name'],
                'systemName': system_name or if_config_vars['system_name'] or project or if_config_vars['project_name'],
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
                'projectName': project or if_config_vars['project_name'],
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
            if record.name == 'worker':
                logger = logging.getLogger(record.name)
                logger.handle(record)
        time.sleep(1)


def worker_configurer(q, level):
    h = QueueHandler(q)  # Just the one handler needed
    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(level)


# project mapping
def project_mapping(agent_config_vars):
    project_map_id = agent_config_vars['project_map_id']
    project_mapping_dict = dict()
    if len(project_map_id) > 0:
        project_mapping_list = project_map_id.split(',')
        for project in project_mapping_list:
            project_info_list = project.split('::')
            if len(project_info_list) == 2:
                project_mapping_dict[project_info_list[0]] = {"custom_project": project_info_list[1],
                                                              "custom_system": ''}
            if len(project_info_list) == 3:
                project_mapping_dict[project_info_list[0]] = {"custom_project": project_info_list[1],
                                                              "custom_system": project_info_list[2]}
    return project_mapping_dict


def main():
    # get config
    cli_config_vars = get_cli_config_vars()

    # logger queue, must use Manager().Queue() because agent may use pool create process
    m = multiprocessing.Manager()
    log_queue = m.Queue()
    listener = Process(target=listener_process, args=(log_queue, cli_config_vars))
    listener.daemon = True
    listener.start()

    # set logger
    worker_configurer(log_queue, cli_config_vars['log_level'])
    logger = logging.getLogger('worker')
    # logger = listener_configurer(cli_config_vars['log_level'])

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)
    logger.info(cli_data_block)

    # get config file
    config_file = os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini'))
    logger.info("Process start with config: {}".format(config_file))

    if_config_vars = get_if_config_vars(logger, config_file)
    if not if_config_vars:
        sys.exit(1)
    agent_config_vars = get_agent_config_vars(logger, config_file, if_config_vars)
    if not agent_config_vars:
        sys.exit(1)
    print_summary_info(logger, if_config_vars, agent_config_vars)

    # start run
    # raw data
    messages = Queue()
    # parsed data
    datas = Queue()
    # all processes
    processes = []

    for kafka_connect in agent_config_vars['kafka_connect_file']:
        kafka_info = get_multiple_kafka_info(logger, kafka_connect, if_config_vars)
        agent_config_vars.update(kafka_kwargs=kafka_info['kafka_kwargs'], topics=kafka_info['topics'])
        partitions = kafka_info['partitions']
        # consumer process
        for x in range(int(partitions)):
            d = Process(target=process_get_data,
                        args=(log_queue, cli_config_vars, if_config_vars, agent_config_vars, messages))
            d.daemon = True
            d.start()
            processes.append(d)

    project_mapping_dict = project_mapping(agent_config_vars)
    # parser process
    for x in range(multiprocessing.cpu_count()):
        d = Process(target=process_parse_messages,
                    args=(log_queue, cli_config_vars, if_config_vars, agent_config_vars, messages, project_mapping_dict, datas))
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

    # build buffer and send data
    process_build_buffer(logger, cli_config_vars, if_config_vars, agent_config_vars, datas)


if __name__ == "__main__":
    main()

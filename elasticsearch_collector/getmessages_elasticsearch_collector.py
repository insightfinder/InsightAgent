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

from elasticsearch import Elasticsearch

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

    # get conn
    es_conn = get_es_connection(logger, agent_config_vars)
    if not es_conn:
        return

    # time query
    timestamp_field = agent_config_vars['timestamp_field']

    # parse sql string by params
    logger.debug('history range config: {}'.format(agent_config_vars['his_time_range']))
    if agent_config_vars['his_time_range']:
        logger.debug('Using time range for replay data')
        for timestamp in range(agent_config_vars['his_time_range'][0],
                               agent_config_vars['his_time_range'][1],
                               if_config_vars['sampling_interval']):
            start_time = timestamp
            end_time = timestamp + if_config_vars['sampling_interval']

            # build query
            query_body = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "range": {
                                    timestamp_field: {
                                        "format": "epoch_second",
                                        'gte': start_time,
                                        'lte': end_time
                                    }
                                }
                            }
                        ],
                    },

                }
            }
            # add user-defined query
            if isinstance(agent_config_vars['query_json'], dict):
                merge(agent_config_vars['query_json'], query_body)

            # get total number of messages
            response = es_conn.search(
                body=query_body,
                index=agent_config_vars['indeces'],
                ignore_unavailable=False,
                size=0
            )
            total = response.get('hits', {}).get('total', 0)
            if not isinstance(total, int):
                total = total.get('value', 0)

            # validate successs
            if 'error' in response:
                logger.error('Query es error: ' + str(response))
                return

            # build query with chunk
            start_index = 0
            while start_index < total:
                query = dict({'from': start_index, "size": agent_config_vars['query_chunk_size']}, **query_body)
                start_index += agent_config_vars['query_chunk_size']

                data = query_messages_elasticsearch(logger, if_config_vars, agent_config_vars, es_conn, query)
                parse_messages_elasticsearch(logger, if_config_vars, agent_config_vars, log_buffer, track, data)

                # clear log buffer when piece of chunk range end
                clear_log_buffer(logger, c_config, if_config_vars, log_buffer, track)

    else:
        logger.debug('Using current time for streaming data')
        time_now = int(arrow.utcnow().float_timestamp)
        start_time = time_now - if_config_vars['sampling_interval']
        end_time = time_now

        # build query
        query_body = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "range": {
                                timestamp_field: {
                                    "format": "epoch_second",
                                    'gte': start_time,
                                    'lte': end_time
                                }
                            }
                        }
                    ],
                },

            }
        }
        # add user-defined query
        if isinstance(agent_config_vars['query_json'], dict):
            merge(agent_config_vars['query_json'], query_body)

        # get total number of messages
        response = es_conn.search(
            body=query_body,
            index=agent_config_vars['indeces'],
            ignore_unavailable=False,
            size=0)
        total = response.get('hits').get('total', 0)

        if not isinstance(total, int):
            total = total.get('value', 0)

        # validate successs
        if 'error' in response:
            logger.error('Query es error: ' + str(response))
            return

        # build query with chunk
        start_index = 0
        while start_index < total:
            query = dict({'from': start_index, "size": agent_config_vars['query_chunk_size']}, **query_body)
            start_index += agent_config_vars['query_chunk_size']

            data = query_messages_elasticsearch(logger, if_config_vars, agent_config_vars, es_conn, query)
            parse_messages_elasticsearch(logger, if_config_vars, agent_config_vars, log_buffer, track, data)

            # clear log buffer when piece of chunk range end
            clear_log_buffer(logger, c_config, if_config_vars, log_buffer, track)

    logger.info('Closed......')


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


def query_messages_elasticsearch(logger, if_config_vars, agent_config_vars, es_conn, query):
    logger.info('Starting query server es')

    data = []
    try:
        # execute sql string
        response = es_conn.search(
            body=query,
            index=agent_config_vars['indeces'],
            ignore_unavailable=False)

        if 'error' in response:
            logger.error('Query es error: ' + str(response))
        else:
            data = response.get('hits', {}).get('hits', [])

    except Exception as e:
        logger.error(e)
        logger.error('Query log error.')

    return data


def parse_messages_elasticsearch(logger, if_config_vars, agent_config_vars, log_buffer, track, result):
    count = 0
    logger.info('Reading {} messages'.format(len(result)))

    for message in result:
        try:
            logger.debug(message)
            message = message.get('_source', {})

            # get timestamp
            timestamp_field = agent_config_vars['timestamp_field']
            timestamp_field = timestamp_field.split('.')
            timestamp = safe_get(message, timestamp_field)
            timestamp = int(arrow.get(timestamp).float_timestamp * 1000)

            # set offset for timestamp
            timestamp += agent_config_vars['target_timestamp_timezone'] * 1000
            timestamp = str(timestamp)

            # get instance name
            instance_field = agent_config_vars['instance_field'][0] if agent_config_vars['instance_field'] and len(
                agent_config_vars['instance_field']) > 0 else 'agent.hostname'
            instance_field = instance_field.split('.')
            instance = safe_get(message, instance_field)

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
                device = safe_get(message, device_field)
            if agent_config_vars['device_field_regex']:
                matches = agent_config_vars['device_field_regex'].match(device)
                if not matches or 'device' not in matches.groupdict().keys():
                    logger.debug('Parse message failed with device_field_regex: {}'.format(device))
                    continue
                device = matches.group('device')
            full_instance = make_safe_instance_string(instance, device)

            # get data
            data_fields = agent_config_vars['data_fields'] if agent_config_vars['data_fields'] and len(
                agent_config_vars['data_fields']) > 0 else ['message']
            data = safe_get_data(message, data_fields)

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

        elasticsearch_kwargs = {}
        es_uris = None
        query_json = None
        query_chunk_size = None
        indeces = None
        his_time_range = None

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
            query_json = config_parser.get('elasticsearch', 'query_json')
            query_chunk_size = config_parser.get('elasticsearch', 'query_chunk_size')
            indeces = config_parser.get('elasticsearch', 'indeces')

            # time range
            his_time_range = config_parser.get('elasticsearch', 'his_time_range')

            # proxies
            agent_http_proxy = config_parser.get('elasticsearch', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('elasticsearch', 'agent_https_proxy')

            # message parsing
            data_format = config_parser.get('elasticsearch', 'data_format').upper()
            component_field = config_parser.get('elasticsearch', 'component_field', raw=True)
            instance_field = config_parser.get('elasticsearch', 'instance_field', raw=True)
            instance_whitelist = config_parser.get('elasticsearch', 'instance_whitelist')
            device_field = config_parser.get('elasticsearch', 'device_field', raw=True)
            device_field_regex = config_parser.get('elasticsearch', 'device_field_regex', raw=True)
            timestamp_field = config_parser.get('elasticsearch', 'timestamp_field', raw=True) or '@timestamp'
            target_timestamp_timezone = config_parser.get('elasticsearch', 'target_timestamp_timezone',
                                                          raw=True) or 'UTC'
            timestamp_format = config_parser.get('elasticsearch', 'timestamp_format', raw=True)
            timezone = config_parser.get('elasticsearch', 'timezone') or 'UTC'
            data_fields = config_parser.get('elasticsearch', 'data_fields', raw=True)

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        # uris required
        if len(es_uris) != 0:
            es_uris = [x.strip() for x in es_uris.split(',') if x.strip()]
        else:
            return config_error(logger, 'es_uris')

        if len(query_json) != 0:
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

            'proxies': agent_proxies,
            'data_format': data_format,
            'component_field': component_field,
            'instance_field': instance_fields,
            "instance_whitelist_regex": instance_whitelist_regex,
            'device_field': device_fields,
            'device_field_regex': device_field_regex,
            'data_fields': data_fields,
            'timestamp_field': timestamp_field,
            'target_timestamp_timezone': target_timestamp_timezone,
            'timezone': timezone,
            'timestamp_format': timestamp_format,
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
            enable_holistic_model = config_parser.get('insightfinder', 'enable_holistic_model').upper()
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
            'enable_holistic_model': True if enable_holistic_model == 'TRUE' else False,
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


def safe_get(dct, keys):
    for key in keys:
        try:
            dct = dct[key]
        except KeyError:
            return None
    return dct


def safe_get_data(dct, keys):
    data = {}
    for key in keys:
        named_key = key.split('::')
        try:
            if len(named_key) > 1:
                data[named_key[0]] = dct[named_key[1]]
            else:
                data[named_key[0]] = dct[named_key[0]]
        except KeyError:
            return None
    return data


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
    logging_handler_err.setLevel(logging.WARNING)
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
                'instanceType': 'PrivateCloud',
                'projectCloudType': 'PrivateCloud',
                'dataType': get_data_type_from_project_type(if_config_vars),
                'insightAgentType': get_insight_agent_type_from_project_type(if_config_vars),
                'samplingInterval': int(if_config_vars['sampling_interval'] / 60),
                'samplingIntervalInSeconds': if_config_vars['sampling_interval'],
                'projectModelFlag': if_config_vars['enable_holistic_model'],
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

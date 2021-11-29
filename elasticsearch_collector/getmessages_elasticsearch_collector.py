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
from sys import getsizeof
from optparse import OptionParser

from elasticsearch import Elasticsearch

"""
This script gathers data to send to Insightfinder
"""


def start_data_processing():
    logger.info('Started......')

    # get conn
    es_conn = get_es_connection()

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
                sys.exit(1)

            # build query with chunk
            start_index = 0
            while start_index < total:
                query = dict({'from': start_index, "size": agent_config_vars['query_chunk_size']}, **query_body)
                start_index += agent_config_vars['query_chunk_size']

                data = query_messages_elasticsearch(es_conn, query)
                parse_messages_elasticsearch(data)

                # clear log buffer when piece of chunk range end
                clear_log_buffer()

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

        # validate successs
        if 'error' in response:
            logger.error('Query es error: ' + str(response))
            sys.exit(1)

        # build query with chunk
        start_index = 0
        while start_index < total:
            query = dict({'from': start_index, "size": agent_config_vars['query_chunk_size']}, **query_body)
            start_index += agent_config_vars['query_chunk_size']

            data = query_messages_elasticsearch(es_conn, query)
            parse_messages_elasticsearch(data)

            # clear log buffer when piece of chunk range end
            clear_log_buffer()

    logger.info('Closed......')


def get_es_connection():
    """ Try to connect to es """
    hosts = build_es_connection_hosts()
    try:
        return Elasticsearch(hosts)
    except Exception as e:
        logger.error('Could not contact ElasticSearch with provided configuration.')
        logger.error(e)
        sys.exit(1)


def build_es_connection_hosts():
    """ Build array of host dicts """
    hosts = []
    for uri in agent_config_vars['es_uris']:
        host = agent_config_vars['elasticsearch_kwargs'].copy()

        # parse uri for overrides
        uri = urllib.parse.urlparse(uri)
        host['host'] = uri.hostname or uri.path
        host['port'] = uri.port or host['port']
        host['http_auth'] = '{}:{}'.format(uri.username, uri.password) or host['http_auth']
        if uri.scheme == 'https':
            host['use_ssl'] = True

        # add ssl info
        if len(agent_config_vars['elasticsearch_kwargs']) != 0:
            host.update(agent_config_vars['elasticsearch_kwargs'])
        hosts.append(host)
    logger.debug(hosts)
    return hosts


def query_messages_elasticsearch(es_conn, query):
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


def parse_messages_elasticsearch(result):
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
            full_instance = make_safe_instance_string(instance, device)

            # get data
            data_fields = agent_config_vars['data_fields'] if agent_config_vars['data_fields'] and len(
                agent_config_vars['data_fields']) > 0 else ['message']
            data = safe_get_data(message, data_fields)

            # build log entry
            entry = prepare_log_entry(str(int(timestamp)), data, full_instance)
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


def get_agent_config_vars():
    """ Read and parse config.ini """
    config_ini = config_ini_path()
    if os.path.exists(config_ini):
        config_parser = configparser.ConfigParser()
        config_parser.read(config_ini)

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
            timestamp_field = config_parser.get('elasticsearch', 'timestamp_field', raw=True) or '@timestamp'
            target_timestamp_timezone = config_parser.get('elasticsearch', 'target_timestamp_timezone',
                                                          raw=True) or 'UTC'
            timestamp_format = config_parser.get('elasticsearch', 'timestamp_format', raw=True)
            timezone = config_parser.get('elasticsearch', 'timezone') or 'UTC'
            data_fields = config_parser.get('elasticsearch', 'data_fields', raw=True)

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            config_error()

        # uris required
        if len(es_uris) != 0:
            es_uris = [x.strip() for x in es_uris.split(',') if x.strip()]
        else:
            logger.error('Agent not correctly configured (es_uris). Check config file.')
            sys.exit(1)

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
                config_error('instance_whitelist')

        if len(his_time_range) != 0:
            his_time_range = [x.strip() for x in his_time_range.split(',') if x.strip()]
            his_time_range = [int(arrow.get(x).float_timestamp) for x in his_time_range]

        if len(target_timestamp_timezone) != 0:
            target_timestamp_timezone = int(arrow.now(target_timestamp_timezone).utcoffset().total_seconds())
        else:
            config_error('target_timestamp_timezone')

        if timezone:
            if timezone not in pytz.all_timezones:
                config_error('timezone')
            else:
                timezone = pytz.timezone(timezone)

        # data format
        if data_format in {'JSON',
                           'JSONTAIL',
                           'AVRO',
                           'XML'}:
            pass
        else:
            config_error('data_format')

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
            'data_fields': data_fields,
            'timestamp_field': timestamp_field,
            'target_timestamp_timezone': target_timestamp_timezone,
            'timezone': timezone,
            'timestamp_format': timestamp_format,
        }

        return config_vars
    else:
        config_error_no_config()


#########################
#   START_BOILERPLATE   #
#########################
def get_if_config_vars():
    """ get config.ini vars """
    config_ini = config_ini_path()
    if os.path.exists(config_ini):
        config_parser = configparser.ConfigParser()
        config_parser.read(config_ini)
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
            config_error()

        # check required variables
        if len(user_name) == 0:
            config_error('user_name')
        if len(license_key) == 0:
            config_error('license_key')
        if len(project_name) == 0:
            config_error('project_name')
        if len(project_type) == 0:
            config_error('project_type')

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
            config_error('project_type')
        is_replay = 'REPLAY' in project_type

        if len(sampling_interval) == 0:
            if 'METRIC' in project_type:
                config_error('sampling_interval')
            else:
                # set default for non-metric
                sampling_interval = 10

        if sampling_interval.endswith('s'):
            sampling_interval = int(sampling_interval[:-1])
        else:
            sampling_interval = int(sampling_interval) * 60

        if len(run_interval) == 0:
            config_error('run_interval')

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
    else:
        config_error_no_config()


def config_ini_path():
    return abs_path_from_cur(cli_config_vars['config'])


def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))


def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    """
    ## not ready.
    parser.add_option('--threads', default=1, action='store', dest='threads',
                      help='Number of threads to run')
    """
    parser.add_option('-c', '--config', action='store', dest='config', default=abs_path_from_cur('config.ini'),
                      help='Path to the config file to use. Defaults to {}'.format(abs_path_from_cur('config.ini')))
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data).' +
                           ' Automatically turns on verbose logging')
    (options, args) = parser.parse_args()

    """
    # not ready
    try:
        threads = int(options.threads)
    except ValueError:
        threads = 1
    """

    config_vars = {
        'config': options.config if os.path.isfile(options.config) else abs_path_from_cur('config.ini'),
        'threads': 1,
        'testing': False,
        'log_level': logging.INFO
    }

    if options.testing:
        config_vars['testing'] = True

    if options.verbose:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING

    return config_vars


def config_error(setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(
        info))
    sys.exit(1)


def config_error_no_config():
    logger.error('No config file found. Exiting...')
    sys.exit(1)


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


def prepare_log_entry(timestamp, data, instanceName):
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


def print_summary_info():
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

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)
    logger.debug(cli_data_block)


def initialize_data_gathering():
    reset_log_buffer()
    reset_track()
    track['chunk_count'] = 0
    track['entry_count'] = 0

    start_data_processing()

    # clear log buffer when data processing end
    clear_log_buffer()

    logger.info('Total chunks created: ' + str(track['chunk_count']))
    logger.info('Total {} entries: {}'.format(
        if_config_vars['project_type'].lower(), track['entry_count']))


def clear_log_buffer():
    # move all buffer data to current data, and send
    buffer_values = log_buffer['buffer_logs']

    count = 0
    for row in buffer_values:
        track['current_row'].append(row)
        count += 1
        track['line_count'] += 1
        if count % 500 == 0 or get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
            logger.debug('Sending buffer chunk')
            send_data_wrapper()

    # last chunk
    if len(track['current_row']) > 0:
        logger.debug('Sending last chunk')
        send_data_wrapper()

    reset_log_buffer()


def reset_log_buffer():
    log_buffer['buffer_logs'] = []


def reset_track():
    """ reset the track global for the next chunk """
    track['start_time'] = time.time()
    track['line_count'] = 0
    track['current_row'] = []
    track['component_map_list'] = []


################################
# Functions to send data to IF #
################################
def send_data_wrapper():
    """ wrapper to send data """
    logger.debug('--- Chunk creation time: {} seconds ---'.format(
        round(time.time() - track['start_time'], 2)))
    send_data_to_if(track['current_row'])
    track['chunk_count'] += 1
    reset_track()


def send_data_to_if(chunk_metric_data):
    send_data_time = time.time()

    # prepare data for metric/log streaming agent
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
    send_request(post_url, 'POST', 'Could not send request to IF',
                 str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.',
                 data=data_to_post, verify=False, proxies=if_config_vars['if_proxies'])
    logger.info('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def send_request(url, mode='GET', failure_message='Failure!', success_message='Success!', **request_passthrough):
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
                logger.warning(failure_message)
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


def get_data_type_from_project_type():
    if 'METRIC' in if_config_vars['project_type']:
        return 'Metric'
    elif 'LOG' in if_config_vars['project_type']:
        return 'Log'
    elif 'ALERT' in if_config_vars['project_type']:
        return 'Alert'
    elif 'INCIDENT' in if_config_vars['project_type']:
        return 'Incident'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'Deployment'
    else:
        logger.warning('Project Type not correctly configured')
        sys.exit(1)


def get_insight_agent_type_from_project_type():
    if 'containerize' in agent_config_vars and agent_config_vars['containerize']:
        if if_config_vars['is_replay']:
            return 'containerReplay'
        else:
            return 'containerStreaming'
    elif if_config_vars['is_replay']:
        if 'METRIC' in if_config_vars['project_type']:
            return 'MetricFile'
        else:
            return 'LogFile'
    else:
        return 'Custom'


def get_agent_type_from_project_type():
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


def get_data_field_from_project_type():
    """ use project type to determine which field to place data in """
    # incident uses a different API endpoint
    if 'INCIDENT' in if_config_vars['project_type']:
        return 'incidentData'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'deploymentData'
    else:  # MERTIC, LOG, ALERT
        return 'metricData'


def get_api_from_project_type():
    """ use project type to determine which API to post to """
    # incident uses a different API endpoint
    if 'INCIDENT' in if_config_vars['project_type']:
        return 'incidentdatareceive'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'deploymentEventReceive'
    else:  # MERTIC, LOG, ALERT
        return 'customprojectrawdata'


def initialize_api_post_data():
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


if __name__ == "__main__":
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
    HOSTNAME = socket.gethostname().partition('.')[0]
    ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
    JSON_LEVEL_DELIM = '.'
    CSV_DELIM = r",|\t"
    ATTEMPTS = 3
    CACHE_NAME = 'cache.db'
    track = dict()
    log_buffer = dict()

    # get config
    cli_config_vars = get_cli_config_vars()
    logger = set_logger_config(cli_config_vars['log_level'])
    logger.debug(cli_config_vars)
    if_config_vars = get_if_config_vars()
    agent_config_vars = get_agent_config_vars()
    print_summary_info()

    initialize_data_gathering()

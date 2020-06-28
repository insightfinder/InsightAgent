#!/usr/bin/env python
import ConfigParser
import json
import logging
import os
import regex
import socket
import sys
import time
import pytz
import arrow
import urlparse
import httplib
import requests
import statistics
import subprocess
import shlex
import traceback
import pymssql

from pymssql import ProgrammingError
from datetime import datetime
from decimal import Decimal
from optparse import OptionParser

"""
This script gathers data to send to Insightfinder
"""


def start_data_processing(thread_number):
    # open conn
    conn = pymssql.connect(**agent_config_vars['mssql_kwargs'])
    cursor = conn.cursor()
    logger.info('Started connection number ' + str(thread_number))

    sql_str = None

    # get instance and metric mapping info
    if agent_config_vars['instance_map_conn']:
        try:
            logger.info('Starting execute SQL to getting instance mapping info.')
            sql_str = "select * from {}".format(agent_config_vars['instance_map_conn']['instance_map_table'])
            logger.debug(sql_str)

            # execute sql string
            cursor.execute(sql_str)

            instance_map = {}
            for message in cursor:
                id_str = str(message[agent_config_vars['instance_map_conn']['instance_map_id_field']])
                name_str = str(message[agent_config_vars['instance_map_conn']['instance_map_name_field']])
                instance_map[id_str] = name_str
            agent_config_vars['instance_map'] = instance_map
        except ProgrammingError as e:
            logger.error(e)
            logger.error('SQL execute error: '.format(sql_str))

    # get table list and filter by whitelist
    table_list = []
    if agent_config_vars['table_list'].startswith('sql:'):
        try:
            logger.info('Starting execute SQL to getting table info.')
            sql_str = agent_config_vars['table_list'].split('sql:')[1]
            logger.debug(sql_str)

            # execute sql string
            cursor.execute(sql_str)

            for message in cursor:
                table = str(message['name'])
                table_list.append(table)

        except ProgrammingError as e:
            logger.error(e)
            logger.error('SQL execute error: '.format(sql_str))
    else:
        table_list = filter(lambda x: x.strip(), agent_config_vars['table_list'].split(','))

    if agent_config_vars['table_whitelist']:
        try:
            db_regex = regex.compile(agent_config_vars['table_whitelist'])
            table_list = list(filter(db_regex.match, table_list))
        except Exception as e:
            logger.error(e)
    if len(table_list) == 0:
        logger.error('Table list is empty')
        sys.exit(1)

    # get device mapping info for different device field
    if agent_config_vars['device_map_conn']:
        agent_config_vars['device_map'] = {}
        for field, map_info in agent_config_vars['device_map_conn'].items():
            try:
                logger.info('Starting execute SQL to getting device mapping info: {}.'.format(field))
                sql_str = "select * from {}".format(map_info['device_map_table'])
                logger.debug(sql_str)

                # execute sql string
                cursor.execute(sql_str)

                device_map = {}
                for message in cursor:
                    id_str = str(message[map_info['device_map_id_field']])
                    name_str = str(message[map_info['device_map_name_field']])
                    device_map[id_str] = name_str
                agent_config_vars['device_map'][field] = device_map
            except ProgrammingError as e:
                logger.error(e)
                logger.error('SQL execute error: '.format(sql_str))

    # get sql string
    sql = agent_config_vars['sql']
    sql = sql.replace('\n', ' ').replace('"""', '')

    # parse sql string by params
    logger.debug('sql config: {}'.format(agent_config_vars['sql_config']))
    if agent_config_vars['sql_config']:
        logger.debug('Using time range for replay data')
        for timestamp in range(agent_config_vars['sql_config']['sql_time_range'][0],
                               agent_config_vars['sql_config']['sql_time_range'][1],
                               agent_config_vars['sql_config']['sql_time_interval']):
            for table in table_list:
                sql_str = sql
                start_time = arrow.get(timestamp).format(agent_config_vars['sql_time_format'])
                end_time = arrow.get(timestamp + agent_config_vars['sql_config']['sql_time_interval']).format(
                    agent_config_vars['sql_time_format'])
                extract_time = arrow.get(
                    timestamp + agent_config_vars['sql_config']['sql_time_interval'] + agent_config_vars[
                        'sql_extract_time_offset']).format(agent_config_vars['sql_extract_time_format'])

                sql_str = sql_str.replace('{{table}}', table)
                sql_str = sql_str.replace('{{extract_time}}', extract_time)
                sql_str = sql_str.replace('{{start_time}}', start_time)
                sql_str = sql_str.replace('{{end_time}}', end_time)

                query_messages_mssql(cursor, sql_str)

            # clear metric buffer when piece of time range end
            clear_metric_buffer()
    else:
        logger.debug('Using current time for streaming data')
        for table in table_list:
            sql_str = sql
            start_time_multiple = agent_config_vars['start_time_multiple'] or 1
            start_time = arrow.get(
                arrow.utcnow().float_timestamp - start_time_multiple * if_config_vars['sampling_interval'],
                tzinfo=agent_config_vars['timezone'].zone).format(
                agent_config_vars['sql_time_format'])
            end_time = arrow.get(arrow.utcnow().float_timestamp, tzinfo=agent_config_vars['timezone'].zone).format(
                agent_config_vars['sql_time_format'])
            extract_time = arrow.get(
                arrow.utcnow().float_timestamp + agent_config_vars['sql_extract_time_offset'],
                tzinfo=agent_config_vars['timezone'].zone).format(
                agent_config_vars['sql_extract_time_format'])

            sql_str = sql_str.replace('{{table}}', table)
            sql_str = sql_str.replace('{{extract_time}}', extract_time)
            sql_str = sql_str.replace('{{start_time}}', start_time)
            sql_str = sql_str.replace('{{end_time}}', end_time)

            query_messages_mssql(cursor, sql_str)

    cursor.close()
    conn.close()
    logger.info('Closed connection number ' + str(thread_number))


def query_messages_mssql(cursor, sql_str):
    try:
        logger.info('Starting execute SQL')
        logger.info(sql_str)

        # execute sql string
        cursor.execute(sql_str)

        parse_messages_mssql(cursor)
    except ProgrammingError as e:
        logger.error(e)
        logger.error('SQL execute error: '.format(sql_str))


def parse_messages_mssql(cursor):
    count = 0
    message_list = cursor.fetchall()
    logger.info('Reading {} messages'.format(len(message_list)))

    for message in message_list:
        try:
            logger.debug('Message received')
            logger.debug(message)

            timestamp = message[agent_config_vars['timestamp_field'][0]]
            if isinstance(timestamp, datetime):
                timestamp = int(arrow.get(timestamp, tzinfo=agent_config_vars['timezone'].zone).float_timestamp * 1000)
            else:
                timestamp = int(arrow.get(timestamp, tzinfo=agent_config_vars['timezone'].zone).float_timestamp * 1000)

            # set offset for timestamp
            timestamp += agent_config_vars['timestamp_offset'] * 1000

            timestamp = str(timestamp)

            instance = str(message[agent_config_vars['instance_field'][0]])
            instance = agent_config_vars['instance_map'].get(instance, instance)

            # add device info if has
            full_instance = instance
            device_field = agent_config_vars['device_field']
            device_field = list(set(device_field) & set(message.keys()))
            if device_field:
                device = str(message[device_field[0]])
                device = agent_config_vars['device_map'].get(device_field[0], {}).get(device, device)
                device = device.replace('_', '-').replace('.', '-')
                full_instance = '{}_{}'.format(device, instance)

            key = '{}-{}'.format(timestamp, full_instance)
            if key not in metric_buffer['buffer_dict']:
                metric_buffer['buffer_dict'][key] = {"timestamp": timestamp}

            setting_values = agent_config_vars['data_fields'] or message.keys()
            setting_values = list(set(setting_values) & set(message.keys()))
            for data_field in setting_values:
                data_value = message[data_field]
                if isinstance(data_value, Decimal):
                    data_value = str(data_value)
                metric_key = '{}[{}]'.format(data_field, full_instance)
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


def get_agent_config_vars():
    """ Read and parse config.ini """
    config_ini = config_ini_path()
    if os.path.exists(config_ini):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(config_ini)

        mssql_kwargs = {}
        table_list = ''
        table_whitelist = ''
        instance_map_conn = None
        device_map_conn = None
        sql = None
        sql_time_format = None
        sql_config = None

        try:
            # mssql settings
            mssql_config = {
                # hard code
                'charset': 'utf8',
                'as_dict': True,
                # connection settings
                'timeout': int(config_parser.get('mssql', 'timeout') or '0'),
                'login_timeout': int(config_parser.get('mssql', 'login_timeout') or '60'),
                'appname': config_parser.get('mssql', 'appname'),
                'port': config_parser.get('mssql', 'port'),
                'conn_properties': config_parser.get('mssql', 'conn_properties'),
                'autocommit': config_parser.get('mssql', 'autocommit'),
                'tds_version': config_parser.get('mssql', 'tds_version'),
            }
            # only keep settings with values
            mssql_kwargs = {k: v for (k, v) in mssql_config.items() if v}

            # handle boolean setting
            if config_parser.get('mssql', 'autocommit').upper() == 'FALSE':
                mssql_kwargs['autocommit'] = False

            # handle required arrays
            # host
            if len(config_parser.get('mssql', 'host')) != 0:
                mssql_kwargs['host'] = config_parser.get('mssql', 'host')
            else:
                config_error('host')
            if len(config_parser.get('mssql', 'user')) != 0:
                mssql_kwargs['user'] = config_parser.get('mssql', 'user')
            else:
                config_error('user')
            if len(config_parser.get('mssql', 'password')) != 0:
                mssql_kwargs['password'] = config_parser.get('mssql', 'password')
            else:
                config_error('password')
            if len(config_parser.get('mssql', 'database')) != 0:
                mssql_kwargs['database'] = config_parser.get('mssql', 'database')
            else:
                config_error('database')

            # handle table info
            if len(config_parser.get('mssql', 'table_list')) != 0:
                table_list = config_parser.get('mssql', 'table_list')
            else:
                config_error('table_list')
            if len(config_parser.get('mssql', 'table_whitelist')) != 0:
                table_whitelist = config_parser.get('mssql', 'table_whitelist')
            elif table_list.startswith('sql:'):
                config_error('table_whitelist')

            # handle instance and metric mapping info
            if len(config_parser.get('mssql', 'instance_map_table')) != 0 \
                    and len(config_parser.get('mssql', 'instance_map_id_field')) != 0 \
                    and len(config_parser.get('mssql', 'instance_map_name_field')) != 0:
                instance_map_table = config_parser.get('mssql', 'instance_map_table')
                instance_map_id_field = config_parser.get('mssql', 'instance_map_id_field')
                instance_map_name_field = config_parser.get('mssql', 'instance_map_name_field')
                instance_map_conn = {
                    'instance_map_table': instance_map_table,
                    'instance_map_id_field': instance_map_id_field,
                    'instance_map_name_field': instance_map_name_field
                }

            # handle device mapping info for different device field
            if len(config_parser.get('mssql', 'device_map_table_info')) != 0:
                device_map_conn = {}
                device_map_table_info = config_parser.get('mssql', 'device_map_table_info')
                device_map_table_list = filter(lambda x: x.strip(), device_map_table_info.split(','))
                for item in device_map_table_list:
                    field_list = filter(lambda x: x.strip(), item.split('#'))
                    device_map_conn[field_list[0]] = {
                        'device_map_table': field_list[1],
                        'device_map_id_field': field_list[2],
                        'device_map_name_field': field_list[3]
                    }

            # sql
            sql = None
            if len(config_parser.get('mssql', 'sql')) != 0:
                sql = config_parser.get('mssql', 'sql')
            else:
                config_error('sql')
            sql_time_format = None
            if len(config_parser.get('mssql', 'sql_time_format')) != 0:
                sql_time_format = config_parser.get('mssql', 'sql_time_format')
            else:
                config_error('sql_time_format')
            sql_extract_time_offset = 0
            if len(config_parser.get('mssql', 'sql_extract_time_offset')) != 0:
                sql_extract_time_offset = int(config_parser.get('mssql', 'sql_extract_time_offset'))
            else:
                config_error('sql_extract_time_offset')
            sql_extract_time_format = None
            if len(config_parser.get('mssql', 'sql_extract_time_format')) != 0:
                sql_extract_time_format = config_parser.get('mssql', 'sql_extract_time_format')
            else:
                config_error('sql_extract_time_format')

            # sql config
            sql_config = None
            if len(config_parser.get('mssql', 'sql_time_range')) != 0 and len(
                    config_parser.get('mssql', 'sql_time_interval')) != 0:
                try:
                    sql_time_range = filter(lambda x: x.strip(),
                                            config_parser.get('mssql', 'sql_time_range').split(','))
                    sql_time_range = map(lambda x: int(arrow.get(x).float_timestamp), sql_time_range)
                    sql_time_interval = int(config_parser.get('mssql', 'sql_time_interval'))
                    sql_config = {
                        "sql_time_range": sql_time_range,
                        "sql_time_interval": sql_time_interval,
                    }
                except Exception as e:
                    logger.debug(e)
                    config_error('sql_time_range|sql_time_interval')

            # proxies
            agent_http_proxy = config_parser.get('mssql', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('mssql', 'agent_https_proxy')

            # message parsing
            data_format = config_parser.get('mssql', 'data_format').upper()
            # project_field = config_parser.get('agent', 'project_field', raw=True)
            instance_field = config_parser.get('mssql', 'instance_field', raw=True)
            device_field = config_parser.get('mssql', 'device_field', raw=True)
            timestamp_field = config_parser.get('mssql', 'timestamp_field', raw=True) or 'timestamp'
            timestamp_offset = config_parser.get('mssql', 'timestamp_offset', raw=True) or '0'
            timestamp_format = config_parser.get('mssql', 'timestamp_format', raw=True)
            timezone = config_parser.get('mssql', 'timezone') or 'UTC'
            data_fields = config_parser.get('mssql', 'data_fields', raw=True)
            start_time_multiple = config_parser.get('mssql', 'start_time_multiple', raw=True)

        except ConfigParser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            config_error()

        if len(start_time_multiple) != 0:
            start_time_multiple = int(start_time_multiple)

        # timestamp format
        if len(timestamp_format) != 0:
            timestamp_format = filter(lambda x: x.strip(), timestamp_format.split(','))
        else:
            config_error('timestamp_format')

        if len(timestamp_offset) != 0:
            timestamp_offset = int(timestamp_offset)
        else:
            config_error('timestamp_offset')

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
        # project_fields = project_field.split(',')
        instance_fields = instance_field.split(',')
        device_fields = device_field.split(',')
        timestamp_fields = timestamp_field.split(',')
        if len(data_fields) != 0:
            data_fields = data_fields.split(',')
            # for project_field in project_fields:
            #   if project_field in data_fields:
            #       data_fields.pop(data_fields.index(project_field))
            for instance_field in instance_fields:
                if instance_field in data_fields:
                    data_fields.pop(data_fields.index(instance_field))
            for device_field in device_fields:
                if device_field in data_fields:
                    data_fields.pop(data_fields.index(device_field))
            for timestamp_field in timestamp_fields:
                if timestamp_field in data_fields:
                    data_fields.pop(data_fields.index(timestamp_field))

        # add parsed variables to a global
        config_vars = {
            'mssql_kwargs': mssql_kwargs,
            'table_list': table_list,
            'table_whitelist': table_whitelist,
            'instance_map_conn': instance_map_conn,
            'device_map_conn': device_map_conn,
            'sql': sql,
            'sql_time_format': sql_time_format,
            'sql_extract_time_offset': sql_extract_time_offset,
            'sql_extract_time_format': sql_extract_time_format,
            'sql_config': sql_config,
            'proxies': agent_proxies,
            'data_format': data_format,
            # 'project_field': project_fields,
            'instance_field': instance_fields,
            'device_field': device_fields,
            'data_fields': data_fields,
            'start_time_multiple': start_time_multiple,
            'timestamp_field': timestamp_fields,
            'timestamp_offset': timestamp_offset,
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
        config_parser = ConfigParser.SafeConfigParser()
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
        except ConfigParser.NoOptionError as cp_noe:
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


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    return len(bytearray(json.dumps(json_data)))


def make_safe_instance_string(instance, device=''):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', instance)
    instance = COLONS.sub('-', instance)
    # if there's a device, concatenate it to the instance with an underscore
    if len(device) != 0:
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


def initialize_data_gathering(thread_number):
    reset_metric_buffer()
    reset_track()
    track['chunk_count'] = 0
    track['entry_count'] = 0

    start_data_processing(thread_number)

    # clear metric buffer when data processing end
    clear_metric_buffer()

    logger.info('Total chunks created: ' + str(track['chunk_count']))
    logger.info('Total {} entries: {}'.format(
        if_config_vars['project_type'].lower(), track['entry_count']))


def clear_metric_buffer():
    # move all buffer data to current data, and send
    buffer_values = metric_buffer['buffer_dict'].values()

    count = 0
    for row in buffer_values:
        track['current_row'].append(row)
        count += 1
        if count % 100 == 0 and get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
            logger.debug('Sending buffer chunk')
            send_data_wrapper()

    # last chunk
    if len(track['current_row']) > 0:
        logger.debug('Sending last chunk')
        send_data_wrapper()

    reset_metric_buffer()


def reset_metric_buffer():
    metric_buffer['buffer_key_list'] = []
    metric_buffer['buffer_ts_list'] = []
    metric_buffer['buffer_dict'] = {}

    metric_buffer['buffer_collected_list'] = []
    metric_buffer['buffer_collected_dict'] = {}


def reset_track():
    """ reset the track global for the next chunk """
    track['start_time'] = time.time()
    track['line_count'] = 0
    track['current_row'] = []


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

    # prepare data for metric streaming agent
    data_to_post = initialize_api_post_data()
    if 'DEPLOYMENT' in if_config_vars['project_type'] or 'INCIDENT' in if_config_vars['project_type']:
        for chunk in chunk_metric_data:
            chunk['data'] = json.dumps(chunk['data'])
    data_to_post[get_data_field_from_project_type()] = json.dumps(chunk_metric_data)

    logger.debug('First:\n' + str(chunk_metric_data[0]))
    logger.debug('Last:\n' + str(chunk_metric_data[-1]))
    logger.info('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
    logger.info('Total Lines: ' + str(track['line_count']))

    # do not send if only testing
    if cli_config_vars['testing']:
        return

    # send the data
    post_url = urlparse.urljoin(if_config_vars['if_url'], get_api_from_project_type())
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

    global REQUESTS
    REQUESTS.update(request_passthrough)
    # logger.debug(REQUESTS)

    req_num = 0
    for req_num in range(ATTEMPTS):
        try:
            response = req(url, **request_passthrough)
            if response.status_code == httplib.OK:
                logger.info(success_message)
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
    REQUESTS = dict()
    track = dict()
    metric_buffer = dict()

    # get config
    cli_config_vars = get_cli_config_vars()
    logger = set_logger_config(cli_config_vars['log_level'])
    logger.debug(cli_config_vars)
    if_config_vars = get_if_config_vars()
    agent_config_vars = get_agent_config_vars()
    print_summary_info()

    initialize_data_gathering(1)

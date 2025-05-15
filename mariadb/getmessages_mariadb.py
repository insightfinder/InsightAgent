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
import statistics
import subprocess
import shlex
import traceback
import pymysql
import sqlite3

from pymysql import ProgrammingError
from datetime import datetime
from decimal import Decimal
from optparse import OptionParser
from multiprocessing.pool import ThreadPool

"""
This script gathers data to send to Insightfinder
"""

def initialize_cache_connection(): 
    # connect to local cache
    cache_loc = abs_path_from_cur(CACHE_NAME)
    if os.path.exists(cache_loc): 
        cache_con = sqlite3.connect(cache_loc)
        cache_cur = cache_con.cursor()
    else: 
        cache_con = sqlite3.connect(cache_loc)
        cache_cur = cache_con.cursor()
        cache_cur.execute('CREATE TABLE "cache" ( "instance"	TEXT NOT NULL UNIQUE, "alias"	TEXT NOT NULL)')

    return cache_con, cache_cur


def start_data_processing():
    # open conn
    conn = pymysql.connect(**agent_config_vars['mariadb_kwargs'])
    logger.info('Started connection.')
    cursor = conn.cursor()

    sql_str = None

    metrics = agent_config_vars['metrics'] or []
    metric_regex = None
    if agent_config_vars['metrics_whitelist']:
        try:
            metric_regex = regex.compile(agent_config_vars['metrics_whitelist'])
        except Exception as e:
            logger.error(e)

    instance_filter_by_company_field = None
    company_regex = None
    company_list = []
    if agent_config_vars['company_whitelist']:
        try:
            company_regex = regex.compile(agent_config_vars['company_whitelist'])
        except Exception as e:
            logger.error(e)

    # get company mapping info
    if agent_config_vars['company_map_conn']:
        instance_filter_by_company_field = agent_config_vars['company_map_conn']['instance_filter_by_company_field']
        try:
            logger.info('Starting execute SQL to getting instance mapping info.')
            sql_str = "select * from {}.{}".format(agent_config_vars['company_map_conn']['company_map_database'],
                                                   agent_config_vars['company_map_conn']['company_map_table'])
            logger.debug(sql_str)

            # execute sql string
            cursor.execute(sql_str)

            company_map = {}
            for message in cursor:
                id_str = str(message[agent_config_vars['company_map_conn']['company_map_id_field']])
                name_str = str(message[agent_config_vars['company_map_conn']['company_map_name_field']])

                if company_regex and not company_regex.match(name_str):
                    continue

                company_list.append(id_str)
                company_map[id_str] = name_str
            agent_config_vars['company_map'] = company_map
        except ProgrammingError as e:
            logger.error(e)
            logger.error('SQL execute error: '.format(sql_str))

    # get instance mapping info
    if agent_config_vars['instance_map_conn']:
        try:
            logger.info('Starting execute SQL to getting instance mapping info.')
            sql_str = "select * from {}.{}".format(agent_config_vars['instance_map_conn']['instance_map_database'],
                                                   agent_config_vars['instance_map_conn']['instance_map_table'])
            logger.debug(sql_str)

            # execute sql string
            cursor.execute(sql_str)

            instance_map = {}
            for message in cursor:
                id_str = str(message[agent_config_vars['instance_map_conn']['instance_map_id_field']])
                name_str = str(message[agent_config_vars['instance_map_conn']['instance_map_name_field']])

                # filter instance by company
                if instance_filter_by_company_field:
                    company_id = str(message[instance_filter_by_company_field])
                    if company_regex and company_id not in company_list:
                        continue

                instance_map[id_str] = name_str
            agent_config_vars['instance_map'] = instance_map
        except ProgrammingError as e:
            logger.error(e)
            logger.error('SQL execute error: '.format(sql_str))

    # get metric mapping info
    if agent_config_vars['metric_map_conn']:
        try:
            logger.info('Starting execute SQL to getting metric mapping info.')
            sql_str = "select * from {}.{}".format(agent_config_vars['metric_map_conn']['metric_map_database'],
                                                   agent_config_vars['metric_map_conn']['metric_map_table'])
            logger.debug(sql_str)

            # execute sql string
            cursor.execute(sql_str)

            metric_map = {}
            for message in cursor:
                id_str = str(message[agent_config_vars['metric_map_conn']['metric_map_id_field']])
                name_str = str(message[agent_config_vars['metric_map_conn']['metric_map_name_field']].encode('utf8'))

                # filter metrics if need
                if len(metrics) > 0 and name_str not in metrics:
                    continue
                if metric_regex and not metric_regex.match(name_str):
                    continue

                metric_map[id_str] = name_str
            agent_config_vars['metric_map'] = metric_map
        except ProgrammingError as e:
            logger.error(e)
            logger.error('SQL execute error: '.format(sql_str))

    # get database list and filter by whitelist
    database_list = []
    if agent_config_vars['database_list'].startswith('sql:'):
        try:
            logger.info('Starting execute SQL to getting database info.')
            sql_str = agent_config_vars['database_list'].split('sql:')[1]
            logger.debug(sql_str)

            # execute sql string
            cursor.execute(sql_str)

            for message in cursor:
                database = str(message['Database'])
                database_list.append(database)

        except ProgrammingError as e:
            logger.error(e)
            logger.error('SQL execute error: '.format(sql_str))
    else:
        database_list = [x for x in agent_config_vars['database_list'].split(',') if x.strip()]

    if agent_config_vars['database_whitelist']:
        try:
            db_regex = regex.compile(agent_config_vars['database_whitelist'])
            database_list = list(filter(db_regex.match, database_list))
        except Exception as e:
            logger.error(e)
    if len(database_list) == 0:
        logger.error('Database list is empty')
        sys.exit(1)

    # close cursor
    cursor.close()
    conn.close()

    # query data from database list
    # get sql string
    sql = agent_config_vars['sql']
    sql = sql.replace('\n', ' ').replace('"""', '')

    # parse sql string by params
    pool_map = ThreadPool(agent_config_vars['thread_pool'])
    if agent_config_vars['sql_config']:
        logger.debug('Using time range for replay data')

        for timestamp in range(agent_config_vars['sql_config']['sql_time_range'][0],
                               agent_config_vars['sql_config']['sql_time_range'][1],
                               agent_config_vars['sql_config']['sql_time_interval']):
            start_time = arrow.get(timestamp).format(agent_config_vars['sql_time_format'])
            end_time = arrow.get(timestamp + agent_config_vars['sql_config']['sql_time_interval']).format(
                agent_config_vars['sql_time_format'])

            params = [(sql, d, start_time, end_time) for d in database_list]
            results = pool_map.map(query_messages_mariadb, params)
            for result in results:
                parse_messages_mariadb(result)

            # clear metric buffer when piece of time range end
            clear_metric_buffer()
    else:
        logger.debug('Using current time for streaming data')
        start_time_with_multiple_sampling = agent_config_vars['start_time_with_multiple_sampling'] or 1
        time_now = arrow.utcnow()
        start_time = arrow.get((time_now.float_timestamp - start_time_with_multiple_sampling * if_config_vars[
            'sampling_interval'])).format(
            agent_config_vars['sql_time_format'])
        end_time = time_now.format(agent_config_vars['sql_time_format'])

        params = [(sql, d, start_time, end_time) for d in database_list]
        results = pool_map.map(query_messages_mariadb, params)
        for result in results:
            parse_messages_mariadb(result)

    logger.info('Closed connection.')


def query_messages_mariadb(args):
    sql, database, start_time, end_time = args
    sql_str = sql
    sql_str = sql_str.replace('{{database}}', database)
    sql_str = sql_str.replace('{{start_time}}', start_time)
    sql_str = sql_str.replace('{{end_time}}', end_time)

    message_list = []
    try:
        logger.info('Starting execute SQL')
        logger.info(sql_str)

        # execute sql string
        conn = pymysql.connect(**agent_config_vars['mariadb_kwargs'])
        cursor = conn.cursor()
        cursor.execute(sql_str)

        # fetch all messages
        message_list = cursor.fetchall()

        cursor.close()
        conn.close()

    except ProgrammingError as e:
        logger.error(e)
        logger.error('SQL execute error: '.format(sql_str))
    return message_list


def parse_messages_mariadb(message_list):
    count = 0
    logger.info('Reading {} messages'.format(len(message_list)))

    for message in message_list:
        try:
            logger.debug('Message received')
            logger.debug(message)

            timestamp = message[agent_config_vars['timestamp_field'][0]]
            if isinstance(timestamp, datetime):
                timestamp = int(arrow.get(timestamp).float_timestamp * 1000)
            else:
                timestamp = int(arrow.get(timestamp).float_timestamp * 1000)

            # set offset for timestamp
            timestamp += agent_config_vars['target_timestamp_timezone'] * 1000
            timestamp = str(timestamp)

            instance = str(message[agent_config_vars['instance_field'][0]])
            if agent_config_vars['instance_map']:
                instance = agent_config_vars['instance_map'].get(instance)
                if not instance:
                    continue

            # check cache for alias
            instance = get_alias_from_cache(instance)

            # filter by instance whitelist
            if agent_config_vars['instance_whitelist_regex'] \
                    and not agent_config_vars['instance_whitelist_regex'].match(instance):
                continue

            key = '{}-{}'.format(timestamp, instance)
            if key not in metric_buffer['buffer_dict']:
                metric_buffer['buffer_dict'][key] = {"timestamp": timestamp}

            extension_metric = str(message[agent_config_vars['extension_metric_field']])
            extension_metric = agent_config_vars['metric_map'].get(extension_metric)
            # if metric not in metric_map, then pass this message
            if not extension_metric:
                continue

            setting_values = agent_config_vars['data_fields'] or list(message.keys())
            for data_field in setting_values:
                data_value = message[data_field]
                if isinstance(data_value, Decimal):
                    data_value = str(data_value)
                if agent_config_vars['metric_format']:
                    metric_format = agent_config_vars['metric_format'].replace('{{extension_metric}}',
                                                                               extension_metric)
                    metric_format = metric_format.replace('{{metric}}', data_field)
                    data_field = metric_format
                metric_key = '{}[{}]'.format(data_field, instance)
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


def get_alias_from_cache(alias):
    if cache_cur:
        cache_cur.execute('select alias from cache where instance="%s"' % alias)
        instance = cache_cur.fetchone()
        if instance:
            return instance[0]
        else: 
            # Hard coded if alias hasn't been added to cache, add it 
            cache_cur.execute('insert into cache (instance, alias) values ("%s", "%s")' % (alias, alias))
            cache_con.commit()
            return alias


def get_agent_config_vars():
    """ Read and parse config.ini """
    config_ini = config_ini_path()
    if os.path.exists(config_ini):
        config_parser = configparser.SafeConfigParser()
        config_parser.read(config_ini)

        mariadb_kwargs = {}
        metrics = None
        metrics_whitelist = None
        database_list = ''
        database_whitelist = ''
        instance_map_conn = None
        company_map_conn = None
        company_whitelist = None
        instance_whitelist = ''
        instance_whitelist_regex = None
        metric_map_conn = None
        sql = None
        sql_time_format = None
        sql_config = None

        try:
            # mariadb settings
            mariadb_config = {
                # hard code
                'cursorclass': pymysql.cursors.DictCursor,
                # connection settings
                'charset': config_parser.get('mariadb', 'charset'),
                'autocommit': config_parser.get('mariadb', 'autocommit'),
                'port': int(config_parser.get('mariadb', 'port')) if config_parser.get('mariadb', 'port') else None,
                'bind_address': config_parser.get('mariadb', 'bind_address'),
                'unix_socket': config_parser.get('mariadb', 'unix_socket'),
                'read_timeout': config_parser.get('mariadb', 'read_timeout'),
                'write_timeout': config_parser.get('mariadb', 'write_timeout'),
                'connect_timeout': config_parser.get('mariadb', 'connect_timeout'),
                'max_allowed_packet': config_parser.get('mariadb', 'max_allowed_packet'),
            }
            # only keep settings with values
            mariadb_kwargs = {k: v for (k, v) in list(mariadb_config.items()) if v}

            # handle boolean setting
            if config_parser.get('mariadb', 'autocommit').upper() == 'FALSE':
                mariadb_kwargs['autocommit'] = False

            # handle required arrays
            # host
            if len(config_parser.get('mariadb', 'host')) != 0:
                mariadb_kwargs['host'] = config_parser.get('mariadb', 'host')
            else:
                config_error('host')
            if len(config_parser.get('mariadb', 'user')) != 0:
                mariadb_kwargs['user'] = config_parser.get('mariadb', 'user')
            else:
                config_error('user')
            if len(config_parser.get('mariadb', 'password')) != 0:
                mariadb_kwargs['password'] = config_parser.get('mariadb', 'password')
            else:
                config_error('password')

            # metrics
            metrics = config_parser.get('mariadb', 'metrics')
            if len(metrics) != 0:
                metrics = [x for x in metrics.split(',') if x.strip()]
            metrics_whitelist = config_parser.get('mariadb', 'metrics_whitelist')

            # handle database info
            if len(config_parser.get('mariadb', 'database_list')) != 0:
                database_list = config_parser.get('mariadb', 'database_list')
            else:
                config_error('database_list')
            if len(config_parser.get('mariadb', 'database_whitelist')) != 0:
                database_whitelist = config_parser.get('mariadb', 'database_whitelist')
            elif database_list.startswith('sql:'):
                config_error('database_whitelist')

            # handle instance mapping info
            if len(config_parser.get('mariadb', 'instance_map_database')) != 0 \
                    and len(config_parser.get('mariadb', 'instance_map_table')) != 0 \
                    and len(config_parser.get('mariadb', 'instance_map_id_field')) != 0 \
                    and len(config_parser.get('mariadb', 'instance_map_name_field')) != 0:
                instance_map_database = config_parser.get('mariadb', 'instance_map_database')
                instance_map_table = config_parser.get('mariadb', 'instance_map_table')
                instance_map_id_field = config_parser.get('mariadb', 'instance_map_id_field')
                instance_map_name_field = config_parser.get('mariadb', 'instance_map_name_field')
                instance_map_conn = {
                    'instance_map_database': instance_map_database,
                    'instance_map_table': instance_map_table,
                    'instance_map_id_field': instance_map_id_field,
                    'instance_map_name_field': instance_map_name_field
                }
            # handle instance filter company mapping info
            if len(config_parser.get('mariadb', 'instance_filter_by_company_field')) != 0 \
                    and len(config_parser.get('mariadb', 'company_map_database')) != 0 \
                    and len(config_parser.get('mariadb', 'company_map_table')) != 0 \
                    and len(config_parser.get('mariadb', 'company_map_id_field')) != 0 \
                    and len(config_parser.get('mariadb', 'company_map_name_field')) != 0:
                instance_filter_by_company_field = config_parser.get('mariadb', 'instance_filter_by_company_field')
                company_map_database = config_parser.get('mariadb', 'company_map_database')
                company_map_table = config_parser.get('mariadb', 'company_map_table')
                company_map_id_field = config_parser.get('mariadb', 'company_map_id_field')
                company_map_name_field = config_parser.get('mariadb', 'company_map_name_field')

                company_map_conn = {
                    'instance_filter_by_company_field': instance_filter_by_company_field,
                    'company_map_database': company_map_database,
                    'company_map_table': company_map_table,
                    'company_map_id_field': company_map_id_field,
                    'company_map_name_field': company_map_name_field,
                }
            company_whitelist = config_parser.get('mariadb', 'company_whitelist')

            # handle metric mapping info
            if len(config_parser.get('mariadb', 'metric_map_database')) != 0 \
                    and len(config_parser.get('mariadb', 'metric_map_table')) != 0 \
                    and len(config_parser.get('mariadb', 'metric_map_id_field')) != 0 \
                    and len(config_parser.get('mariadb', 'metric_map_name_field')) != 0:
                metric_map_database = config_parser.get('mariadb', 'metric_map_database')
                metric_map_table = config_parser.get('mariadb', 'metric_map_table')
                metric_map_id_field = config_parser.get('mariadb', 'metric_map_id_field')
                metric_map_name_field = config_parser.get('mariadb', 'metric_map_name_field')
                metric_map_conn = {
                    'metric_map_database': metric_map_database,
                    'metric_map_table': metric_map_table,
                    'metric_map_id_field': metric_map_id_field,
                    'metric_map_name_field': metric_map_name_field
                }

            # sql
            if len(config_parser.get('mariadb', 'sql')) != 0:
                sql = config_parser.get('mariadb', 'sql')
            else:
                config_error('sql')
            if len(config_parser.get('mariadb', 'sql_time_format')) != 0:
                sql_time_format = config_parser.get('mariadb', 'sql_time_format')
            else:
                config_error('sql_time_format')

            # sql config
            if len(config_parser.get('mariadb', 'sql_time_range')) != 0 and len(
                    config_parser.get('mariadb', 'sql_time_interval')) != 0:
                try:
                    sql_time_range = [x for x in config_parser.get('mariadb', 'sql_time_range').split(',') if x.strip()]
                    sql_time_range = [int(arrow.get(x).float_timestamp) for x in sql_time_range]
                    sql_time_interval = int(config_parser.get('mariadb', 'sql_time_interval'))
                    sql_config = {
                        "sql_time_range": sql_time_range,
                        "sql_time_interval": sql_time_interval,
                    }
                except Exception as e:
                    logger.debug(e)
                    config_error('sql_time_range|sql_time_interval')

            # proxies
            agent_http_proxy = config_parser.get('mariadb', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('mariadb', 'agent_https_proxy')

            # message parsing
            data_format = config_parser.get('mariadb', 'data_format').upper()
            # project_field = config_parser.get('mariadb', 'project_field', raw=True)
            instance_field = config_parser.get('mariadb', 'instance_field', raw=True)
            instance_whitelist = config_parser.get('mariadb', 'instance_whitelist')
            device_field = config_parser.get('mariadb', 'device_field', raw=True)
            extension_metric_field = config_parser.get('mariadb', 'extension_metric_field', raw=True)
            metric_format = config_parser.get('mariadb', 'metric_format', raw=True)
            timestamp_field = config_parser.get('mariadb', 'timestamp_field', raw=True) or 'timestamp'
            target_timestamp_timezone = config_parser.get('mariadb', 'target_timestamp_timezone', raw=True) or 'UTC'
            timestamp_format = config_parser.get('mariadb', 'timestamp_format', raw=True)
            timezone = config_parser.get('mariadb', 'timezone')
            data_fields = config_parser.get('mariadb', 'data_fields', raw=True)
            start_time_with_multiple_sampling = config_parser.get('mariadb', 'start_time_with_multiple_sampling',
                                                                  raw=True)
            thread_pool = config_parser.get('mariadb', 'thread_pool', raw=True)

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            config_error()

        if len(instance_whitelist) != 0:
            try:
                instance_whitelist_regex = regex.compile(instance_whitelist)
            except Exception:
                config_error('instance_whitelist')

        # timestamp format
        if len(timestamp_format) != 0:
            timestamp_format = [x for x in timestamp_format.split(',') if x.strip()]
        else:
            config_error('timestamp_format')

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

        if len(start_time_with_multiple_sampling) != 0:
            start_time_with_multiple_sampling = int(start_time_with_multiple_sampling)

        if len(thread_pool) != 0:
            thread_pool = int(thread_pool)
        else:
            thread_pool = 5

        # add parsed variables to a global
        config_vars = {
            'mariadb_kwargs': mariadb_kwargs,
            'metrics': metrics,
            'metrics_whitelist': metrics_whitelist,
            'database_list': database_list,
            'database_whitelist': database_whitelist,
            'instance_map_conn': instance_map_conn,
            'company_map_conn': company_map_conn,
            'company_whitelist': company_whitelist,
            'metric_map_conn': metric_map_conn,
            'sql': sql,
            'sql_time_format': sql_time_format,
            'sql_config': sql_config,

            'proxies': agent_proxies,
            'data_format': data_format,
            # 'project_field': project_fields,
            'instance_field': instance_fields,
            "instance_whitelist_regex": instance_whitelist_regex,
            'device_field': device_fields,
            'extension_metric_field': extension_metric_field,
            'metric_format': metric_format,
            'data_fields': data_fields,
            'start_time_with_multiple_sampling': start_time_with_multiple_sampling,
            'thread_pool': thread_pool,
            'timestamp_field': timestamp_fields,
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
        config_parser = configparser.SafeConfigParser()
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


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    return sys.getsizeof(json.dumps(json_data))


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
    reset_metric_buffer()
    reset_track()
    track['chunk_count'] = 0
    track['entry_count'] = 0

    start_data_processing()

    # clear metric buffer when data processing end
    clear_metric_buffer()

    logger.info('Total chunks created: ' + str(track['chunk_count']))
    logger.info('Total {} entries: {}'.format(
        if_config_vars['project_type'].lower(), track['entry_count']))


def clear_metric_buffer():
    # move all buffer data to current data, and send
    for row in list(metric_buffer['buffer_dict'].values()):
        track['current_row'].append(row)
        if get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
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

    logger.debug('First:\n' + str(chunk_metric_data[0] if len(chunk_metric_data) > 0 else ''))
    logger.debug('Last:\n' + str(chunk_metric_data[-1] if len(chunk_metric_data) > 0 else ''))
    logger.info('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
    logger.info('Total Lines: ' + str(track['line_count']))

    # do not send if only testing or empty chunk
    if cli_config_vars['testing'] or len(chunk_metric_data) == 0:
        logger.debug('Skipping data ingestion...')
        return

    # send the data
    post_url = urllib.parse.urljoin(if_config_vars['if_url'], get_api_from_project_type())
    send_request(post_url, 'POST', 'Could not send request to IF',
                 str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.',
                 data=data_to_post, proxies=if_config_vars['if_proxies'])
    logger.info('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def send_request(url, mode='GET', failure_message='Failure!', success_message='Success!', **request_passthrough):
    """ sends a request to the given url """
    # determine if post or get (default)
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
            if response.status_code == http.client.OK:
                logger.info(success_message)
                return response
            else:
                logger.warn(failure_message)
                logger.debug('Response Code: {}\nTEXT: {}'.format(
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
        return 'Log'
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
    CACHE_NAME = 'cache.db'
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

    (cache_con, cache_cur) = initialize_cache_connection()

    initialize_data_gathering()

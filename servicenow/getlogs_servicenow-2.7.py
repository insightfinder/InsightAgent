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
from optparse import OptionParser
from multiprocessing import Process
from datetime import datetime
import dateutil
import tzlocal
import urlparse
import httplib
import requests
import statistics
import subprocess
import shlex
import xmltodict
import ifobfuscate
from requests.auth import HTTPBasicAuth
import re

'''
This script gathers data to send to Insightfinder
'''

location_map = {}
RESULT_KEY = "result"
LOCATION_KEY = "location"
LINK_KEY = "link"
VALUE_KEY = "value"
NAME_KEY = "name"


def start_data_processing(thread_number):
    # set sysparm limi/offset
    passthru = {'sysparm_limit': 100,
                'sysparm_exclude_reference_link': 'true',
                'sysparm_display_value': 'true',
                'sysparm_offset': agent_config_vars['state']['sysparm_offset'],
                'sysparm_query': ''}

    ## add timestamp query
    # get utc earliest datetime
    utc_earliest_epoch = time.time()
    # get localized earliest datetime
    local_earliest_datetime = tzlocal.get_localzone().localize(
        datetime.fromtimestamp(utc_earliest_epoch))
    # convert earliest datetime to the data timezone
    data_earliest_datetime = local_earliest_datetime.astimezone(
        agent_config_vars['timezone'])
    # do not apply timezone conversion later
    # agent_config_vars['timezone'] = pytz.utc
    # convert to string for Glide
    earliest_date_and_time = data_earliest_datetime.strftime(
        agent_config_vars['timestamp_format'][0]).split(' ')
    # add timestamp filter
    if agent_config_vars['start_time'] and agent_config_vars['end_time'] and agent_config_vars['is_historical'] == '1':
        start_time = agent_config_vars['start_time']
        end_time = agent_config_vars['end_time']
        statement = agent_config_vars['timestamp_field'][
                        0] + 'BETWEENjavascript:gs.dateGenerate(\'<START_DATE>\',\'00:00:00\')@javascript:gs.dateGenerate(\'<END_DATE>\',\'23:59:59\')'
        statement = statement.replace('<START_DATE>', start_time).replace('<END_DATE>', end_time)
        passthru['sysparm_query'] = '{}^OR{}'.format(passthru['sysparm_query'], statement) if len(
            passthru['sysparm_query']) != 0 else statement
    elif agent_config_vars['is_historical'] == '0':
        if agent_config_vars['cron_start_time']:
            utc_cron_epoch = agent_config_vars['cron_start_time']
            # get localized earliest datetime
            local_cron_datetime = tzlocal.get_localzone().localize(
                datetime.fromtimestamp(float(utc_cron_epoch)))
            # convert earliest datetime to the data timezone
            data_cron_datetime = local_cron_datetime.astimezone(
                agent_config_vars['timezone'])
            # do not apply timezone conversion later
            agent_config_vars['timezone'] = pytz.utc
            # convert to string for Glide
            cron_date_and_time = data_cron_datetime.strftime(
                agent_config_vars['timestamp_format'][0]).split(' ')
            earliest_date = cron_date_and_time[0]
            earliest_time = cron_date_and_time[1]
        else:
            earliest_date = earliest_date_and_time[0]
            earliest_time = '00:00:00'
        for timestamp_field in agent_config_vars['timestamp_field']:
            if not is_formatted(timestamp_field):
                statement = '{}>=javascript:gs.dateGenerate(\'{}\',\'{}\')'.format(
                    timestamp_field,
                    earliest_date,
                    earliest_time)
                # OR between fields
                passthru['sysparm_query'] = '{}^OR{}'.format(passthru['sysparm_query'], statement) if len(
                    passthru['sysparm_query']) != 0 else statement
        passthru['sysparm_offset'] = 0
    # add applicable keyword filtering
    for in_filter in agent_config_vars['filters_include']:
        filter_keyword, filter_values = in_filter.split(':')
        filter_statement = ''
        for filter_value in filter_values.split(','):
            statement = '{keyword}*{value}^{keyword}ISNOTEMPTY'.format(keyword=filter_keyword, value=filter_value)
            # OR between values
            filter_statement = '{}^OR{}'.format(filter_statement, statement) if len(
                filter_statement) != 0 else statement
        # AND between keywords
        passthru['sysparm_query'] = '{}^{}'.format(passthru['sysparm_query'], filter_statement) if len(
            passthru['sysparm_query']) != 0 else '{}'.format(filter_statement)
    # clear since it's handled already
    agent_config_vars['filters_include'] = ''
    for ex_filter in agent_config_vars['filters_exclude']:
        filter_keyword, filter_values = ex_filter.split(':')
        filter_statement = ''
        for filter_value in filter_values.split(','):
            statement = '{keyword}!*{value}^{keyword}ISNOTEMPTY'.format(keyword=filter_keyword, value=filter_value)
            # OR between values
            filter_statement = '{}^OR{}'.format(filter_statement, statement) if len(
                filter_statement) != 0 else statement
        # AND between keywords
        passthru['sysparm_query'] = '{}^{}'.format(passthru['sysparm_query'], filter_statement) if len(
            passthru['sysparm_query']) != 0 else '{}'.format(filter_statement)
    # clear since it's handled already
    agent_config_vars['filters_exclude'] = ''
    passthru['sysparm_query'] = '{}^{}'.format(passthru['sysparm_query'], agent_config_vars['addl_query']) if len(
        agent_config_vars['addl_query']) != 0 else passthru['sysparm_query']
    # build auth
    auth = (agent_config_vars['username'], ifobfuscate.decode(agent_config_vars['password']))
    # logger.debug(ifobfuscate.decode(agent_config_vars['password']))
    # call API
    logger.info(
        'Trying to get next {} records, starting at {}'.format(passthru['sysparm_limit'], passthru['sysparm_offset']))
    logger.debug(passthru)
    api_response = send_request(agent_config_vars['api_url'], auth=auth, params=passthru)
    count = 0
    if api_response != -1 and not api_response.text.index('hibernating'):
        count = int(api_response.headers['X-Total-Count'])
    logger.debug('Processing {} records'.format(count))
    while api_response != -1 and passthru['sysparm_offset'] < count:
        # parse messages
        try:
            api_json = json.loads(api_response.content)
            parse_json_message(api_json)
        except Exception as e:
            logger.warning(e)
            pass
        # set limit and offset
        passthru['sysparm_offset'] = passthru['sysparm_offset'] + passthru['sysparm_limit']
        passthru['sysparm_limit'] = min(100, count - passthru['sysparm_offset'])
        if passthru['sysparm_offset'] >= count or passthru['sysparm_limit'] <= 0:
            break
        update_state('sysparm_offset', passthru['sysparm_offset'], write=True)
        # call API for next cycle
        logger.info('Trying to get next {} records, starting at {}'.format(passthru['sysparm_limit'],
                                                                           passthru['sysparm_offset']))
        api_response = send_request(agent_config_vars['api_url'], auth=auth, params=passthru)

    update_state('sysparm_offset', count, write=True)

    if agent_config_vars['is_historical'] == '0':
        update_setting('cron_start_time', utc_earliest_epoch, write=True)

    if agent_config_vars['is_historical'] == '1':
        update_setting('is_historical', '0', write=True)


def get_agent_config_vars():
    """ Read and parse config.ini """
    config_ini = config_ini_path()
    if os.path.exists(config_ini):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(config_ini)
        try:
            # state
            sysparm_offset = config_parser.get('state', 'sysparm_offset')

            # api
            base_url = config_parser.get('agent', 'base_url')
            api_endpoint = config_parser.get('agent', 'api_endpoint')
            username = config_parser.get('agent', 'username')
            password = config_parser.get('agent', 'password_encrypted')
            addl_query = config_parser.get('agent', 'sysparm_query')

            # proxies
            agent_http_proxy = config_parser.get('agent', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('agent', 'agent_https_proxy')

            # filters
            filters_include = config_parser.get('agent', 'filters_include')
            filters_exclude = config_parser.get('agent', 'filters_exclude')

            # message parsing
            json_top_level = config_parser.get('agent', 'json_top_level')
            # project_field = config_parser.get('agent', 'project_field', raw=True)
            instance_field = config_parser.get('agent', 'instance_field', raw=True)
            device_field = config_parser.get('agent', 'device_field', raw=True)
            timestamp_field = config_parser.get('agent', 'timestamp_field', raw=True) or 'timestamp'
            timestamp_format = config_parser.get('agent', 'timestamp_format', raw=True) or 'epoch'
            timezone = config_parser.get('agent', 'timezone') or 'UTC'
            data_fields = config_parser.get('agent', 'data_fields', raw=True)
            start_time = config_parser.get('agent', 'start_time', raw=True)
            end_time = config_parser.get('agent', 'end_time', raw=True)
            is_historical = config_parser.get('agent', 'is_historical', raw=True)
            cron_start_time = config_parser.get('agent', 'cron_start_time', raw=True)
            instance_regex = config_parser.get('agent', 'instance_regex', raw=True)

        except ConfigParser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            config_error()

        # API
        api_url = urlparse.urljoin(base_url, api_endpoint)
        if len(api_url) == 0:
            config_error('base_url or api_endpoint')
        if len(username) == 0:
            config_error('username')
        if len(password) == 0:
            config_error('password')

        if len(is_historical) == 0:
            is_historical = '1'

        # proxies
        agent_proxies = dict()
        if len(agent_http_proxy) > 0:
            agent_proxies['http'] = agent_http_proxy
        if len(agent_https_proxy) > 0:
            agent_proxies['https'] = agent_https_proxy

        # filters
        if len(filters_include) != 0:
            filters_include = filters_include.split('|')
        if len(filters_exclude) != 0:
            filters_exclude = filters_exclude.split('|')

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

        # timestamp format
        timestamp_format = timestamp_format.partition('.')[0]
        if '%z' in timestamp_format or '%Z' in timestamp_format:
            ts_format_info = strip_tz_info(timestamp_format)
        elif timestamp_format:
            ts_format_info = {'strip_tz': False,
                              'strip_tz_fmt': '',
                              'timestamp_format': [timestamp_format]}
        else:  # ISO8601?
            ts_format_info = {'strip_tz': True,
                              'strip_tz_fmt': PCT_z_FMT,
                              'timestamp_format': ISO8601}
        if timezone not in pytz.all_timezones:
            config_error('timezone')
        else:
            timezone = pytz.timezone(timezone)

        try:
            sysparm_offset = int(sysparm_offset)
        except Exception:
            sysparm_offset = 0

        # add parsed variables to a global
        config_vars = {
            'state': {'sysparm_offset': sysparm_offset},
            'api_url': api_url,
            'username': username,
            'password': password,
            'addl_query': addl_query,
            'proxies': agent_proxies,
            'filters_include': filters_include,
            'filters_exclude': filters_exclude,
            'data_format': 'JSON',
            'json_top_level': json_top_level,
            # 'project_field': project_fields,
            'instance_field': instance_fields,
            'device_field': device_fields,
            'data_fields': data_fields,
            'timestamp_field': timestamp_fields,
            'timezone': timezone,
            'timestamp_format': ts_format_info['timestamp_format'],
            'strip_tz': ts_format_info['strip_tz'],
            'strip_tz_fmt': ts_format_info['strip_tz_fmt'],
            'start_time': start_time,
            'end_time': end_time,
            'is_historical': is_historical,
            'cron_start_time': cron_start_time,
            'instance_regex': instance_regex
        }

        return config_vars
    else:
        config_error_no_config()


#########################
### START_BOILERPLATE ###
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
            'if_proxies': if_proxies
        }

        return config_vars
    else:
        config_error_no_config()


def update_state(setting, value, append=False, write=False):
    # update in-mem
    if append:
        current = ','.join(agent_config_vars['state'][setting])
        value = '{},{}'.format(current, value) if current else value
        agent_config_vars['state'][setting] = value.split(',')
    else:
        agent_config_vars['state'][setting] = value
    logger.debug('setting {} to {}'.format(setting, value))
    # update config file
    if write:
        config_ini = config_ini_path()
        if os.path.exists(config_ini):
            config_parser = ConfigParser.SafeConfigParser()
            config_parser.read(config_ini)
            config_parser.set('state', setting, str(value))
            with open(config_ini, 'w') as config_file:
                config_parser.write(config_file)
    # return new value (if append)
    return value


def update_setting(setting, value, write=False):
    if write:
        config_ini = config_ini_path()
        if os.path.exists(config_ini):
            config_parser = ConfigParser.SafeConfigParser()
            config_parser.read(config_ini)
            config_parser.set('agent', setting, str(value))
            with open(config_ini, 'w') as config_file:
                config_parser.write(config_file)


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

    if options.verbose or options.testing:
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


def strip_tz_info(timestamp_format):
    # strptime() doesn't allow timezone info
    if '%Z' in timestamp_format:
        position = timestamp_format.index('%Z')
        strip_tz_fmt = PCT_Z_FMT
    if '%z' in timestamp_format:
        position = timestamp_format.index('%z')
        strip_tz_fmt = PCT_z_FMT

    if len(timestamp_format) > (position + 2):
        timestamp_format = timestamp_format[:position] + timestamp_format[position + 2:]
    else:
        timestamp_format = timestamp_format[:position]

    return {'strip_tz': True,
            'strip_tz_fmt': strip_tz_fmt,
            'timestamp_format': [timestamp_format]}


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    return len(bytearray(json.dumps(json_data)))


def is_formatted(setting_value):
    """ returns True if the setting is a format string """
    return len(FORMAT_STR.findall(setting_value)) != 0


def is_complex(setting_value):
    """ returns True if the setting is 'complex' """
    return '!!' in setting_value


def is_math_expr(setting_value):
    return '==' in setting_value


def get_math_expr(setting_value):
    return setting_value.strip('=')


def is_named_data_field(setting_value):
    return '::' in setting_value


def merge_data(field, value, data={}):
    fields = field.split(JSON_LEVEL_DELIM)
    for i in range(len(fields) - 1):
        field = fields[i]
        if field not in data:
            data[field] = dict()
        data = data[field]
    data[fields[-1]] = value
    return data


def parse_formatted(message, setting_value, default='', allow_list=False, remove=False):
    """ fill a format string with values """
    fields = {field: get_json_field(message,
                                    field,
                                    default=0 if default == 0 else '',  # special case for evaluate func
                                    allow_list=allow_list,
                                    remove=remove)
              for field in FORMAT_STR.findall(setting_value)}
    if len(fields) == 0:
        return default
    return setting_value.format(**fields)


def get_data_values(timestamp, message):
    setting_values = agent_config_vars['data_fields'] or message.keys()
    # reverse list so it's in priority order, as shared fields names will get overwritten
    setting_values.reverse()
    data = {x: dict() for x in timestamp}
    for setting_value in setting_values:
        name, value = get_data_value(message, setting_value)
        if isinstance(value, (set, tuple, list)):
            for i in range(minlen(timestamp, value)):
                merge_data(name, value[i], data[timestamp[i]])
        else:
            merge_data(name, value, data[timestamp[0]])
    return data


def get_data_value(message, setting_value):
    if is_named_data_field(setting_value):
        name, value = setting_value.split('::')
        # get name
        name = get_single_value(message,
                                name,
                                default=name,
                                allow_list=False,
                                remove=False)
        # check if math
        evaluate = False
        if is_math_expr(value):
            evaluate = True
            value = get_math_expr(value)
        value = get_single_value(message,
                                 value,
                                 default=0 if evaluate else '',
                                 allow_list=not evaluate,
                                 remove=False)
        if value and evaluate:
            value = eval(value)
    elif is_complex(setting_value):
        this_field, metadata, that_field = setting_value.split('!!')
        name = this_field
        value = get_complex_value(message,
                                  this_field,
                                  metadata,
                                  that_field,
                                  default=that_field,
                                  allow_list=True,
                                  remove=False)
    else:
        name = setting_value
        value = get_single_value(message,
                                 setting_value,
                                 default='',
                                 allow_list=True,
                                 remove=False)
    return (name, value)


def get_complex_value(message, this_field, metadata, that_field, default='', allow_list=False, remove=False):
    metadata = metadata.split('&')
    data_type, data_return = metadata[0].upper().split('=')
    if data_type == 'REF':
        ref = get_single_value(message,
                               this_field,
                               default='',
                               allow_list=False,
                               remove=remove)
        if not ref:
            return default
        passthrough = {'mode': 'GET'}
        for param in metadata[1:]:
            if '=' in param:
                key, value = param.split('=')
                try:
                    value = json.loads(value)
                except Exception:
                    value = value
            else:
                key = param
                value = REQUESTS[key]
            passthrough[key] = value
        response = send_request(ref, **passthrough)
        if response == -1:
            return default
        data = response.content
        if data_return == 'RAW':
            return data
        elif data_return == 'CSV':
            data = label_message(agent_config_vars['csv_field_delimiter'].split(data))
        elif data_return == 'XML':
            data = xml2dict.parse(data)
        elif data_return == 'JSON':
            data = json.loads(data)
        return get_single_value(data,
                                that_field,
                                default=default,
                                allow_list=True,
                                remove=False)
    else:
        logger.warning('Unsupported complex setting {}!!{}!!{}'.format(this_field, metadata, that_field))
        return default


def get_setting_value(message, config_setting, default='', allow_list=False, remove=False):
    if config_setting not in agent_config_vars or len(agent_config_vars[config_setting]) == 0:
        return default
    setting_value = agent_config_vars[config_setting]
    return get_single_value(message,
                            setting_value,
                            default=default,
                            allow_list=allow_list,
                            remove=remove)


def get_single_value(message, setting_value, default='', allow_list=False, remove=False):
    if isinstance(setting_value, (set, list, tuple)):
        setting_value_single = setting_value[0]
    else:
        setting_value_single = setting_value
        setting_value = [setting_value]
    if is_complex(setting_value_single):
        this_field, metadata, that_field = setting_value_single.split('!!')
        return get_complex_value(message,
                                 this_field,
                                 metadata,
                                 that_field,
                                 default=default,
                                 allow_list=allow_list,
                                 remove=remove)
    elif is_formatted(setting_value_single):
        return parse_formatted(message,
                               setting_value_single,
                               default=default,
                               allow_list=False,
                               remove=remove)
    else:
        return get_json_field_by_pri(message,
                                     [i for i in setting_value],
                                     default=default,
                                     allow_list=allow_list,
                                     remove=remove)


def get_json_field_by_pri(message, pri_list, default='', allow_list=False, remove=False):
    value = ''
    while value == '' and len(pri_list) != 0:
        field = pri_list.pop(0)
        if field:
            value = get_json_field(message,
                                   field,
                                   allow_list=allow_list,
                                   remove=remove)
    return value or default


def get_json_field(message, setting_value, default='', allow_list=False, remove=False):
    field_val = json_format_field_value(
        _get_json_field_helper(
            message,
            setting_value.split(JSON_LEVEL_DELIM),
            allow_list=allow_list,
            remove=remove))
    if len(field_val) == 0:
        field_val = default
    return field_val


class ListNotAllowedError():
    pass


def _get_json_field_helper(nested_value, next_fields, allow_list=False, remove=False):
    # check inputs; need a dict that is a subtree, an _array_ of fields to traverse down
    if len(next_fields) == 0:
        # nothing to look for
        return ''
    elif isinstance(nested_value, (list, set, tuple)):
        # for each elem in the list
        # already checked in the recursive call that this is OK
        return json_gather_list_values(nested_value, next_fields)
    elif not isinstance(nested_value, dict):
        # nothing to walk down
        return ''

    # get the next value
    next_field = next_fields.pop(0)
    next_value = json.loads(json.dumps(nested_value.get(next_field)))
    try:
        if len(next_fields) == 0 and remove:
            # last field to grab, so remove it
            nested_value.pop(next_field)
    except Exception:
        pass

    # check the next value
    if next_value is None:
        # no next value defined
        return ''
    elif len(next_value) == 0:
        # no next value set
        return ''

    # sometimes payloads come in formatted
    try:
        next_value = json.loads(next_value)
    except Exception as ex:
        next_value = json.loads(json.dumps(next_value))

    # handle simple lists
    while isinstance(next_value, (list, set, tuple)) and len(next_value) == 1:
        next_value = next_value.pop()

    # continue traversing?
    if next_fields is None:
        # some error, but return the value
        return next_value
    elif len(next_fields) == 0:
        # final value in the list to walk down
        return next_value
    elif isinstance(next_value, (list, set, tuple)):
        # we've reached an early terminal point, which may or may not be ok
        if allow_list:
            return json_gather_list_values(
                next_value,
                next_fields,
                remove=remove)
        else:
            raise ListNotAllowedError('encountered list or set in json when not allowed')
    elif isinstance(next_value, dict):
        # there's more tree to walk down
        return _get_json_field_helper(
            json.loads(json.dumps(next_value)),
            next_fields,
            allow_list=allow_list,
            remove=remove)
    else:
        # catch-all
        return ''


def json_gather_list_values(l, fields, remove=False):
    sub_field_value = []
    # treat each item in the list as a potential tree to walk down
    for sub_value in l:
        fields_copy = list(fields[i] for i in range(len(fields)))
        json_value = json_format_field_value(
            _get_json_field_helper(
                sub_value,
                fields_copy,
                allow_list=True,
                remove=remove))
        if len(json_value) != 0:
            sub_field_value.append(json_value)
    # return the full list of field values
    return sub_field_value


def json_format_field_value(value):
    # flatten 1-item set/list
    if isinstance(value, (list, set, tuple)):
        if len(value) == 1:
            return value.pop()
        return list(value)
    # keep dicts intact
    elif isinstance(value, dict):
        return value
    # stringify everything else
    try:
        return str(value)
    except Exception as e:
        return str(value.encode('utf-8'))


def parse_json_message(messages):
    if isinstance(messages, (list, set, tuple)):
        for message in messages:
            parse_json_message(message)
    else:
        if len(agent_config_vars['json_top_level']) == 0:
            parse_json_message_single(messages)
        else:
            top_level = _get_json_field_helper(
                messages,
                agent_config_vars['json_top_level'].split(JSON_LEVEL_DELIM),
                allow_list=True)
            if isinstance(top_level, (list, set, tuple)):
                for message in top_level:
                    parse_json_message_single(message)
            else:
                parse_json_message_single(top_level)


def parse_json_message_single(message):
    message = json.loads(json.dumps(message))
    # filter
    if len(agent_config_vars['filters_include']) != 0:
        # for each provided filter
        is_valid = False
        for _filter in agent_config_vars['filters_include']:
            filter_field = _filter.split(':')[0]
            filter_vals = _filter.split(':')[1].split(',')
            filter_check = get_json_field(
                message,
                filter_field,
                allow_list=True)
            # check if a valid value
            for filter_val in filter_vals:
                if filter_val.upper() in filter_check.upper():
                    is_valid = True
                    break
            if is_valid:
                break
        if not is_valid:
            logger.debug('filtered message (inclusion): {} not in {}'.format(
                filter_check, filter_vals))
            return
        else:
            logger.debug('passed filter (inclusion)')

    if len(agent_config_vars['filters_exclude']) != 0:
        # for each provided filter
        for _filter in agent_config_vars['filters_exclude']:
            filter_field = _filter.split(':')[0]
            filter_vals = _filter.split(':')[1].split(',')
            filter_check = get_json_field(
                message,
                filter_field,
                allow_list=True)
            # check if a valid value
            for filter_val in filter_vals:
                if filter_val.upper() in filter_check.upper():
                    logger.debug('filtered message (exclusion): {} in {}'.format(
                        filter_val, filter_check))
                    return
        logger.debug('passed filter (exclusion)')

    # get project, instance, & device
    # check_project(get_setting_value(message,
    #                                'project_field',
    #                                default=if_config_vars['project_name']),
    #                                remove=True)
    logging.debug('message: ' + str(message))
    instance = get_setting_value(message,
                                 'instance_field',
                                 default=UNKNOWN_INSTANCE,
                                 remove=True)

    if instance != UNKNOWN_INSTANCE and agent_config_vars['instance_regex']:
        group = re.search(agent_config_vars['instance_regex'], instance)
        if (group != None):
            instance = group.group(0)

    logger.warn(instance)
    device = get_setting_value(message,
                               'device_field',
                               remove=True)
    # get timestamp
    try:
        timestamp = get_setting_value(message,
                                      'timestamp_field',
                                      remove=True)
        timestamp = [timestamp]
    except ListNotAllowedError as lnae:
        timestamp = get_setting_value(message,
                                      'timestamp_field',
                                      remove=True,
                                      allow_list=True)
    except Exception as e:
        logger.warn(e)
        sys.exit(1)
    logger.warn(timestamp)

    # get data
    data = get_data_values(timestamp, message)

    # hand off
    for timestamp, report_data in data.items():
        # check if this is within the time range
        ts = get_timestamp_from_date_string(timestamp)
        if long((time.time() - if_config_vars['run_interval']) * 1000) > ts and not agent_config_vars[
            'start_time'] and not agent_config_vars['end_time']:
            logger.debug('skipping message with timestamp {}'.format(ts))
            continue
        if ts < agent_config_vars['start_time'] and ts > agent_config_vars['end_time']:
            logger.debug('skipping message with timestamp {}'.format(ts))
            continue
        if 'METRIC' in if_config_vars['project_type']:
            data_folded = fold_up(report_data, value_tree=True)  # put metric data in top level
            for data_field, data_value in data_folded.items():
                if data_value is not None:
                    metric_handoff(
                        ts,
                        data_field,
                        data_value,
                        instance,
                        device)
        else:
            log_handoff(ts, report_data, instance, device)


def label_message(message, fields=[]):
    """ turns unlabeled, split data into labeled data """
    if agent_config_vars['data_format'] in {'CSV', 'CSVTAIL', 'IFEXPORT'}:
        fields = agent_config_vars['csv_field_names']
    json = dict()
    for i in range(minlen(fields, message)):
        json[fields[i]] = message[i]
    return json


def minlen(one, two):
    return min(len(one), len(two))


def parse_csv_message(message):
    # filter
    if len(agent_config_vars['filters_include']) != 0:
        # for each provided filter, check if there are any allowed valued
        is_valid = False
        for _filter in agent_config_vars['filters_include']:
            filter_field = _filter.split(':')[0]
            filter_vals = _filter.split(':')[1].split(',')
            filter_check = message[int(filter_field)]
            # check if a valid value
            for filter_val in filter_vals:
                if filter_val.upper() in filter_check.upper():
                    is_valid = True
                    break
            if is_valid:
                break
        if not is_valid:
            logger.debug('filtered message (inclusion): {} not in {}'.format(
                filter_check, filter_vals))
            return
        else:
            logger.debug('passed filter (inclusion)')

    if len(agent_config_vars['filters_exclude']) != 0:
        # for each provided filter, check if there are any disallowed values
        for _filter in agent_config_vars['filters_exclude']:
            filter_field = _filter.split(':')[0]
            filter_vals = _filter.split(':')[1].split(',')
            filter_check = message[int(filter_field)]
            # check if a valid value
            for filter_val in filter_vals:
                if filter_val.upper() in filter_check.upper():
                    logger.debug('filtered message (exclusion): {} in {}'.format(
                        filter_check, filter_val))
                    return
        logger.debug('passed filter (exclusion)')

    # project
    # if isinstance(agent_config_vars['project_field'], int):
    #    check_project(message[agent_config_vars['project_field']])

    # instance
    instance = HOSTNAME
    if isinstance(agent_config_vars['instance_field'], int):
        instance = message[agent_config_vars['instance_field']]

    # device
    device = ''
    if isinstance(agent_config_vars['device_field'], int):
        device = message[agent_config_vars['device_field']]

    # data & timestamp
    columns = [agent_config_vars['timestamp_field']] + agent_config_vars['data_fields']
    row = list(message[i] for i in columns)
    fields = list(agent_config_vars['csv_field_names'][j] for j in agent_config_vars['data_fields'])
    parse_csv_row(row, fields, instance, device)


def parse_csv_data(csv_data, instance, device=''):
    """
    parses CSV data, assuming the format is given as:
        header row:  timestamp,field_1,field_2,...,field_n
        n data rows: TIMESTAMP,value_1,value_2,...,value_n
    """

    # get field names from header row
    field_names = csv_data.pop(0).split(CSV_DELIM)[1:]

    # go through each row
    for row in csv_data:
        if len(row) > 0:
            parse_csv_row(row.split(CSV_DELIM), field_names, instance, device)


def parse_csv_row(row, field_names, instance, device=''):
    timestamp = get_timestamp_from_date_string(row.pop(0))
    if 'METRIC' in if_config_vars['project_type']:
        for i in range(len(row)):
            metric_handoff(timestamp, field_names[i], row[i], instance, device)
    else:
        json_message = dict()
        for i in range(len(row)):
            json_message[field_names[i]] = row[i]
        log_handoff(timestamp, json_message, instance, device)


def get_timestamp_from_date_string(date_string):
    """ parse a date string into unix epoch (ms) """
    timestamp_datetime = get_datetime_from_date_string(date_string)
    return get_timestamp_from_datetime(timestamp_datetime)


def get_datetime_from_date_string(date_string):
    timestamp_datetime = date_string.partition('.')[0]
    if 'strip_tz' in agent_config_vars and agent_config_vars['strip_tz']:
        date_string = ''.join(agent_config_vars['strip_tz_fmt'].split(date_string))
    if 'timestamp_format' in agent_config_vars:
        for timestamp_format in agent_config_vars['timestamp_format']:
            try:
                if timestamp_format == 'epoch':
                    timestamp_datetime = get_datetime_from_unix_epoch(date_string)
                else:
                    timestamp_datetime = datetime.strptime(date_string,
                                                           timestamp_format)
                break
            except Exception as e:
                logger.info('timestamp {} does not match {}'.format(
                    date_string,
                    timestamp_format))
                continue
    else:
        try:
            timestamp_datetime = dateutil.parse.parse(date_string)
        except:
            timestamp_datetime = get_datetime_from_unix_epoch(date_string)
            agent_config_vars['timestamp_format'] = ['epoch']

    return timestamp_datetime


def get_timestamp_from_datetime(timestamp_datetime):
    # add tzinfo
    timestamp_localize = agent_config_vars['timezone'].localize(timestamp_datetime)

    # calc seconds since Unix Epoch 0
    epoch = long(
        (timestamp_localize - datetime(1970, 1, 1, tzinfo=agent_config_vars['timezone'])).total_seconds()) * 1000
    return epoch


def get_datetime_from_unix_epoch(date_string):
    try:
        # strip leading whitespace and zeros
        epoch = date_string.lstrip(' 0')
        # roughly check for a timestamp between ~1973 - ~2286
        if len(epoch) in range(13, 15):
            epoch = int(epoch) / 1000
        elif len(epoch) in range(9, 13):
            epoch = int(epoch)

        return datetime.fromtimestamp(epoch)
    except ValueError:
        # if the date cannot be converted into a number by built-in long()
        logger.warn('Date format not defined & data does not look like unix epoch: {}'.format(date_string))
        sys.exit(1)


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


def run_subproc_once(command, **passthrough):
    command = format_command(command)
    output = subprocess.check_output(command,
                                     universal_newlines=True,
                                     **passthrough).split('\n')
    for line in output:
        yield line


def run_subproc_background(command, **passthrough):
    command = format_command(command)
    try:
        proc = subprocess.Popen(command,
                                universal_newlines=True,
                                stdout=subprocess.PIPE,
                                **passthrough)
        while True:
            yield proc.stdout.readline()
    except Exception as e:
        logger.warn(e)
    finally:
        # make sure process exits
        proc.terminate()
        proc.wait()
        pass


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
    reset_track()
    track['chunk_count'] = 0
    track['entry_count'] = 0

    start_data_processing(thread_number)

    # last chunk
    if len(track['current_row']) > 0 or len(track['current_dict']) > 0:
        logger.debug('Sending last chunk')
        send_data_wrapper()

    logger.debug('Total chunks created: ' + str(track['chunk_count']))
    logger.debug('Total {} entries: {}'.format(
        if_config_vars['project_type'].lower(), track['entry_count']))


def reset_track():
    """ reset the track global for the next chunk """
    track['start_time'] = time.time()
    track['line_count'] = 0
    track['current_row'] = []
    track['current_dict'] = dict()


#########################################
# Functions to handle Log/Incident data #
#########################################
def incident_handoff(timestamp, data, instance, device=''):
    send_log(timestamp, data, instance or HOSTNAME, device)


def deployment_handoff(timestamp, data, instance, device=''):
    send_log(timestamp, data, instance or HOSTNAME, device)


def alert_handoff(timestamp, data, instance, device=''):
    send_log(timestamp, data, instance or HOSTNAME, device)


def log_handoff(timestamp, data, instance, device=''):
    send_log(timestamp, data, instance or HOSTNAME, device)


def send_log(timestamp, data, instance, device=''):
    entry = prepare_log_entry(str(int(timestamp)), data, instance, device)
    track['current_row'].append(entry)
    track['line_count'] += 1
    track['entry_count'] += 1
    if get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size'] or (
            time.time() - track['start_time']) >= if_config_vars['sampling_interval']:
        send_data_wrapper()
    elif track['entry_count'] % 100 == 0:
        logger.debug('Current data object size: {} bytes'.format(
            get_json_size_bytes(track['current_row'])))


def prepare_log_entry(timestamp, data, instance, device=''):
    """ creates the log entry """
    entry = dict()
    entry['data'] = data
    if 'INCIDENT' in if_config_vars['project_type'] or 'DEPLOYMENT' in if_config_vars['project_type']:
        entry['timestamp'] = timestamp
        entry['instanceName'] = make_safe_instance_string(instance, device)
    else:  # LOG or ALERT
        entry['eventId'] = timestamp
        entry['tag'] = make_safe_instance_string(instance, device)
    return entry


###################################
# Functions to handle Metric data #
###################################
def metric_handoff(timestamp, field_name, data, instance, device=''):
    add_and_send_metric(timestamp, field_name, data, instance or HOSTNAME, device)


def add_and_send_metric(timestamp, field_name, data, instance, device=''):
    # validate data
    try:
        data = float(data)
    except Exception as e:
        logger.warning(e)
        logger.warning(
            'timestamp: {}\nfield_name: {}\ninstance: {}\ndevice: {}\ndata: {}'.format(
                timestamp, field_name, instance, device, data))
    else:
        append_metric_data_to_entry(timestamp, field_name, data, instance, device)
        send_metric()


def send_metric():
    track['entry_count'] += 1
    if get_json_size_bytes(track['current_dict']) >= if_config_vars['chunk_size'] or (
            time.time() - track['start_time']) >= if_config_vars['sampling_interval']:
        send_data_wrapper()
    elif track['entry_count'] % 500 == 0:
        logger.debug('Current data object size: {} bytes'.format(
            get_json_size_bytes(track['current_dict'])))


def append_metric_data_to_entry(timestamp, field_name, data, instance, device=''):
    """ creates the metric entry """
    key = '{}[{}]'.format(make_safe_metric_key(field_name),
                          make_safe_instance_string(instance, device))
    ts_str = str(timestamp)
    if ts_str not in track['current_dict']:
        track['current_dict'][ts_str] = dict()
    current_obj = track['current_dict'][ts_str]

    # use the next non-null value to overwrite the prev value
    # for the same metric in the same timestamp
    if key in current_obj.keys():
        if data is not None and len(str(data)) > 0:
            current_obj[key] += '|' + str(data)
    else:
        current_obj[key] = str(data)
    track['current_dict'][ts_str] = current_obj


def transpose_metrics():
    """ flatten data up to the timestamp"""
    for timestamp, kvs in track['current_dict'].items():
        track['line_count'] += 1
        new_row = dict()
        new_row['timestamp'] = timestamp
        for key, value in kvs.items():
            if '|' in value:
                value = statistics.median(
                    map(lambda v: float(v), value.split('|')))
            new_row[key] = str(value)
        track['current_row'].append(new_row)


def fold_up(tree, sentence_tree=False, value_tree=False):
    '''
    Entry point for fold_up. See fold_up_helper for details
    '''
    folded = dict()
    for node_name, node in tree.items():
        fold_up_helper(
            folded,
            node_name,
            node,
            sentence_tree=sentence_tree,
            value_tree=value_tree)
    return folded


def fold_up_helper(current_path, node_name, node, sentence_tree=False, value_tree=False):
    '''
    Recursively build a new sentence tree, where,
        for each node that has only one child,
        that child is "folded up" into its parent.
    The tree therefore treats unique phrases as words s.t.
                      /---> "red apples"
        "I ate" -> "two" -> "green pears"
             \---> "one" -> "yellow banana"
    If sentence_tree=True and there are terminal '_name' nodes,
        this also returns a hash of
            <raw_name : formatted name>
    If value_tree=True and branches terminate in values,
        this also returns a hash of
            <formatted path : value>
    '''
    while isinstance(node, dict) and (len(node.keys()) == 1 or '_name' in node.keys()):
        keys = node.keys()
        # if we've reached a terminal end
        if '_name' in keys:
            if sentence_tree:
                current_path[node['_name']] = node_name
            keys.remove('_name')
            node.pop('_name')
        # if there's still a single key path to follow
        if len(keys) == 1:
            next_key = keys[0]
            node_name += '_' + next_key
            node = node[next_key]

    if not isinstance(node, dict):
        if value_tree:
            # node is the value of the metric node_name
            current_path[node_name] = node
    else:
        for node_nested, node_next in node.items():
            fold_up_helper(
                current_path,
                '{}/{}'.format(node_name, node_nested),
                node_next,
                sentence_tree=sentence_tree,
                value_tree=value_tree)


################################
# Functions to send data to IF #
################################
def send_data_wrapper():
    """ wrapper to send data """
    if 'METRIC' in if_config_vars['project_type']:
        transpose_metrics()
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
    logger.debug('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
    logger.debug('Total Lines: ' + str(track['line_count']))

    # do not send if only testing
    if cli_config_vars['testing']:
        return

    # send the data
    post_url = urlparse.urljoin(if_config_vars['if_url'], get_api_from_project_type())
    send_request(post_url, 'POST', 'Could not send request to IF',
                 str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.',
                 data=data_to_post, proxies=if_config_vars['if_proxies'])
    logger.debug('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def send_request(url, mode='GET', failure_message='Failure!', success_message='Success!', **request_passthrough):
    """ sends a request to the given url """
    # determine if post or get (default)
    req = requests.get
    if mode.upper() == 'POST':
        req = requests.post

    global REQUESTS
    REQUESTS.update(request_passthrough)
    # logger.debug(REQUESTS)

    for i in range(ATTEMPTS):
        try:
            response = req(url, **request_passthrough)
            if response.status_code == httplib.OK:
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

    logger.error('Failed! Gave up after {} attempts.'.format(i + 1))
    return -1


def get_agent_type_from_project_type():
    """ use project type to determine agent type """
    if 'METRIC' in if_config_vars['project_type']:
        if is_replay():
            return 'MetricFileReplay'
        else:
            return 'CUSTOM'
    elif is_replay():
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


def is_replay():
    return 'REPLAY' in if_config_vars['project_type']


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
    PCT_z_FMT = regex.compile(r"[\+\-][0-9]{2}[\:]?[0-9]{2}|\w+\s+\w+\s+\w+")
    PCT_Z_FMT = regex.compile(r"[A-Z]{3,4}")
    FORMAT_STR = regex.compile(r"{(.*?)}")
    HOSTNAME = socket.gethostname().partition('.')[0]
    UNKNOWN_INSTANCE = 'unknownInstance'
    ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
    JSON_LEVEL_DELIM = '.'
    CSV_DELIM = r",|\t"
    ATTEMPTS = 3
    REQUESTS = dict()
    track = dict()

    # get config
    cli_config_vars = get_cli_config_vars()
    logger = set_logger_config(cli_config_vars['log_level'])
    logger.debug(cli_config_vars)
    if_config_vars = get_if_config_vars()
    agent_config_vars = get_agent_config_vars()
    print_summary_info()

    # start data processing
    for i in range(0, cli_config_vars['threads']):
        Process(target=initialize_data_gathering,
                args=(i,)
                ).start()

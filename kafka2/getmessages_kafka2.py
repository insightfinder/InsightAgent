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
from optparse import OptionParser
from multiprocessing import Process
from datetime import datetime
import urlparse
import httplib
import requests
import statistics
import subprocess
import shlex

from kafka import KafkaConsumer

'''
This script gathers data to send to Insightfinder
'''


def start_data_processing(thread_number):
    # open consumer
    consumer = KafkaConsumer(**agent_config_vars['kafka_kwargs'])
    logger.info('Started consumer number ' + str(thread_number))
    # subscribe to given topics
    consumer.subscribe(agent_config_vars['topics'])
    logger.info('Successfully subscribed to topics' + str(agent_config_vars['topics']))
    # start consuming messages
    parse_messages_kafka(consumer)
    consumer.close()
    logger.info('Closed consumer number ' + str(thread_number))


def parse_messages_kafka(consumer):
    logger.info('Reading messages')
    for message in consumer:
        try:
            logger.debug('Message received')
            logger.debug(message.value)
            if 'JSON' in agent_config_vars['data_format']:
                parse_json_message(json.loads(str(message.value)))
            elif 'CSV' in agent_config_vars['data_format']:
                parse_json_message(label_message(message.value.split(',')))
            else:
                parse_raw_message(message)
        except Exception as e:
            logger.warn('Error when parsing message')
            logger.warn(e)
            continue


def get_agent_config_vars():
    """ Read and parse config.ini """
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini'))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini')))
        try:
            # proxy settings
            agent_http_proxy = config_parser.get('kafka', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('kafka', 'agent_https_proxy')

            # kafka settings
            kafka_config = {
                # hardcoded
                'api_version': (0, 9),
                'auto_offset_reset': 'latest',
                'consumer_timeout_ms': 30 * if_config_vars['sampling_interval'] * 1000 if 'METRIC' in if_config_vars[
                    'project_type'] or 'LOG' in if_config_vars['project_type'] else None,

                # consumer settings
                'group_id': config_parser.get('kafka', 'group_id'),
                'client_id': config_parser.get('kafka', 'client_id'),

                # SSL
                'security_protocol': 'SSL' if config_parser.get('kafka', 'security_protocol') == 'SSL' else 'PLAINTEXT',
                'ssl_context': config_parser.get('kafka', 'ssl_context'),
                'ssl_cafile': config_parser.get('kafka', 'ssl_cafile'),
                'ssl_certfile': config_parser.get('kafka', 'ssl_certfile'),
                'ssl_keyfile': config_parser.get('kafka', 'ssl_keyfile'),
                'ssl_password': config_parser.get('kafka', 'ssl_password'),
                'ssl_crlfile': config_parser.get('kafka', 'ssl_crlfile'),
                'ssl_ciphers': config_parser.get('kafka', 'ssl_ciphers'),
                'ssl_check_hostname': ternary_tfd(config_parser.get('kafka', 'ssl_check_hostname')),

                # SASL
                'sasl_mechanism': config_parser.get('kafka', 'sasl_mechanism'),
                'sasl_plain_username': config_parser.get('kafka', 'sasl_plain_username'),
                'sasl_plain_password': config_parser.get('kafka', 'sasl_plain_password'),
                'sasl_kerberos_service_name': config_parser.get('kafka', 'sasl_kerberos_service_name'),
                'sasl_kerberos_domain_name': config_parser.get('kafka', 'sasl_kerberos_domain_name'),
                'sasl_oauth_token_provider': config_parser.get('kafka', 'sasl_oauth_token_provider')
            }

            # only keep settings with values
            kafka_kwargs = {k: v for (k, v) in kafka_config.items() if v}

            # check SASL
            if 'sasl_mechanism' in kafka_kwargs:
                if kafka_kwargs['sasl_mechanism'] not in {'PLAIN', 'GSSAPI', 'OAUTHBEARER'}:
                    logger.warn('sasl_mechanism not one of PLAIN, GSSAPI, or OAUTHBEARER')
                    kafka_kwargs.pop('sasl_mechanism')
                elif kafka_kwargs['sasl_mechanism'] == 'PLAIN':
                    # set required vars for plain sasl if not present
                    if 'sasl_plain_username' not in kafka_kwargs:
                        kafka_kwargs['sasl_plain_username'] = ''
                    if 'sasl_plain_password' not in kafka_kwargs:
                        kafka_kwargs['sasl_plain_password'] = ''

            # handle boolean setting
            if config_parser.get('kafka', 'ssl_check_hostname').upper() == 'FALSE':
                kafka_kwargs['ssl_check_hostname'] = False

            # handle required arrays
            # bootstrap serverss
            if len(config_parser.get('kafka', 'bootstrap_servers')) != 0:
                kafka_kwargs['bootstrap_servers'] = config_parser.get('kafka', 'bootstrap_servers').strip().split(',')
            else:
                config_error('bootstrap_servers')

            # topics
            if len(config_parser.get('kafka', 'topics')) != 0:
                topics = config_parser.get('kafka', 'topics').split(',')
            else:
                config_error('topics')

            # filters
            filters_include = config_parser.get('kafka', 'filters_include')
            filters_exclude = config_parser.get('kafka', 'filters_exclude')

            # message parsing
            timestamp_format = config_parser.get('kafka', 'timestamp_format', raw=True)
            timestamp_field = config_parser.get('kafka', 'timestamp_field', raw=True) or 'timestamp'
            timezone = config_parser.get('kafka', 'timezone') or 'UTC'
            instance_field = config_parser.get('kafka', 'instance_field', raw=True)
            device_field = config_parser.get('kafka', 'device_field', raw=True)
            data_fields = config_parser.get('kafka', 'data_fields', raw=True)

            # definitions
            data_format = config_parser.get('kafka', 'data_format').upper()
            csv_field_names = config_parser.get('kafka', 'csv_field_names')
            csv_field_delimiter = config_parser.get('kafka', 'csv_field_delimiter', raw=True) or ',|\t'
            json_top_level = config_parser.get('kafka', 'json_top_level')
            raw_regex = config_parser.get('kafka', 'raw_regex', raw=True)
            raw_start_regex = config_parser.get('kafka', 'raw_start_regex', raw=True)

            # metric buffer
            all_metrics = config_parser.get('kafka', 'all_metrics')
            metric_buffer_size_mb = config_parser.get('kafka', 'metric_buffer_size_mb') or '10'

        except ConfigParser.NoOptionError:
            config_error()

        # any post-processing
        # check SASL
        if 'sasl_mechanism' in kafka_kwargs:
            if kafka_kwargs['sasl_mechanism'] not in {'PLAIN', 'GSSAPI', 'OAUTHBEARER'}:
                logger.warn('sasl_mechanism not one of PLAIN, GSSAPI, or OAUTHBEARER')
                kafka_kwargs.pop('sasl_mechanism')
            elif kafka_kwargs['sasl_mechanism'] == 'PLAIN':
                # set required vars for plain sasl if not present
                if 'sasl_plain_username' not in kafka_kwargs:
                    kafka_kwargs['sasl_plain_username'] = ''
                if 'sasl_plain_password' not in kafka_kwargs:
                    kafka_kwargs['sasl_plain_password'] = ''

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
        # project_field = project_field.split(',')
        instance_field = instance_field.split(',')
        device_field = device_field.split(',')
        timestamp_field = timestamp_field.split(',')
        if len(data_fields) != 0:
            data_fields = data_fields.split(',')
            # if project_field in data_fields:
            #    data_fields.pop(data_fields.index(project_field))
            if instance_field in data_fields:
                data_fields.pop(data_fields.index(instance_field))
            if device_field in data_fields:
                data_fields.pop(data_fields.index(device_field))
            if timestamp_field in data_fields:
                data_fields.pop(data_fields.index(timestamp_field))

        # timestamp format
        if len(timestamp_format) != 0:
            timestamp_format = filter(lambda x: x.strip(), timestamp_format.split(','))
        else:
            config_error('timestamp_format')

        if timezone not in pytz.all_timezones:
            config_error('timezone')
        else:
            timezone = pytz.timezone(timezone)

        # data format
        if data_format == 'CSV':
            if len(csv_field_names) == 0:
                config_error('csv_field_names')
            csv_field_names = csv_field_names.split(',')
            try:
                csv_field_delimiter = regex.compile(csv_field_delimiter)
            except Exception as e:
                config_error('csv_field_delimiter')
        elif data_format == 'RAW':
            try:
                raw_regex = regex.compile(raw_regex)
            except Exception as e:
                config_error('raw_regex')
            # multiline
            if len(raw_start_regex) != 0:
                if raw_start_regex[0] != '^':
                    config_error('raw_start_regex')
                try:
                    raw_start_regex = regex.compile(raw_start_regex)
                except Exception as e:
                    config_error('raw_start_regex')
        elif data_format == 'JSON':
            pass
        else:
            config_error('data_format')

        # defaults
        if all_metrics:
            all_metrics = all_metrics.split(',')

        # add parsed variables to a global
        config_vars = {
            'kafka_kwargs': kafka_kwargs,
            'topics': topics,
            'filters_include': filters_include,
            'filters_exclude': filters_exclude,
            'data_format': data_format,
            'raw_regex': raw_regex,
            'raw_start_regex': raw_start_regex,
            'csv_field_names': csv_field_names,
            'csv_field_delimiter': csv_field_delimiter,
            'json_top_level': json_top_level,
            'timestamp_format': timestamp_format,
            'timezone': timezone,
            'timestamp_field': timestamp_field,
            'instance_field': instance_field,
            'device_field': device_field,
            'data_fields': data_fields,
            'proxies': agent_proxies,
            'all_metrics': all_metrics,
            'metric_buffer_size': int(metric_buffer_size_mb) * 1024 * 1024,  # as bytes
        }

        return config_vars
    else:
        config_error_no_config()


#########################
### START_BOILERPLATE ###
#########################
def get_if_config_vars():
    """ get config.ini vars """
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini'))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini')))
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


def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    """
    ## not ready.
    parser.add_option('--threads', default=1, action='store', dest='threads',
                      help='Number of threads to run')
    """
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet',
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose',
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing',
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


def check_csv_fieldnames(csv_field_names, all_fields):
    # required
    for field, _map in all_fields['required_fields']:
        _map['index'] = get_field_index(
            csv_field_names,
            _map['name'],
            field,
            True)

    # optional
    for field, _map in all_fields['optional_fields']:
        if len(_map['name']) != 0:
            index = get_field_index(
                csv_field_names,
                _map['name'],
                field)
            _map['index'] = index if isinstance(index, int) else ''

    # filters
    for field, _map in all_fields['filters']:
        if len(_map['name']) != 0:
            filters_temp = []
            for _filter in _map['name']:
                filter_field = _filter.split(':')[0]
                filter_vals = _filter.split(':')[1]
                filter_index = get_field_index(
                    csv_field_names,
                    filter_field,
                    field)
                if isinstance(filter_index, int):
                    filter_temp = '{}:{}'.format(filter_index, filter_vals)
                    filters_temp.append(filter_temp)
            _map['filter'] = filters_temp

    # data
    if len(all_fields['data_fields']) != 0:
        data_fields_temp = []
        for data_field in all_fields['data_fields']:
            data_field_temp = get_field_index(
                csv_field_names,
                data_field,
                'data_field')
            if isinstance(data_field_temp, int):
                data_fields_temp.append(data_field_temp)
        all_fields['data_fields'] = data_fields_temp
    if len(all_fields['data_fields']) == 0:
        # use all non-timestamp fields
        all_fields['data_fields'] = range(len(csv_field_names))

    return all_fields


def ternary_tfd(b, default=''):
    if TRUE.match(b):
        return True
    elif FALSE.match(b):
        return False
    else:
        return default


def is_in(find, find_in):
    if isinstance(find, (set, list, tuple)):
        for f in find:
            if f in find_in:
                return True
    else:
        if find in find_in:
            return True
    return False


def get_sentence_segment(sentence, start, end=None):
    segment = sentence.split(' ')[start:end]
    return ' '.join(segment)


def check_project(project_name):
    if 'token' in if_config_vars and len(if_config_vars['token']) != 0:
        logger.debug(project_name)
        try:
            # check for existing project
            check_url = urlparse.urljoin(if_config_vars['if_url'], '/api/v1/getprojectstatus')
            output_check_project = subprocess.check_output(
                'curl "' + check_url + '?userName=' + if_config_vars['user_name'] + '&token=' + if_config_vars[
                    'token'] + '&projectList=%5B%7B%22projectName%22%3A%22' + project_name + '%22%2C%22customerName%22%3A%22' +
                if_config_vars['user_name'] + '%22%2C%22projectType%22%3A%22CUSTOM%22%7D%5D&tzOffset=-14400000"',
                shell=True)
            # create project if no existing project
            if project_name not in output_check_project:
                logger.debug('creating project')
                create_url = urlparse.urljoin(if_config_vars['if_url'], '/api/v1/add-custom-project')
                output_create_project = subprocess.check_output(
                    'no_proxy= curl -d "userName=' + if_config_vars['user_name'] + '&token=' + if_config_vars[
                        'token'] + '&projectName=' + project_name + '&instanceType=PrivateCloud&projectCloudType=PrivateCloud&dataType=' + get_data_type_from_project_type() + '&samplingInterval=' + str(
                        if_config_vars['sampling_interval'] / 60) + '&samplingIntervalInSeconds=' + str(if_config_vars[
                                                                                                            'sampling_interval']) + '&zone=&email=&access-key=&secrete-key=&insightAgentType=' + get_insight_agent_type_from_project_type() + '" -H "Content-Type: application/x-www-form-urlencoded" -X POST ' + create_url + '?tzOffset=-18000000',
                    shell=True)
            # set project name to proposed name
            if_config_vars['project_name'] = project_name
            # try to add new project to system
            if 'system_name' in if_config_vars and len(if_config_vars['system_name']) != 0:
                system_url = urlparse.urljoin(if_config_vars['if_url'], '/api/v1/projects/update')
                output_update_project = subprocess.check_output(
                    'no_proxy= curl -d "userName=' + if_config_vars['user_name'] + '&token=' + if_config_vars[
                        'token'] + '&operation=updateprojsettings&projectName=' + project_name + '&systemName=' +
                    if_config_vars[
                        'system_name'] + '" -H "Content-Type: application/x-www-form-urlencoded" -X POST ' + system_url + '?tzOffset=-18000000',
                    shell=True)
        except subprocess.CalledProcessError as e:
            logger.error('Unable to create project for ' + project_name + '. Data will be sent to ' + if_config_vars[
                'project_name'])


def get_field_index(field_names, field, label, is_required=False):
    err_code = ''
    try:
        temp = int(field)
        if temp > len(field_names):
            err_msg = 'field {} is not a valid array index given field names {}'.format(field, field_names)
            field = err_code
        else:
            field = temp
    # not an integer
    except ValueError:
        try:
            field = field_names.index(field)
        # not in the field names
        except ValueError:
            err_msg = 'field {} is not a valid field in field names {}'.format(field, field_names)
            field = err_code
    finally:
        if field == err_code:
            logger.warn('Agent not configured correctly ({})\n{}'.format(label, err_msg))
            if is_required:
                sys.exit(1)
            return
        else:
            return field


def should_include_per_config(setting, value):
    """ determine if an agent config filter setting would exclude a given value """
    return len(agent_config_vars[setting]) != 0 and value not in agent_config_vars[setting]


def should_exclude_per_config(setting, value):
    """ determine if an agent config exclude setting would exclude a given value """
    return len(agent_config_vars[setting]) != 0 and value in agent_config_vars[setting]


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    return len(bytearray(json.dumps(json_data)))


def get_all_files(files, file_regex_c):
    return [i for j in
            map(lambda k:
                get_file_list_for_directory(k, file_regex_c),
                files)
            for i in j if i]


def get_file_list_for_directory(root_path='/', file_name_regex_c=''):
    root_path = os.path.expanduser(root_path)
    if os.path.isdir(root_path):
        file_list = []
        for path, subdirs, files in os.walk(root_path):
            for name in files:
                if check_regex(file_name_regex_c, name):
                    file_list.append(os.path.join(path, name))
        return file_list
    elif os.path.isfile(root_path):
        if check_regex(file_name_regex_c, root_path):
            return [root_path]
    return []


def parse_raw_line(message, line):
    # if multiline
    if agent_config_vars['raw_start_regex']:
        # if new message, parse old and start new
        if agent_config_vars['raw_start_regex'].match(line):
            parse_raw_message(message)
            message = line
        else:  # add to current message
            logger.debug('continue building message')
            message += line
    else:
        parse_raw_message(line)
    return message


def parse_raw_message(message):
    matches = agent_config_vars['raw_regex'].match(message)
    if matches:
        message_json = matches.groupdict()
        message_json['_raw'] = message
        parse_json_message(message_json)


def check_regex(pattern_c, check):
    return not pattern_c or pattern_c.match(check)


def is_formatted(setting_value):
    """ returns True if the setting is a format string """
    return check_regex(FORMAT_STR, setting_value)


def is_math_expr(setting_value):
    return '=' in setting_value


def get_math_expr(setting_value):
    return setting_value.strip('=')


def is_named_data_field(setting_value):
    return ':' in setting_value


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
                                    default='',
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
        setting_value = setting_value.split(':')
        # get name
        name = setting_value[0]
        if is_formatted(name):
            name = parse_formatted(message,
                                   name,
                                   default=name)
        # get value
        value = setting_value[1]
        # check if math
        evaluate = False
        if is_math_expr(value):
            evaluate = True
            value = get_math_expr(value)
        if is_formatted(value):
            value = parse_formatted(message,
                                    value,
                                    default=value,
                                    allow_list=True)
        if evaluate:
            value = eval(value)
    else:
        name = setting_value
        value = get_json_field(message,
                               setting_value,
                               allow_list=True)
    return (name, value)


def get_single_value(message, config_setting, default='', allow_list=False, remove=False):
    if config_setting not in agent_config_vars or len(agent_config_vars[config_setting]) == 0:
        return default
    setting_value = agent_config_vars[config_setting]
    if isinstance(setting_value, (set, list, tuple)):
        setting_value_single = setting_value[0]
    else:
        setting_value_single = setting_value
    if is_formatted(setting_value_single):
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
    if len(next_fields) == 0 and remove:
        # last field to grab, so remove it
        nested_value.pop(next_field)

    # check the next value
    if next_value is None:
        # no next value defined
        return ''
    elif len(bytes(next_value)) == 0:
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
    return str(value)


def parse_json_message(messages):
    if len(agent_config_vars['json_top_level']) != 0:
        if agent_config_vars['json_top_level'] == '[]' and isinstance(messages, (list, set, tuple)):
            for message in messages:
                parse_json_message_single(message)
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
    elif isinstance(messages, (list, set, tuple)):
        for message_single in messages:
            parse_json_message_single(message_single)
    else:
        parse_json_message_single(messages)


def parse_json_message_single(message):
    # message = json.loads(json.dumps(message))
    # filter
    if len(agent_config_vars['filters_include']) != 0:
        # for each provided filter
        is_valid = False
        for _filter in agent_config_vars['filters_include']:
            filter_field = _filter.split(':')[0]
            filter_vals = _filter.split(':')[1].split(',')
            filter_check = get_json_field(
                message,
                filter_field.split(JSON_LEVEL_DELIM),
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
                filter_field.split(JSON_LEVEL_DELIM),
                allow_list=True)
            # check if a valid value
            for filter_val in filter_vals:
                if filter_val.upper() in filter_check.upper():
                    logger.debug('filtered message (exclusion): {} in {}'.format(
                        filter_val, filter_check))
                    return
        logger.debug('passed filter (exclusion)')

    instance = get_single_value(message,
                                'instance_field',
                                default=HOSTNAME,
                                remove=True)
    device = get_single_value(message,
                              'device_field',
                              remove=True)
    # get timestamp
    try:
        timestamp = get_single_value(message,
                                     'timestamp_field',
                                     remove=True)
        timestamp = [timestamp]
    except ListNotAllowedError as lnae:
        timestamp = get_single_value(message,
                                     'timestamp_field',
                                     remove=True,
                                     allow_list=True)
    except Exception as e:
        logger.warn(e)
        sys.exit(1)

    # get data
    data = get_data_values(timestamp, message)

    # hand off
    for timestamp, report_data in data.items():
        ts = get_timestamp_from_date_string(timestamp)
        if not ts:
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
    if agent_config_vars['data_format'] == 'CSV':
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
    if not timestamp:
        return
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
    datetime_obj = None
    epoch = None
    if 'timestamp_format' in agent_config_vars:
        for timestamp_format in agent_config_vars['timestamp_format']:
            try:
                if timestamp_format == 'epoch':
                    if 13 <= len(date_string) < 15:
                        timestamp = int(date_string) / 1000
                        datetime_obj = arrow.get(timestamp, tzinfo=agent_config_vars['timezone'].zone)
                    elif 9 <= len(date_string) < 13:
                        timestamp = int(date_string)
                        datetime_obj = arrow.get(timestamp, tzinfo=agent_config_vars['timezone'].zone)
                    else:
                        raise
                else:
                    datetime_obj = arrow.get(date_string, timestamp_format, tzinfo=agent_config_vars['timezone'].zone)
                break
            except Exception as e:
                logger.debug(e)
                logger.debug('timestamp {} does not match {}'.format(date_string, timestamp_format))
                continue
    else:
        try:
            datetime_obj = arrow.get(date_string, tzinfo=agent_config_vars['timezone'].zone)
        except Exception as e:
            logger.debug(e)
            logger.error('timestamp {} can not parse'.format(date_string))

    # get epoch (misc)
    if datetime_obj:
        epoch = int(datetime_obj.float_timestamp * 1000)

    return epoch


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
    reset_metric_buffer()
    reset_track()
    track['chunk_count'] = 0
    track['entry_count'] = 0

    start_data_processing(thread_number)

    # move all buffer data to current data, and send
    while metric_buffer['buffer_ts_list']:
        (ts, key) = metric_buffer['buffer_ts_list'].pop()
        transpose_metrics(ts, key)
        if get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
            logger.debug('Sending buffer chunk')
            send_data_wrapper()

    # last chunk
    if len(track['current_row']) > 0:
        logger.debug('Sending last chunk')
        send_data_wrapper()

    logger.debug('Total chunks created: ' + str(track['chunk_count']))
    logger.debug('Total {} entries: {}'.format(
        if_config_vars['project_type'].lower(), track['entry_count']))


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
    send_metric(timestamp, field_name, data, instance or HOSTNAME, device)


def send_metric(timestamp, field_name, data, instance, device=''):
    # validate data
    try:
        data = float(data)
    except Exception as e:
        logger.warning(e)
        logger.warning(
            'timestamp: {}\nfield_name: {}\ninstance: {}\ndevice: {}\ndata: {}'.format(
                timestamp, field_name, instance, device, data))
    else:
        append_metric_data_to_buffer(timestamp, field_name, data, instance, device)
        track['entry_count'] += 1

        # send data if all metrics of instance is collected
        while metric_buffer['buffer_collected_list']:
            (ts, key, index) = metric_buffer['buffer_collected_list'].pop()
            del metric_buffer['buffer_ts_list'][index]
            metric_buffer['buffer_collected_dict'].pop(key)
            transpose_metrics(ts, key)
            if get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
                logger.debug('Sending buffer chunk')
                send_data_wrapper()

        # send data if buffer size is bigger than threshold
        while get_json_size_bytes(metric_buffer['buffer_dict']) >= agent_config_vars['metric_buffer_size'] and \
                metric_buffer['buffer_ts_list']:
            (ts, key) = metric_buffer['buffer_ts_list'].pop()
            transpose_metrics(ts, key)
            if get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
                logger.debug('Sending buffer chunk')
                send_data_wrapper()

        # send data
        if get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size'] or (
                time.time() - track['start_time']) >= if_config_vars['run_interval']:
            send_data_wrapper()
        elif track['entry_count'] % 500 == 0:
            logger.debug('Buffer data object size: {} bytes'.format(
                get_json_size_bytes(metric_buffer['buffer_dict'])))


def append_metric_data_to_buffer(timestamp, field_name, data, instance, device=''):
    """ creates the metric entry """
    ts_str = str(timestamp)
    instance_str = make_safe_instance_string(instance, device)
    key = '{}-{}'.format(ts_str, instance_str)
    metric_str = make_safe_metric_key(field_name)
    metric_key = '{}[{}]'.format(metric_str, instance_str)

    if key not in metric_buffer['buffer_key_list']:
        # add timestamp in buffer_ts_list and buffer_dict
        metric_buffer['buffer_key_list'].append(key)
        metric_buffer['buffer_ts_list'].append((timestamp, key))
        metric_buffer['buffer_ts_list'].sort(key=lambda elem: elem[0], reverse=True)
        metric_buffer['buffer_dict'][key] = dict()
        metric_buffer['buffer_collected_dict'][key] = []
    metric_buffer['buffer_dict'][key][metric_key] = str(data)
    metric_buffer['buffer_collected_dict'][key].append(metric_str)

    # if all metrics of ts_instance is collected, then send these data
    if agent_config_vars['all_metrics'] and set(agent_config_vars['all_metrics']) <= set(
            metric_buffer['buffer_collected_dict'][key]):
        metric_buffer['buffer_collected_list'].append(
            (timestamp, key, metric_buffer['buffer_ts_list'].index((timestamp, key))))


def transpose_metrics(ts, key):
    metric_buffer['buffer_key_list'].remove(key)
    track['current_row'].append(
        dict({'timestamp': str(ts)}, **metric_buffer['buffer_dict'].pop(key))
    )


def build_metric_name_map():
    '''
    Contstructs a hash of <raw_metric_name>: <formatted_metric_name>
    '''
    # get metrics from the global
    metrics = agent_config_vars['metrics_copy']
    # initialize the hash of formatted names
    agent_config_vars['metrics_names'] = dict()
    tree = build_sentence_tree(metrics)
    min_tree = fold_up(tree, sentence_tree=True)


def build_sentence_tree(sentences):
    '''
    Takes a list of sentences and builds a tree from the words
        I ate two red apples ----\                     /---> "red" ----> "apples" -> "_name" -> "I ate two red apples"
        I ate two green pears ----> "I" -> "ate" -> "two" -> "green" --> "pears" --> "_name" -> "I ate two green pears"
        I ate one yellow banana -/             \--> "one" -> "yellow" -> "banana" -> "_name" -> "I ate one yellow banana"
    '''
    tree = dict()
    for sentence in sentences:
        words = format_sentence(sentence)
        current_path = tree
        for word in words:
            if word not in current_path:
                current_path[word] = dict()
            current_path = current_path[word]
        # add a terminal _name node with the raw sentence as the value
        current_path['_name'] = sentence
    return tree


def format_sentence(sentence):
    '''
    Takes a sentence and chops it into an array by word
    Implementation-specifc
    '''
    words = sentence.strip(':')
    words = COLONS.sub('/', words)
    words = UNDERSCORE.sub('/', words)
    words = words.split('/')
    return words


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

    logger.error('Failed! Gave up after {} attempts.'.format(i))
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
        if is_replay():
            return 'containerReplay'
        else:
            return 'containerStreaming'
    elif is_replay():
        if 'METRIC' in if_config_vars['project_type']:
            return 'MetricFile'
        else:
            return 'LogFile'
    else:
        return 'Custom'


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
    FORMAT_STR = regex.compile(r"{(.*?)}")
    HOSTNAME = socket.gethostname().partition('.')[0]
    ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
    JSON_LEVEL_DELIM = '.'
    CSV_DELIM = ','
    ATTEMPTS = 3
    track = dict()
    metric_buffer = dict()

    # get config
    cli_config_vars = get_cli_config_vars()
    logger = set_logger_config(cli_config_vars['log_level'])
    if_config_vars = get_if_config_vars()
    agent_config_vars = get_agent_config_vars()
    print_summary_info()

    # start data processing
    process_list = []
    for i in range(0, cli_config_vars['threads']):
        p = Process(target=initialize_data_gathering,
                    args=(i,)
                    )
        process_list.append(p)

    for p in process_list:
        p.start()

    for p in process_list:
        p.join()

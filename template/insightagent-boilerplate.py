#!/usr/bin/env python
import ConfigParser
import collections
import json
import logging
import os
import re
import socket
import sys
import time
import pytz
from optparse import OptionParser
from multiprocessing import Process
from itertools import islice
from datetime import datetime
import datefinder
import urlparse
import httplib
import requests
import statistics

'''
This script gathers data to send to Insightfinder
'''


def start_data_processing(thread_number):
    """ TODO: replace with your code.
    Most work regarding sending to IF is abstracted away for you.
    This function will get the data to send and prepare it for the API.
    The general outline should be:
    0. Define the project type in config.ini
    1. Parse config options
    2. Gather data
    3. Parse each entry
    4. Call the appropriate handoff function
        metric_handoff()
        log_handoff()
        alert_handoff()
        incident_handoff()
        deployment_handoff()
    See zipkin for an example that uses os.fork to send both metric and log data.
    """


def raw_parse_log(message):
    # call as log_handoff(*raw_parse(message))
    timestamp = get_timestamp_from_date_string(time.time()) 
    data = 'data'
    instance = 'instance'
    device = 'device'
    return timestamp, data, instance, device


def raw_parse_metric(message):
    # call as metric_handoff(*raw_parse(message))
    timestamp = get_timestamp_from_date_string(time.time()) 
    metric = 'metric'
    data = 'data'
    instance = 'instance'
    device = 'device'
    return timestamp, metric, data, instance, device
    

def get_agent_config_vars():
    """ Read and parse config.ini """
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini'))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini')))
        try:
            ## TODO: fill out the fields to grab. examples given below
            ## replace 'agent' with the appropriate section header.
            # proxies
            agent_http_proxy = config_parser.get('agent', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('agent', 'agent_https_proxy')
            
            # filters
            filters_include = config_parser.get('agent', 'filters_include')
            filters_exclude = config_parser.get('agent', 'filters_exclude')

            # message parsing
            data_format = config_parser.get('agent', 'data_format').upper()
            csv_field_names = config_parser.get('agent', 'csv_field_names')
            json_top_level = config_parser.get('agent', 'json_top_level')
            project_field = config_parser.get('agent', 'project_field')
            instance_field = config_parser.get('agent', 'instance_field')
            device_field = config_parser.get('agent', 'device_field')
            timestamp_field = config_parser.get('agent', 'timestamp_field') or 'timestamp'
            timestamp_format = config_parser.get('agent', 'timestamp_format', raw=True) or 'epoch'
            data_fields = config_parser.get('agent', 'data_fields')
                    
        except ConfigParser.NoOptionError:
            logger.error('Agent not correctly configured. Check config file.')
            sys.exit(1)
         
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
        if len(data_fields) != 0:
            data_fields = data_fields.split(',')
        
        # timestamp format
        if '%z' in timestamp_format or '%Z' in timestamp_format:
            ts_format_info = strip_tz_info(timestamp_format)
        else:
            ts_format_info = {'strip_tz': False, 'strip_tz_fmt': '', 'timestamp_format': timestamp_format}
        
        if data_format not in { 'CSV', 'JSON' }:
            data_format = 'RAW'

        # CSV-specific
        if data_format == 'CSV':
            if len(csv_field_names) == 0:
                logger.warning('Agent not correctly configured (csv_field_names)')
                sys.exit()
                
            filters = {'filters_include': {'name': filters_include},
                       'filters_exclude': {'name': filters_exclude}}
            optional_fields = {'project_field': {'name': project_field},
                               'instance_field': {'name': instance_field},
                               'device_field': {'name': device_field}}
            required_fields = {'timestamp_field': {'name': timestamp_field}}
            all_fields = {'filters': filter_fields,
                          'required_fields': required_fields,
                          'optional_fields': optional_fields,
                          'data_fields': data_fields}
            all_fields = check_csv_field_indeces(csv_field_names.split(','), all_fields)
            filters_include = all_fields['filters']['filters_include']['filter']
            filters_exclude = all_fields['filters']['filters_exclude']['filter']
            project_field = all_fields['optional_fields']['project_field']['index']
            instance_field = all_fields['optional_fields']['instance_field']['index']
            device_field = all_fields['optional_fields']['device_field']['index']
            data_fields = all_fields['data_fields']
            timestamp_field = all_fields['required_fields']['timestamp_field']['index']
            
            if timestamp_field in data_fields:
                data_fields.pop(timestamp_field)

        # add parsed variables to a global
        config_vars = {
            'proxies': agent_proxies,
            'filters_include': filters_include,
            'filters_exclude': filters_exclude,
            'data_format': data_format,
            'json_top_level': json_top_level,
            'csv_field_names': csv_field_names,
            'project_field': project_field,
            'instance_field': instance_field,
            'device_field': device_field,
            'data_fields': data_fields,
            'timestamp_field': timestamp_field,
            'timestamp_format': ts_format_info['timestamp_format'],
            'strip_tz': ts_format_info['strip_tz'],
            'strip_tz_fmt': ts_format_info['strip_tz_fmt']
        }

        return config_vars
    else:
        logger.warning('No config file found. Exiting...')
        exit()


########################
# Start of boilerplate #
########################
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
            chunk_size_kb = config_parser.get('insightfinder', 'chunk_size_kb')
            if_url = config_parser.get('insightfinder', 'if_url')
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
        except ConfigParser.NoOptionError:
            logger.error('Agent not correctly configured. Check config file.')
            sys.exit(1)

        # check required variables
        if len(user_name) == 0:
            logger.warning('Agent not correctly configured (user_name). Check config file.')
            sys.exit(1)
        if len(license_key) == 0:
            logger.warning('Agent not correctly configured (license_key). Check config file.')
            sys.exit(1)
        if len(project_name) == 0:
            logger.warning('Agent not correctly configured (project_name). Check config file.')
            sys.exit(1)
        if len(project_type) == 0:
            logger.warning('Agent not correctly configured (project_type). Check config file.')
            sys.exit(1)
        
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
           logger.warning('Agent not correctly configured (project_type). Check config file.')
           sys.exit(1)  

        if len(sampling_interval) == 0:
            if 'METRIC' in project_type:
                logger.warning('Agent not correctly configured (sampling_interval). Check config file.')
                sys.exit(1)
            else:
                # set default for non-metric
                sampling_interval = 10

        if sampling_interval.endswith('s'):
            sampling_interval = int(sampling_interval[:-1])
        else:
            sampling_interval = int(sampling_interval) * 60

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
            'sampling_interval': int(sampling_interval),     # as seconds
            'chunk_size': int(chunk_size_kb) * 1024,         # as bytes
            'if_url': if_url,
            'if_proxies': if_proxies
        }

        return config_vars
    else:
        logger.error('Agent not correctly configured. Check config file.')
        sys.exit(1)


def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    """
    ## not ready.
    parser.add_option('--threads', default=1,
                      action='store', dest='threads', help='Number of threads to run')
    """
    parser.add_option('--tz', default='UTC', action='store', dest='time_zone', 
                      help='Timezone of the data. See pytz.all_timezones')
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
        'log_level': logging.INFO,
        'time_zone': pytz.utc
        }

    if options.testing:
        config_vars['testing'] = True

    if options.verbose or options.testing:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING

    if len(options.time_zone) != 0 and options.time_zone in pytz.all_timezones:
        config_vars['time_zone'] = pytz.timezone(options.time_zone)

    return config_vars


def strip_tz_info(timestamp_format):
    # strptime() doesn't allow timezone info
    if '%Z' in timestamp_format:
        position = timestamp_format.index('%Z')
        strip_tz_fmt = PCT_Z_FMT
    if '%z' in timestamp_format:
        position = timestamp_format.index('%z')
        strip_tz_fmt = PCT_z_FMT
    
    if len(timestamp_format) > (position + 2):
        timestamp_format = timestamp_format[:position] + timestamp_format[position+2:]
    else:
        timestamp_format = timestamp_format[:position]
    if cli_config_vars['time_zone'] == pytz.timezone('UTC'):
        logger.warning('Time zone info will be stripped from timestamps, but no time zone info was supplied in the config. Assuming UTC')
    
    return {'strip_tz': True, 'strip_tz_fmt': strip_tz_fmt, 'timestamp_format': timestamp_format}


def check_csv_fieldnames(csv_field_names, all_fields):
    # required
    for field in all_fields['required_fields']:
        all_fields['required_fields'][field]['index'] = get_field_index(csv_field_names, all_fields['optional_fields'][field]['name'], field, True)

    # optional
    for field in all_fields['optional_fields']:
        if len(all_fields['optional_fields'][field]['name']) != 0:
            index = get_field_index(csv_field_names, all_fields['optional_fields'][field]['name'], field)
            if isinstance(index, int):
                all_fields['optional_fields'][field]['index'] = index
            else:
                all_fields['optional_fields'][field]['index'] = ''

    # filters
    for field in all_fields['filters']:
        if len(all_fields['filters'][field]['name']) != 0:
            filters_temp = []
            for _filter in all_fields['filters'][field]['name']:
                filter_field = _filter.split(':')[0]          
                filter_vals = _filter.split(':')[1]
                filter_index = get_field_index(csv_field_names, filter_field, field)
                if isinstance(filter_index, int):
                    filter_temp = str(filter_index) + ':' + filter_vals
                    filters_temp.append(filter_temp)
            all_fields['filters'][field]['filter'] = filters_temp

    # data
    data_fields = all_fields['data_fields']
    if len(all_fields['data_fields']) != 0:
        data_fields_temp = []
        for data_field in all_fields['data_fields']:
            data_field_temp = get_field_index(csv_field_names, data_field, 'data_field')
            if isinstance(data_field_temp, int):
                data_fields_temp.append(data_field_temp)
        all_fields['data_fields'] = data_fields_temp
    if len(all_fields['data_fields']) == 0:
        # use all non-timestamp fields
        all_fields['data_fields'] = range(len(csv_field_names))

    return all_fields


def check_project(project_name):
    if 'token' in if_config_vars and len(if_config_vars['token']) != 0:
        logger.debug(project_name)
        try:
            # check for existing project
            check_url = urlparse.urljoin(if_config_vars['if_url'], '/api/v1/getprojectstatus')
            output_check_project = subprocess.check_output('curl "' + check_url + '?userName=' + if_config_vars['user_name'] + '&token=' + if_config_vars['token'] + '&projectList=%5B%7B%22projectName%22%3A%22' + project_name + '%22%2C%22customerName%22%3A%22' + if_config_vars['user_name'] + '%22%2C%22projectType%22%3A%22CUSTOM%22%7D%5D&tzOffset=-14400000"', shell=True)
            # create project if no existing project
            if project_name not in output_check_project:
                logger.debug('creating project')
                create_url = urlparse.urljoin(if_config_vars['if_url'], '/api/v1/add-custom-project')
                output_create_project = subprocess.check_output('no_proxy= curl -d "userName=' + if_config_vars['user_name'] + '&token=' + if_config_vars['token'] + '&projectName=' + project_name + '&instanceType=PrivateCloud&projectCloudType=PrivateCloud&dataType=' + get_data_type_from_project_type() + '&samplingInterval=' + str(if_config_vars['sampling_interval'] / 60) +  '&samplingIntervalInSeconds=' + str(if_config_vars['sampling_interval']) + '&zone=&email=&access-key=&secrete-key=&insightAgentType=' + get_insight_agent_type_from_project_type() + '" -H "Content-Type: application/x-www-form-urlencoded" -X POST ' + create_url + '?tzOffset=-18000000', shell=True)
            # set project name to proposed name
            if_config_vars['project_name'] = project_name
            # try to add new project to system
            if 'system_name' in if_config_vars and len(if_config_vars['system_name']) != 0:
                system_url = urlparse.urljoin(if_config_vars['if_url'], '/api/v1/projects/update')
                output_update_project = subprocess.check_output('no_proxy= curl -d "userName=' + if_config_vars['user_name'] + '&token=' + if_config_vars['token'] + '&operation=updateprojsettings&projectName=' + project_name + '&systemName=' + if_config_vars['system_name'] + '" -H "Content-Type: application/x-www-form-urlencoded" -X POST ' + system_url + '?tzOffset=-18000000', shell=True)
        except subprocess.CalledProcessError as e:
            logger.error('Unable to create project for ' + project_name + '. Data will be sent to ' + if_config_vars['project_name'])


def get_field_index(field_names, field, label, is_required=False):
    err_code = ''
    try:
        temp = int(field)
        if temp > len(field_names):
            err_msg = 'field ' + str(field) + ' is not a valid array index given field names ' + str(field_names)
            field = err_code
        else:
            field = temp
    # not an integer
    except ValueError:
        try:
            field = field_names.index(field)
        # not in the field names
        except ValueError:
            err_msg = 'field ' + str(field) + ' is not a valid field in field names ' + str(field_names)
            field = err_code
    finally:
        if field == err_code:
            logger.warn('Agent not configured correctly (' + label + ')\n' + err_msg)
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


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for index in xrange(0, len(l), n):
        yield l[index:index + n]


def chunk_map(data, SIZE=50):
    """Yield successive n-sized chunks from l."""
    it = iter(data)
    for i in xrange(0, len(data), SIZE):
        yield {k: data[k] for k in islice(it, SIZE)}


def get_file_list_for_directory(root_path):
    file_list = []
    for path, subdirs, files in os.walk(root_path):
        for name in files:
            file_list.append(os.path.join(path, name))
    return file_list


def parse_raw_message(message):
    if 'METRIC' in if_config_vars['project_type']:
        metric_handoff(*raw_parse_metric(message))
    else:
        log_handoff(*raw_parse_log(message))


def get_json_field(message, config_setting, default=''):
    if len(agent_config_vars[config_setting]) == 0:
        return default
    field_val = json_format_field_value(
                    _get_json_field_helper(message, agent_config_vars[config_setting].split(JSON_LEVEL_DELIM)))
    if len(field_val) == 0:
        field_val = default
    return field_val


def _get_json_field_helper(nested_value, next_fields, allow_list=False):
    if len(next_fields) == 0:
        return ''
    elif isinstance(nested_value, list):
        return json_gather_list_values(nested_value, next_fields)
    elif not isinstance(nested_value, dict):
        return ''
    next_field = next_fields.pop(0)
    next_value = nested_value.get(next_field)
    if next_value is None:
        return ''
    elif len(bytes(next_value)) == 0:
        return ''
    elif next_fields is None:
        return next_value
    elif len(next_fields) == 0:
        return next_value
    elif isinstance(next_value, set):
        next_value_all = ''
        for item in next_value:
            next_value_all += str(item)
        return next_value_all
    elif isinstance(next_value, list):
        if allow_list: 
            return json_gather_list_values(next_value, next_fields)
        else:
            raise Exception('encountered list in json when not allowed')
            return ''
    elif isinstance(next_value, dict):
        return _get_json_field_helper(next_value, next_fields, allow_list)
    else:
        logger.debug('given field could not be found')
        return ''


def json_gather_list_values(l, fields):
    sub_field_value = []
    for sub_value in l:
        fields_copy = list(fields[i] for i in range(len(fields)))
        json_value = json_format_field_value(_get_json_field_helper(sub_value, fields_copy, True))
        if len(json_value) != 0:
            sub_field_value.append(json_value)
    return sub_field_value


def json_format_field_value(value):
    if isinstance(value, (dict, list)):
        if len(value) == 1 and isinstance(value, list):
            return value.pop(0)
        return value
    return str(value)


def parse_json_message(messages):
    if len(agent_config_vars['json_top_level']) != 0:
        if agent_config_vars['json_top_level'] == '[]' and isinstance(messages, list):
            for message in messages:
                parse_json_message_single(message)
        else:
            top_level = _get_json_field_helper(messages, agent_config_vars['json_top_level'].split(JSON_LEVEL_DELIM), True)
            if isinstance(top_level, list):
                for message in top_level:
                    parse_json_message_single(message)
            else:
                parse_json_message_single(top_level)
    else:
        parse_json_message_single(messages)


def parse_json_message_single(message):
    # filter
    if len(agent_config_vars['filters_include']) != 0:
        # for each provided filter
        is_valid = False
        for _filter in agent_config_vars['filters_include']:
            filter_field = _filter.split(':')[0]
            filter_vals = _filter.split(':')[1].split(',')
            filter_check = str(_get_json_field_helper(message, filter_field.split(JSON_LEVEL_DELIM), True))
            # check if a valid value
            for filter_val in filter_vals:
                if filter_val.upper() in filter_check.upper():
                    is_valid = True
                    break
            if is_valid:
                break
        if not is_valid:
            logger.debug('filtered message (inclusion): ' + filter_check + ' not in ' + str(filter_vals))
            return
        else:
            logger.debug('passed filter (inclusion)')
            
    if len(agent_config_vars['filters_exclude']) != 0:
        # for each provided filter
        for _filter in agent_config_vars['filters_exclude']:
            filter_field = _filter.split(':')[0]
            filter_vals = _filter.split(':')[1].split(',')
            filter_check = str(_get_json_field_helper(message, filter_field.split(JSON_LEVEL_DELIM), True))
            # check if a valid value
            for filter_val in filter_vals:
                if filter_val.upper() in filter_check.upper():
                    logger.debug('filtered message (exclusion): ' + str(filter_val) + ' in ' + str(filter_check))
                    return
        logger.debug('passed filter (exclusion)')

    # get project, instance, & device
    # check_project(get_json_field(message, 'project_field', if_config_vars['project_name']))
    instance = get_json_field(message, 'instance_field', HOSTNAME)
    device = get_json_field(message, 'device_field')

    # get timestamp
    timestamp = get_json_field(message, 'timestamp_field')
    timestamp = get_timestamp_from_date_string(timestamp)

    # get data
    log_data = dict()
    if len(agent_config_vars['data_fields']) != 0: 
        for data_field in agent_config_vars['data_fields']:
            data_value = json_format_field_value(_get_json_field_helper(message, data_field.split(JSON_LEVEL_DELIM), True))
            if len(data_value) != 0:
                if 'METRIC' in if_config_vars['project_type']:
                    metric_handoff(timestamp, data_field.replace('.', '/'), data_value, instance, device)
                else:
                    log_data[data_field.replace('.', '/')] = data_value
    else:    
        if 'METRIC' in if_config_vars['project_type']:
            # assume metric data is in top level
            for data_field in message:
                data_value = str(_get_json_field_helper(message, data_field.split(JSON_LEVEL_DELIM), True))
                if data_value is not None:
                    metric_handoff(timestamp, data_field.replace('.', '/'), data_value, instance, device)
        else:
            log_data = message

    # hand off to log
    if 'METRIC' not in if_config_vars['project_type']:
        log_handoff(timestamp, log_data, instance, device)


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
                if filter_val.upper() not in filter_check.upper():
                    is_valid = True
                    break
            if is_valid:
                break
        if not is_valid:
            logger.debug('filtered message (inclusion): ' + filter_check + ' not in ' + str(filter_vals))
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
                    logger.debug('filtered message (exclusion): ' + filter_check + ' in ' + str(filter_vals))
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
    if 'strip_tz' in agent_config_vars and agent_config_vars['strip_tz']:
        date_string = ''.join(agent_config_vars['strip_tz_fmt'].split(date_string))

    if 'timestamp_format' in agent_config_vars:
        if agent_config_vars['timestamp_format'] == 'epoch':
            timestamp_datetime = get_datetime_from_unix_epoch(date_string)
        else:
            timestamp_datetime = datetime.strptime(date_string, agent_config_vars['timestamp_format'])
    else:
        try:
            # try a guess
            timestamp_datetime = datefinder.find_date(date_string)[0]
        except:
            # maybe it's an epoch?
            timestamp_datetime = get_datetime_from_unix_epoch(date_string)
            agent_config_vars['timestamp_format'] = 'epoch'

    timestamp_localize = cli_config_vars['time_zone'].localize(timestamp_datetime)

    epoch = long((timestamp_localize - datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()) * 1000
    return epoch


def get_datetime_from_unix_epoch(date_string):
    try:
        # strip leading whitespace and zeros
        epoch = date_string.lstrip(' 0')
        # roughly check for a timestamp between ~1973 - ~2286
        if len(epoch) in range(13, 15):
            epoch = int(epoch) / 1000
        elif len(epoch) in range(9, 12):
            epoch = int(epoch)

        return datetime.fromtimestamp(epoch)
    except ValueError:
        # if the date cannot be converted into a number by built-in long()
        logger.warn('Date format not defined & data does not look like unix epoch: ' + date_string)
        sys.exit(1)


def make_safe_instance_string(instance, device=''):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', instance)
    instance = COLONS.sub('-', instance)
    # if there's a device, concatenate it to the instance with an underscore
    if len(device) != 0:
        instance = make_safe_instance_string(device) + '_' + instance
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
    formatter = logging.Formatter('%(asctime)s [pid %(process)d] %(levelname)-8s %(module)s.%(funcName)s():%(lineno)d %(message)s')
    logging_handler_out.setFormatter(formatter)
    logger_obj.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logger_obj.addHandler(logging_handler_err)
    return logger_obj


def print_summary_info():
    # info to be sent to IF
    post_data_block = '\nIF settings:'
    for i in if_config_vars.keys():
        post_data_block += '\n\t' + i + ': ' + str(if_config_vars[i])
    logger.debug(post_data_block)

    # variables from agent-specific config
    agent_data_block = '\nAgent settings:'
    for j in agent_config_vars.keys():
        agent_data_block += '\n\t' + j + ': ' + str(agent_config_vars[j])
    logger.debug(agent_data_block)

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for k in cli_config_vars.keys():
        cli_data_block += '\n\t' + k + ': ' + str(cli_config_vars[k])
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
    logger.debug('Total ' + if_config_vars['project_type'].lower() + ' entries: ' + str(track['entry_count']))


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
    log_handoff(timestamp, data, instance, device)


def deployment_handoff(timestamp, data, instance, device=''):
    log_handoff(timestamp, data, instance, device)


def alert_handoff(timestamp, data, instance, device=''):
    log_handoff(timestamp, data, instance, device)


def log_handoff(timestamp, data, instance, device=''):
    entry = prepare_log_entry(str(int(timestamp)), data, instance, device)
    track['current_row'].append(entry)
    track['line_count'] += 1
    track['entry_count'] += 1
    if get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size'] or (time.time() - track['start_time']) >= if_config_vars['sampling_interval']:
        send_data_wrapper()
    elif track['entry_count'] % 100 == 0:
        logger.debug('Current data object size: ' + str(get_json_size_bytes(track['current_row'])) + ' bytes')


def prepare_log_entry(timestamp, data, instance, device=''):
    """ creates the log entry """
    entry = dict()
    entry['data'] = data
    if 'INCIDENT' in if_config_vars['project_type'] or 'DEPLOYMENT' in if_config_vars['project_type']:
        entry['timestamp'] = timestamp
        entry['instanceName'] = make_safe_instance_string(instance, device)
    else: # LOG or ALERT
        entry['eventId'] = timestamp
        entry['tag'] = make_safe_instance_string(instance, device)
    return entry


###################################
# Functions to handle Metric data #
###################################
def metric_handoff(timestamp, field_name, data, instance, device=''):
    append_metric_data_to_entry(timestamp, field_name, data, instance, device)
    track['entry_count'] += 1
    if get_json_size_bytes(track['current_dict']) >= if_config_vars['chunk_size'] or (time.time() - track['start_time']) >= if_config_vars['sampling_interval']:
        send_data_wrapper()
    elif track['entry_count'] % 500 == 0:
        logger.debug('Current data object size: ' + str(get_json_size_bytes(track['current_dict'])) + ' bytes')


def append_metric_data_to_entry(timestamp, field_name, data, instance, device=''):
    """ creates the metric entry """
    key = make_safe_metric_key(field_name) + '[' + make_safe_instance_string(instance, device) + ']'
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
    for timestamp in track['current_dict'].keys():
        track['line_count'] += 1
        new_row = dict()
        new_row['timestamp'] = timestamp
        for key in track['current_dict'][timestamp]:
            value = track['current_dict'][timestamp][key]
            if '|' in value:
                value = statistics.median(map(lambda v: float(v), value.split('|')))
            new_row[key] = str(value)
        track['current_row'].append(new_row)


################################
# Functions to send data to IF #
################################
def send_data_wrapper():
    """ wrapper to send data """
    if 'METRIC' in if_config_vars['project_type']:
        transpose_metrics()
    logger.debug('--- Chunk creation time: %s seconds ---' % round(time.time() - track['start_time'], 2))
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

    for i in xrange(ATTEMPTS):
        try:
            response = req(url, **request_passthrough)
            if response.status_code == httplib.OK:
                logger.info(success_message)
                return response
            else:
                logger.warn(failure_message)
                logger.debug('Response Code: ' + str(response.status_code) + '\n' +
                             'TEXT: ' + str(response.text))
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

    logger.error('Failed! Gave up after %d attempts.', i)
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
        if 'REPLAY' in if_config_vars['project_type']:
            return 'containerReplay'
        else:
            return 'containerStreaming'
    elif 'REPLAY' in if_config_vars['project_type']:
        if 'METRIC' in if_config_vars['project_type']:
            return 'MetricFile'
        else:
            return 'LogFile'
    else:
        return 'Custom'


def get_agent_type_from_project_type():
    """ use project type to determine agent type """
    if 'METRIC' in if_config_vars['project_type']:
        if 'REPLAY' in if_config_vars['project_type']:
            return 'MetricFileReplay'
        else:
            return 'CUSTOM'
    elif 'REPLAY' in if_config_vars['project_type']: # LOG, ALERT
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
    else: # MERTIC, LOG, ALERT
        return 'metricData'


def get_api_from_project_type():
    """ use project type to determine which API to post to """
    # incident uses a different API endpoint
    if 'INCIDENT' in if_config_vars['project_type']:
        return 'incidentdatareceive'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'deploymentEventReceive'
    else: # MERTIC, LOG, ALERT
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
    SPACES = re.compile(r"\s+")
    SLASHES = re.compile(r"\/+")
    UNDERSCORE = re.compile(r"\_+")
    COLONS = re.compile(r"\:+")
    LEFT_BRACE = re.compile(r"\[")
    RIGHT_BRACE = re.compile(r"\]")
    PERIOD = re.compile(r"\.")
    NON_ALNUM = re.compile(r"[^a-zA-Z0-9]")
    PCT_z_FMT = re.compile(r"[\+\-][0-9]{4}")
    PCT_Z_FMT = re.compile(r"[A-Z]{3,4}")
    HOSTNAME = socket.gethostname().partition('.')[0]
    JSON_LEVEL_DELIM = '.'
    CSV_DELIM = ','
    ATTEMPTS = 3
    track = dict()

    # get config
    cli_config_vars = get_cli_config_vars()
    logger = set_logger_config(cli_config_vars['log_level'])
    if_config_vars = get_if_config_vars()
    agent_config_vars = get_agent_config_vars()
    print_summary_info()

    # start data processing
    for i in range(0, cli_config_vars['threads']):
        Process(target=initialize_data_gathering,
                args=(i,)
                ).start()

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
from optparse import OptionParser
from itertools import islice
from datetime import datetime
import urlparse
import httplib
import requests
import subprocess

'''
This script gathers data to send to Insightfinder
'''


def start_data_processing():
    track['mode'] = 'METRIC'

    # set up shared api call info
    base_url = 'https://api.newrelic.com/'
    headers = {'X-Api-Key': agent_config_vars['api_key']}
    now = int(time.time())
    to_timestamp = datetime.utcfromtimestamp(now).isoformat()
    from_timestamp = datetime.utcfromtimestamp(now - agent_config_vars['run_interval']).isoformat()
    data = {
        'to': to_timestamp,
        'from': from_timestamp,
        'period': str(if_config_vars['samplingInterval'])
    }

    get_applications(base_url, headers, data)


def get_applications(base_url, headers, data):
    url = urlparse.urljoin(base_url, '/v2/applications.json')
    response = send_request(url, headers=headers, proxies=agent_config_vars['proxies'])
    try:
        logger.debug(response.text)
        response_json = json.loads(response.text)
        filter_applications(base_url, headers, data, response_json['applications'])
    # response = -1
    except TypeError:
        logger.warn('Failure when contacting NewRelic API when fetching applications')
    except KeyError:
        logger.warn('NewRelic API returned malformed data when fetching applications. ' +
                    'Please contact support if this problem persists.')


def filter_applications(base_url, headers, data, app_list):
    for app in app_list:
        app_name = app['name']
        app_id = str(app['id'])
        logger.debug(app_name + ': ' + app_id)
        # check app filter
        if should_filter_per_config('app_name_filter', app_name):
            logger.debug('skipping')
            continue

        if should_filter_per_config('app_id_filter', app_id):
            logger.debug('skipping')
            continue

        if agent_config_vars['auto_create_project']:
            # make sure we send the last chunk for the previous project
            send_data_wrapper()
            check_project(make_safe_project_string(app_name))
            logger.debug(if_config_vars['projectName'])

        if use_host_api():
            get_hosts_for_app(base_url, headers, data, get_metrics_list('host_metrics'), app_id)
        if use_app_api():
            get_metrics_for_app_host(base_url, headers, data, get_metrics_list('app_metrics'), app_id, make_safe_instance_string(app_name)) 


def get_hosts_for_app(base_url, headers, data, metrics_list, app_id):
    api = '/v2/applications/' + app_id + '/hosts.json'
    url = urlparse.urljoin(base_url, api)
    response = send_request(url, headers=headers, proxies=agent_config_vars['proxies'])
    try:
        response_json = json.loads(response.text)
        filter_hosts(base_url, headers, data, metrics_list, app_id, response_json['application_hosts'])
    # response = -1
    except TypeError as te:
        logger.warn('Failure when contacting NewRelic API when fetching hosts for app ' + app_id + '].')
        logger.warn(str(te))
        logger.warn(response.text)
    # malformed response_json
    # handles errors from filter_hosts
    except KeyError as ke:
        logger.warn('NewRelic API returned malformed data when fetching hosts for app ' + app_id + '].'
                    'Please contact support if this problem persists.')
        logger.warn(str(ke))
        logger.warn(response.text)


def filter_hosts(base_url, headers, data, metrics_list, app_id, hosts_list):
    for host in hosts_list:
        hostname = host['host']
        if should_filter_per_config('host_filter', hostname):
            continue
        # clear out hostname if not containerizing
        if not agent_config_vars['containerize']:
            instance = hostname
            hostname = ''
        else:
            instance = host['application_name']
        get_metrics_for_app_host(base_url, headers, data, metrics_list, app_id, instance, str(host['id']), hostname)


def get_metrics_for_app_host(base_url, headers, data, metrics_list, app_id, instance='', host_id='', hostname=''):
    api = get_metrics_api(app_id, host_id)
    url = urlparse.urljoin(base_url, api)
    for metric in metrics_list:
        data_copy = data
        data_copy['names[]'] = metric
        data_copy['values[]'] = metrics_list[metric]
        response = send_request(url, headers=headers, proxies=agent_config_vars['proxies'], data=data_copy)
        try:
            metric_data = json.loads(response.text)
            parse_metric_data(metric_data['metric_data']['metrics'], instance, hostname)
        # response = -1
        except TypeError as te:
            logger.warn('Failure when contacting NewRelic API while fetching metrics ' +
                        'for app ' + app_id + ' & host ' + host_id + '.')
            logger.warn(str(te))
            logger.warn(response.text)
        # malformed response_json
        # handles errors from parse_metric_data as well
        except KeyError as ke:
            logger.warn('NewRelic API returned malformed data when fetching metrics ' +
                        'for app ' + app_id + ' & host ' + host_id + '.' +
                        'Please contact support if this problem persists.')
            logger.warn(str(ke))
            logger.warn(response.text)


def parse_metric_data(metrics, instance, hostname=''):
    for metric in metrics:
        metric_key_base = metric['name']
        for timeslice in metric['timeslices']:
            # though timestamp was defined when we called the API, use the response as the source of truth
            # format is '2019-05-31T13:51:00+00:00'
            # remove tz info since it's utc
            timestamp = get_timestamp_from_date_string(timeslice['to'].split('+')[0], '%Y-%m-%dT%H:%M:%S')
            for value in timeslice['values']:
                metric_key = metric_key_base + '/' + value
                data = timeslice['values'][value]
                metric_handoff(timestamp, metric_key, data, instance, hostname)


def check_project(project_name):
    if 'token' in if_config_vars and len(if_config_vars['token']) != 0:
        try:
            # check for existing project
            check_url = urlparse.urljoin(if_config_vars['ifURL'], '/api/v1/getprojectstatus'
            output_check_project = subprocess.check_output('curl "' + check_url + '?userName=' + if_config_vars['userName'] + '&token=' + if_config_vars['token'] + '&projectList=%5B%7B%22projectName%22%3A%22' + project_name + '%22%2C%22customerName%22%3A%22' + if_config_vars['userName'] + '%22%2C%22projectType%22%3A%22CUSTOM%22%7D%5D&tzOffset=-14400000"', shell=True)
            # create project if no existing project
            if project_name not in output_check_project:
                logger.debug('creating project')
                create_url = urlparse.urljoin(if_config_vars['ifURL'], '/api/v1/add-custom-project')
                output_create_project = subprocess.check_output('no_proxy= curl -d "userName=' + if_config_vars['userName'] + '&token=' + if_config_vars['token'] + '&projectName=' + project_name + '&instanceType=PrivateCloud&projectCloudType=PrivateCloud&dataType=Metric&samplingInterval=' + str(if_config_vars['samplingInterval'] / 60) +  '&samplingIntervalInSeconds=' + str(if_config_vars['samplingInterval']) + '&zone=&email=&access-key=&secrete-key=&insightAgentType=' + get_agent_type_from_mode_wrap() + '" -H "Content-Type: application/x-www-form-urlencoded" -X POST ' + create_url + '?tzOffset=-18000000', shell=True)
            # set project name to proposed name
            if_config_vars['projectName'] = project_name
            # try to add new project to system
            if 'systemName' in if_config_vars and len(if_config_vars['systemName']) != 0:
                system_url = urlparse.urljoin(if_config_vars['ifURL'], '/api/v1/projects/update')
                output_update_project = subprocess.check_output('no_proxy= curl -d "userName=' + if_config_vars['userName'] + '&token=' + if_config_vars['token'] + '&operation=updateprojsettings&projectName=' + project_name + '&systemName=' + if_config_vars['systemName'] + '" -H "Content-Type: application/x-www-form-urlencoded" -X POST ' + system_url + '?tzOffset=-18000000', shell=True)
        except subprocess.CalledProcessError as e:
            logger.error('Unable to create project for ' + project_name + '. Data will be sent to ' + if_config_vars['projectName'])


def get_metrics_list(setting):
    """ Parse metrics given in config.ini, if any """
    metrics_list = dict()
    if len(agent_config_vars[setting]) != 0:
        # build an object; see default_metrics_list() for the structure
        for metric_object in agent_config_vars['metrics']:
            metric_object = metric_object.split(':')
            metric_name = metric_object[0]
            values = metric_object[1].split('|')
            metrics_list[metric_name] = values
    # if malformed or none specified, use default
    if len(metrics_list) == 0:
        metrics_list = default_metrics_list(setting)
    return metrics_list


def get_metrics_api(app_id, host_id=''):
    if use_host_api() and len(host_id) != 0:
        return '/v2/applications/' + app_id + '/hosts/' + host_id + '/metrics/data.json'
    else:
        return '/v2/applications/' + app_id + '/metrics/data.json'


def use_app_api():
    return agent_config_vars['app_or_host'] == 'APP' or agent_config_vars['app_or_host'] == 'BOTH'


def use_host_api():
    return agent_config_vars['app_or_host'] == 'HOST' or agent_config_vars['app_or_host'] == 'BOTH'


def default_metrics_list(setting):
    metrics = dict()
    metrics['app_metrics'] = { }
    metrics['host_metrics'] = {
        'CPU/User Time': [
            'percent'
        ],
        'Memory/Heap/Used': [
            'used_mb_by_host'
        ],
        'Memory/Physical': [
            'used_mb_by_host'
        ],
        'Instance/connectsReqPerMin': [
            'requests_per_minute'
        ],
        'Controller/reports/show': [
            'average_response_time',
            'calls_per_minute',
            'call_count',
            'min_response_time',
            'max_response_time',
            'average_exclusive_time',
            'average_value',
            'total_call_time_per_minute',
            'requests_per_minute',
            'standard_deviation',
            'throughput',
            'average_call_time',
            'min_call_time',
            'max_call_time',
            'total_call_time'
        ]
    }
    if setting not in metrics.keys():
        setting = host_metrics
    return metrics[setting]


def get_agent_config_vars():
    """ Read and parse config.ini """
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini'))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini')))
        try:
            # fields to grab
            api_key = config_parser.get('newrelic', 'api_key')
            app_or_host = config_parser.get('newrelic', 'app_or_host').upper()
            auto_create_project = config_parser.get('newrelic', 'auto_create_project').upper()
            containerize = config_parser.get('newrelic', 'containerize').upper()
            app_name_filter = config_parser.get('newrelic', 'app_name_filter')
            app_id_filter = config_parser.get('newrelic', 'app_id_filter')
            host_filter = config_parser.get('newrelic', 'host_filter')
            app_metrics = config_parser.get('newrelic', 'app_metrics')
            host_metrics = config_parser.get('newrelic', 'host_metrics')
            run_interval = config_parser.get('newrelic', 'run_interval')
            agent_http_proxy = config_parser.get('newrelic', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('newrelic', 'agent_https_proxy')
        except ConfigParser.NoOptionError:
            logger.error(
                'Agent not correctly configured. Check config file.')
            sys.exit(1)

        # required fields
        if len(api_key) == 0:
            logger.warning(
                'Agent not correctly configured (api_key). Check config file.')
            exit()
        if len(run_interval) == 0:
            logger.warning(
                'Agent not correctly configured (run_interval). Check config file.')
            exit()

        # default
        if len(app_or_host) == 0 or app_or_host not in { 'APP', 'HOST' , 'BOTH'}:
            logger.warning(
                'Agent not correctly configured (app_or_host). Check config file.')
            exit()

        # set filters
        if len(app_name_filter) != 0:
            app_name_filter = app_name_filter.strip().split(',')
        if len(app_id_filter) != 0:
            app_id_filter = app_id_filter.strip().split(',')
        if len(host_filter) != 0:
            host_filter = host_filter.strip().split(',')
        if len(app_metrics) != 0:
            app_metrics = app_metrics.strip().split(',')
        if len(host_metrics) != 0:
            host_metrics = host_metrics.strip().split(',')

        # set up proxies for agent
        agent_proxies = dict()
        if len(agent_http_proxy) > 0:
            agent_proxies['http'] = agent_http_proxy
        if len(agent_https_proxy) > 0:
            agent_proxies['https'] = agent_https_proxy

        # add parsed variables to a global
        config_vars = {
            'api_key': api_key,
            'app_or_host': app_or_host,
            'auto_create_project': True if auto_create_project == 'YES' else False,
            'containerize': True if containerize == 'YES' else False,
            'app_name_filter': app_name_filter,
            'app_id_filter': app_id_filter,
            'host_filter': host_filter,
            'app_metrics': app_metrics,
            'host_metrics': host_metrics,
            'run_interval': int(run_interval) * 60,  # as seconds
            'proxies': agent_proxies
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
            project_name = config_parser.get('insightfinder', 'project_name')
            system_name = config_parser.get('insightfinder', 'system_name')
            token = config_parser.get('insightfinder', 'token')
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            chunk_size_kb = config_parser.get('insightfinder', 'chunk_size_kb')
            if_url = config_parser.get('insightfinder', 'url')
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
        except ConfigParser.NoOptionError:
            logger.error(
                'Agent not correctly configured. Check config file.')
            sys.exit(1)

        # check required variables
        if len(user_name) == 0:
            logger.warning(
                'Agent not correctly configured (user_name). Check config file.')
            sys.exit(1)
        if len(license_key) == 0:
            logger.warning(
                'Agent not correctly configured (license_key). Check config file.')
            sys.exit(1)
        if len(project_name) == 0:
            logger.warning(
                'Agent not correctly configured (project_name). Check config file.')
            sys.exit(1)
        if len(sampling_interval) == 0:
            logger.warning(
                'Agent not correctly configured (sampling_interval). Check config file.')
            sys.exit(1)

        if sampling_interval.endswith('s'):
            sampling_interval = sampling_interval[:-1]
        else:
            sampling_interval = int(sampling_interval) * 60

        # defaults
        if len(chunk_size_kb) == 0:
            chunk_size_kb = 2048
        if len(if_url) == 0:
            if_url = 'https://app.insightfinder.com'

        # set IF proxies
        if_proxies = dict()
        if len(if_http_proxy) > 0:
            if_proxies['http'] = if_http_proxy
        if len(if_https_proxy) > 0:
            if_proxies['https'] = if_https_proxy

        config_vars = {
            'userName': user_name,
            'licenseKey': license_key,
            'projectName': project_name,
            'systemName': system_name,
            'token': token,
            'samplingInterval': int(sampling_interval),     # as seconds
            'chunkSize': int(chunk_size_kb) * 1024,         # as bytes
            'ifURL': if_url,
            'ifProxies': if_proxies
        }

        return config_vars
    else:
        logger.error(
            'Agent not correctly configured. Check config file.')
        sys.exit(1)


def get_cli_config_vars():
    """ get CLI options """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    parser.add_option('-q', '--quiet',
                      action='store_true', dest='quiet', help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose',
                      action='store_true', dest='verbose', help='Enable verbose logging')
    parser.add_option('-t', '--testing',
                      action='store_true', dest='testing', help='Set to testing mode (do not send data).'
                                                                ' Automatically turns on verbose logging')
    (options, args) = parser.parse_args()

    config_vars = dict()
    config_vars['testing'] = False
    if options.testing:
        config_vars['testing'] = True
    config_vars['logLevel'] = logging.INFO
    if options.verbose or options.testing:
        config_vars['logLevel'] = logging.DEBUG
    elif options.quiet:
        config_vars['logLevel'] = logging.WARNING

    return config_vars


def should_filter_per_config(setting, value):
    return len(agent_config_vars[setting]) != 0 and value not in agent_config_vars[setting]


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for index in xrange(0, len(l), n):
        yield l[index:index + n]


def chunk_map(data, SIZE=50):
    """Yield successive n-sized chunks from l."""
    it = iter(data)
    for i in xrange(0, len(data), SIZE):
        yield {k: data[k] for k in islice(it, SIZE)}


def get_timestamp_from_date_string(date_string, format):
    timestamp_datetime = datetime.strptime(date_string, format)
    epoch = long((timestamp_datetime - datetime(1970, 1, 1)).total_seconds())*1000
    return epoch


def make_safe_project_string(project_name):
    project_name = PERIOD.sub('_', project_name)
    project_name = SLASHES.sub('-', project_name)
    project_name = SPACES.sub('-', project_name)
    return project_name


def make_safe_instance_string(instance, device=''):
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
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(process)d - %(threadName)s - %(levelname)s - %(message)s')
    logging_handler_out.setFormatter(formatter)
    logger_obj.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logger_obj.addHandler(logging_handler_err)
    return logger_obj


def print_summary_info():
    # info to be sent to IF
    post_data_block = '\nData sent to IF:'
    for i in if_config_vars.keys():
        post_data_block += '\n\t' + i + ': ' + str(if_config_vars[i])
    logger.debug(post_data_block)

    # variables from agent-specific config
    agent_data_block = '\nAgent settings:'
    for j in agent_config_vars.keys():
        agent_data_block += '\n\t' + j + ': ' + str(agent_config_vars[j])
    logger.debug(agent_data_block)


def initialize_data_gathering():
    reset_track()
    track['chunk_count'] = 0
    track['entry_count'] = 0

    start_data_processing()

    # last chunk
    if len(track['current_row']) > 0 or len(track['current_dict']) > 0:
        logger.debug('Sending last chunk')
        send_data_wrapper()

    logger.debug('Total chunks created: ' + str(track['chunk_count']))
    logger.debug('Total ' + track['mode'].lower() + ' entries: ' + str(track['entry_count']))


def reset_track():
    """ reset the track global for the next chunk """
    track['start_time'] = time.time()
    track['line_count'] = 0
    track['current_row'] = []
    track['current_dict'] = dict()


#########################################
# Functions to handle Log/Incident data #
#########################################
def log_handoff(timestamp, instance, data):
    entry = prepare_log_entry(timestamp, instance, data)
    track['current_row'].append(entry)
    track['line_count'] += 1
    track['entry_count'] += 1
    if len(bytearray(json.dumps(track['current_row']))) >= if_config_vars['chunkSize']:
        send_data_wrapper()


def prepare_log_entry(timestamp, instance, data):
    """ creates the log entry """
    entry = dict()
    entry['data'] = data
    if 'INCIDENT' in track['mode'].upper():
        entry['timestamp'] = timestamp
        entry['instanceName'] = instance
    else:
        entry['eventId'] = timestamp
        entry['tag'] = instance
    return entry


###################################
# Functions to handle Metric data #
###################################
def metric_handoff(timestamp, field_name, data, instance, device=''):
    append_metric_data_to_entry(timestamp, field_name, data, instance, device)
    track['line_count'] += 1
    track['entry_count'] += 1
    if len(bytearray(json.dumps(track['current_dict']))) >= if_config_vars['chunkSize']:
        send_data_wrapper()


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
        new_row = dict()
        new_row['timestamp'] = timestamp
        for key in track['current_dict'][timestamp]:
            value = track['current_dict'][timestamp][key]
            if '|' in value:
                value = median(map(lambda v: int(v), value.split('|')))
            new_row[key] = str(value)
        track['current_row'].append(new_row)


################################
# Functions to send data to IF #
################################
def send_data_wrapper():
    """ wrapper to send data """
    if 'METRIC' in track['mode'].upper():
        transpose_metrics()
    logger.debug('--- Chunk creation time: %s seconds ---' % (time.time() - track['start_time']))
    send_data_to_if(track['current_row'])
    track['chunk_count'] += 1
    reset_track()


def send_data_to_if(chunk_metric_data):
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = initialize_api_post_data()
    to_send_data_dict['metricData'] = json.dumps(chunk_metric_data)

    to_send_data_json = json.dumps(to_send_data_dict)
    logger.debug('TotalData: ' + str(len(bytearray(to_send_data_json))))
    logger.debug('TotalLines: ' + str(track['line_count']))

    if cli_config_vars['testing']:
        logger.debug(to_send_data_json)
        return

    # send the data
    post_url = urlparse.urljoin(if_config_vars['ifURL'], get_api_from_mode())
    send_request(post_url, 'POST', 'Could not send request to IF',
                 str(len(bytearray(to_send_data_json))) + ' bytes of data are reported.',
                 data=json.loads(to_send_data_json), proxies=if_config_vars['ifProxies'])
    logger.debug('--- Send data time: %s seconds ---' % (time.time() - send_data_time))


def send_request(url, mode='GET', failure_message='Failure!', success_message='Success!', **request_passthrough):
    """ sends a request to the given url """
    # determine if post or get (default)
    req = requests.get
    if mode.upper() == 'POST':
        req = requests.post

    for _ in xrange(ATTEMPTS):
        try:
            response = req(url, **request_passthrough)
            if response.status_code == httplib.OK:
                logger.info(success_message)
                return response
            else:
                logger.warn(failure_message)
                logger.debug('Response Code: ' + str(response.status_code) + '\nTEXT: ' + str(response.text))
        # handle various exceptions
        except requests.exceptions.Timeout:
            logger.exception(
                'Timed out. Reattempting...')
            continue
        except requests.exceptions.TooManyRedirects:
            logger.exception(
                'Too many redirects.')
            break
        except requests.exceptions.RequestException as e:
            logger.exception(
                'Exception ' + str(e))
            break

    logger.error(
        'Failed! Gave up after %d attempts.', ATTEMPTS)
    return -1


def get_agent_type_from_mode_wrap():
    if agent_config_vars['containerize']:
        return 'ContainerStreaming'
    return get_agent_type_from_mode()


def get_agent_type_from_mode():
    """ use mode to determine agent type """
    if 'METRIC' in track['mode'].upper():
        if 'REPLAY' in track['mode'].upper():
            return 'MetricFileReplay'
        else:
            return 'CUSTOM'
    elif 'REPLAY' in track['mode'].upper():
        return 'LogFileReplay'
    else:
        return 'LogStreaming'


def get_api_from_mode():
    """ use mode to determine which API to post to """
    # incident uses a different API endpoint
    if 'INCIDENT' in track['mode'].upper():
        return 'incidentdatareceive'
    else:
        return 'customprojectrawdata'


def initialize_api_post_data():
    """ set up the unchanging portion of this """
    to_send_data_dict = dict()
    to_send_data_dict['userName'] = if_config_vars['userName']
    to_send_data_dict['licenseKey'] = if_config_vars['licenseKey']
    to_send_data_dict['projectName'] = if_config_vars['projectName']
    to_send_data_dict['instanceName'] = socket.gethostname().partition('.')[0]
    to_send_data_dict['agentType'] = get_agent_type_from_mode()
    if 'METRIC' in track['mode'].upper() and 'samplingInterval' in if_config_vars:
        to_send_data_dict['samplingInterval'] = str(if_config_vars['samplingInterval'])
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
    ATTEMPTS = 3
    track = dict()

    # get config
    cli_config_vars = get_cli_config_vars()
    logger = set_logger_config(cli_config_vars['logLevel'])
    if_config_vars = get_if_config_vars()
    agent_config_vars = get_agent_config_vars()
    print_summary_info()

    # start data processing
    initialize_data_gathering()

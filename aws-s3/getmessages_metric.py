#!/usr/bin/env python
import configparser
import glob
import http
import io
import json
import logging
import multiprocessing
import os
import re
import sys
import threading
import time
import urllib
from logging.handlers import QueueHandler
from optparse import OptionParser
from pathlib import Path
from sys import getsizeof

import arrow
import boto3
import pytz
import regex
import requests

threadLock = threading.Lock()
messages_dict = {}
metadata_dict = {}
instance_dict = {}

MAX_RETRY_NUM = 10
RETRY_WAIT_TIME_IN_SEC = 30
UNDERSCORE = regex.compile(r"\_+")
COLONS = regex.compile(r"\:+")
# chunk size is 2Mb
CHUNK_SIZE = 2 * 1024 * 1024
MAX_PACKET_SIZE = 5000000
ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
RUNNING_INDEX = 'running_index-{}.txt'
RUNNING_INDEX_METADATA = 'running_index_metadata-{}.txt'
MAX_THREAD_COUNT = multiprocessing.cpu_count() + 1
# MAX_THREAD_COUNT = 1
ATTEMPTS = 3
NOT_EXIST_COMPONENT_NAME = '__not_exist_component_name__'


def format_timestamp(ts):
    return arrow.get(int(ts) / 1000).format('YYYY-MM-DD HH:mm:ssZZ') if ts else ""


def file_time_diff(logger, file_name, ts):
    ret = ''
    match = re.search(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}', file_name)
    if match:
        file_time = arrow.get(match.group(), 'YYYY-MM-DD_HH-mm-ss')
        if file_time and ts:
            logger.info(file_time)
            data_time = arrow.get(int(ts) / 1000)
            ret = str(file_time - data_time)

    return ret


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    return getsizeof(json.dumps(json_data))


def config_error(logger, setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(info))
    return False


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
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data).' +
                           ' Automatically turns on verbose logging')
    parser.add_option('--timeout', action='store', dest='timeout',
                      help='Minutes of timeout for all processes')
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

    config_vars['timeout'] = int(options.timeout) * 60 if options.timeout else 0

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
            project_name_prefix = config_parser.get('insightfinder', 'project_name_prefix')
            project_type = config_parser.get('insightfinder', 'project_type').upper()
            metadata_max_instances = config_parser.get('insightfinder', 'metadata_max_instances', fallback=None)
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            run_interval = config_parser.get('insightfinder', 'run_interval')
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
        if len(project_name) == 0 and len(project_name_prefix) == 0:
            logger.error('Agent not correctly configured. Check config file with project_name or project_name_prefix.')
            return False
        if len(project_type) == 0:
            return config_error(logger, 'project_type')
        if len(project_name_prefix) > 0 and not project_name_prefix.endswith('-'):
            project_name_prefix = project_name_prefix + '-'

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

        if metadata_max_instances and len(metadata_max_instances) > 0:
            metadata_max_instances = int(metadata_max_instances)

        # defaults
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
            'project_name_prefix': project_name_prefix,
            'project_type': project_type,
            'metadata_max_instances': metadata_max_instances,
            'sampling_interval': int(sampling_interval),  # as seconds
            'run_interval': int(run_interval),  # as seconds
            'if_url': if_url,
            'if_proxies': if_proxies,
            'is_replay': is_replay
        }

        return config_vars


def get_agent_config_vars(logger, config_ini):
    """ Read and parse config.ini """
    """ get config.ini vars """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False

    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)

        try:
            # aws s3 options
            aws_access_key_id = config_parser.get('agent', 'aws_access_key_id')
            aws_secret_access_key = config_parser.get('agent', 'aws_secret_access_key')
            aws_region = config_parser.get('agent', 'aws_region') or None
            aws_s3_bucket_name = config_parser.get('agent', 'aws_s3_bucket_name')
            aws_s3_object_prefix = config_parser.get('agent', 'aws_s3_object_prefix') or ''
            aws_s3_metadata_bucket_name = config_parser.get('agent', 'aws_s3_metadata_bucket_name')
            aws_s3_metadata_object_prefix = config_parser.get('agent', 'aws_s3_metadata_object_prefix') or ''

            if not aws_access_key_id:
                return config_error(logger, 'aws_access_key_id')
            if not aws_secret_access_key:
                return config_error(logger, 'aws_secret_access_key')
            if not aws_s3_bucket_name:
                return config_error(logger, 'aws_s3_bucket_name')
            if not aws_s3_object_prefix:
                return config_error(logger, 'aws_s3_object_prefix')
            if not aws_s3_metadata_bucket_name:
                return config_error(logger, 'aws_s3_metadata_bucket_name')
            if not aws_s3_metadata_object_prefix:
                return config_error(logger, 'aws_s3_metadata_object_prefix')

            # message parsing
            timezone = config_parser.get('agent', 'timezone') or 'UTC'
            timestamp_field = config_parser.get('agent', 'timestamp_field', raw=True) or 'timestamp'
            target_timestamp_timezone = config_parser.get('agent', 'target_timestamp_timezone', raw=True) or 'UTC'
            instance_field = config_parser.get('agent', 'instance_field')
            metric_fields = config_parser.get('agent', 'metric_fields')
            metric_whitelist = config_parser.get('agent', 'metric_whitelist')
            metadata_instance_field = config_parser.get('agent', 'metadata_instance_field')
            metadata_component_field = config_parser.get('agent', 'metadata_component_field')

            # proxies
            agent_http_proxy = config_parser.get('agent', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('agent', 'agent_https_proxy')

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        if timezone:
            if timezone not in pytz.all_timezones:
                return config_error(logger, 'timezone')
            else:
                timezone = pytz.timezone(timezone)

        if len(target_timestamp_timezone) != 0:
            target_timestamp_timezone = int(arrow.now(target_timestamp_timezone).utcoffset().total_seconds())
        else:
            return config_error(logger, 'target_timestamp_timezone')

        if len(timestamp_field) == 0:
            return config_error(logger, 'timestamp_field')

        metric_whitelist_regex = None
        if len(metric_whitelist) != 0:
            try:
                metric_whitelist_regex = regex.compile(metric_whitelist)
            except Exception as e:
                logger.error(e)
                return config_error(logger, 'metrics_whitelist')

        if len(metric_fields) == 0:
            return config_error(logger, 'metric_fields')

        # proxies
        agent_proxies = dict()
        if len(agent_http_proxy) > 0:
            agent_proxies['http'] = agent_http_proxy
        if len(agent_https_proxy) > 0:
            agent_proxies['https'] = agent_https_proxy

        metric_fields = [x.strip() for x in metric_fields.split(',') if x.strip()]

        # add parsed variables to a global
        config_vars = {
            'aws_access_key_id': aws_access_key_id,
            'aws_secret_access_key': aws_secret_access_key,
            'aws_region': aws_region,
            'aws_s3_bucket_name': aws_s3_bucket_name,
            'aws_s3_object_prefix': aws_s3_object_prefix,
            'aws_s3_metadata_bucket_name': aws_s3_metadata_bucket_name,
            'aws_s3_metadata_object_prefix': aws_s3_metadata_object_prefix,
            'timezone': timezone,
            'timestamp_field': timestamp_field,
            'instance_field': instance_field,
            'metric_fields': metric_fields,
            'metric_whitelist_regex': metric_whitelist_regex,
            'metadata_instance_field': metadata_instance_field,
            'metadata_component_field': metadata_component_field,
            'target_timestamp_timezone': target_timestamp_timezone,
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


def check_project_exist(logger, if_config_vars, project_name, system_name):
    is_project_exist = False
    if not system_name:
        system_name = if_config_vars['system_name']

    try:
        logger.info('Starting check project: ' + project_name)
        params = {
            'operation': 'check',
            'userName': if_config_vars['user_name'],
            'licenseKey': if_config_vars['license_key'],
            'projectName': project_name,
        }
        url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
        response = send_request(logger, url, 'POST', data=params, verify=False, proxies=if_config_vars['if_proxies'])
        if response == -1:
            logger.error('Check project error: ' + project_name)
        else:
            result = response.json()
            if result['success'] is False or result['isProjectExist'] is False:
                logger.error('Check project error: ' + project_name)
            else:
                is_project_exist = True
                logger.info('Check project success: ' + project_name)

    except Exception as e:
        logger.error(e)
        logger.error('Check project error: ' + project_name)

    create_project_sucess = False
    if not is_project_exist:
        try:
            logger.info('Starting add project: {}/{}'.format(system_name, project_name))
            params = {
                'operation': 'create',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': project_name,
                'systemName': system_name or project_name,
                'instanceType': 'AmazonS3',
                'projectCloudType': 'AmazonS3',
                'dataType': get_data_type_from_project_type(if_config_vars),
                'insightAgentType': get_insight_agent_type_from_project_type(if_config_vars),
                'samplingInterval': int(if_config_vars['sampling_interval'] / 60),
                'samplingIntervalInSeconds': if_config_vars['sampling_interval'],
            }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'])
            if response == -1:
                logger.error('Add project error: ' + project_name)
            else:
                result = response.json()
                if result['success'] is False:
                    logger.error('Add project error: {}/{}'.format(system_name, project_name))
                else:
                    create_project_sucess = True
                    logger.info('Add project success: {}/{}'.format(system_name, project_name))

        except Exception as e:
            logger.error(e)
            logger.error('Add project error: {}/{}'.format(system_name, project_name))

    if create_project_sucess:
        # if create project is success, sleep 10s and check again
        time.sleep(10)
        try:
            logger.info('Starting check project: ' + project_name)
            params = {
                'operation': 'check',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': project_name,
            }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'])
            if response == -1:
                logger.error('Check project error: ' + project_name)
            else:
                result = response.json()
                if result['success'] is False or result['isProjectExist'] is False:
                    logger.error('Check project error: ' + project_name)
                else:
                    is_project_exist = True
                    logger.info('Check project success: ' + project_name)

        except Exception as e:
            logger.error(e)
            logger.error('Check project error: ' + project_name)

    return is_project_exist


def yield_message(message):
    for metric in message:
        yield metric


def process_get_data(logger, cli_config_vars, bucket, object_key):
    logger.info('start to process data from file: {}'.format(object_key))
    global messages_dict

    buf = io.BytesIO()
    logger.info('downloading file: {}'.format(object_key))

    bucket.download_fileobj(object_key, buf)
    content = buf.getvalue()
    logger.info('download {} bytes from file: {}'.format(len(content), object_key))

    lines = content.splitlines()
    message = [json.loads(metric_data) for metric_data in lines]
    threadLock.acquire()
    messages_dict[object_key] = message
    threadLock.release()

    logger.info('finish proces data from file: {}'.format(object_key))


class MyThread(threading.Thread):
    def __init__(self, logger, cli_config_vars, bucket, object_key):
        threading.Thread.__init__(self)
        self.cli_config_vars = cli_config_vars
        self.bucket = bucket
        self.object_key = object_key
        self.logger = logger

    def run(self):
        process_get_data(self.logger, self.cli_config_vars, self.bucket, self.object_key)


def process_parse_data(logger, cli_config_vars, agent_config_vars):
    logger.info('start to parse data...')

    timestamp_field = agent_config_vars['timestamp_field']
    instance = agent_config_vars['instance_field']
    metric_fields = agent_config_vars['metric_fields']

    global messages_dict
    global instance_dict

    parse_data = {}
    for file_name in sorted(messages_dict.keys()):

        last_ts = None
        messages = messages_dict[file_name]
        # ignore messages without instance field
        messages = [metric for metric in messages if metric[instance]]

        for metric in yield_message(messages):
            if metric_fields and len(metric_fields) > 0:
                for field in metric_fields:
                    data_field = field
                    data_value = metric.get(field)
                    if field.find('::') != -1:
                        metric_name, metric_value = field.split('::')
                        data_field = metric.get(metric_name)
                        data_value = metric.get(metric_value)
                    if not data_field:
                        continue

                    # filter by metric whitelist
                    if agent_config_vars['metric_whitelist_regex'] and not agent_config_vars[
                        'metric_whitelist_regex'].match(data_field):
                        logger.debug('metric_whitelist has no matching data')
                        continue

                    inst_name = metric[instance]
                    component_name = instance_dict.get(inst_name)
                    if not component_name:
                        component_name = NOT_EXIST_COMPONENT_NAME

                    ts = metric[timestamp_field]
                    full_instance = make_safe_instance_string(inst_name)
                    metric_key = '{}[{}]'.format(data_field, full_instance)

                    if component_name not in parse_data:
                        parse_data[component_name] = {}

                    if ts not in parse_data[component_name]:
                        timestamp = int(ts) if len(str(int(ts))) > 10 else int(ts) * 1000
                        if not last_ts or timestamp > last_ts:
                            last_ts = timestamp
                        parse_data[component_name][ts] = {}
                    if inst_name not in parse_data[component_name][ts]:
                        parse_data[component_name][ts][inst_name] = {}
                    parse_data[component_name][ts][inst_name][metric_key] = str(data_value)

        if last_ts:
            logger.info(
                "In file {} the last timestamp is {} {}, time diff: {}".format(file_name, format_timestamp(last_ts),
                                                                               last_ts,
                                                                               file_time_diff(logger, file_name,
                                                                                              last_ts)))

    return parse_data


def send_data(logger, component_name, if_config_vars, metric_data):
    """ Sends parsed metric data to InsightFinder """
    project_name = if_config_vars['project_name']
    if component_name != NOT_EXIST_COMPONENT_NAME and if_config_vars['project_name_prefix']:
        project_name = if_config_vars['project_name_prefix'] + component_name

    if not project_name:
        logger.error('Cannot find project name to receive data for:' + component_name)
        return

    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = dict()
    # for backend so this is the camel case in to_send_data_dict
    to_send_data_dict["metricData"] = json.dumps(metric_data)
    to_send_data_dict["licenseKey"] = if_config_vars['license_key']
    to_send_data_dict["projectName"] = project_name
    to_send_data_dict["userName"] = if_config_vars['user_name']
    to_send_data_dict["agentType"] = "streaming"

    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = if_config_vars['if_url'] + "/customprojectrawdata"
    send_data_to_receiver(logger, post_url, to_send_data_json, len(metric_data))
    last_ts = None
    if len(metric_data):
        last_ts = metric_data[-1].get('timestamp', None)

    logger.info(
        "--- Send data to {}, last timestamp: {}, {}, use: {} seconds ---".format(project_name,
                                                                                  format_timestamp(last_ts),
                                                                                  last_ts,
                                                                                  str(time.time() - send_data_time)))


def send_data_to_receiver(logger, post_url, to_send_data, num_of_message):
    attempts = 0
    while attempts < MAX_RETRY_NUM:
        data_size = sys.getsizeof(to_send_data)
        if data_size > MAX_PACKET_SIZE:
            logger.error("Packet size too large %s.  Dropping packet." + str(sys.getsizeof(to_send_data)))
            break
        response_code = -1
        attempts += 1
        try:
            response = requests.post(post_url, data=json.loads(to_send_data), verify=False)
            response_code = response.status_code
        except Exception as ex:
            logger.error("Attempts: %d. Fail to send %d data to %s, response code: %d, %s, wait %d sec to resend." % (
                attempts, data_size, '/customprojectrawdata', response_code, ex, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
            continue
        if response_code == 200:
            if num_of_message:
                logger.info("Data send successfully. Number of events: {}, bytes: {}".format(num_of_message, data_size))
            else:
                logger.info("Data send successfully. Bytes: {}".format(data_size))
            break
        else:
            logger.error("Attempts: %d. Fail to send %d data to %s, response code: %d wait %d sec to resend." % (
                attempts, data_size, '/customprojectrawdata', response_code, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)

    if attempts == MAX_RETRY_NUM:
        logger.error("Fail to send data to {} with max retry {}, ignore it.".format('/customprojectrawdata', MAX_RETRY_NUM))


def make_safe_instance_string(instance):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', str(instance))
    instance = COLONS.sub('-', str(instance))
    return instance


def read_s3_objects(is_metadata, logger, config_name, cli_config_vars, agent_config_vars, if_config_vars):
    if is_metadata:
        index_file = RUNNING_INDEX_METADATA.format(config_name)
        bucket_name = agent_config_vars['aws_s3_metadata_bucket_name']
        object_prefix = agent_config_vars['aws_s3_metadata_object_prefix']
    else:
        index_file = RUNNING_INDEX.format(config_name)
        bucket_name = agent_config_vars['aws_s3_bucket_name']
        object_prefix = agent_config_vars['aws_s3_object_prefix']

    # read the previous processed file from the running index file
    last_object_key = None
    index_file = os.path.abspath(os.path.join(__file__, os.pardir, index_file))
    if os.path.exists(index_file):
        try:
            with open(index_file, 'r') as fp:
                last_object_key = (fp.readline() or '').strip() or None
                logger.info('Got last object key {}'.format(last_object_key))
        except Exception as e:
            logger.error('Failed to read index file: {}, start from the beginning\n {}'.format(index_file, e))

    region_name = agent_config_vars['aws_region']
    s3 = boto3.resource('s3',
                        aws_access_key_id=agent_config_vars['aws_access_key_id'],
                        aws_secret_access_key=agent_config_vars['aws_secret_access_key'],
                        region_name=region_name)
    bucket = s3.Bucket(bucket_name)
    logger.info('Connect to s3 bucket, region: {}, bucket: {}'.format(region_name, bucket_name))

    objects_keys = [x.key for x in bucket.objects.filter(Prefix=object_prefix)]
    logger.info('Found {} files in the bucket with prefix {}:\n{}'.format(len(objects_keys), object_prefix,
                                                                          '\n'.join(objects_keys)))

    new_object_keys = objects_keys
    if last_object_key:
        found = False

        # first, whole string match, if found, start from the next item
        for idx, val in enumerate(objects_keys):
            if val and val == last_object_key:
                found = True
                new_object_keys = objects_keys[idx + 1:]

        if not found:
            # try to find based on date
            match = re.search(r'\d{4}-\d{2}-\d{2}', last_object_key)
            if match:
                last_date = arrow.get(match.group(), 'YYYY-MM-DD')

                for index, val in enumerate(objects_keys):
                    if val:
                        val_match = re.search(r'\d{4}-\d{2}-\d{2}', val)
                        if match:
                            val_date = arrow.get(val_match.group(), 'YYYY-MM-DD')
                            if val_date >= last_date:
                                new_object_keys = objects_keys[index:]
                                last_object_key = val
                                found = True
                                break
        if not found:
            new_object_keys = []

    logger.info(
        'Found {} new files after {}:\n{}'.format(len(new_object_keys), last_object_key, '\n'.join(new_object_keys)))

    return new_object_keys, last_object_key, bucket


def retrieve_s3_metadata(logger, cli_config_vars, bucket, object_key):
    logger.info('start to retrieve metadata from file: {}'.format(object_key))

    buf = io.BytesIO()
    logger.info('downloading file: {}'.format(object_key))

    bucket.download_fileobj(object_key, buf)
    content = buf.getvalue()
    logger.info('download {} bytes from file: {}'.format(len(content), object_key))

    msgs = json.loads(content)
    logger.info('finish retrieve metadata from file: {}'.format(object_key))
    return msgs


def send_metadata_to_receiver(logger, post_url, to_send_data):
    attempts = 0
    while attempts < MAX_RETRY_NUM:
        data_size = sys.getsizeof(to_send_data)
        if data_size > MAX_PACKET_SIZE:
            logger.error("Packet size too large %s.  Dropping packet." + str(sys.getsizeof(to_send_data)))
            break
        response_code = -1
        attempts += 1
        try:
            response = requests.post(post_url, data=json.dumps(to_send_data), verify=False)
            response_code = response.status_code
        except Exception as ex:
            logger.error("Attempts: %d. Fail to send %d data to %s, response code: %d, %s, wait %d sec to resend." % (
                attempts, data_size, '/v1/agent-upload-instancemetadata', response_code, ex, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
            continue
        if response_code == 200:
            logger.info("Data send successfully. Bytes: {}".format(data_size))
            break
        else:
            logger.error("Attempts: %d. Fail to send %d data to %s, response code: %d wait %d sec to resend." % (
                attempts, data_size, '/v1/agent-upload-instancemetadata', response_code, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)

    if attempts == MAX_RETRY_NUM:
        logger.error("Fail to send metadata to {} with max retry {}, ignore it.".format('/v1/agent-upload-instancemetadata', MAX_RETRY_NUM))


def send_metadata(logger, component_name, if_config_vars, data):
    project_name = if_config_vars['project_name']
    if component_name != NOT_EXIST_COMPONENT_NAME and if_config_vars['project_name_prefix']:
        project_name = if_config_vars['project_name_prefix'] + component_name

    send_data_time = time.time()

    params = dict()
    params["licenseKey"] = if_config_vars['license_key']
    params["userName"] = if_config_vars['user_name']
    params["projectName"] = project_name
    params["override"] = "true"
    post_url = if_config_vars['if_url'] + "/api/v1/agent-upload-instancemetadata?" + urllib.parse.urlencode(params)

    # send the data
    metadata_max_instances = if_config_vars['metadata_max_instances']
    if metadata_max_instances:
        count = 0
        buf = []
        for d in data:
            count += 1
            buf.append(d)
            if count == metadata_max_instances:
                send_metadata_to_receiver(logger, post_url, buf)
                logger.info(
                    "Send metadata {} to {}, time: {} seconds ---".format(component_name or '', project_name,
                                                                          (time.time() - send_data_time)))
                buf = []
        if len(buf) > 0:
            send_metadata_to_receiver(logger, post_url, buf)
            logger.info("Send metadata {} to {}, time: {} seconds ---".format(component_name or '', project_name,
                                                                              (time.time() - send_data_time)))
    else:
        send_metadata_to_receiver(logger, post_url, data)
        logger.info("Send metadata {} to {}, time: {} seconds ---".format(component_name or '', project_name,
                                                                          (time.time() - send_data_time)))


def process_s3_metadata(logger, config_name, cli_config_vars, agent_config_vars, if_config_vars):
    (new_object_keys, last_object_key, bucket) = read_s3_objects(True, logger, config_name, cli_config_vars,
                                                                 agent_config_vars, if_config_vars)

    # If now new metadata, use the last one
    if not new_object_keys and last_object_key and bucket:
        new_object_keys = [last_object_key]

    messages = []
    for obj_key in new_object_keys:
        msgs = retrieve_s3_metadata(logger, cli_config_vars, bucket, obj_key)
        messages.extend(msgs)
        logger.info('Parsing metadata completed...')

    instance_field = agent_config_vars['metadata_instance_field']
    component_field = agent_config_vars['metadata_component_field']
    project_name_prefix = if_config_vars['project_name_prefix']

    global metadata_dict
    global instance_dict

    for m in messages:
        if m:
            instance_name = m.get(instance_field)
            component_name = m.get(component_field)
            if instance_name and component_name:
                if not metadata_dict.get(component_name):
                    metadata_dict[component_name] = []
                metadata_dict[component_name].append(instance_name)
                instance_dict[instance_name] = component_name

    # Create project if we use project_name_prefix option
    if not cli_config_vars['testing'] and project_name_prefix:
        for component_name in metadata_dict.keys():
            project_name = project_name_prefix + component_name
            system_name = component_name
            check_success = check_project_exist(logger, if_config_vars, project_name, system_name)
            if not check_success:
                return

    # Send metadata
    if not cli_config_vars['testing']:
        if project_name_prefix:
            # send metadata by component
            for component_name in metadata_dict.keys():
                data = []
                for instance_name in metadata_dict[component_name]:
                    data.append({'instanceName': instance_name, 'metricInstanceName': instance_name,
                                 'componentName': component_name})
                send_metadata(logger, component_name, if_config_vars, data)
        else:
            data = []
            for component_name in metadata_dict.keys():
                for instance_name in metadata_dict[component_name]:
                    data.append({'instanceName': instance_name, 'metricInstanceName': instance_name,
                                 'componentName': component_name})
            send_metadata(logger, None, if_config_vars, data)

    if len(new_object_keys) > 0:
        new_last_object_key = new_object_keys[-1]
        index_file = os.path.abspath(os.path.join(__file__, os.pardir, RUNNING_INDEX_METADATA.format(config_name)))
        try:
            with open(index_file, 'w') as fp:
                fp.writelines([new_last_object_key])
                logger.info('Update metadata index file to file: {}'.format(new_last_object_key))
        except Exception as e:
            logger.warning('Failed to update running index file with file: {}\n'.format(new_last_object_key, e))


def process_s3_data(logger, config_name, cli_config_vars, agent_config_vars, if_config_vars):
    (new_object_keys, last_object_key, bucket) = read_s3_objects(False, logger, config_name, cli_config_vars,
                                                                 agent_config_vars, if_config_vars)

    while len(new_object_keys) > 0:
        keys = new_object_keys[0:MAX_THREAD_COUNT]

        threads = []
        for obj_key in keys:
            thread = MyThread(logger, cli_config_vars, bucket, obj_key)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # parse data
        parse_data = process_parse_data(logger, cli_config_vars, agent_config_vars)
        logger.info('Parsing data completed...')

        # send data
        for component_name in parse_data.keys():
            data = []
            for key in sorted(parse_data[component_name].keys()):
                value = parse_data[component_name][key]
                timestamp = int(key) if len(str(int(key))) > 10 else int(key) * 1000
                line = {'timestamp': str(timestamp)}
                for d in value.values():
                    line.update(d)
                data.append(line)

                if get_json_size_bytes(data) >= CHUNK_SIZE:
                    if cli_config_vars['testing']:
                        logger.info('testing!!! do not sent data to IF. Data: {}'.format(data))
                        data = []
                    else:
                        send_data(logger, component_name, if_config_vars, data)
                        data = []

            if len(data) > 0:
                if cli_config_vars['testing']:
                    logger.info('testing!!! do not sent data to IF. Data: {}'.format(data))
                else:
                    logger.debug('send data {} to IF.'.format(data))
                    send_data(logger, component_name, if_config_vars, data)

        # move to next batch
        new_object_keys = new_object_keys[MAX_THREAD_COUNT:]

        # Update running index file
        if len(keys) > 0:
            new_last_object_key = keys[-1]
            index_file = os.path.abspath(os.path.join(__file__, os.pardir, RUNNING_INDEX.format(config_name)))
            try:
                with open(index_file, 'w') as fp:
                    fp.writelines([new_last_object_key])
                logger.info('Update index file to file: {}'.format(new_last_object_key))
            except Exception as e:
                logger.warning('Failed to update running index file with file: {}\n'.format(new_last_object_key, e))


def listener_configurer():
    """ set up logging according to the defined log level """
    # create a logging format
    formatter = logging.Formatter(
        '{ts} {name} [pid {pid}] {lvl} {mod}.{func}():{line} {msg}'.format(
            ts='%(asctime)s',
            name='%(name)s',
            pid='%(process)d',
            lvl='%(levelname)-8s',
            mod='%(module)s',
            func='%(funcName)s',
            line='%(lineno)d',
            msg='%(message)s'),
        ISO8601[0])

    # Get the root logger
    root = logging.getLogger()

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

            if not record or record.name == 'KILL':
                return

            logger = logging.getLogger(record.name)
            logger.handle(record)
        time.sleep(1)


def queue_configurer(q):
    h = QueueHandler(q)  # Just the one handler needed
    root = logging.getLogger()
    root.addHandler(h)
    # Default log level to info
    root.setLevel(logging.INFO)


def worker_process(args):
    (config_file, c_config, time_now, q) = args

    config_name = Path(config_file).stem
    level = c_config['log_level']

    # start sub process
    logger = logging.getLogger('worker.' + config_name)
    logger.setLevel(level)

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
        # check project first if project_name is set
        project_name = if_config_vars['project_name']
        if project_name:
            check_success = check_project_exist(logger, if_config_vars, project_name, None)
            if not check_success:
                return

    logger.info("Process metadata files from s3 bucket")
    process_s3_metadata(logger, config_name, c_config, agent_config_vars, if_config_vars)

    logger.info("Process data files from s3 bucket")
    process_s3_data(logger, config_name, c_config, agent_config_vars, if_config_vars)

    time.sleep(10)


def main():
    # capture warnings to logging system
    logging.captureWarnings(True)

    # get config
    cli_config_vars = get_cli_config_vars()

    # get all config file
    files_path = os.path.join(cli_config_vars['config'], "*.ini")
    config_files = glob.glob(files_path)

    if len(config_files) == 0:
        logging.error("Config files not found")
        sys.exit(1)

    # logger
    m = multiprocessing.Manager()
    queue = m.Queue()
    listener = multiprocessing.Process(target=listener_process, args=(queue, cli_config_vars))
    listener.start()

    # set up main logger following example from work_process
    queue_configurer(queue)
    main_logger = logging.getLogger('main')

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)
    main_logger.info(cli_data_block)

    # get args
    utc_time_now = int(arrow.utcnow().float_timestamp)
    arg_list = [(f, cli_config_vars, utc_time_now, queue) for f in config_files]

    # start sub process by pool
    pool = multiprocessing.Pool(len(arg_list))
    pool_result = pool.map_async(worker_process, arg_list)
    pool.close()

    timeout = cli_config_vars['timeout']
    need_timeout = timeout > 0
    if need_timeout:
        pool_result.wait(timeout=timeout)

    try:
        pool_result.get(timeout=1 if need_timeout else None)
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


if __name__ == "__main__":
    main()

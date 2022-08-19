#!/usr/bin/env python
import configparser
import json
import logging
import os
import socket
import sys
import time
import urllib.parse
import http.client
import shlex
import traceback
import signal
import pytz
import arrow
import requests
import threading
import regex
from optparse import OptionParser


threadLock = threading.Lock()
messages = []


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


def get_agent_config_vars(logger, config_ini, if_config_vars):
    """ Read and parse config.ini """
    """ get config.ini vars """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False
    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)

        project_whitelist_regex = None
        metric_whitelist_regex = None
        instance_whitelist_regex = None
        try:
            # api settings
            api_urls = config_parser.get('agent', 'api_urls')
            request_method = config_parser.get('agent', 'request_method')

            # handle required arrays
            # api_urls
            if api_urls:
                api_urls = api_urls.split(',')
            else:
                return config_error(logger, 'api_urls')

            if not request_method:
                return config_error(logger, 'request_method')

            # project
            project_field = config_parser.get('agent', 'project_field')
            project_whitelist = config_parser.get('agent', 'project_whitelist')

            # metric
            metric_fields = config_parser.get('agent', 'metric_fields')
            metrics_whitelist = config_parser.get('agent', 'metrics_whitelist')

            # message parsing
            timezone = config_parser.get('agent', 'timezone') or 'UTC'
            timestamp_field = config_parser.get('agent', 'timestamp_field', raw=True) or 'timestamp'
            target_timestamp_timezone = config_parser.get('agent', 'target_timestamp_timezone', raw=True) or 'UTC'
            component_field = config_parser.get('agent', 'component_field', raw=True)
            instance_field = config_parser.get('agent', 'instance_field', raw=True)
            instance_whitelist = config_parser.get('agent', 'instance_whitelist')
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
        buffer_sampling_interval_multiple = int(
            buffer_sampling_interval_multiple.strip()) if buffer_sampling_interval_multiple.strip() else 2

        if len(timestamp_field) == 0:
            return config_error(logger, 'timestamp_field')
        if len(instance_field) == 0:
            return config_error(logger, 'instance_field')

        # proxies
        agent_proxies = dict()
        if len(agent_http_proxy) > 0:
            agent_proxies['http'] = agent_http_proxy
        if len(agent_https_proxy) > 0:
            agent_proxies['https'] = agent_https_proxy

        # add parsed variables to a global
        config_vars = {
            'api_urls': api_urls,
            'request_method': request_method,
            'project_field': project_field,
            'project_whitelist_regex': project_whitelist_regex,
            'metric_whitelist_regex': metric_whitelist_regex,
            'metric_fields': metric_fields,
            'timezone': timezone,
            'timestamp_field': timestamp_field,
            'target_timestamp_timezone': target_timestamp_timezone,
            'component_field': component_field,
            'instance_field': instance_field,
            "instance_whitelist_regex": instance_whitelist_regex,
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


def yield_message(message):
    for metric in message:
        yield metric


def process_get_data(log_queue, cli_config_vars, method, url):
    # logger = logging.getLogger('worker')
    # logger.info('Started data consumer process ......')
    global messages
    req = requests.get
    if method.upper() == 'POST':
        req = requests.post
    response = req(url, headers=headers)
    if response.status_code == http.client.OK:
        message = response.text.splitlines()
        print(message)
        message = [json.loads(metric_data) for metric_data in message]
        threadLock.acquire()
        messages.extend(message)
        threadLock.release()
    else:
        print('failtttttt')
        logger.warn('Fail')
        # logger.info('Response Code: {}\nTEXT: {}'.format(
        #     response.status_code, response.text))

    # logger.info('Closed data process......')


class myThread(threading.Thread):
    def __init__(self, logger, cli_config_vars, method, url):
        threading.Thread.__init__(self)
        self.cli_config_vars = cli_config_vars
        self.method = method
        self.url = url
        self.logger = logger

    def run(self):
        process_get_data(self.logger, self.cli_config_vars, self.method, self.url)


def process_parse_data(log_queue, cli_config_vars, agent_config_vars, messages):
    messages = [metric for metric in messages if metric[agent_config_vars['instance_field']]]
    timestamps = []
    for metric in yield_message(messages):
        if metric[agent_config_vars['timestamp_field']] not in timestamps:
            timestamps.append(metric[agent_config_vars['timestamp_field']])

    for timestamp in timestamps:
        to_post_data = [message for message in messages if int(message[agent_config_vars['timestamp_field']]) == int(timestamp)]
        send_data(to_post_data)

def send_data(cli_config_vars, metric_data):
    """ Sends parsed metric data to InsightFinder """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = {"metricData": json.dumps(metric_data),
                         "licenseKey": cli_config_vars['license_key'],
                         "projectName": cli_config_vars['project_name'],
                         "userName": cli_config_vars['user_name'],
                         "agentType": "MetricFileReplay"}
    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = config_vars['server_url'] + "/customprojectrawdata"
    send_data_to_receiver(post_url, to_send_data_json, len(log_data))
    print("--- Send data time: %s seconds ---" + str(time.time() - send_data_time))


def send_data_to_receiver(post_url, to_send_data, num_of_message):
    attempts = 0
    while attempts < MAX_RETRY_NUM:
        if sys.getsizeof(to_send_data) > MAX_PACKET_SIZE:
            print("Packet size too large %s.  Dropping packet." + str(sys.getsizeof(to_send_data)))
            break
        response_code = -1
        attempts += 1
        try:
            response = requests.post(post_url, data=json.loads(to_send_data), proxies=config_vars['proxies'], verify=False)
            response_code = response.status_code
        except:
            print("Attempts: %d. Fail to send data, response code: %d wait %d sec to resend." % (
                attempts, response_code, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
            continue
        if response_code == 200:
            print("Data send successfully. Number of events: %d" % num_of_message)
            break
        else:
            print("Attempts: %d. Fail to send data, response code: %d wait %d sec to resend." % (
                attempts, response_code, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
    if attempts == MAX_RETRY_NUM:
        sys.exit(1)


def main():
    global messages
    # get config
    cli_config_vars = get_cli_config_vars()

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)
    # logger.info(cli_data_block)
    logger = logging.getLogger()
    # get config file
    config_file = os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini'))
    # logger.info("Process start with config: {}".format(config_file))

    if_config_vars = get_if_config_vars(logger, config_file)
    if not if_config_vars:
        sys.exit(1)
    agent_config_vars = get_agent_config_vars(logger, config_file, if_config_vars)
    if not agent_config_vars:
        time.sleep(1)
        sys.exit(1)
    print_summary_info(logger, if_config_vars, agent_config_vars)

    # consumer process

    threads = []
    for url in agent_config_vars['api_urls']:
        thread = myThread(logging, cli_config_vars, agent_config_vars['request_method'], url)
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    #parse data
    process_parse_data(logging, cli_config_vars, agent_config_vars, messages)

if __name__ == "__main__":
    main()
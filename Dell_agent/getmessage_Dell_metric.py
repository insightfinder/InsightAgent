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
from logging.handlers import QueueHandler
from sys import getsizeof
from queue import Queue
import multiprocessing
from multiprocessing import Process, Queue


threadLock = threading.Lock()
messages = []

MAX_RETRY_NUM = 10
RETRY_WAIT_TIME_IN_SEC = 30
UNDERSCORE = regex.compile(r"\_+")
COLONS = regex.compile(r"\:+")
# chunk size is 2Mb
CHUNK_SIZE = 2 * 1024 * 1024
MAX_PACKET_SIZE = 5000000
ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    # return len(bytearray(json.dumps(json_data)))
    return getsizeof(json.dumps(json_data))

def config_error(logger, setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(
        info))
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
            'project_type': project_type,
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

            # message parsing
            timezone = config_parser.get('agent', 'timezone') or 'UTC'
            timestamp_field = config_parser.get('agent', 'timestamp_field', raw=True) or 'timestamp'
            target_timestamp_timezone = config_parser.get('agent', 'target_timestamp_timezone', raw=True) or 'UTC'
            instance_field = config_parser.get('agent', 'instance_field')
            metric_fields = config_parser.get('agent', 'metric_fields')
            metric_whitelist = config_parser.get('agent', 'metric_whitelist')

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

        if len(metric_whitelist) != 0:
            try:
                metric_whitelist_regex = regex.compile(metrics_whitelist)
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
            'api_urls': api_urls,
            'request_method': request_method,
            'timezone': timezone,
            'timestamp_field': timestamp_field,
            'instance_field': instance_field,
            'metric_fields': metric_fields,
            'metric_whitelist_regex': metric_whitelist,
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


def yield_message(message):
    for metric in message:
        yield metric


def process_get_data(logger, cli_config_vars, method, url):
    logger.info('start to request data')
    global messages
    req = requests.get
    if method.upper() == 'POST':
        req = requests.post
    response = req(url)
    if response.status_code == http.client.OK:
        message = response.text.splitlines()
        message = [json.loads(metric_data) for metric_data in message]
        threadLock.acquire()
        messages.extend(message)
        threadLock.release()
    else:
        logger.error('{} failed to get data'.format(url))

    logger.info('Closed data process......')


class myThread(threading.Thread):
    def __init__(self, logger, cli_config_vars, method, url):
        threading.Thread.__init__(self)
        self.cli_config_vars = cli_config_vars
        self.method = method
        self.url = url
        self.logger = logger

    def run(self):
        process_get_data(self.logger, self.cli_config_vars, self.method, self.url)


def process_parse_data(logger, cli_config_vars, agent_config_vars):
    logger.info('start to parse data...')
    global messages
    messages = [metric for metric in messages if metric[agent_config_vars['instance_field']]]
    timestamp_field = agent_config_vars['timestamp_field']
    instance = agent_config_vars['instance_field']
    metric_fields = agent_config_vars['metric_fields']
    # {"ts1": {'instance1': {'ts': 23,'metric1': value},}
    parse_data = {}
    # all_timestamps = []
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
                if agent_config_vars['metric_whitelist_regex'] and not agent_config_vars['metric_whitelist_regex'].match(data_field):
                    logger.debug('metric_whitelist has no matching data')
                    continue
                full_instance = make_safe_instance_string(metric[instance])
                metric_key = '{}[{}]'.format(data_field, full_instance)
                # all_timestamps.append(metric[timestamp_field])
                if metric[timestamp_field] not in parse_data:
                    parse_data[metric[timestamp_field]] = {}
                timestamp = int(metric[timestamp_field]) if len(str(int(metric[timestamp_field]))) > 10 else int(metric[timestamp_field]) * 1000
                if metric[instance] not in parse_data[metric[timestamp_field]]:
                    parse_data[metric[timestamp_field]][instance] = {'timestamp': timestamp}
                parse_data[metric[timestamp_field]][instance][metric_key] =  data_value

    return parse_data


def send_data(logger, if_config_vars, metric_data):
    """ Sends parsed metric data to InsightFinder """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = dict()
    # for backend so this is the camel case in to_send_data_dict
    to_send_data_dict["metricData"] = json.dumps(metric_data)
    to_send_data_dict["licenseKey"] = if_config_vars['license_key']
    to_send_data_dict["projectName"] = if_config_vars['project_name']
    to_send_data_dict["userName"] = if_config_vars['user_name']
    to_send_data_dict["agentType"] = "MetricFileReplay"

    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = if_config_vars['if_url'] + "/customprojectrawdata"
    send_data_to_receiver(logger, post_url, to_send_data_json, len(metric_data))
    logger.info("--- Send data time: %s seconds ---" %
          str(time.time() - send_data_time))


def send_data_to_receiver(logger, post_url, to_send_data, num_of_message):
    attempts = 0
    while attempts < MAX_RETRY_NUM:
        if sys.getsizeof(to_send_data) > MAX_PACKET_SIZE:
            logger.error("Packet size too large %s.  Dropping packet." + str(sys.getsizeof(to_send_data)))
            break
        response_code = -1
        attempts += 1
        try:
            response = requests.post(post_url, data=json.loads(to_send_data), verify=False)
            response_code = response.status_code
        except:
            logger.error("Attempts: %d. Fail to send data, response code: %d wait %d sec to resend." % (
                attempts, response_code, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
            continue
        if response_code == 200:
            logger.info("Data send successfully. Number of events: %d" % num_of_message)
            break
        else:
            logger.error("Attempts: %d. Fail to send data, response code: %d wait %d sec to resend." % (
                attempts, response_code, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
    if attempts == MAX_RETRY_NUM:
        sys.exit(1)



def make_safe_instance_string(instance):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', str(instance))
    instance = COLONS.sub('-', str(instance))
    return instance

def logger_control(user, level):
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
    root = logging.getLogger(user)
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
    root.setLevel(level)
    return root



def main():
    global messages
    # get config
    cli_config_vars = get_cli_config_vars()

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)

    # set logger
    logger = logger_control('worker', cli_config_vars['log_level'])
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
        thread = myThread(logger, cli_config_vars, agent_config_vars['request_method'], url)
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    #parse data
    parse_data = process_parse_data(logger, cli_config_vars, agent_config_vars)
    logger.info('Parsing data completed...')
    # send data
    data = []
    for key, value in parse_data.items():
        data.extend(list(value.values()))
        if get_json_size_bytes(data) >= CHUNK_SIZE:
            logger.info('testing!!! do not sent data to IF. Data: {}'.format(data))
            if cli_config_vars['testing']:
                data = []
                continue
            send_data(logger, if_config_vars, data)
            data = []
    if len(data) > 0:
        if cli_config_vars['testing']:
            logger.info('testing!!! do not sent data to IF. Data: {}'.format(data))
            return
        logger.debug('send data {} to IF.'.format(data))
        send_data(logger, if_config_vars, data)


if __name__ == "__main__":
    main()
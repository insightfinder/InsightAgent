# -*- coding: utf-8 -*-
import arrow
import json
import os
import sys
import time
import urllib3
import importlib
import requests
from configparser import ConfigParser
from optparse import OptionParser
import logging
import regex

MAX_RETRY_NUM = 10
RETRY_WAIT_TIME_IN_SEC = 30
MAX_MESSAGE_LENGTH = 10000
MAX_DATA_SIZE = 4000000
MAX_PACKET_SIZE = 5000000

def get_cli_config_vars():
    """ get CLI options """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    parser.add_option('-c', '--config', action='store', dest='config', default=abs_path_from_cur('config.ini'),
                      help='Path to the config file to use. Defaults to {}'.format(abs_path_from_cur('config.ini')))
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data).' +
                           ' Automatically turns on verbose logging')
    parser.add_option('-f', '--file', action='store', dest='logfile', 
                      help='Full path to the log file to parse')

    (options, args) = parser.parse_args()
    
    try: 
        if os.path.isabs(options.config): 
            config_file = options.config
        else: 
            config_file = abs_path_from_cur(options.config)
    except Exception:
        print("Valid configuration file is missing (-c / --config)")
        sys.exit(1)

    try:
        if os.path.isabs(options.logfile):
            log_file = options.logfile
        else:
            log_file = abs_path_from_cur(options.logfile)
    except Exception:
        print("Valid log file is missing (-f / --file).")
        sys.exit(1)

    config_vars = {
        'config': config_file,
        'log_file': log_file,
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

def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(cli_config_vars['config']):
            parser = ConfigParser()
            parser.read(cli_config_vars['config'])
            # IF Variables
            license_key = parser.get('InsightFinder', 'insightFinder_license_key')
            project_name = parser.get('InsightFinder', 'insightFinder_project_name')
            user_name = parser.get('InsightFinder', 'insightFinder_user_name')
            server_url = parser.get('InsightFinder', 'insightFinder_server_url')
            http_proxy = parser.get('InsightFinder', 'http_proxy')
            https_proxy = parser.get('InsightFinder', 'https_proxy')

            # Log Parsing Variables
            instance_name = parser.get('LogParsing', 'instance')
            timestamp_regex = parser.get('LogParsing', 'timestamp_regex')
            timestamp_format = parser.get('LogParsing', 'timestamp_format')
            timestamp_timezone = parser.get('LogParsing', 'timestamp_timezone')

            if len(license_key) == 0:
                print("Agent not correctly configured(license key). Check config file.")
                sys.exit(1)
            if len(project_name) == 0:
                print("Agent not correctly configured(project name). Check config file.")
                sys.exit(1)
            if len(user_name) == 0:
                print("Agent not correctly configured(user name). Check config file.")
                sys.exit(1)
            if len(server_url) == 0:
                print("Agent not correctly configured(server url). Check config file.")
                sys.exit(1)

            if len(instance_name) == 0:
                print("Agent not correctly configured(instance). Check config file.")
                sys.exit(1)
            if len(timestamp_regex) == 0:
                print("Agent not correctly configured(timestamp_regex). Check config file.")
                sys.exit(1)

            # Proxies
            proxies = dict()
            if len(http_proxy) > 0:
                proxies['http'] = http_proxy
            if len(https_proxy) > 0:
                proxies['https'] = https_proxy

            config_vars['license_key'] = license_key
            config_vars['project_name'] = project_name
            config_vars['user_name'] = user_name
            config_vars['server_url'] = server_url
            config_vars['proxies'] = proxies

            config_vars['instance_name'] =  make_safe_instance_string(instance_name)
            config_vars['timestamp_regex'] = regex.compile(timestamp_regex)
            config_vars['timestamp_format'] = timestamp_format
            config_vars['timestamp_timezone'] = timestamp_timezone

    except IOError:
        print("config.ini file is missing")
    return config_vars


def send_data(log_data):
    """ Sends parsed metric data to InsightFinder """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = {"metricData": json.dumps(log_data),
                         "licenseKey": config_vars['license_key'],
                         "projectName": config_vars['project_name'],
                         "userName": config_vars['user_name'],
                         "agentType": "LogFileReplay"}
    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = config_vars['server_url'] + "/customprojectrawdata"
    send_data_to_receiver(post_url, to_send_data_json, len(log_data))
    logger.info("--- Send data time: {} seconds ---".format(str(time.time() - send_data_time)))


def send_data_to_receiver(post_url, to_send_data, num_of_message):
    attempts = 0
    while attempts < MAX_RETRY_NUM:
        if sys.getsizeof(to_send_data) > MAX_PACKET_SIZE:
            logger.warn("Packet size too large.  Dropping packet.")
            break
        response_code = -1
        attempts += 1
        try:
            response = requests.post(post_url, data=json.loads(to_send_data), proxies = config_vars['proxies'], verify=False)
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

def make_safe_instance_string(instance, device=''):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', instance)
    instance = COLONS.sub('-', instance)
    # if there's a device, concatenate it to the instance with an underscore
    if device:
        instance = '{}_{}'.format(make_safe_instance_string(device), instance)
    return instance

def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))

if __name__ == "__main__":
    # Declare constants
    UNDERSCORE = regex.compile(r"\_+")
    COLONS = regex.compile(r"\:+")
    ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']

    # Disable the InsecureRequestWarning which occurs when connecting to an SSL endpoint without verifying the certificate
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    importlib.reload(sys)

    # Load configurations
    cli_config_vars = get_cli_config_vars()
    logger = set_logger_config(cli_config_vars['log_level'])
    config_vars = get_agent_config_vars()

    # Process File
    CHUNK_SIZE = 1000
    with open(cli_config_vars['log_file'], encoding='utf-8') as log_file:
        logs = log_file.readlines()
        data = []
        count = 0
        size = 0
        for line in logs:
            entry = {'eventId': '','tag': config_vars['instance_name'], 'data': line}

            ts = config_vars['timestamp_regex'].findall(line)
            
            if len(ts) == 1: 
                try:
                    if isinstance(ts[0], tuple):
                        timestamp = ts[0][0]
                    else: 
                        timestamp = ts[0]
                    
                    if config_vars['timestamp_format']:
                        if config_vars['timestamp_timezone']:
                            eventId = arrow.get(timestamp, config_vars['timestamp_format'], tzinfo=config_vars['timestamp_timezone'])
                        else: 
                            eventId = arrow.get(timestamp, config_vars['timestamp_format'])
                    else: 
                        if config_vars['timestamp_timezone']:
                            eventId = arrow.get(timestamp, tzinfo=config_vars['timestamp_timezone'])
                        else: 
                            eventId = arrow.get(timestamp)
                    entry['eventId'] = int(eventId.to('utc').timestamp() * 1000)
                except Exception as e: 
                    logger.warning("Timestamp error: {}".format(e))
                    continue
            else:
                logger.warn("Unable to parse timestamp: {}".format(line))
                continue

            # Check length of log message and truncate if too long
            if len(entry['data']) > MAX_MESSAGE_LENGTH:
                entry['data'] = entry['data'][0:MAX_MESSAGE_LENGTH - 1]

            # Check size of entry and overall packet size
            entry_size = sys.getsizeof(json.dumps(entry))
            if size + entry_size >= MAX_DATA_SIZE:
                if not cli_config_vars['testing']:
                    send_data(data)
                else: 
                    logger.info("--- Data Chunk: {} entries ---".format(count))
                size = 0
                count = 0
                data = []

            # Add the log entry to send
            logger.debug(entry)
            data.append(entry)
            count += 1

            # Chunk number of log entries
            if count >= CHUNK_SIZE:
                if not cli_config_vars['testing']:
                    send_data(data)
                else: 
                    logger.info("--- Data Chunk: {} entries ---".format(count))
                size = 0
                count = 0
                data = []
        if count != 0:
            if not cli_config_vars['testing']:
                send_data(data)
            else: 
                logger.info("--- Data Chunk: {} entries ---".format(count))


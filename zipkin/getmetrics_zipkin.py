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
from statistics import median
import urlparse
import httplib
import requests

'''
This script gathers data to send to Insightfinder
'''


def start_data_processing():
    """ get traces from the last <samplingInterval> minutes """
    # fork off a process to handle metric agent
    parent = os.fork()
    if parent > 0:
        track['mode'] = "LOG"
        if_config_vars['projectName'] += '-log'
        logger.debug(str(os.getpid()) + ' is running the log agent')
    else:
        track['mode'] = "METRIC"
        if_config_vars['projectName'] += '-metric'
        logger.debug(str(os.getpid()) + ' is running the metric agent')
    timestamp_fixed = int(time.time() * 1000)
    traces = zipkin_get_traces()
    for trace in traces:
        for span in trace:
            process_zipkin_span(timestamp_fixed, span)


def process_zipkin_span(timestamp_fixed, span):
    """
    for a single span, check if it passes the filter, add it to the
    current chunk, and send the chunk if appropriate
    """
    endpoint = span['localEndpoint']
    span_name = span['name']
    if filter_zipkin_span(endpoint['serviceName'], span_name):
        return

    timestamp = int(span.pop('timestamp')) / 1000
    instance = make_instance_name(endpoint)

    if track['mode'] == "LOG":
        log_handoff(timestamp, instance, span)
    else:
        metric_handoff(timestamp_fixed, span_name, instance, span['duration'])


def filter_zipkin_span(service_name, span_name):
    """ determine if this span should be excluded """
    if len(agent_config_vars['services_filter']) != 0 and service_name not in agent_config_vars['services_filter']:
        return True

    if len(agent_config_vars['span_filter']) != 0 and span_name not in agent_config_vars['span_filter']:
        return True

    return False


def make_instance_name(endpoint):
    """ makes a safe instance name, a la Zipkin's UI """
    service_name = make_safe_instance_string(endpoint['serviceName'])
    if 'ipv4' in endpoint:
        return endpoint['ipv4'] + ' (' + service_name + ')'
    return service_name


def zipkin_get_traces():
    """ get traces from zipkin for the last reporting period """
    data = {
        'lookback': int(if_config_vars['samplingInterval']) * 60 * 1000,
        'limit': if_config_vars['chunkLines']
    }
    url = urlparse.urljoin(agent_config_vars['url'], '/api/v2/traces')
    resp = send_request(url, "GET", data, agent_config_vars['proxies'],
                        'Could not reach out to Zipkin APIs',
                        'Fetched traces from Zipkin')
    return json.loads(resp.text)


#################
# Configuration #
#################
def get_agent_config_vars():
    """Read and parse config.ini"""
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            # fields to grab
            zipkin_url = config_parser.get('zipkin', 'url')
            zipkin_services_filter = config_parser.get('zipkin', 'services_filter')
            zipkin_span_filter = config_parser.get('zipkin', 'span_filter')
            zipkin_http_proxy = config_parser.get('zipkin', 'zipkin_http_proxy')
            zipkin_https_proxy = config_parser.get('zipkin', 'zipkin_https_proxy')
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        # defined required fields
        if len(zipkin_url) == 0:
            logger.warning(
                "Agent not correctly configured (Zipkin URL). Check config file.")
            exit()

        # any post-processing
        zipkin_proxies = dict()
        if len(zipkin_http_proxy) > 0:
            zipkin_proxies['http'] = zipkin_http_proxy
        if len(zipkin_https_proxy) > 0:
            zipkin_proxies['https'] = zipkin_https_proxy

        # add parsed variables to a global
        config_vars = {
            "url": zipkin_url,
            "services_filter": zipkin_services_filter,
            "span_filter": zipkin_span_filter,
            "proxies": zipkin_proxies
        }

        return config_vars
    else:
        logger.warning("No config file found. Exiting...")
        exit()


########################
# Start of boilerplate #
########################
def get_if_config_vars():
    """ get config.ini vars """
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            user_name = config_parser.get('insightfinder', 'user_name')
            license_key = config_parser.get('insightfinder', 'license_key')
            project_name = config_parser.get('insightfinder', 'project_name')
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            chunk_lines = config_parser.get('insightfinder', 'chunk_lines')
            if_url = config_parser.get('insightfinder', 'url')
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        # check required variables
        if len(user_name) == 0:
            logger.warning(
                "Agent not correctly configured (user_name). Check config file.")
            sys.exit(1)
        if len(license_key) == 0:
            logger.warning(
                "Agent not correctly configured (license_key). Check config file.")
            sys.exit(1)
        if len(project_name) == 0:
            logger.warning(
                "Agent not correctly configured (project_name). Check config file.")
            sys.exit(1)
        if len(sampling_interval) == 0:
            logger.warning(
                "Agent not correctly configured (sampling_interval). Check config file.")
            sys.exit(1)
        if len(sampling_interval) == 0:
            logger.warning(
                "Agent not correctly configured (sampling_interval). Check config file.")
            sys.exit(1)

        # defaults
        if len(chunk_lines) == 0:
            chunk_lines = 50
        if len(if_url) == 0:
            if_url = 'https://app.insightfinder.com'

        # set IF proxies
        if_proxies = dict()
        if len(if_http_proxy) > 0:
            if_proxies['http'] = if_http_proxy
        if len(if_https_proxy) > 0:
            if_proxies['https'] = if_https_proxy

        config_vars = {
            "userName": user_name,
            "licenseKey": license_key,
            "projectName": project_name,
            "samplingInterval": sampling_interval,
            "chunkLines": chunk_lines,
            "ifURL": if_url,
            "ifProxies": if_proxies
        }

        return config_vars
    else:
        logger.error(
            "Agent not correctly configured. Check config file.")
        sys.exit(1)


def get_cli_config_vars():
    """ get CLI options """
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", help="Enable verbose logging")
    parser.add_option("-t", "--testing",
                      action="store_true", dest="testing", help="Set to testing mode (do not send data)."
                                                                " Automatically turns on verbose logging")
    (options, args) = parser.parse_args()

    config_vars = dict()
    config_vars['testing'] = False
    if options.testing:
        config_vars['testing'] = True
    config_vars['logLevel'] = logging.INFO
    if options.verbose or options.testing:
        config_vars['logLevel'] = logging.DEBUG

    return config_vars


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for index in xrange(0, len(l), n):
        yield l[index:index + n]


def chunk_map(data, SIZE=50):
    """Yield successive n-sized chunks from l."""
    it = iter(data)
    for i in xrange(0, len(data), SIZE):
        yield {k: data[k] for k in islice(it, SIZE)}


def make_safe_instance_string(string):
    return UNDERSCORE.sub(".", string)


def make_safe_metric_key(string):
    """ make safe string already handles this"""
    return make_safe_string(string)


def make_safe_string(string):
    """
    Take a single string and return the same string with spaces, slashes,
    underscores, and non-alphanumeric characters subbed out.
    """
    string = SPACES.sub("-", string)
    string = SLASHES.sub(".", string)
    string = UNDERSCORE.sub(".", string)
    string = NON_ALNUM.sub("", string)
    return string


def set_logger_config(level):
    """Set up logging according to the defined log level"""
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
    post_data = initialize_api_post_data()
    for i in post_data.keys():
        post_data_block += '\n\t' + i + ': ' + str(post_data[i])
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
        send_data_wrapper()

    logger.debug("Total chunks created: " + str(track['chunk_count']))
    logger.debug("Total " + track['mode'].lower() + " entries: " + str(track['entry_count']))


def reset_track():
    """ reset the track global for the next chunk """
    track['start_time'] = time.time()
    track['line_count'] = 0
    track['current_row'] = []
    track['current_dict'] = dict()


###################################
# Functions to handle Metric data #
###################################
def metric_handoff(timestamp, field_name, instance, data):
    append_metric_data_to_entry(timestamp, field_name, instance, data)
    track['line_count'] += 1
    track['entry_count'] += 1
    if len(track['current_dict']) >= if_config_vars['chunkLines']:
        send_data_wrapper()


def append_metric_data_to_entry(timestamp, field_name, instance, data):
    """ creates the metric entry """
    logger.debug(instance + '|' + str(timestamp) + '|' +
                 datetime.fromtimestamp(timestamp/1000).strftime('%Y-%m-%d %H:%M:%S'))
    key = make_safe_metric_key(field_name) + '[' + make_safe_instance_string(instance) + ']'
    ts_str = str(timestamp)
    if ts_str not in track['current_dict'].keys():
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
    """ builds a flatten data up to the timestamp"""
    for timestamp in track['current_dict'].keys():
        new_row = dict()
        new_row['timestamp'] = timestamp
        for key in track['current_dict'][timestamp]:
            value = track['current_dict'][timestamp][key]
            if '|' in value:
                value = median(map(lambda v: int(v), value.split('|')))
            new_row[key] = str(value)
        track['current_row'].append(new_row)


#########################################
# Functions to handle Log/Incident data #
#########################################
def log_handoff(timestamp, instance, data):
    entry = prepare_log_entry(timestamp, instance, data)
    track['current_row'].append(entry)
    track['line_count'] += 1
    track['entry_count'] += 1
    if track['line_count'] >= if_config_vars['chunkLines'] * 100:
        send_data_wrapper()


def prepare_log_entry(timestamp, instance, data):
    """ creates the log entry """
    logger.debug(instance + '|' + str(timestamp) + '|' +
                 datetime.fromtimestamp(timestamp/1000).strftime('%Y-%m-%d %H:%M:%S'))
    entry = dict()
    entry['data'] = data
    if 'INCIDENT' in track['mode'].upper():
        entry['timestamp'] = timestamp
        entry['instanceName'] = instance
    else:
        entry['eventId'] = timestamp
        entry['tag'] = instance
    return entry


################################
# Functions to send data to IF #
################################
def send_data_wrapper():
    """ wrapper to send data """
    logger.debug("--- Chunk creation time: %s seconds ---" % (time.time() - track['start_time']))
    # transpose metrics up
    if 'METRIC' in track['mode'].upper():
        transpose_metrics()

    send_data_to_if(track['current_row'], track['mode'])
    track['chunk_count'] += 1
    reset_track()


def send_data_to_if(chunk_metric_data, mode):
    """ sends data to IF. valid modes are METRIC, METRICREPLAY, LOG, LOGREPLAY, INCIDENT, INCIDENTREPLAY """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = initialize_api_post_data()
    to_send_data_dict["metricData"] = json.dumps(chunk_metric_data)
    to_send_data_dict["agentType"] = get_agent_type_from_mode(mode)

    to_send_data_json = json.dumps(to_send_data_dict)
    logger.debug("TotalData: " + str(len(bytearray(to_send_data_json))))
    logger.debug(to_send_data_json)

    if cli_config_vars['testing']:
        return

    # send the data
    post_url = urlparse.urljoin(if_config_vars['ifURL'], get_api_from_mode(mode))
    send_request(post_url, "POST", json.loads(to_send_data_json), if_config_vars['ifProxies'],
                 'Could not send request to IF',
                 str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - send_data_time))


def send_request(url, mode="GET", data={}, proxies={}, failure_message='Failure!', success_message='Success!'):
    """ posts a request to the given url """
    # determine if getting or get (default)
    req = requests.get
    if mode.upper() == "POST":
        req = requests.post

    for _ in xrange(ATTEMPTS):
        try:
            if len(proxies) == 0:
                response = req(url, data=data)
            else:
                response = req(url, data=data, proxies=proxies)
            if response.status_code == httplib.OK:
                logger.info(success_message)
                return response
            else:
                logger.warn(failure_message)
                logger.debug("Response Code: " + str(response.status_code) + "\nTEXT: " + str(response.text))
        # handle various exceptions
        except requests.exceptions.Timeout:
            logger.exception(
                "Timed out. Reattempting...")
            continue
        except requests.exceptions.TooManyRedirects:
            logger.exception(
                "Too many redirects.")
            break
        except requests.exceptions.RequestException as e:
            logger.exception(
                "Exception " + str(e))
            break

    logger.error(
        "Failed! Gave up after %d attempts.", ATTEMPTS)
    return -1


def get_agent_type_from_mode(mode):
    if 'METRIC' in mode.upper():
        if 'REPLAY' in mode.upper():
            return 'MetricFileReplay'
        else:
            return 'CUSTOM'
    elif 'REPLAY' in mode.upper():
        return 'LogFileReplay'
    else:
        return 'LogStreaming'


def get_api_from_mode(mode):
    # incident uses a different API endpoint
    if 'INCIDENT' in mode.upper():
        return 'incidentdatareceive'
    else:
        return 'customprojectrawdata'


def initialize_api_post_data():
    to_send_data_dict = dict()
    to_send_data_dict["licenseKey"] = if_config_vars['licenseKey']
    to_send_data_dict["projectName"] = if_config_vars['projectName']
    to_send_data_dict["userName"] = if_config_vars['userName']
    to_send_data_dict["samplingInterval"] = str(int(if_config_vars['samplingInterval']) * 60)
    to_send_data_dict["instanceName"] = socket.gethostname().partition(".")[0]
    return to_send_data_dict


if __name__ == "__main__":
    # declare a few vars
    SPACES = re.compile(r"\s+")
    SLASHES = re.compile(r"\/+")
    UNDERSCORE = re.compile(r"\_+")
    NON_ALNUM = re.compile(r"[^a-zA-Z0-9]")
    ATTEMPTS = 3

    # get config
    cli_config_vars = get_cli_config_vars()
    logger = set_logger_config(cli_config_vars['logLevel'])
    if_config_vars = get_if_config_vars()
    agent_config_vars = get_agent_config_vars()
    print_summary_info()

    # start data processing
    track = dict()
    initialize_data_gathering()

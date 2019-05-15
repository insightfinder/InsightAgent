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
import urlparse
import httplib
import requests

'''
This script gathers data to send to Insightfinder
'''


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for index in xrange(0, len(l), n):
        yield l[index:index + n]


def chunk_map(data, SIZE=50):
    """Yield successive n-sized chunks from l."""
    it = iter(data)
    for i in xrange(0, len(data), SIZE):
        yield {k: data[k] for k in islice(it, SIZE)}


def normalize_key(metric_key):
    """
    Take a single metric key string and return the same string with spaces, slashes and
    non-alphanumeric characters subbed out.
    """
    metric_key = SPACES.sub("_", metric_key)
    metric_key = SLASHES.sub("-", metric_key)
    metric_key = NON_ALNUM.sub("", metric_key)
    return metric_key


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


def send_data(chunk_metric_data):
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = dict()
    to_send_data_dict["metricData"] = json.dumps(chunk_metric_data)
    to_send_data_dict["licenseKey"] = agent_config_vars['licenseKey']
    to_send_data_dict["projectName"] = agent_config_vars['projectName']
    to_send_data_dict["userName"] = agent_config_vars['userName']
    to_send_data_dict["instanceName"] = socket.gethostname().partition(".")[0]
    to_send_data_dict["samplingInterval"] = str(int(agent_config_vars['samplingInterval']) * 60)
    to_send_data_dict["agentType"] = "custom"

    to_send_data_json = json.dumps(to_send_data_dict)
    logger.debug("TotalData: " + str(len(bytearray(to_send_data_json))))

    # send the data
    post_url = urlparse.urljoin(agent_config_vars['ifURL'], "customprojectrawdata")
    post_request(post_url, json.loads(to_send_data_json), agent_config_vars['ifProxies'],
                 str(len(bytearray(to_send_data_json))) + " bytes of data are reported.", '')
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - send_data_time))


def post_request(url, data, proxies, success_message, failure_message):
    for _ in xrange(ATTEMPTS):
        try:
            if len(proxies) == 0:
                response = requests.post(url, data=data)
            else:
                response = requests.post(url, data=data, proxies=proxies)
            if response.status_code == httplib.OK:
                # default success message
                if success_message == '':
                    success_message = 'Successfully posted to ' + url
                logger.info(success_message)
            else:
                # default failure message
                if failure_message == '':
                    failure_message = 'Failed to post to ' + url
                logger.warn(failure_message)
                logger.debug("Response Code: " + str(response.status_code) + "\nTEXT: " + str(response.text))
            return response
        # handle various expections
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


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-c", "--chunkLines",
                      action="store", dest="chunkLines", help="Timestamps per chunk for historical data.")
    parser.add_option("-l", "--logLevel",
                      action="store", dest="logLevel", help="Change log verbosity(WARNING: 0, INFO: 1, DEBUG: 2)")
    (options, args) = parser.parse_args()

    params = {}
    if options.chunkLines is None:
        params['chunkLines'] = 50
    else:
        params['chunkLines'] = int(options.chunkLines)
    params['logLevel'] = logging.INFO
    if options.logLevel == '0':
        params['logLevel'] = logging.WARNING
    elif options.logLevel == '1':
        params['logLevel'] = logging.INFO
    elif options.logLevel >= '2':
        params['logLevel'] = logging.DEBUG

    return params


def get_agent_config_vars():
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            user_name = config_parser.get('insightfinder', 'user_name')
            license_key = config_parser.get('insightfinder', 'license_key')
            project_name = config_parser.get('insightfinder', 'project_name')
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            if_url = config_parser.get('insightfinder', 'url')
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

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
            "ifURL": if_url,
            "ifProxies": if_proxies
        }

        return config_vars
    else:
        logger.error(
            "Agent not correctly configured. Check config file.")
        sys.exit(1)
# end template


def get_zipkin_config():
    """Read and parse config.ini"""
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            zipkin_url = config_parser.get('zipkin', 'url')
            zipkin_services_filter = config_parser.get('zipkin', 'services_filter')
            zipkin_span_filter = config_parser.get('zipkin', 'span_filter')
            zipkin_http_proxy = config_parser.get('zipkin', 'zipkin_http_proxy')
            zipkin_https_proxy = config_parser.get('zipkin', 'zipkin_https_proxy')
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        if len(zipkin_url) == 0:
            logger.warning(
                "Agent not correctly configured (Zipkin URL). Check config file.")
            exit()

        # set IF proxies
        zipkin_proxies = dict()
        if len(zipkin_http_proxy) > 0:
            zipkin_proxies['http'] = zipkin_http_proxy
        if len(zipkin_https_proxy) > 0:
            zipkin_proxies['https'] = zipkin_https_proxy

        zipkin_config = {
            "url": zipkin_url,
            "services_filter": zipkin_services_filter,
            "span_filter": zipkin_span_filter,
            "proxies": zipkin_proxies
        }

        return zipkin_config
    else:
        logger.warning("No config file found. Exiting...")
        exit()


def zipkin_get_api(api, data={}):
    url = urlparse.urljoin(zipkin_config_vars['url'], api)
    if len(zipkin_config_vars['proxies']) != 0:
        response = requests.get(url, data=data, proxies=zipkin_config_vars['proxies'])
    else:
        response = requests.get(url, data=data)
    if response.status_code == httplib.OK:
        return json.loads(response.text)
    else:
        logger.warning('Could not reach out to Zipkin APIs')
        logger.debug("Response Code: " + str(response.status_code) + "\nTEXT: " + str(response.text))


def zipkin_get_services():
    """ returns an array of available services """
    services = zipkin_get_api('/api/v2/services')
    return list(filter(lambda service: service in zipkin_config_vars['services_filter'], services))


def zipkin_get_spans(service):
    """ returns an array of available spans for a service """
    spans = zipkin_get_api('/api/v2/spans', { 'serviceName': service })
    return list(filter(lambda span: span in zipkin_config_vars['span_filter'], spans))


def zipkin_get_traces():
    logger.debug('fetching traces')
    data = {
        'lookback': int(agent_config_vars['samplingInterval']) * 60 * 1000 * 1000,
        'limit': parameters['chunkLines']
    }
    return zipkin_get_api('/api/v2/traces', data)


def filter_zipkin_span(service_name, span_name):
    """ determine if this span should be excluded """
    if len(zipkin_config_vars['services_filter']) != 0 and service_name not in zipkin_config_vars['services_filter']:
        return True

    if len(zipkin_config_vars['span_filter']) != 0 and span_name not in zipkin_config_vars['span_filter']:
        return True

    return False


def make_instance_name(endpoint):
    if 'ipv4' in endpoint:
        return endpoint['ipv4'] + ' (' + endpoint['serviceName'] + ')'
    else:
        return endpoint['serviceName']


def prepare_log_entry(timestamp, instance, span):
    log_entry = dict()
    log_entry['eventId'] = timestamp
    log_entry['tag'] = instance
    log_entry['data'] = span
    track['current_row'].append(log_entry)
    track['line_count'] += 1
    return


def reset_track():
    """ reset the track global for the next chunk """
    track['current_row'] = []
    track['line_count'] = 0
    track['start_time'] = time.time()


def gather_zipkin_traces():
    """ get traces from the last <samplingInterval> minutes """
    reset_track()
    track['chunk_count'] = 0
    traces = zipkin_get_traces()
    for trace in traces:
        for span in trace:
            process_zipkin_span(span)

    # last chunk
    if len(track['current_row']) > 0:
        send_zipkin_data_log()

    logger.debug("Total chunks created: " + str(track['chunk_count']))


def process_zipkin_span(span):
    endpoint = span['localEndpoint']
    service = endpoint['serviceName']
    name = span['name']
    if filter_zipkin_span(service, name):
        return

    timestamp = int(span['timestamp']) / 1000
    instance = make_instance_name(endpoint)

    prepare_log_entry(timestamp, instance, span)
    if track['line_count'] >= parameters['chunkLines']:
        send_zipkin_data_log()

    return


def send_zipkin_data_log():
    """ wrapper to send zipkin log data """
    logger.debug("--- Chunk creation time: %s seconds ---" % (time.time() - track['start_time']))
    send_data(track['current_row'])
    track['chunk_count'] += 1
    reset_track()


if __name__ == "__main__":
    SPACES = re.compile(r"\s+")
    SLASHES = re.compile(r"\/+")
    NON_ALNUM = re.compile(r"[^a-zA-Z_\-0-9\.]")
    ATTEMPTS = 3

    parameters = get_parameters()
    log_level = parameters['logLevel']
    logger = set_logger_config(log_level)
    agent_config_vars = get_agent_config_vars()
    # end template

    zipkin_config_vars = get_zipkin_config()
    track = dict()
    gather_zipkin_traces()

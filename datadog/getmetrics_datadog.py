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

import datadog
import requests

'''
This script gathers metric data from opentsdb and use http api to send to Insightfinder
'''


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-c", "--chunkLines",
                      action="store", dest="chunkLines", help="Timestamps per chunk for historical data.")
    parser.add_option("-l", "--logLevel",
                      action="store", dest="logLevel", help="Change log verbosity(WARNING: 0, INFO: 1, DEBUG: 2)")
    (options, args) = parser.parse_args()

    params = {}
    if options.serverUrl is None:
        params['serverUrl'] = 'https://app.insightfinder.com'
    else:
        params['serverUrl'] = options.serverUrl
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
            all_metrics = []
            filter_hosts = []

            if len(config_parser.get('insightfinder', 'all_metrics')) != 0:
                all_metrics = config_parser.get('insightfinder', 'all_metrics').split(",")
            else:
                temp_metrics = get_metric_list_from_file()
                if temp_metrics is not None and len(temp_metrics) != 0:
                    all_metrics = temp_metrics
                else:
                    all_metrics = ['system.cpu.user', 'system.cpu.idle', 'system.cpu.system', 'system.disk.used',
                                   'system.disk.free', 'system.mem.pct_usable', 'system.mem.total',
                                   'system.mem.used', 'system.net.bytes_rcvd', 'system.net.bytes_sent',
                                   'system.swap.used', 'system.net.packets_in.error', 'system.net.packets_out.error']
            if len(config_parser.get('insightfinder', 'filter_hosts')) != 0:
                filter_hosts = config_parser.get('insightfinder', 'filter_hosts').split(",")
            else:
                filter_hosts = get_host_list_from_file()
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
            host_chunk_size = int(config_parser.get('insightfinder', 'host_chunk_size'))
            metric_chunk_size = int(config_parser.get('insightfinder', 'metric_chunk_size'))
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        if len(user_name) == 0:
            logger.warning(
                "Agent not correctly configured(user_name). Check config file.")
            sys.exit(1)
        if len(license_key) == 0:
            logger.warning(
                "Agent not correctly configured(license_key). Check config file.")
            sys.exit(1)
        if len(project_name) == 0:
            logger.warning(
                "Agent not correctly configured(project_name). Check config file.")
            sys.exit(1)

        config_vars = {
            "userName": user_name,
            "licenseKey": license_key,
            "projectName": project_name,
            "allMetrics": all_metrics,
            "filterHosts": filter_hosts,
            "samplingInterval": sampling_interval,
            "hostChunkSize": host_chunk_size,
            "metricChunkSize": metric_chunk_size,
            "httpProxy": if_http_proxy,
            "httpsProxy": if_https_proxy
        }

        return config_vars
    else:
        logger.error(
            "Agent not correctly configured. Check config file.")
        sys.exit(1)


def get_datadog_config():
    """Read and parse DataDog config from config.ini"""
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            datadog_app_key = config_parser.get('datadog', 'app_key')
            datadog_api_key = config_parser.get('datadog', 'api_key')
            datadog_http_proxy = config_parser.get('datadog', 'datadog_http_proxy')
            datadog_https_proxy = config_parser.get('datadog', 'datadog_https_proxy')
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        if len(datadog_app_key) == 0:
            logger.warning(
                "Agent not correctly configured(APP KEY). Check config file.")
            exit()
        if len(datadog_api_key) == 0:
            logger.warning(
                "Agent not correctly configured(API KEY). Check config file.")
            exit()

        datadog_config = {
            "DATADOG_APP_KEY": datadog_app_key,
            "DATADOG_API_KEY": datadog_api_key,
            "httpProxy": datadog_http_proxy,
            "httpsProxy": datadog_https_proxy
        }
    else:
        logger.warning("No config file found. Exiting...")
        exit()

    return datadog_config


def get_metric_list_from_file():
    """Get available metric list from File"""
    metric_list = set()
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "metrics.txt"))):
        with open(os.path.abspath(os.path.join(__file__, os.pardir, "metrics.txt")), 'r') as f:
            for line in f:
                if line not in ['\n', '\r\n']:
                    metric_list.add(line.replace('\n', ''))
            logger.debug("Get metric list from file: " + str(metric_list))
    return list(metric_list)


def get_host_list_from_file():
    """Get available host list from File"""
    metric_list = set()
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "hosts.txt"))):
        with open(os.path.abspath(os.path.join(__file__, os.pardir, "hosts.txt")), 'r') as f:
            for line in f:
                if line not in ['\n', '\r\n']:
                    metric_list.add(line.replace('\n', ''))
            logger.debug("Get host list from file: " + str(metric_list))
    return list(metric_list)


def get_metric_list():
    """Get available metric list from Datadog API"""
    metric_list = []
    from_time = int(time.time()) - 60 * 60 * 24 * 1
    result = datadog.api.Metric.list(from_time)
    if 'metrics' in result.keys() and len(result['metrics']) != 0:
        metric_list = list(result['metrics'])
    return metric_list


def get_host_list():
    """Get available host list from Datadog API"""
    hosts_list = []
    host_totals = datadog.api.Hosts.totals()
    total_hosts = 0
    if 'total_active' in host_totals.keys():
        total_hosts = int(host_totals['total_active'])
    if total_hosts > 100:
        for index in range(0, total_hosts + 1, 100):
            result = datadog.api.Hosts.search(start=index)
            if 'host_list' in result.keys() and len(result['host_list']) != 0:
                for host_meta in result['host_list']:
                    hosts_list.append(host_meta["name"])
    else:
        result = datadog.api.Hosts.search()
        if 'host_list' in result.keys() and len(result['host_list']) != 0:
            for host_meta in result['host_list']:
                hosts_list.append(host_meta["name"])
    return hosts_list


def get_metric_data(metric_list, host_list, start_time, end_time, collected_data_map):
    """Get metric data from Datadog API"""

    def format_data_entry(json_data_entry):
        metric_name = json_data_entry.get('metric')
        logger.debug("json_data_entry is: " + str(json_data_entry))
        host_name_arr = str(json_data_entry.get('scope'))
        logger.debug("host_name_arr is: " + host_name_arr)
        host_name_arr = host_name_arr.split(":")
        logger.debug("host_name_arr length is: " + str(len(host_name_arr)))
        if len(host_name_arr) > 0:
            logger.debug("host_name_arr[1] is: " + str(host_name_arr[1]))
        if len(host_name_arr) == 2:
            #host_name = host_name_arr[0]
            host_name = host_name_arr[1]
        else:
            host_name = "unknown_host"
        datapoints = json_data_entry.get('pointlist', [])
        header_field = make_safe_metric_key(metric_name) + "[" + make_safe_metric_key(host_name) + "]"
        for each_point in datapoints:
            if len(each_point) < 2 or each_point[1] is None:
                continue
            metric_value = each_point[1]
            epoch = int(each_point[0])
            if epoch in collected_data_map:
                timestamp_value_map = collected_data_map[epoch]
            else:
                timestamp_value_map = {}

            timestamp_value_map[header_field] = str(metric_value)
            collected_data_map[epoch] = timestamp_value_map

    # Set one metric multiple host
    # for metric in all_metrics_list:
    query = ""
    for host_name in host_list:
        for each_metric in metric_list:
            #query += each_metric + '{*}by{' + host_name + '},'
            query += each_metric + '{host:' + host_name + '},'
    query = query[:-1]

    datadog_metrics_result = datadog.api.Metric.query(start=start_time, end=end_time, query=query)

    status = datadog_metrics_result.get('status', 'error')

    if status == 'ok' and datadog_metrics_result['series']:
        # format metric and save to collected_data_map
        map(lambda d: format_data_entry(d), datadog_metrics_result['series'])


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
    post_url = parameters['serverUrl'] + "/customprojectrawdata"
    for _ in xrange(ATTEMPTS):
        try:
            if len(if_proxies) == 0:
                response = requests.post(post_url, data=json.loads(to_send_data_json))
            else:
                response = requests.post(post_url, data=json.loads(to_send_data_json), proxies=if_proxies)
            if response.status_code == 200:
                logger.info(str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
                logger.debug("--- Send data time: %s seconds ---" % (time.time() - send_data_time))
            else:
                logger.info("Failed to send data.")
            return
        except requests.exceptions.Timeout:
            logger.exception(
                "Timed out while flushing to InsightFinder. Reattempting...")
            continue
        except requests.exceptions.TooManyRedirects:
            logger.exception(
                "Too many redirects while flushing to InsightFinder.")
            break
        except requests.exceptions.RequestException as e:
            logger.exception(
                "Exception while flushing to InsightFinder.")
            break

    logger.error(
        "Failed to flush to InsightFinder! Gave up after %d attempts.", ATTEMPTS)


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for index in xrange(0, len(l), n):
        yield l[index:index + n]


def chunk_map(data, SIZE=50):
    """Yield successive n-sized chunks from l."""
    it = iter(data)
    for i in xrange(0, len(data), SIZE):
        yield {k: data[k] for k in islice(it, SIZE)}


def make_safe_metric_key(metric):
    metric = LEFT_BRACE.sub('(', metric)
    metric = RIGHT_BRACE.sub(')', metric)
    metric = PERIOD.sub('/', metric)
    return metric


def normalize_key(metric_key):
    """
    Take a single metric key string and return the same string with spaces, slashes and
    non-alphanumeric characters subbed out.
    """
    metric_key = SPACES.sub("_", metric_key)
    metric_key = SLASHES.sub(".", metric_key)
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


if __name__ == "__main__":
    GROUPING_START = 15000
    GROUPING_END = 20000
    SPACES = re.compile(r"\s+")
    SLASHES = re.compile(r"\/+")
    NON_ALNUM = re.compile(r"[^a-zA-Z_\-0-9\.]")
    LEFT_BRACE = re.compile(r"\[")
    RIGHT_BRACE = re.compile(r"\]")
    PERIOD = re.compile(r"\.")
    ATTEMPTS = 3

    parameters = get_parameters()
    log_level = parameters['logLevel']
    logger = set_logger_config(log_level)
    data_dir = 'data'
    agent_config_vars = get_agent_config_vars()
    if_proxies = dict()
    if len(agent_config_vars['httpProxy']) != 0:
        if_proxies['http'] = agent_config_vars['httpProxy']
    if len(agent_config_vars['httpsProxy']) != 0:
        if_proxies['https'] = agent_config_vars['httpsProxy']

    # get agent configuration details
    datadog_config = get_datadog_config()
    datadog_proxies = dict()
    if len(datadog_config['httpProxy']) != 0:
        datadog_proxies['http'] = datadog_config['httpProxy']
    if len(datadog_config['httpsProxy']) != 0:
        datadog_proxies['https'] = datadog_config['httpsProxy']
    if len(datadog_proxies) != 0:
        datadog_api = datadog.initialize(api_key=datadog_config['DATADOG_API_KEY'],
                                         app_key=datadog_config['DATADOG_APP_KEY'],
                                         proxies=datadog_proxies)
    else:
        datadog_api = datadog.initialize(api_key=datadog_config['DATADOG_API_KEY'],
                                         app_key=datadog_config['DATADOG_APP_KEY'])

    time_list = []
    # get data by cron
    data_end_ts = int(time.time())
    interval_in_secs = int(agent_config_vars['samplingInterval']) * 60
    data_start_ts = data_end_ts - interval_in_secs
    time_list = [(data_start_ts, data_end_ts)]
    try:
        raw_data_map = collections.OrderedDict()
        metric_data = []
        chunk_number = 0

        # get hosts list
        all_host_list = agent_config_vars['filterHosts']
        if len(all_host_list) == 0:
            all_host_list = get_host_list()

        # generate normalization ids if metrics are from API(config list empty)
        all_metrics_list = agent_config_vars['allMetrics']
        if len(all_metrics_list) == 0:
            all_metrics_list = get_metric_list()

        for data_start_ts, data_end_ts in time_list:
            logger.debug("Getting data from datadog for range: {}-{}".format(data_start_ts, data_end_ts))
            retry_metric_list = []
            retry_host_list = []

            for sub_metric_list in chunks(all_metrics_list, agent_config_vars['metricChunkSize']):
                for sub_host_list in chunks(all_host_list, agent_config_vars['hostChunkSize']):
                    # get metric data from datadog every SAMPLING_INTERVAL
                    try:
                        get_metric_data(sub_metric_list, sub_host_list, data_start_ts, data_end_ts, raw_data_map)
                    except Exception as e:
                        retry_host_list.append(sub_host_list)
                        retry_metric_list.append(sub_metric_list)
                        logger.debug("Error while fetching metrics from DataDog. " + str(sub_host_list))

            # retry for failed hosts
            for sub_metric_list in retry_metric_list:
                for sub_host_list in retry_host_list:
                    # get metric data from datadog every SAMPLING_INTERVAL with 3 retry attempts
                    for _ in xrange(ATTEMPTS):
                        try:
                            get_metric_data(sub_metric_list, sub_host_list, data_start_ts, data_end_ts, raw_data_map)
                            break
                        except Exception as e:
                            logger.exception(
                                "Error while fetching metrics from DataDog. Reattempting...\n Hosts: " + str(
                                    sub_host_list))
                            logger.exception(e)

        if len(raw_data_map) == 0:
            logger.error("No data for metrics received from datadog.")
            sys.exit()
        for raw_data_map_chunk in chunk_map(raw_data_map, parameters['chunkLines']):
            min_timestamp = sys.maxsize
            max_timestamp = -sys.maxsize
            for timestamp in raw_data_map_chunk.keys():
                value_map = raw_data_map_chunk[timestamp]
                value_map['timestamp'] = str(timestamp)
                metric_data.append(value_map)
                min_timestamp = min(min_timestamp, timestamp)
                max_timestamp = max(max_timestamp, timestamp)
            if len(metric_data) != 0:
                chunk_number += 1
                logger.debug("Sending Chunk Number: " + str(chunk_number))
                logger.info("Sending from datadog for range: {}-{}".format(min_timestamp, max_timestamp))
                send_data(metric_data)
                metric_data = []

    except Exception as e:
        logger.error("Error sending metric data to InsightFinder.")
        logger.error(e)

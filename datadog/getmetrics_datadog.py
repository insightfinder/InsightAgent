#!/usr/bin/env python
import ConfigParser
import collections
import json
import logging
import os
import random
import re
import socket
import sys
import time
from optparse import OptionParser

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


def get_agent_config_vars(normalization_ids_map):
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            user_name = config_parser.get('insightfinder', 'user_name')
            license_key = config_parser.get('insightfinder', 'license_key')
            project_name = config_parser.get('insightfinder', 'project_name')
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            all_metrics = []
            if len(config_parser.get('insightfinder', 'all_metrics')) != 0:
                all_metrics = config_parser.get('insightfinder', 'all_metrics').split(",")
            normalization_ids = config_parser.get('insightfinder', 'normalization_id').split(",")
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

        if len(normalization_ids[0]) != 0:
            for index in range(len(all_metrics)):
                metric = all_metrics[index]
                normalization_id = int(normalization_ids[index])
                if normalization_id > 1000:
                    logger.error("Please config the normalization_id between 0 to 1000.")
                    sys.exit(1)
                normalization_ids_map[metric] = GROUPING_START + normalization_id
        if len(normalization_ids[0]) == 0:
            count = 1
            for index in range(len(all_metrics)):
                metric = all_metrics[index]
                normalization_ids_map[metric] = GROUPING_START + count
                count += 1

        config_vars = {
            "userName": user_name,
            "licenseKey": license_key,
            "projectName": project_name,
            "allMetrics": all_metrics,
            "samplingInterval": sampling_interval
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
            "DATADOG_API_KEY": datadog_api_key
        }
    else:
        logger.warning("No config file found. Exiting...")
        exit()

    return datadog_config


def save_grouping(metric_grouping):
    """
    Saves the grouping data to grouping.json
    Parameters:
        - `grouping_map` : metric_name-grouping_id dict
    :return: None
    """
    with open('grouping.json', 'w+') as f:
        f.write(json.dumps(metric_grouping))


def load_grouping():
    """
    Loads the grouping data from grouping.json
    :return: grouping JSON string
    """
    if os.path.isfile('grouping.json'):
        logger.debug("Grouping file exists. Loading..")
        with open('grouping.json', 'r+') as f:
            try:
                grouping_json = json.loads(f.read())
            except ValueError:
                grouping_json = json.loads("{}")
                logger.debug("Error parsing grouping.json.")
    else:
        grouping_json = json.loads("{}")
    return grouping_json


def get_grouping_id(metric_key, metric_grouping):
    """
    Get grouping id for a metric key
    Parameters:
    - `metric_key` : metric key str to get group id.
    - `metric_grouping` : metric_key-grouping id map
    """
    for index in range(3):
        grouping_candidate = random.randint(GROUPING_START, GROUPING_END)
        if metric_key in metric_grouping:
            grouping_id = int(metric_grouping[metric_key])
            return grouping_id
        else:
            grouping_id = grouping_candidate
            metric_grouping[metric_key] = grouping_id
            return grouping_id
    return GROUPING_START


def get_metric_list(config):
    """Get available metric list from Datadog API"""
    metric_list = []
    from_time = int(time.time()) - 60 * 60 * 24 * 1
    result = datadog.api.Metric.list(from_time)
    if 'metrics' in result.keys() and len(result['metrics']) != 0:
        metric_list = list(result['metrics'])
    return metric_list


def get_metric_data(config, metric_list, metric_grouping, start_time, end_time, collected_data_map):
    """Get metric data from Datadog API"""

    def format_data_entry(json_data_entry):
        metric_name = json_data_entry.get('metric')
        host_name = json_data_entry.get('scope') or 'unknown_host'
        datapoints = json_data_entry.get('pointlist', [])
        header_field = normalize_key(metric_name) + "[" + host_name + "]:" + str(
            get_grouping_id(metric_name, metric_grouping))
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

    # for metric in all_metrics_list:
    query = ""
    for each_metric in metric_list:
        query += each_metric + '{*}by{host},'
    query = query[:-1]
    datadog_metrics_result = datadog.api.Metric.query(start=start_time, end=end_time, query=query)
    print(json.dumps(datadog_metrics_result))

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
    to_send_data_dict["samplingInterval"] = str(int(reporting_config_vars['reporting_interval'] * 60))
    to_send_data_dict["agentType"] = "custom"

    to_send_data_json = json.dumps(to_send_data_dict)
    logger.debug("TotalData: " + str(len(bytearray(to_send_data_json))))

    # send the data
    post_url = parameters['serverUrl'] + "/customprojectrawdata"
    response = requests.post(post_url, data=json.loads(to_send_data_json))
    if response.status_code == 200:
        logger.info(str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
    else:
        logger.info("Failed to send data.")
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - send_data_time))


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for index in xrange(0, len(l), n):
        yield l[index:index + n]


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


if __name__ == "__main__":
    GROUPING_START = 15000
    GROUPING_END = 20000
    METRIC_CHUNKS = 50
    SPACES = re.compile(r"\s+")
    SLASHES = re.compile(r"\/+")
    NON_ALNUM = re.compile(r"[^a-zA-Z_\-0-9\.]")

    normalization_ids_map = dict()
    parameters = get_parameters()
    log_level = parameters['logLevel']
    logger = set_logger_config(log_level)
    data_dir = 'data'
    agent_config_vars = get_agent_config_vars(normalization_ids_map)
    grouping_map = load_grouping()

    # get agent configuration details
    datadog_config = get_datadog_config()
    datadog_api = datadog.initialize(api_key=datadog_config['DATADOG_API_KEY'],
                                     app_key=datadog_config['DATADOG_APP_KEY'])

    time_list = []
    # get data by cron
    data_end_ts = int(time.time())
    interval_in_secs = int(agent_config_vars['reportingInterval'] * 60)
    data_start_ts = data_end_ts - interval_in_secs
    time_list = [(data_start_ts, data_end_ts)]
    try:
        raw_data_map = collections.OrderedDict()
        metric_data = []
        chunk_number = 0

        # get metric list
        all_metrics_list = agent_config_vars['allMetrics']
        if len(all_metrics_list) == 0:
            all_metrics_list = get_metric_list(datadog_config)
            if len(normalization_ids_map) == 0:
                count = 1
                for index in range(len(all_metrics_list)):
                    metric = all_metrics_list[index]
                    normalization_ids_map[metric] = GROUPING_START + count
                    count += 1

        for data_start_ts, data_end_ts in time_list:
            logger.debug("Getting data from datadog for range: {}-{}".format(data_start_ts, data_end_ts))
            chunked_metric_list = chunks(all_metrics_list, METRIC_CHUNKS)
            for sub_list in chunked_metric_list:
                # get metric data from datadog every SAMPLING_INTERVAL
                get_metric_data(datadog_config, sub_list, grouping_map, data_start_ts, data_end_ts, raw_data_map)
                if len(raw_data_map) == 0:
                    logger.error("No data for metrics received from datadog.")
                    sys.exit()
            if len(raw_data_map) >= parameters['chunkLines']:
                min_timestamp = sys.maxsize
                max_timestamp = -sys.maxsize
                for timestamp in raw_data_map.keys():
                    value_map = raw_data_map[timestamp]
                    value_map['timestamp'] = str(timestamp)
                    metric_data.append(value_map)
                    min_timestamp = min(min_timestamp, timestamp)
                    max_timestamp = max(max_timestamp, timestamp)
                chunk_number += 1
                logger.debug("Sending Chunk Number: " + str(chunk_number))
                logger.info("Sending from datadog for range: {}-{}".format(min_timestamp, max_timestamp))
                send_data(metric_data)
                metric_data = []
                raw_data_map = collections.OrderedDict()

        # send final chunk
        min_timestamp = sys.maxsize
        max_timestamp = -sys.maxsize
        for timestamp in raw_data_map.keys():
            value_map = raw_data_map[timestamp]
            value_map['timestamp'] = str(timestamp)
            metric_data.append(value_map)
            min_timestamp = min(min_timestamp, timestamp)
            max_timestamp = max(max_timestamp, timestamp)
        if len(metric_data) != 0:
            chunk_number += 1
            logger.debug("Sending Final Chunk: " + str(chunk_number))
            logger.info("Sending from datadog for range: {}-{}".format(min_timestamp, max_timestamp))
            send_data(metric_data)
        save_grouping(grouping_map)

    except Exception as e:
        logger.error("Error sending metric data to InsightFinder.")
        logger.error(e)

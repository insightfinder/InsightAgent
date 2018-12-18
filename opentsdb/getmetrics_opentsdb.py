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
from datetime import datetime
from optparse import OptionParser

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
    parser.add_option("-m", "--mode",
                      action="store", dest="mode", help="Data sending mode(streaming/historical)")
    parser.add_option("-s", "--startDate",
                      action="store", dest="startDate", help="Historical data start date")
    parser.add_option("-e", "--endDate",
                      action="store", dest="endDate", help="Historical data end date")
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
    if options.mode is None or options.mode != "historical":
        params['mode'] = "streaming"
    else:
        params['mode'] = "historical"
    if options.startDate is None or options.mode == "streaming":
        params['startDate'] = ""
    else:
        params['startDate'] = options.startDate
    if options.endDate is None or options.mode == "streaming":
        params['endDate'] = ""
    else:
        params['endDate'] = options.endDate
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
            "projectName": project_name
        }

        return config_vars
    else:
        logger.error(
            "Agent not correctly configured. Check config file.")
        sys.exit(1)


def get_reporting_config_vars():
    reporting_config = {}
    with open(os.path.abspath(os.path.join(__file__, os.pardir, os.pardir, "reporting_config.json")), 'r') as f:
        config = json.load(f)
    reporting_interval_string = config['reporting_interval']
    if reporting_interval_string[-1:] == 's':
        reporting_interval = float(config['reporting_interval'][:-1])
        reporting_config['reporting_interval'] = float(reporting_interval / 60.0)
    else:
        reporting_config['reporting_interval'] = int(config['reporting_interval'])
        reporting_config['keep_file_days'] = int(config['keep_file_days'])
        reporting_config['prev_endtime'] = config['prev_endtime']
        reporting_config['deltaFields'] = config['delta_fields']

    reporting_config['keep_file_days'] = int(config['keep_file_days'])
    reporting_config['prev_endtime'] = config['prev_endtime']
    reporting_config['deltaFields'] = config['delta_fields']
    return reporting_config


def get_opentsdb_config():
    """Read and parse Open TSDB config from config.ini"""
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            opentsdb_url = config_parser.get('opentsdb', 'opentsdb_server_url')
            opentsdb_token = config_parser.get('opentsdb', 'token')
            opentsdb_metrics = config_parser.get('opentsdb', 'metrics')
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        if len(opentsdb_url) == 0:
            logger.warning(
                "Agent not correctly configured(OPENTSDB_URL). Check config file. Using \"127.0.0.1:4242\" as default.")
            opentsdb_url = "http://127.0.0.1:4242"
        if len(opentsdb_metrics) != 0:
            opentsdb_metrics = opentsdb_metrics.split(",")
        else:
            opentsdb_metrics = []

        opentsdb_config = {
            "OPENTSDB_URL": opentsdb_url,
            "OPENTSDB_METRICS": opentsdb_metrics,
            "OPENTSDB_TOKEN": opentsdb_token
        }
    else:
        logger.warning("No config file found. Using defaults.")
        opentsdb_config = {
            "OPENTSDB_URL": "http://127.0.0.1:4242",
            "OPENTSDB_METRICS": "",
            "OPENTSDB_TOKEN": ""
        }

    return opentsdb_config


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
    """Get available metric list from Open TSDB API"""
    metric_list = []
    url = config["OPENTSDB_URL"] + "/api/suggest?type=metrics&q="
    response = requests.get(url)
    if response.status_code == 200:
        metric_list = response.json()
        logger.debug("Get metric list from opentsdb: " + str(metric_list))
    return metric_list


def get_metric_data(config, metric_list, metric_grouping, start_time, end_time, collected_data_map):
    """Get metric data from Open TSDB API"""

    def format_data_entry(json_data_entry):
        metric_name = json_data_entry.get('metric')
        host_name = json_data_entry.get('tags', {}).get('host') or 'unknownHost'
        dps = json_data_entry.get('dps', {})
        metric_value = None
        header_field = normalize_key(metric_name) + "[" + host_name + "]:" + str(
            get_grouping_id(metric_name, metric_grouping))
        mtime = 0
        for stime, val in dps.items():
            if int(stime) > mtime:
                metric_value = val
                mtime = int(stime)

        epoch = mtime * 1000

        if epoch in collected_data_map:
            timestamp_value_map = collected_data_map[epoch]
        else:
            timestamp_value_map = {}

        timestamp_value_map[header_field] = str(metric_value)
        collected_data_map[epoch] = timestamp_value_map

    json_data = {
        "token": config['OPENTSDB_TOKEN'],
        "start": start_time,
        "end": end_time,
        "queries": map(lambda m: {
            "aggregator": "avg",
            "downsample": "1m-avg",
            "metric": m.encode('ascii')
        }, metric_list)
    }

    url = config["OPENTSDB_URL"] + "/api/query"
    response = requests.post(url, data=json.dumps(json_data))
    if response.status_code == 200:
        rawdata_list = response.json()
        logger.debug("Get metric data from opentsdb: " + str(len(rawdata_list)))

        # format metric and save to collected_data_map
        map(lambda d: format_data_entry(d), rawdata_list)


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

    parameters = get_parameters()
    log_level = parameters['logLevel']
    logger = set_logger_config(log_level)
    data_dir = 'data'
    agent_config_vars = get_agent_config_vars()
    reporting_config_vars = get_reporting_config_vars()
    grouping_map = load_grouping()

    # get agent configuration details
    agent_config = get_opentsdb_config()

    time_list = []
    if parameters['mode'] == 'streaming':
        # get data by cron
        data_end_ts = int(time.time())
        interval_in_secs = int(reporting_config_vars['reporting_interval'] * 60)
        data_start_ts = data_end_ts - interval_in_secs
        time_list = [(data_start_ts, data_end_ts)]
    else:
        # get data from history date
        start_day = parameters['startDate']
        end_day = parameters['endDate']
        start_day_obj = datetime.strptime(start_day, "%Y-%m-%d")
        start_ts = int(time.mktime(start_day_obj.timetuple()))
        end_day_obj = datetime.strptime(end_day, "%Y-%m-%d")
        end_ts = int(time.mktime(end_day_obj.timetuple()))
        if start_ts >= end_ts:
            logger.error(
                "Agent not correctly configured(historical start date and end date). Check parameters")
            sys.exit(1)
        timeInterval = (end_ts - start_ts) / 60
        time_list = [(start_ts + i * 60, start_ts + (i + 1) * 60) for i in range(timeInterval)]
    try:
        raw_data_map = collections.OrderedDict()
        metric_data = []
        chunk_number = 0

        # get metric list
        all_metrics_list = agent_config['OPENTSDB_METRICS']
        if len(all_metrics_list) == 0:
            all_metrics_list = get_metric_list(agent_config)

        for data_start_ts, data_end_ts in time_list:
            logger.debug("Getting data from OpenTSDB for range: {}-{}".format(data_start_ts, data_end_ts))
            chunked_metric_list = chunks(all_metrics_list, METRIC_CHUNKS)
            for sub_list in chunked_metric_list:
                # get metric data from opentsdb every SAMPLING_INTERVAL
                get_metric_data(agent_config, sub_list, grouping_map, data_start_ts, data_end_ts, raw_data_map)
                if len(raw_data_map) == 0:
                    logger.error("No data for metrics received from OpenTSDB.")
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
                logger.info("Sending from OpenTSDB for range: {}-{}".format(min_timestamp, max_timestamp))
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
            logger.info("Sending from OpenTSDB for range: {}-{}".format(min_timestamp, max_timestamp))
            send_data(metric_data)
        save_grouping(grouping_map)

    except Exception as e:
        logger.error("Error sending metric data to InsightFinder.")
        logger.error(e)

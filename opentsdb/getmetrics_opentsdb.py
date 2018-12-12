#!/usr/bin/env python
import ConfigParser
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
this script gathers metric info from opentsdb and use http api to send to server
'''


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-c", "--chunkSize",
                      action="store", dest="chunkSize", help="Metrics per chunk")
    (options, args) = parser.parse_args()

    params = {}
    if options.homepath is None:
        params['homepath'] = os.getcwd()
    else:
        params['homepath'] = options.homepath
    if options.serverUrl is None:
        params['serverUrl'] = 'https://app.insightfinder.com'
    else:
        params['serverUrl'] = options.serverUrl
    if options.chunkSize is None:
        params['chunkSize'] = 50
    else:
        params['chunkSize'] = int(options.chunkSize)
    return params


def get_agent_config_vars():
    config_vars = {}
    with open(os.path.join(parameters['homepath'], ".agent.bashrc"), 'r') as configFile:
        file_content = configFile.readlines()
        if len(file_content) < 6:
            logger.error("Agent not correctly configured. Check .agent.bashrc file.")
            sys.exit(1)
        # get license key
        license_key_line = file_content[0].split(" ")
        if len(license_key_line) != 2:
            logger.error("Agent not correctly configured(license key). Check .agent.bashrc file.")
            sys.exit(1)
        config_vars['licenseKey'] = license_key_line[1].split("=")[1].strip()
        # get project name
        project_name_line = file_content[1].split(" ")
        if len(project_name_line) != 2:
            logger.error("Agent not correctly configured(project name). Check .agent.bashrc file.")
            sys.exit(1)
        config_vars['projectName'] = project_name_line[1].split("=")[1].strip()
        # get username
        user_name_line = file_content[2].split(" ")
        if len(user_name_line) != 2:
            logger.error("Agent not correctly configured(username). Check .agent.bashrc file.")
            sys.exit(1)
        config_vars['userName'] = user_name_line[1].split("=")[1].strip()
        # get sampling interval
        sampling_interval_line = file_content[4].split(" ")
        if len(sampling_interval_line) != 2:
            logger.error("Agent not correctly configured(sampling interval). Check .agent.bashrc file.")
            sys.exit(1)
        config_vars['samplingInterval'] = sampling_interval_line[1].split("=")[1].strip()
    return config_vars


def get_reporting_config_vars():
    reporting_config = {}
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), 'r') as f:
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
    """Read and parse Open TSDB config from config.txt"""
    opentsdb_config = {}
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))

        try:
            opentsdb_url = config_parser.get('opentsdb', 'OPENTSDB_URL')
            opentsdb_token = config_parser.get('opentsdb', 'OPENTSDB_TOKEN')
            opentsdb_mode = config_parser.get('opentsdb', 'OPENTSDB_MODE')
            opentsdb_metrics = config_parser.get('opentsdb', 'OPENTSDB_METRICS').split(",")
            opentsdb_history_start_date = config_parser.get('opentsdb', 'OPENTSDB_HIS_START_DAY')
            opentsdb_history_end_date = config_parser.get('opentsdb', 'OPENTSDB_HIS_END_DAY')
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        if len(opentsdb_url) == 0:
            logger.warning(
                "Agent not correctly configured(OPENTSDB_URL). Check config file. Using \"127.0.0.1:4242\" as default.")
            opentsdb_url = "http://127.0.0.1:4242"

        if len(opentsdb_mode) == 0:
            logger.warning(
                "Agent not correctly configured(OPENTSDB_MODE). Check config file. Using \"streaming\" as default.")
            opentsdb_mode = "streaming"
        else:
            if not (opentsdb_mode == 'streaming' or opentsdb_mode == 'historical'):
                logger.warning(
                    "Agent not correctly configured(OPENTSDB_MODE). Check config file. Using \"streaming\" as default.")
                opentsdb_mode = "streaming"

        if opentsdb_mode == 'historical':
            if len(opentsdb_history_start_date) == 0:
                logger.error(
                    "Agent not correctly configured(OPENTSDB_HIS_START_DAY). Check config file.")
                sys.exit(1)
            if len(opentsdb_history_end_date) == 0:
                logger.error(
                    "Agent not correctly configured(OPENTSDB_HIS_END_DAY). Check config file.")
                sys.exit(1)

        opentsdb_config = {
            "OPENTSDB_URL": opentsdb_url,
            "OPENTSDB_METRICS": opentsdb_metrics,
            "OPENTSDB_TOKEN": opentsdb_token,
            "OPENTSDB_MODE": opentsdb_mode,
            "OPENTSDB_HIS_START_DAY": opentsdb_history_start_date,
            "OPENTSDB_HIS_END_DAY": opentsdb_history_end_date
        }
    else:
        logger.warning("No config file found. Using defaults.")
        opentsdb_config = {
            "OPENTSDB_URL": "http://127.0.0.1:4242",
            "OPENTSDB_METRICS": "",
            "OPENTSDB_TOKEN": "",
            "OPENTSDB_MODE": "streaming",
            "OPENTSDB_HIS_START_DAY": "",
            "OPENTSDB_HIS_END_DAY": ""
        }

    return opentsdb_config


def save_grouping(grouping_map):
    """
    Saves the grouping data to grouping.json
    :return: None
    """
    with open('grouping.json', 'w+') as f:
        f.write(json.dumps(grouping_map))


def load_grouping():
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


def get_grouping_id(metric_key, grouping_map):
    """
    Get grouping id for a metric key
    Parameters:
    - `metric_key` : metric key str to get group id.
    - `temp_id` : proposed group id integer
    """
    for i in range(3):
        grouping_candidate = random.randint(GROUPING_START, GROUPING_END)
        if metric_key in grouping_map:
            grouping_id = int(grouping_map[metric_key])
            return grouping_id
        else:
            grouping_id = grouping_candidate
            grouping_map[metric_key] = grouping_id
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


def get_metric_list_from_file(config, filePath):
    """Get available metric list from File"""
    metric_list = set()
    try:
        with open(filePath, 'r') as f:
            for line in f:
                m = re.search(r'(?P<metric>\d\.\d\..+):', line)
                if m:
                    metric = m.groupdict().get('metric')
                    metric_list.add(metric)
                    logger.debug("Get metric list from file: " + str(metric_list))
    except:
        logger.error("No metrics.txt file found.")
    return list(metric_list)


def get_metric_data(config, metric_list, grouping_map, startTime, endTime):
    """Get metric data from Open TSDB API"""

    def full_data(d):
        value_map = {}
        metric_name = d.get('metric')
        host_name = d.get('tags', {}).get('host') or 'unknownApplication'
        dps = d.get('dps', {})
        metric_value = None
        header_field = metric_name + "[" + host_name + "]:" + str(get_grouping_id(metric_name, grouping_map))
        mtime = 0
        for stime, val in dps.items():
            if int(stime) > mtime:
                metric_value = val
                mtime = int(stime)

        value_map[header_field] = str(metric_value)
        value_map['timestamp'] = str(mtime * 1000)

        return value_map

    opentsdb_metric_list = []
    json_data = {
        "token": config['OPENTSDB_TOKEN'],
        "start": startTime,
        "end": endTime,
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

        # completion metric data
        opentsdb_metric_list = map(lambda d: full_data(d), rawdata_list)

    return opentsdb_metric_list


def send_data(metric_data):
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = {}
    to_send_data_dict["metric_data"] = json.dumps(metric_data)
    to_send_data_dict["licenseKey"] = agent_config_ars['licenseKey']
    to_send_data_dict["projectName"] = agent_config_ars['projectName']
    to_send_data_dict["userName"] = agent_config_ars['userName']
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
    for i in xrange(0, len(l), n):
        yield l[i:i + n]


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

    log_level = logging.INFO
    logger = set_logger_config(log_level)
    data_dir = 'data'
    parameters = get_parameters()
    agent_config_ars = get_agent_config_vars()
    reporting_config_vars = get_reporting_config_vars()
    grouping_map = load_grouping()

    # get agent configuration details
    agent_config = get_opentsdb_config()

    time_list = []
    if agent_config['OPENTSDB_MODE'] == 'streaming':
        # get data by cron
        data_end_ts = int(time.time())
        interval_in_secs = int(reporting_config_vars['reporting_interval'] * 60)
        data_start_ts = data_end_ts - interval_in_secs
        time_list = [(data_start_ts, data_end_ts)]
    else:
        # get data from history date
        start_day = agent_config['OPENTSDB_HIS_START_DAY']
        end_day = agent_config['OPENTSDB_HIS_END_DAY']
        start_day_obj = datetime.strptime(start_day, "%Y-%m-%d")
        start_ts = int(time.mktime(start_day_obj.timetuple()))
        end_day_obj = datetime.strptime(end_day, "%Y-%m-%d")
        end_ts = int(time.mktime(end_day_obj.timetuple()))
        timeInterval = (end_ts - start_ts) / 60
        time_list = [(start_ts + i * 60, start_ts + (i + 1) * 60) for i in range(timeInterval)]

    for data_start_ts, data_end_ts in time_list:
        try:
            logger.debug("Start to send metric data: {}-{}".format(data_start_ts, data_end_ts))
            # get metric list from opentsdb
            # metric_list = get_metric_list(agent_config)
            # all_metrics_list = get_metric_list_from_file(agent_config, agent_config['OPENTSDB_METRIC_FILEPATH'])
            if len(all_metrics_list) == 0:
                all_metrics_list = get_metric_list(agent_config)
                logger.error("No metrics to get data for.")
                # sys.exit()

            chunked_metric_list = chunks(all_metrics_list, parameters['chunkSize'])
            for sub_list in chunked_metric_list:
                # get metric data from opentsdb every SAMPLING_INTERVAL
                metric_data_list = get_metric_data(agent_config, sub_list, grouping_map, data_start_ts,
                                                   data_end_ts)
                if len(metric_data_list) == 0:
                    logger.error("No data for metrics received from Open TSDB.")
                    sys.exit()
                # send metric data to insightfinder
                send_data(metric_data_list)
                save_grouping(grouping_map)

            logger.info("Send metric date for {} - {}.".format(data_start_ts, data_end_ts))
        except Exception as e:
            logger.error("Error send metric data to insightfinder: {}-{}".format(data_start_ts, data_end_ts))
            logger.error(e)

#!/usr/bin/env python
import time
import sys
from optparse import OptionParser
import ConfigParser
import os
import requests
import json
import logging
import socket
import random
import re
from datetime import datetime

'''
this script gathers system info from prometheus and use http api to send to server
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
            logger.error(
                "Agent not correctly configured. Check .agent.bashrc file.")
            sys.exit(1)
        # get license key
        license_key_line = file_content[0].split(" ")
        if len(license_key_line) != 2:
            logger.error(
                "Agent not correctly configured(license key). Check .agent.bashrc file.")
            sys.exit(1)
        config_vars['licenseKey'] = license_key_line[1].split("=")[1].strip()
        # get project name
        project_name_line = file_content[1].split(" ")
        if len(project_name_line) != 2:
            logger.error(
                "Agent not correctly configured(project name). Check .agent.bashrc file.")
            sys.exit(1)
        config_vars['projectName'] = project_name_line[1].split("=")[1].strip()
        # get username
        user_name_line = file_content[2].split(" ")
        if len(user_name_line) != 2:
            logger.error(
                "Agent not correctly configured(username). Check .agent.bashrc file.")
            sys.exit(1)
        config_vars['userName'] = user_name_line[1].split("=")[1].strip()
        # get sampling interval
        sampling_interval_line = file_content[4].split(" ")
        if len(sampling_interval_line) != 2:
            logger.error(
                "Agent not correctly configured(sampling interval). Check .agent.bashrc file.")
            sys.exit(1)
        config_vars['samplingInterval'] = sampling_interval_line[1].split("=")[
            1].strip()
    return config_vars


def get_reporting_config_vars():
    config_data = {}
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), 'r') as f:
        config = json.load(f)
    reporting_interval_string = config['reporting_interval']
    if reporting_interval_string[-1:] == 's':
        reporting_interval = float(config['reporting_interval'][:-1])
        config_data['reporting_interval'] = float(
            reporting_interval / 60.0)
    else:
        config_data['reporting_interval'] = int(
            config['reporting_interval'])
        config_data['keep_file_days'] = int(config['keep_file_days'])
        config_data['prev_endtime'] = config['prev_endtime']
        config_data['deltaFields'] = config['delta_fields']

    config_data['keep_file_days'] = int(config['keep_file_days'])
    config_data['prev_endtime'] = config['prev_endtime']
    config_data['deltaFields'] = config['delta_fields']
    return config_data


def get_prometheus_config(params):
    """Read and parse Prometheus config from config.txt"""
    prometheus_config = {}
    if os.path.exists(os.path.join(params['homepath'], "prometheus/config.txt")):
        cp = ConfigParser.SafeConfigParser()
        cp.read(os.path.join(params['homepath'], "prometheus/config.txt"))
        prometheus_config = {
            "GROUPING_START": cp.getint('prometheus', 'GROUPING_START'),
            "GROUPING_END": cp.getint('prometheus', 'GROUPING_END'),
            "PROMETHEUS_URL": cp.get('prometheus', 'PROMETHEUS_URL'),
            "PROMETHEUS_METRICS_FILE": cp.get('prometheus', 'PROMETHEUS_METRICS_FILE'),
        }
    return prometheus_config


def save_grouping(grouping):
    """
    Saves the grouping data to grouping.json
    :return: None
    """
    with open('grouping.json', 'w+') as f:
        f.write(json.dumps(grouping))


def load_grouping():
    if os.path.isfile('grouping.json'):
        logger.debug("Grouping file exists. Loading..")
        with open('grouping.json', 'r+') as f:
            try:
                grouping = json.loads(f.read())
            except ValueError:
                grouping = json.loads("{}")
                logger.debug("Error parsing grouping.json.")
    else:
        grouping = json.loads("{}")
    return grouping


def get_grouping_id(config, metric_key, grouping):
    """
    Get grouping id for a metric key
    Parameters:
    - `metric_key` : metric key str to get group id.
    - `temp_id` : proposed group id integer
    """
    for i in range(3):
        grouping_candidate = random.randint(
            config["GROUPING_START"], config["GROUPING_END"])
        if metric_key in grouping:
            grouping_id = int(grouping[metric_key])
            return grouping_id
        else:
            grouping_id = grouping_candidate
            grouping[metric_key] = grouping_id
            return grouping_id
    return config["GROUPING_START"]


def get_metric_list_from_file(config):
    """Get available metric list from File"""
    metric_list = set()
    with open(config['PROMETHEUS_METRICS_FILE'], 'r') as f:
        for line in f:
            if line:
                metric_list.add(line.replace('\n', ''))
        logger.debug("Get metric list from file: " + str(metric_list))
    return list(metric_list)


def get_metric_data(config, metric_list, grouping, start_time, end_time):
    """Get metric data from Prometheus API"""
    metric_datas = []

    for m in metric_list:
        params = {
            "query": m,
            "start": start_time,
            "end": end_time,
            "step": '60s',
        }
        url = config["PROMETHEUS_URL"] + "/api/v1/query_range"
        response = requests.get(url, params=params)
        if response.status_code == 200:
            res = response.json()
            if res and res.get('status') == 'success':
                datas = res.get('data', {}).get('result', [])
                metric_datas.extend(datas)

    # change data to raw data api format:
    value_map = {
        'timestamp': str(end_time)
    }
    filter_hosts = ['localhost']
    metric_data_all = []
    for log in metric_datas:
        host = log.get('metric').get('instance', '').split(':')[0]

        if host in filter_hosts:
            continue

        metric_name = log.get('metric').get('__name__')
        host_name = host
        metric_value = None
        header_field = metric_name + \
            "[" + host_name + "]:" + \
            str(get_grouping_id(config, metric_name, grouping))
        mtime = 0
        for stime, val in log.get('values', []):
            if int(stime) > mtime:
                metric_value = val
                mtime = int(stime)

        value_map[header_field] = str(metric_value)
        metric_data_all.append(value_map)

    logger.info('metric_data_all:' + str(metric_data_all))
    return metric_data_all


def send_data(metric_data):
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = {}
    to_send_data_dict["metric_data"] = json.dumps(metric_data)
    to_send_data_dict["licenseKey"] = agent_config_vars['licenseKey']
    to_send_data_dict["projectName"] = agent_config_vars['projectName']
    to_send_data_dict["userName"] = agent_config_vars['userName']
    to_send_data_dict["instanceName"] = socket.gethostname().partition(".")[0]
    to_send_data_dict["samplingInterval"] = str(
        int(reporting_config_vars['reporting_interval'] * 60))
    to_send_data_dict["agentType"] = "custom"

    to_send_data_json = json.dumps(to_send_data_dict)
    logger.debug("TotalData: " +
                 str(len(bytearray(to_send_data_json))) + " Bytes")

    # send the data
    post_url = parameters['serverUrl'] + "/customprojectrawdata"
    response = requests.post(post_url, data=json.loads(to_send_data_json))
    if response.status_code == 200:
        logger.info(str(len(bytearray(to_send_data_json))) +
                    " bytes of data are reported.")
    else:
        logger.info("Failed to send data.")
    logger.debug("--- Send data time: %s seconds ---" %
                 (time.time() - send_data_time))


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in xrange(0, len(l), n):
        yield l[i:i + n]


def set_logger_config(log_level):
    """Set up logging according to the defined log level"""
    # Get the root logger
    logger_obj = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger_obj.setLevel(log_level)
    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
    logging_handler_out.addFilter(LessThanFilter(logging.WARNING))
    logger_obj.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logger_obj.addHandler(logging_handler_err)
    return logger_obj


class LessThanFilter(logging.Filter):
    def __init__(self, exclusive_maximum, name=""):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        # non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0


if __name__ == "__main__":
    logger = set_logger_config(logging.INFO)
    parameters = get_parameters()
    agent_config_vars = get_agent_config_vars()
    reporting_config_vars = get_reporting_config_vars()
    grouping_map = load_grouping()

    # get agent configuration details
    agent_config = get_prometheus_config(parameters)
    for item in agent_config.values():
        if not item:
            logger.error("config error, check prometheus/config.txt")
            sys.exit("config error, check config.txt")

    dataEndTimestamp = int(time.time())
    intervalInSecs = int(reporting_config_vars['reporting_interval'] * 60)
    dataStartTimestamp = dataEndTimestamp - intervalInSecs

    try:
        logger.debug(
            "Start to send metric data: {}-{}".format(dataStartTimestamp, dataEndTimestamp))
        # get metric list from prometheus
        metricListAll = get_metric_list_from_file(agent_config)
        if len(metricListAll) == 0:
            logger.error("No metrics to get data for.")
            sys.exit()

        chunked_metric_list = chunks(metricListAll, parameters['chunkSize'])
        for sub_list in chunked_metric_list:
            # get metric data from prometheus every SAMPLING_INTERVAL
            metric_data_list = get_metric_data(
                agent_config, sub_list, grouping_map, dataStartTimestamp, dataEndTimestamp)
            if len(metric_data_list) == 0:
                logger.error("No data for metrics received from Prometheus.")
                sys.exit()
            # send metric data to insightfinder
            send_data(metric_data_list)
            save_grouping(grouping_map)

    except Exception as e:
        logger.error(
            "Error send metric data to insightfinder: {}-{}".format(dataStartTimestamp, dataEndTimestamp))
        logger.error(e)

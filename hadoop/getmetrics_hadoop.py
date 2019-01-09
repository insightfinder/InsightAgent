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

import requests

'''
This script gathers metric data from hadoop and use http api to send to Insightfinder
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


def get_hadoop_config():
    """Read and parse Hadoop config from config.ini"""
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            name_nodes = config_parser.get('hadoop', 'name_nodes')
            data_nodes = config_parser.get('hadoop', 'data_nodes')
            yarn_nodes = config_parser.get('hadoop', 'yarn_nodes')
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        if len(name_nodes) != 0:
            name_nodes = name_nodes.split(",")
        else:
            name_nodes = ["http://127.0.0.1:50070"]
        if len(data_nodes) != 0:
            data_nodes = data_nodes.split(",")
        else:
            data_nodes = ["http://127.0.0.1:50075"]
        if len(yarn_nodes) != 0:
            yarn_nodes = yarn_nodes.split(",")
        else:
            yarn_nodes = ["http://127.0.0.1:8088"]

        hadoop_config = {
            "NAME_NODES": name_nodes,
            "DATA_NODES": data_nodes,
            "YARN_NODES": yarn_nodes
        }
    else:
        logger.warning("No config file found. Using defaults.")
        hadoop_config = {
            "NAME_NODES": ["http://127.0.0.1:50070"],
            "DATA_NODES": ["http://127.0.0.1:50075"],
            "YARN_NODES": ["http://127.0.0.1:8088"]
        }

    return hadoop_config


def get_grouping_id(metric_key, node_type):
    """
    Get grouping id for a metric key
    Parameters:
    - `metric_key` : metric key str to get group id.
    - `node_type` : node type the metric key is from
    """
    name_node_start = 23000
    data_node_start = 24000
    yarn_node_start = 25000
    grouping_candidate = 0
    if node_type == "NameNode":
        grouping_candidate = filter_metrics_map[node_type].index(metric_key) + name_node_start + 1
    if node_type == "DataNode":
        grouping_candidate = filter_metrics_map[node_type].index(metric_key) + data_node_start + 1
    if node_type == "YarnNode":
        grouping_candidate = filter_metrics_map[node_type].index(metric_key) + yarn_node_start + 1
    return grouping_candidate


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
    to_send_data_dict["insightAgentType"] = "collectd"
    # to_send_data_dict["onlyNewMetricTable"] = "true"

    to_send_data_json = json.dumps(to_send_data_dict)
    logger.debug("TotalData: " + str(len(bytearray(to_send_data_json))))
    logger.debug("Data: " + str(to_send_data_json))

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


def filter_metrics_json(all_jmx_metrics, nodetype, node_url):
    filtered_jmx_metrics = {}
    if "beans" in all_jmx_metrics:
        all_beans = all_jmx_metrics["beans"]
        for current_jmx_bean in all_beans:
            if "tag.Hostname" in current_jmx_bean:
                host_name = current_jmx_bean["tag.Hostname"]
            else:
                continue

            host_name_parts = host_name.split(".")
            host_name = host_name_parts[0]
            if "name" in current_jmx_bean:
                bean_name = current_jmx_bean["name"]
                if nodetype == "NameNode" or nodetype == "DataNode":
                    service = "Hadoop:service=" + nodetype
                elif nodetype == "YarnNode":
                    service = "Hadoop:service=ResourceManager"
                if service in bean_name:
                    filtered_jmx_bean = {}
                    for metric_key in current_jmx_bean:
                        if "_percentile" in metric_key or "-inf" in metric_key or "_table" in metric_key:
                            continue
                        if metric_key not in filter_metrics_map[nodetype]:
                            continue
                        filtered_jmx_bean[metric_key] = current_jmx_bean[metric_key]
                        filtered_jmx_bean["hostname"] = host_name
                        filtered_jmx_metrics[bean_name] = filtered_jmx_bean
    return filtered_jmx_metrics


def format_jmx_metrics_json(filtered_metrics_json, node_type, config, collected_data_map):
    epoch_time = int(round(time.time() * 1000))
    for curr_jmx_bean in filtered_metrics_json:
        host_name = filtered_metrics_json[curr_jmx_bean]["hostname"]
        # create subsystem name
        sub_system_name = ""
        sub_system_parts = str(curr_jmx_bean).split(",")
        service = sub_system_parts[0].split("=")[1].replace("[^A-Za-z0-9 ]", "")
        if len(sub_system_parts) >= 2 and len(sub_system_parts[1]) != 0:
            modeler_name = sub_system_parts[1].split("=")[1].replace("[^A-Za-z0-9 ]", "")
            sub_system_name += modeler_name
        if len(sub_system_parts) >= 3 and len(sub_system_parts[2]) != 0:
            sub_system_name += "."
            modeler_sub_name = sub_system_parts[2].split("=")[1].replace("[^A-Za-z0-9 ]", "")
            sub_system_name += modeler_sub_name

        if epoch_time in collected_data_map:
            value_map = collected_data_map[epoch_time]
        else:
            value_map = {}

        for metric_key in filtered_metrics_json[curr_jmx_bean]:
            if "hostname" in metric_key:
                continue
            metric_name = sub_system_name + "-" + metric_key
            header_field = metric_name + "[" + node_type + "_" + host_name + "]:" + str(
                get_grouping_id(metric_key, node_type))
            metric_value = filtered_metrics_json[curr_jmx_bean][metric_key]
            value_map[header_field] = str(metric_value)

        collected_data_map[epoch_time] = value_map


def get_node_metrics(node_type, node_url, config, collected_data_map):
    """Get metric data from Open TSDB API"""
    jmx_url = node_url + "/jmx"
    response = requests.get(jmx_url)
    try:
        response_json = json.loads(response.content)
        filtered_metrics = filter_metrics_json(response_json, node_type, node_url)
        format_jmx_metrics_json(filtered_metrics, node_type, config, collected_data_map)
        if len(filtered_metrics) == 0:
            logger.warning("No metrics to send for url: " + node_url)
        logger.debug(response_json)
    except ValueError:
        logger.error("Unable to parse result from " + node_url)


if __name__ == "__main__":
    GROUPING_START = 20000
    GROUPING_END = 25000
    METRIC_CHUNKS = 50
    SPACES = re.compile(r"\s+")
    SLASHES = re.compile(r"\/+")
    NON_ALNUM = re.compile(r"[^a-zA-Z_\-0-9\.]")

    # Map to filter metrics according to node type
    filter_metrics_map = {}
    filter_metrics_map["NameNode"] = ["BlockReceivedAndDeletedAvgTime", "RollEditLogAvgTime", "GetBlockLocationsNumOps",
                                      "AddBlockOps", "BlockReceivedAndDeletedOps", "BlockReceivedAndDeletedNumOps",
                                      "RollEditLogNumOps", "BlockReportAvgTime", "BlockReportAvgTime",
                                      "GetBlockLocationsAvgTime",
                                      "BlockOpsQueued", "BlockOpsBatched", "BlockReportNumOps", "BlockReportNumOps",
                                      "GetBlockLocations", "StorageBlockReportOps", "AddBlockAvgTime", "AddBlockNumOps"]
    filter_metrics_map["DataNode"] = ["RamDiskBlocksLazyPersistWindowMsAvgTime", "RamDiskBlocksWriteFallback",
                                      "ReplaceBlockOpNumOps", "RamDiskBlocksWrite", "RamDiskBlocksLazyPersisted",
                                      "BlocksRemoved", "BlocksCached", "BlockReportsAvgTime", "BlockChecksumOpAvgTime",
                                      "IncrementalBlockReportsNumOps", "RamDiskBlocksEvictionWindowMsAvgTime",
                                      "RamDiskBlocksLazyPersistWindowMsNumOps", "WriteBlockOpAvgTime",
                                      "ReadBlockOpNumOps", "RamDiskBlocksReadHits", "IncrementalBlockReportsAvgTime",
                                      "RamDiskBlocksEvictedWithoutRead", "BlocksUncached", "BlockVerificationFailures",
                                      "CopyBlockOpAvgTime", "BlockReportsNumOps", "RamDiskBlocksEvictionWindowMsNumOps",
                                      "BlocksRead", "BlocksReplicated", "BlocksVerified", "BlocksGetLocalPathInfo",
                                      "RamDiskBlocksDeletedBeforeLazyPersisted", "BlockChecksumOpNumOps",
                                      "BlocksWritten", "RamDiskBlocksEvicted", "WriteBlockOpNumOps",
                                      "ReplaceBlockOpAvgTime", "ReadBlockOpAvgTime", "CopyBlockOpNumOps"]

    filter_metrics_map["YarnNode"] = ["ThreadsTerminated", "Get_mean", "Get_num_ops", "ThreadsWaiting",
                                      "readRequestCount", "ThreadsBlocked",
                                      "LogWarn", "ThreadsRunnable", "CheckAndPut_num_ops", "Put_mean", "LogInfo",
                                      "updatesBlockedTime", "ThreadsNew", "CheckAndPut_mean", "ThreadsTimedWaiting",
                                      "ProcessCallTime_num_ops", "Put_num_ops", "LogError", "LogFatal",
                                      "writeRequestCount", "ProcessCallTime_mean"]

    parameters = get_parameters()
    log_level = parameters['logLevel']
    logger = set_logger_config(log_level)
    agent_config_vars = get_agent_config_vars()
    reporting_config_vars = get_reporting_config_vars()

    # get agent configuration details
    agent_config = get_hadoop_config()
    raw_data_map = collections.OrderedDict()
    metric_data = []
    chunk_number = 0

    for key in agent_config.keys():
        if key == "NAME_NODES":
            node_type = "NameNode"
        elif key == "DATA_NODES":
            node_type = "DataNode"
        elif key == "YARN_NODES":
            node_type = "YarnNode"
        for node in agent_config[key]:
            get_node_metrics(node_type, node, agent_config, raw_data_map)

    for timestamp in raw_data_map.keys():
        value_map = raw_data_map[timestamp]
        value_map['timestamp'] = str(timestamp)
        metric_data.append(value_map)
    if len(metric_data) != 0:
        logger.info("Start sending data to InsightFinder")
        send_data(metric_data)

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
This script gathers elasticsearch data and use http api to send to Insightfinder
'''

epoch_value_map = {}


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="server_url", help="Server Url")
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-l", "--logLevel",
                      action="store", dest="logLevel", help="Change log verbosity(WARNING: 0, INFO: 1, DEBUG: 2)")
    (options, args) = parser.parse_args()

    params = {}
    params['server_url'] = 'https://app.insightfinder.com' if not options.server_url else options.server_url
    params['homepath'] = os.getcwd() if not options.homepath else options.homepath
    params['logLevel'] = logging.INFO
    if options.logLevel == '0':
        params['logLevel'] = logging.WARNING
    elif options.logLevel == '1':
        params['logLevel'] = logging.INFO
    elif options.logLevel >= '2':
        params['logLevel'] = logging.DEBUG

    return params


def get_agent_config_vars():
    config_vars = {}
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            config_vars["user_name"] = config_parser.get('insightfinder', 'user_name')
            config_vars["license_key"] = config_parser.get('insightfinder', 'license_key')
            config_vars["project_name"] = config_parser.get('insightfinder', 'project_name')
            config_vars["ssl_verification"] = config_parser.get('insightfinder', 'ssl_verify')

        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        if len(config_vars['license_key']) == 0 or len(config_vars['project_name']) == 0 or len(
                config_vars['user_name']) == 0:
            logger.error("Agent not correctly configured. Check config file.")
            sys.exit(1)

        if len(config_vars["ssl_verification"]) != 0 and (
                config_vars["ssl_verification"].lower() == 'false' or config_vars["ssl_verification"].lower() == 'f'):
            ssl_verification = False
        else:
            ssl_verification = True

        config_vars["ssl_security"] = ssl_verification

        return config_vars
    else:
        logger.error(
            "Agent not correctly configured. Check config file.")
        sys.exit(1)


def get_elastic_config():
    """Read and parse Hadoop config from config.ini"""
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            elastic_config = {"elastic_search_nodes": config_parser.get('elastic', 'elastic_search_nodes')}
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        if len(elastic_config["elastic_search_nodes"]) != 0:
            elastic_config["elastic_search_nodes"] = elastic_config["elastic_search_nodes"].replace(" ", "").split(",")

    else:
        logger.warning("No config file found. Using defaults.")
        elastic_config = {
            "elastic_search_nodes": ["http://52.90.112.179:9200"]
        }

    return elastic_config


def send_data(chunk_metric_data):
    """Sends metric data to InsightFinder backend"""
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = dict()
    to_send_data_dict["metricData"] = json.dumps(chunk_metric_data)
    to_send_data_dict["licenseKey"] = agent_config_vars['license_key']
    to_send_data_dict["projectName"] = agent_config_vars['project_name']
    to_send_data_dict["userName"] = agent_config_vars['user_name']
    to_send_data_dict["instanceName"] = socket.gethostname().partition(".")[0]
    # to_send_data_dict["samplingInterval"] = str(int(reporting_config_vars['reporting_interval'] * 60))
    to_send_data_dict["agentType"] = "custom"

    to_send_data_json = json.dumps(to_send_data_dict)
    logger.debug("TotalData: " + str(len(bytearray(to_send_data_json))))

    # send the data
    post_url = parameters['server_url'] + "/customprojectrawdata"
    print post_url
    response = requests.post(post_url, data=json.loads(to_send_data_json))
    if response.status_code == 200:
        logger.info(str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
    else:
        logger.info("Failed to send data.")
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - send_data_time))


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


def get_grouping_id(metric_key):
    elastic_node_start = 23014
    index = 0
    for key in all_metrics:
        if metric_key.endswith(key):
            return elastic_node_start + index
        index = index + 1
    return elastic_node_start


def get_previous_results():
    file_path = os.path.join(parameters['homepath'], datadir + "previous_results.json")
    if os.path.isfile(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    else:
        return {}


def handle_cluster_health_json(json_response, hostname, epoch_time, collected_data_map):
    for key in json_response:
        if key in all_metrics:
            add_metric_to_buffers(hostname, json_response, key, key, "cluster.health")
    collected_data_map[epoch_time] = epoch_value_map


def handle_accum_metric_keys(host_name, shards_json_obj, metric_name, key, node_type):
    header_field = metric_name + "[" + node_type + "_" + host_name + "]:" + str(
        get_grouping_id(metric_name))
    metric_value = shards_json_obj[key]
    if header_field in previuos_results_dict:
        old_value = long(previuos_results_dict[header_field])
        delta = metric_value - old_value
        previuos_results_dict[header_field] = metric_value
        epoch_value_map[header_field] = str(delta)
    else:
        epoch_value_map[header_field] = metric_value
        previuos_results_dict[header_field] = metric_value


def add_metric_to_buffers(host_name, shards_json_obj, metric_name, key, node_type):
    for keyMetric in all_metrics:
        if metric_name.endswith(keyMetric):
            if keyMetric in nonAccumKeys:
                header_field = metric_name + "[" + node_type + "_" + host_name + "]:" + str(
                    get_grouping_id(metric_name))
                metric_value = shards_json_obj[key]
                epoch_value_map[header_field] = str(metric_value)
            else:
                handle_accum_metric_keys(host_name, shards_json_obj, metric_name, key, node_type)
                pass


def get_primaries_and_total_and_addit_to_buffers(hostname, all_json_object, insightfinder_metric_name):
    if all_json_object["primaries"] is not None or all_json_object["total"] is not None:
        for majorKeys in all_json_object:
            temp_metric_name_root = insightfinder_metric_name
            temp_metric_name_root += "_" + majorKeys.replace("_", ".")
            primaries_json_obj = all_json_object["primaries"]
            for keyPrimaries in primaries_json_obj:
                temp_metric_name_primary = temp_metric_name_root
                temp_metric_name_primary += "_" + keyPrimaries.replace("_", ".")
                key_primaries_json_object = primaries_json_obj[keyPrimaries]
                for actualKeys in key_primaries_json_object:
                    leaf_metric_name = temp_metric_name_primary
                    leaf_metric_name += "_" + actualKeys.replace("_", ".")
                    add_metric_to_buffers(hostname, key_primaries_json_object, leaf_metric_name, actualKeys,
                                          "all.stats")


def handle_all_stats_json(metric_resp, hostname, epoch_time, collected_data_map):
    for respJsonKey in metric_resp:
        if respJsonKey == "_shards":
            shards_json_obj = metric_resp[respJsonKey]
            for key in shards_json_obj:
                if key == "successful" or key == "total":
                    insightfinder_metric_name = "shards_" + key
                    add_metric_to_buffers(hostname, shards_json_obj, insightfinder_metric_name, key, "all.stats")
        elif respJsonKey == "_all":
            all_json_object = metric_resp["_all"]
            insightfinder_metric_name = "all"
            get_primaries_and_total_and_addit_to_buffers(hostname, all_json_object, insightfinder_metric_name)
    collected_data_map[epoch_time] = epoch_value_map


def handle_nodes_local_json(matric_response, epoch_time, collected_data_map):
    for keyOuter in matric_response:
        if keyOuter == "nodes":
            nodes = matric_response[keyOuter]
            new_metric_name = "nodes"
            for key in nodes:
                host = nodes[key]["host"]
                inner_node = nodes[key]
                for jKey in inner_node:
                    if jKey == "jvm":
                        jvm_json_object = inner_node["jvm"]
                        new_metric_name += "_" + jKey.replace("_", ".")
                        for jvmkey in jvm_json_object:
                            if jvmkey == "start_time_in_millis":
                                new_metric_name += "_" + jvmkey.replace("_", ".")
                                add_metric_to_buffers(host, jvm_json_object, new_metric_name, jvmkey, "nodes.local")
                            elif jvmkey == "mem":
                                new_metric_name += "_" + jvmkey.replace("_", ".")
                                for jvmMemKeys in jvm_json_object["mem"]:
                                    new_metric_name += "_" + jvmMemKeys.replace("_", ".")
                                    add_metric_to_buffers(host, jvm_json_object["mem"], new_metric_name, jvmMemKeys,
                                                          "nodes.local")
                                    new_metric_name = new_metric_name.replace("_" + jvmMemKeys.replace("_", "."), "")
                            new_metric_name = new_metric_name.replace("_" + jvmkey.replace("_", "."), "")
                        new_metric_name = new_metric_name.replace("_" + jKey.replace("_", "."), "")
                    new_metric_name = new_metric_name.replace("_" + key.replace("_", "."), "")
    collected_data_map[epoch_time] = epoch_value_map


def get_hostname_from_url(elastic_search_node_url):
    elastic_search_node_url = elastic_search_node_url.replace("https://", "").replace("http://", "")
    elastic_search_node_url = elastic_search_node_url.split(":")[0].split("/")[0]
    return elastic_search_node_url


def get_node_metrics(elastic_search_nodes, collected_data_map):
    elastic_search_urls = ["_cluster/health", "_all/_stats#", "_nodes/_local"]
    epoch_time = int(round(time.time() * 1000))
    for elastic_search_node in elastic_search_nodes:
        for elastic_search_url in elastic_search_urls:
            if "http" not in elastic_search_node:
                elastic_search_node_url = "http://" + elastic_search_node + "/" + elastic_search_url
            else:
                elastic_search_node_url = elastic_search_node + "/" + elastic_search_url
            try:
                response = requests.get(elastic_search_node_url, verify=agent_config_vars['ssl_security'])
                response_json = json.loads(response.content)
                hostname = get_hostname_from_url(elastic_search_node_url)  # calculate hostname
                if elastic_search_url == "_cluster/health":
                    handle_cluster_health_json(response_json, hostname, epoch_time, collected_data_map)
                elif elastic_search_url == "_all/_stats#":
                    handle_all_stats_json(response_json, hostname, epoch_time, collected_data_map)
                else:
                    handle_nodes_local_json(response_json, epoch_time, collected_data_map)
            except requests.exceptions.ConnectionError:
                logger.error("Unable to connect to: " + elastic_search_node_url)
            except requests.exceptions.MissingSchema as e:
                logger.error("Missing Schema: " + str(e))
            except requests.exceptions.Timeout:
                logger.error("Timed out connecting to: " + elastic_search_node_url)
            except requests.exceptions.TooManyRedirects:
                logger.error("Too many redirects to: " + elastic_search_node_url)
            except ValueError:
                logger.error("Unable to parse result from: " + elastic_search_node_url)
            except requests.exceptions.RequestException as e:
                logger.error(str(e))


def set_previous_results(previuos_results_dict_l):
    with open(os.path.join(parameters['homepath'], datadir + "previous_results.json"), 'w') as f:
        f.write(json.dumps(previuos_results_dict_l))


if __name__ == "__main__":
    parameters = get_parameters()
    log_level = parameters['logLevel']
    logger = set_logger_config(log_level)
    agent_config_vars = get_agent_config_vars()

    elastic_search_node_start = 23013

    SPACES = re.compile(r"\s+")
    SLASHES = re.compile(r"/+")
    NON_ALNUM = re.compile(r"[^a-zA-Z_\-0-9.]")
    nonAccumKeys = {"active_shards", "unassigned_shards",
                    "shards_total",
                    "shards_successful", "primaries_get_time.in.millis", "primaries_get_missing.time.in.millis",
                    "jvm_start.time.in.millis", "jvm_mem_heap.max.in.bytes", "total_merges_total",
                    "total_search_query.total", "total_query.cache_miss.count", "primaries_search_scroll.total",
                    "primaries_search_scroll.time.in.millis", "primaries_indexing_delete.time.in.millis",
                    "primaries_search_scroll.total",
                    "primaries_search_scroll.time.in.millis", "primaries_search_query.total",
                    "primaries_search_query.time.in.millis", "primaries_search_fetch.time.in.millis",
                    "primaries_search_fetch.total", "primaries_indexing_delete.time.in.millis"}

    all_metrics = {"active_shards", "unassigned_shards", "shards_total", "shards_successful",
                   "primaries_indexing_index.time.in.millis",
                   "primaries_indexing_delete.time.in.millis", "primaries_get_time.in.millis",
                   "primaries_get_missing.time.in.millis",
                   "primaries_search_query.time.in.millis", "primaries_search_query.total",
                   "primaries_search_fetch.total",
                   "primaries_search_fetch.time.in.millis", "primaries_search_scroll.total",
                   "primaries_search_scroll.time.in.millis",
                   "primaries_merges_total", "primaries_merges_total.time.in.millis",
                   "primaries_query.cache_miss.count",
                   "total_indexing_index.time.in.millis", "total_indexing_delete.time.in.millis",
                   "total_get_time.in.millis",
                   "total_get_missing.time.in.millis", "total_search_query.time.in.millis", "total_search_query.total",
                   "total_search_fetch.total", "total_search_fetch.time.in.millis", "total_search_scroll.total",
                   "total_search_scroll.time.in.millis", "total_merges_total", "total_merges_total.time.in.millis",
                   "total_query.cache_miss.count",
                   "jvm_start.time.in.millis", "jvm_mem_heap.max.in.bytes"}

    agent_config = get_elastic_config()
    raw_data_map = collections.OrderedDict()
    metric_data = []
    datadir = 'data/'
    previuos_results_dict = get_previous_results()

    get_node_metrics(agent_config["elastic_search_nodes"], raw_data_map)

    for timestamp in raw_data_map.keys():
        value_map = raw_data_map[timestamp]
        value_map['timestamp'] = str(timestamp)
        metric_data.append(value_map)
    logger.info("metric data" + metric_data)

    set_previous_results(previuos_results_dict)
    if len(metric_data) != 0:
        logger.info("Start sending data to InsightFinder")
        send_data(metric_data)
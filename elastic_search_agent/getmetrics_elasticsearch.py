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

        if len(config_vars["ssl_verification"]) != 0 and (config_vars["ssl_verification"].lower() == 'false' or config_vars["ssl_verification"].lower() == 'f'):
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

# need to think of diff stratergy
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

epoch_value_map = {}


def handle_cluster_health_json(json_response, hostname, epoch_time, collected_data_map):
    for key in json_response:
        if key in all_metrics:
            addMetricToBuffers(hostname, json_response, key, key, "cluster_health")
    collected_data_map[epoch_time] = epoch_value_map


def handle_accum_metric_keys(host_name, shardsJsonObj, metricName, key, node_type):
    header_field = metricName + "[" + node_type + "_" + host_name + "]:" + str(
        get_grouping_id(metricName))
    metricValue = shardsJsonObj[key]
    if header_field in previuos_results_dict:
        old_value = long(previuos_results_dict[header_field])
        delta = metricValue - old_value
        previuos_results_dict[header_field] = metricValue
        epoch_value_map[header_field] = str(delta)
    else:
        epoch_value_map[header_field] = metricValue
        previuos_results_dict[header_field] = metricValue


def addMetricToBuffers(host_name, shardsJsonObj, metricName, key, node_type):
    for keyMetric in all_metrics:
        if metricName.endswith(keyMetric):
            # need to check for accumulating metrices
            if keyMetric in nonAccumKeys:
                header_field = metricName + "[" + node_type + "_" + host_name + "]:" + str(
                    get_grouping_id(metricName))
                metricValue = shardsJsonObj[key]
                epoch_value_map[header_field] = str(metricValue)
            else:
                handle_accum_metric_keys(host_name, shardsJsonObj, metricName, key, node_type)
                pass

            return


def getPrimariesAndTotalAndAddItToBuffers(hostname, allJsonObject, insightfinderMetricName):
    if allJsonObject["primaries"] is not None or allJsonObject["total"] is not None:
        for majorKeys in allJsonObject:
            tempMetricNameRoot = insightfinderMetricName
            tempMetricNameRoot += "_" + majorKeys.replace("_", ".")
            primariesJsonObj = allJsonObject["primaries"]
            for keyPrimaries in primariesJsonObj:
                tempMetricNamePrimary = tempMetricNameRoot
                tempMetricNamePrimary += "_" + keyPrimaries.replace("_", ".")
                keyPrimariesJsonObject = primariesJsonObj[keyPrimaries]
                for actualKeys in keyPrimariesJsonObject:
                    leafMetricName = tempMetricNamePrimary
                    leafMetricName += "_" + actualKeys.replace("_", ".")
                    addMetricToBuffers(hostname, keyPrimariesJsonObject, leafMetricName, actualKeys, "all_stats")


def handle_all_stats_json(metricResp, hostname, epoch_time, collected_data_map):
    for respJsonKey in metricResp:
        if respJsonKey == "_shards":
            shardsJsonObj = metricResp[respJsonKey]
            for key in shardsJsonObj:
                if key == "successful" or key == "total":
                    insightfinderMetricName = "shards_" + key
                    addMetricToBuffers(hostname, shardsJsonObj, insightfinderMetricName, key, "all_stats")
        elif respJsonKey == "_all":
            allJsonObject = metricResp["_all"]
            insightfinderMetricName = "all"
            getPrimariesAndTotalAndAddItToBuffers(hostname, allJsonObject, insightfinderMetricName)
    collected_data_map[epoch_time] = epoch_value_map


def handle_nodes_local_json( matricResponse, epoch_time, collected_data_map ):
    for keyOuter in matricResponse:
        if keyOuter == "nodes":
            nodes = matricResponse[keyOuter]
            newMetricName = "nodes"
            for key in nodes:
                host = nodes[key]["host"]
                innerNode = nodes[key]
                for jKey in innerNode:
                    if jKey == "jvm":
                        jvmJsonObject = innerNode["jvm"]
                        newMetricName += "_" + jKey.replace("_", ".")
                        for jvmkey in jvmJsonObject:
                            if jvmkey == "start_time_in_millis":
                                newMetricName += "_" + jvmkey.replace("_", ".")
                                addMetricToBuffers(host, jvmJsonObject, newMetricName, jvmkey, "nodes_local")
                            elif jvmkey == "mem":
                                newMetricName += "_" + jvmkey.replace("_", ".")
                                for jvmMemKeys in jvmJsonObject["mem"]:
                                    newMetricName += "_" + jvmMemKeys.replace("_", ".")
                                    addMetricToBuffers(host, jvmJsonObject["mem"], newMetricName, jvmMemKeys, "nodes_local")
                                    newMetricName = newMetricName.replace("_" + jvmMemKeys.replace("_","."), "")
                            newMetricName = newMetricName.replace("_" + jvmkey.replace("_", "."), "")
                        newMetricName = newMetricName.replace("_" + jKey.replace("_","."), "")
                    newMetricName = newMetricName.replace("_" + key.replace("_", "."), "")
    collected_data_map[epoch_time] = epoch_value_map


def get_hostname_from_url( elastic_search_node_url ):
    elastic_search_node_url = elastic_search_node_url.replace("https://", "").replace("http://", "")
    elastic_search_node_url = elastic_search_node_url.split(":")[0].split("/")[0]
    return elastic_search_node_url


def get_node_metrics(elastic_search_nodes, collected_data_map):
    elastic_search_urls = [ "_cluster/health",  "_all/_stats#", "_nodes/_local"]
    epoch_time = int(round(time.time() * 1000))
    for elastic_search_node in elastic_search_nodes:
        for elastic_search_url in elastic_search_urls:
            if "http" not in elastic_search_node:
                elastic_search_node_url = "https://" + elastic_search_node + "/" +elastic_search_url
            else:
                elastic_search_node_url = elastic_search_node + "/" + elastic_search_url

            try:
                response = requests.get(elastic_search_node_url, verify=agent_config_vars['ssl_security'])
                response_json = json.loads(response.content)
                # print response_json
                hostname = get_hostname_from_url(elastic_search_node_url)   # calculate hostname
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


def set_previous_results(previuos_results_dict):
    with open(os.path.join(parameters['homepath'], datadir + "previous_results.json"), 'w') as f:
        f.write(json.dumps(previuos_results_dict))


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
    print "metric data" , metric_data

    set_previous_results(previuos_results_dict)
    if len(metric_data) != 0:
        logger.info("Start sending data to InsightFinder")
        send_data(metric_data)
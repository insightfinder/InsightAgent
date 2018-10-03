#!/usr/bin/env python
import collections
import json
import logging
import os
import random
import socket
import sys
import time
from ConfigParser import SafeConfigParser
from datetime import datetime
from optparse import OptionParser

import pytz
import requests
from kafka import KafkaConsumer

'''
this script gathers metrics from kafka and send to InsightFinder
'''


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-t", "--timeout",
                      action="store", dest="timeout", help="Timeout in seconds. Default is 30")
    parser.add_option("-p", "--topic",
                      action="store", dest="topic", help="Kafka topic to read data from")
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-l", "--chunkLines",
                      action="store", dest="chunkLines", help="Max number of lines in chunk")
    (options, args) = parser.parse_args()

    parameters = {}
    if options.homepath is None:
        parameters['homepath'] = os.getcwd()
    else:
        parameters['homepath'] = options.homepath
    if options.serverUrl == None:
        parameters['serverUrl'] = 'https://app.insightfinder.com'
    else:
        parameters['serverUrl'] = options.serverUrl
    if options.topic == None:
        parameters['topic'] = 'insightfinder_csv'
    else:
        parameters['topic'] = options.topic
    if options.timeout == None:
        parameters['timeout'] = 300
    else:
        parameters['timeout'] = int(options.timeout)
    if options.chunkLines is None:
        parameters['chunkLines'] = 100
    else:
        parameters['chunkLines'] = int(options.chunkLines)

    return parameters


def save_grouping(grouping_map):
    """
    Saves the grouping data to grouping.json
    :return: None
    """
    with open('grouping.json', 'w+') as f:
        f.write(json.dumps(grouping_map))


def load_grouping():
    if (os.path.isfile('grouping.json')):
        logger.debug("Grouping file exists. Loading..")
        with open('grouping.json', 'r+') as f:
            try:
                grouping_map = json.loads(f.read())
            except ValueError:
                grouping_map = json.loads("{}")
                logger.debug("Error parsing grouping.json.")
    else:
        grouping_map = json.loads("{}")
    return grouping_map


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


def get_agent_config_vars():
    configVars = {}
    try:
        with open(os.path.join(parameters['homepath'], ".agent.bashrc"), 'r') as configFile:
            fileContent = configFile.readlines()
            if len(fileContent) < 6:
                logger.error("Agent not correctly configured. Check .agent.bashrc file.")
                sys.exit(1)
            # get license key
            licenseKeyLine = fileContent[0].split(" ")
            if len(licenseKeyLine) != 2:
                logger.error("Agent not correctly configured(license key). Check .agent.bashrc file.")
                sys.exit(1)
            configVars['licenseKey'] = licenseKeyLine[1].split("=")[1].strip()
            # get project name
            projectNameLine = fileContent[1].split(" ")
            if len(projectNameLine) != 2:
                logger.error("Agent not correctly configured(project name). Check .agent.bashrc file.")
                sys.exit(1)
            configVars['projectName'] = projectNameLine[1].split("=")[1].strip()
            # get username
            userNameLine = fileContent[2].split(" ")
            if len(userNameLine) != 2:
                logger.error("Agent not correctly configured(username). Check .agent.bashrc file.")
                sys.exit(1)
            configVars['userName'] = userNameLine[1].split("=")[1].strip()
            # get sampling interval
            samplingIntervalLine = fileContent[4].split(" ")
            if len(samplingIntervalLine) != 2:
                logger.error("Agent not correctly configured(sampling interval). Check .agent.bashrc file.")
                sys.exit(1)
            configVars['samplingInterval'] = samplingIntervalLine[1].split("=")[1].strip()
    except IOError:
        logger.error("Agent not correctly configured. Missing .agent.bashrc file.")
    return configVars


def get_reporting_config_vars():
    reportingConfigVars = {}
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), 'r') as f:
        config = json.load(f)
    reporting_interval_string = config['reporting_interval']
    if reporting_interval_string[-1:] == 's':
        reporting_interval = float(config['reporting_interval'][:-1])
        reportingConfigVars['reporting_interval'] = float(reporting_interval / 60.0)
    else:
        reportingConfigVars['reporting_interval'] = int(config['reporting_interval'])
        reportingConfigVars['keep_file_days'] = int(config['keep_file_days'])
        reportingConfigVars['prev_endtime'] = config['prev_endtime']
        reportingConfigVars['deltaFields'] = config['delta_fields']

    reportingConfigVars['keep_file_days'] = int(config['keep_file_days'])
    reportingConfigVars['prev_endtime'] = config['prev_endtime']
    reportingConfigVars['deltaFields'] = config['delta_fields']
    return reportingConfigVars


def getKafkaConfig():
    if os.path.exists(os.path.join(parameters['homepath'], "kafka", "config.ini")):
        parser = SafeConfigParser()
        parser.read(os.path.join(parameters['homepath'], "kafka", "config.ini"))
        bootstrap_servers = parser.get('kafka', 'bootstrap_servers').split(",")
        topic = parser.get('kafka', 'topic')
        filter_hosts = parser.get('kafka', 'filter_hosts').split(",")
        all_metrics = parser.get('kafka', 'all_metrics').split(",")
        if len(bootstrap_servers) == 0:
            logger.info("Using default server localhost:9092")
            bootstrap_servers = ['localhost:9092']
        if len(topic) == 0:
            print "using default topic"
            topic = 'insightfinder_metric'
        if len(filter_hosts[0]) == 0:
            filter_hosts = []
        if len(all_metrics[0]) == 0:
            all_metrics = []
    else:
        bootstrap_servers = ['localhost:9092']
        topic = 'insightfinder_metrics'
        filter_hosts = []
    return (bootstrap_servers, topic, filter_hosts, all_metrics)


def sendData(metricData):
    sendDataTime = time.time()
    # prepare data for metric streaming agent
    toSendDataDict = {}
    toSendDataDict["metricData"] = json.dumps(metricData)
    toSendDataDict["licenseKey"] = agent_config_vars['licenseKey']
    toSendDataDict["projectName"] = agent_config_vars['projectName']
    toSendDataDict["userName"] = agent_config_vars['userName']
    toSendDataDict["instanceName"] = socket.gethostname().partition(".")[0]
    toSendDataDict["samplingInterval"] = str(int(reporting_config_vars['reporting_interval'] * 60))
    toSendDataDict["agentType"] = "kafka"

    toSendDataJSON = json.dumps(toSendDataDict)
    logger.debug("TotalData: " + str(len(bytearray(toSendDataJSON))))

    # send the data
    postUrl = parameters['serverUrl'] + "/customprojectrawdata"
    response = requests.post(postUrl, data=json.loads(toSendDataJSON))
    if response.status_code == 200:
        logger.info(str(len(bytearray(toSendDataJSON))) + " bytes of data are reported.")
        # updateLastSentFiles(pcapFileList)
    else:
        logger.info("Failed to send data.")
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - sendDataTime))


def isTimeFormat(timeString, format):
    """
    Determines the validity of the input date-time string according to the given format
    Parameters:
    - `timeString` : datetime string to check validity
    - `temp_id` : datetime format to compare with
    """
    try:
        datetime.strptime(str(timeString), format)
        return True
    except ValueError:
        return False


def getTimestampForZone(dateString, timeZone, format):
    dtexif = datetime.strptime(dateString, format)
    tz = pytz.timezone(timeZone)
    tztime = tz.localize(dtexif)
    epoch = long((tztime - datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()) * 1000
    return epoch

def isReceivedAllMetrics(collectedMetrics, all_metrics):
    if len(all_metrics) == 0:
        return True
    for metric in all_metrics:
        if metric not in collectedMetrics:
            return False
    return True

def parseConsumerMessages(consumer, grouping_map, all_metrics):
    rawDataMap = collections.OrderedDict()
    metricData = []
    chunkNumber = 0
    collectedValues = 0
    collectedMetricsMap = {}
    completedRowsTimestampSet = set()


    for message in consumer:
        try:
            json_message = json.loads(message.value)
            timestamp = json_message.get('@timestamp', {})[:-5]
            host_name = json_message.get('beat', {}).get('hostname', {})
            metric_module = json_message.get('metricset', {}).get('module', {})
            metric_class = json_message.get('metricset', {}).get('name', {})
            if len(filter_hosts) != 0 and host_name not in filter_hosts:
                continue
            pattern = "%Y-%m-%dT%H:%M:%S"
            if isTimeFormat(timestamp, pattern):
                epoch = getTimestampForZone(timestamp, "GMT", pattern)

            # get previous collected values for timestamp if available
            # get previous collected metrics name for timestamp if available
            if epoch in rawDataMap:
                valueMap = rawDataMap[epoch]
                collectedMetricsSet = collectedMetricsMap[epoch]
            else:
                valueMap = {}
                collectedMetricsSet = set()
            if metric_module == "system":
                if metric_class == "cpu":
                    cpuMetricsList = ["idle", "iowait", "irq", "nice", "softirq", "steal", "system", "user"]
                    for metric in cpuMetricsList:
                        metric_value = json_message.get('system', {}).get('cpu', {}).get(metric, {}).get('pct', '')
                        metric_name = "cpu-" + metric
                        header_field = metric_name + "[" + host_name + "]:" + str(
                            get_grouping_id(metric_name, grouping_map))
                        valueMap[header_field] = str(metric_value)
                        rawDataMap[epoch] = valueMap
                        # add collected metric name
                        collectedValues += 1
                        collectedMetricsSet.add(metric_name)
                        # update the collected metrics for this timestamp
                        collectedMetricsMap[epoch] = collectedMetricsSet
                elif metric_class == "memory":
                    memoryMetricsList = ["actual", "swap"]
                    for metric in memoryMetricsList:
                        metric_value = json_message.get('system', {}).get('memory', {}).get(metric, {}).get('used',{}).get(
                            'bytes', '')
                        metric_name = "memory-" + metric
                        header_field = metric_name + "[" + host_name + "]:" + str(
                            get_grouping_id(metric_name, grouping_map))
                        valueMap[header_field] = str(metric_value)
                        rawDataMap[epoch] = valueMap
                        # add collected metric name
                        collectedValues += 1
                        collectedMetricsSet.add(metric_name)
                        # update the collected metrics for this timestamp
                        collectedMetricsMap[epoch] = collectedMetricsSet
                elif metric_class == "filesystem":
                    metric_value_bytes = json_message.get('system', {}).get('filesystem', {}).get('used', {}).get(
                        'bytes', '')
                    metric_value_pct = json_message.get('system', {}).get('filesystem', {}).get('used', {}).get(
                        'pct', '')
                    metric_name_bytes = "filesystem/used-bytes"
                    metric_name_pct = "filesystem/used-pct"
                    header_field_bytes = metric_name_bytes + "[" + host_name + "]:" + str(
                        get_grouping_id(metric_name_bytes, grouping_map))
                    header_field_pct = metric_name_pct + "[" + host_name + "]:" + str(
                        get_grouping_id(metric_name_pct, grouping_map))
                    valueMap[header_field_bytes] = str(metric_value_bytes)
                    valueMap[header_field_pct] = str(metric_value_pct)
                    rawDataMap[epoch] = valueMap
                    # add collected metric name
                    collectedValues += 1
                    collectedMetricsSet.add(metric_name_pct)
                    collectedMetricsSet.add(metric_name_bytes)
                    # update the collected metrics for this timestamp
                    collectedMetricsMap[epoch] = collectedMetricsSet

            # check whether collected all metrics basd on the config file
            if (isReceivedAllMetrics(collectedMetricsSet, all_metrics)):
                # add the completed timestamp into set
                completedRowsTimestampSet.add(epoch)
                print "All metrics collected for timestamp " + str(epoch) + " Completed rows count: " + str(len(completedRowsTimestampSet))
            
            numberOfCompletedRows = len(completedRowsTimestampSet)
            # check whether the number of completed rows is greater than 100
            if numberOfCompletedRows >= CHUNK_METRIC_VALUES:
                # go through all completed timesamp data and add to the buffer
                for timestamp in completedRowsTimestampSet:
                    # get and delete the data of the timestamp
                    valueMap = rawDataMap.pop(timestamp)
                    # remove recorded metric for the timestamp
                    collectedMetricsMap.pop(timestamp)
                    valueMap['timestamp'] = str(timestamp)
                    metricData.append(valueMap)

                chunkNumber += 1
                logger.debug("Sending Chunk Number: " + str(chunkNumber))
                sendData(metricData)
                # clean the buffer and completed row set
                metricData = []
                completedRowsTimestampSet = set()
                collectedValues = 0

        except ValueError:
            logger.error("Error parsing metric json")
            continue

    # send final chunk
    for timestamp in rawDataMap.keys():
        valueMap = rawDataMap[timestamp]
        valueMap['timestamp'] = str(timestamp)
        metricData.append(valueMap)
    if len(metricData) == 0:
        logger.info("No data remaining to send")
    else:
        chunkNumber += 1
        logger.debug("Sending Final Chunk: " + str(chunkNumber))
        sendData(metricData)


def set_logger_config():
    # Get the root logger
    logger = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger.setLevel(logging.DEBUG)
    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
    logging_handler_out.addFilter(LessThanFilter(logging.WARNING))
    logger.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logger.addHandler(logging_handler_err)
    return logger


class LessThanFilter(logging.Filter):
    def __init__(self, exclusive_maximum, name=""):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        # non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0


if __name__ == "__main__":
    CHUNK_METRIC_VALUES = 100
    GROUPING_START = 15000
    GROUPING_END = 20000
    logger = set_logger_config()
    parameters = get_parameters()
    agent_config_vars = get_agent_config_vars()
    reporting_config_vars = get_reporting_config_vars()
    grouping_map = load_grouping()

    # path to write the daily csv file
    data_directory = 'data/'
    prev_csv_header_list = "timestamp,"
    hostname = socket.gethostname().partition(".")[0]
    try:
        # Kafka consumer configuration
        (brokers, topic, filter_hosts, all_metrics) = getKafkaConfig()
        consumer = KafkaConsumer(bootstrap_servers=brokers, consumer_timeout_ms=1000 * parameters['timeout'],
                                 group_id="if_consumers")
        consumer.subscribe([topic])
        parseConsumerMessages(consumer, grouping_map, all_metrics)

        consumer.close()
        save_grouping(grouping_map)
    except KeyboardInterrupt:
        print "Interrupt from keyboard"

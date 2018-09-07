#!/usr/bin/env python
import collections
import json
import logging
import os
import random
import socket
import sys
import time
from optparse import OptionParser

import requests
from kafka import KafkaConsumer

'''
this script gathers metrics from kafka and send to InsightFinder
'''


def getParameters():
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
        parameters['timeout'] = 30
    else:
        parameters['timeout'] = int(options.timeout)

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


def getAgentConfigVars():
    configVars = {}
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
    return configVars


def getReportingConfigVars():
    reportingConfigVars = {}
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), 'r') as f:
        config = json.load(f)
    reporting_interval_string = config['reporting_interval']
    is_second_reporting = False
    if reporting_interval_string[-1:] == 's':
        is_second_reporting = True
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


def get_kafka_config():
    if os.path.exists(os.path.join(parameters['homepath'], datadir + "config.txt")):
        config_file = open(os.path.join(parameters['homepath'], datadir + "config.txt"), "r")
        host = config_file.readline()
        host = host.strip('\n\r')  # remove newline character from read line
        if len(host) == 0:
            print "using default host"
            host = 'localhost'
        port = config_file.readline()
        port = port.strip('\n\r')
        if len(port) == 0:
            print "using default port"
            port = '9092'
        topic = config_file.readline()
        topic = topic.strip('\n\r')
        if len(topic) == 0:
            print "using default topic"
            topic = 'insightfinder_csv'
    else:
        host = '127.0.0.1'
        port = '9092'
        topic = 'insightfinder_csv'
    return (host, port, topic)


def sendData(metricData):
    sendDataTime = time.time()
    # prepare data for metric streaming agent
    toSendDataDict = {}
    toSendDataDict["metricData"] = json.dumps(metricData)
    toSendDataDict["licenseKey"] = agentConfigVars['licenseKey']
    toSendDataDict["projectName"] = agentConfigVars['projectName']
    toSendDataDict["userName"] = agentConfigVars['userName']
    toSendDataDict["instanceName"] = socket.gethostname().partition(".")[0]
    toSendDataDict["samplingInterval"] = str(int(reportingConfigVars['reporting_interval'] * 60))
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


def parseConsumerMessages(consumer, grouping_map):
    rawDataMap = collections.OrderedDict()
    for message in consumer:
        json_message = json.loads(message.value)
        metric_json_array = json_message.get('content', {}).get('metrics', [])
        timestamp = json_message.get('content', {}).get('ts', 0)

        if timestamp in rawDataMap:
            valueMap = rawDataMap[timestamp]
        else:
            valueMap = {}

        # instance_name = info.get('tag', '')
        instance_name = ''
        host_name = json_message.get('agentSN', '')
        # read metrics for each instance
        for metric_json in metric_json_array:
            value = metric_json.get('v', '')
            metric_name = metric_json.get('m', None)
            if not metric_name:
                continue
            if len(instance_name) == 0:
                header_field = metric_name + "[" + host_name + "]:" + str(get_grouping_id(metric_name, grouping_map))
            else:
                header_field = metric_name + "_" + instance_name + "[" + host_name + "]:" + str(
                    get_grouping_id(metric_name, grouping_map))
            valueMap[header_field] = str(value)
            rawDataMap[timestamp] = valueMap
    return rawDataMap


def setloggerConfig():
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
    CHUNK_SIZE = 4000000
    GROUPING_START = 15000
    GROUPING_END = 20000
    logger = setloggerConfig()
    parameters = getParameters()
    agentConfigVars = getAgentConfigVars()
    reportingConfigVars = getReportingConfigVars()
    grouping_map = load_grouping()

    # path to write the daily csv file
    datadir = 'data/'
    prev_csv_header_list = "timestamp,"
    hostname = socket.gethostname().partition(".")[0]
    try:
        # Kafka consumer configuration
        (host, port, topic) = get_kafka_config()
        consumer = KafkaConsumer(bootstrap_servers=[host + ':' + port],
                                 auto_offset_reset='earliest', consumer_timeout_ms=1000 * parameters['timeout'],
                                 group_id="if_consumers")
        consumer.subscribe([topic])
        rawDataMap = parseConsumerMessages(consumer, grouping_map)

        # format the collectd data to send to insightfinder
        metricData = []
        chunkNumber = 0

        if len(rawDataMap) == 0:
            logger.info("No data to send")
            exit(1)

        for timestamp in rawDataMap.keys():
            if len(bytearray(json.dumps(metricData))) >= CHUNK_SIZE:
                chunkNumber += 1
                logger.debug("Sending Chunk Number: " + str(chunkNumber))
                sendData(metricData)
                metricData = []
            valueMap = rawDataMap[timestamp]
            valueMap['timestamp'] = str(timestamp)
            metricData.append(valueMap)

        if len(metricData) == 0:
            logger.info("No data remaining to send")
        else:
            chunkNumber += 1
            logger.debug("Sending Final Chunk: " + str(chunkNumber))
            sendData(metricData)
        consumer.close()
        save_grouping(grouping_map)
    except KeyboardInterrupt:
        print "Interrupt from keyboard"

#!/usr/bin/env python
import json
import logging
import os
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
this script gathers logs from kafka and send to InsightFinder
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
        parameters['timeout'] = 30
    else:
        parameters['timeout'] = int(options.timeout)
    if options.chunkLines is None:
        parameters['chunkLines'] = 1000
    else:
        parameters['chunkLines'] = int(options.chunkLines)

    return parameters


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


def getKafkaConfig():
    if os.path.exists(os.path.join(parameters['homepath'], "kafka", "config.ini")):
        parser = SafeConfigParser()
        parser.read(os.path.join(parameters['homepath'], "kafka", "config.ini"))
        bootstrap_servers = parser.get('kafka', 'bootstrap_servers').split(",")
        topic = parser.get('kafka', 'topic')
        filter_hosts = parser.get('kafka', 'filter_hosts').split(",")

        if len(bootstrap_servers) == 0:
            logger.info("Using default server localhost:9092")
            bootstrap_servers = ['localhost:9092']
        if len(topic) == 0:
            print "using default topic"
            topic = 'insightfinder_metric'
        if len(filter_hosts[0]) == 0:
            filter_hosts = []
    else:
        bootstrap_servers = ['localhost:9092']
        topic = 'insightfinder_metrics'
        filter_hosts = []
    return (bootstrap_servers, topic, filter_hosts)


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


def sendData(metricData):
    """ Sends parsed metric data to InsightFinder """
    sendDataTime = time.time()
    # prepare data for metric streaming agent
    toSendDataDict = {}
    toSendDataDict["metricData"] = json.dumps(metricData)
    toSendDataDict["licenseKey"] = agentConfigVars['licenseKey']
    toSendDataDict["projectName"] = agentConfigVars['projectName']
    toSendDataDict["userName"] = agentConfigVars['userName']
    toSendDataDict["instanceName"] = socket.gethostname().partition(".")[0]
    toSendDataDict["samplingInterval"] = str(int(reportingConfigVars['reporting_interval'] * 60))
    toSendDataDict["agentType"] = "LogStreaming"

    toSendDataJSON = json.dumps(toSendDataDict)
    logger.debug("TotalData: " + str(len(bytearray(toSendDataJSON))))

    # send the data
    postUrl = parameters['serverUrl'] + "/customprojectrawdata"
    response = requests.post(postUrl, data=json.loads(toSendDataJSON))
    if response.status_code == 200:
        logger.info(str(len(bytearray(toSendDataJSON))) + " bytes of data are reported.")
    else:
        logger.info("Failed to send data.")
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - sendDataTime))


def parseConsumerMessages(consumer):
    lineCount = 0
    chunkCount = 0
    currentRow = []
    start_time = time.time()
    for message in consumer:
        try:
            json_message = json.loads(message.value)
            host_name = json_message.get('beat', {}).get('hostname', {})
            message = json_message.get('message', {})
            timestamp = json_message.get('@timestamp', {})[:-5]

            if len(filter_hosts) != 0 and host_name.upper() not in (filter_host.upper() for filter_host in
                                                                    filter_hosts):
                continue

            if lineCount == parameters['chunkLines']:
                logger.debug("--- Chunk creation time: %s seconds ---" % (time.time() - start_time))
                sendData(currentRow)
                currentRow = []
                chunkCount += 1
                lineCount = 0
                start_time = time.time()

            pattern = "%Y-%m-%dT%H:%M:%S"
            if isTimeFormat(timestamp, pattern):
                try:
                    epoch = getTimestampForZone(timestamp, "GMT", pattern)
                except ValueError:
                    continue

            currentLogMsg = {}
            currentLogMsg['timestamp'] = epoch
            currentLogMsg['tag'] = host_name
            currentLogMsg['data'] = message
            currentRow.append(currentLogMsg)
            lineCount += 1
        except:
            continue

    if len(currentRow) != 0:
        logger.debug("--- Chunk creation time: %s seconds ---" % (time.time() - start_time))
        sendData(currentRow)
        chunkCount += 1
    logger.debug("Total chunks created: " + str(chunkCount))


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
    logger = setloggerConfig()
    parameters = get_parameters()
    agentConfigVars = get_agent_config_vars()
    reportingConfigVars = getReportingConfigVars()

    try:
        # Kafka consumer configuration
        datadir = 'data/'
        (brokers, topic, filter_hosts) = getKafkaConfig()
        consumer = KafkaConsumer(bootstrap_servers=brokers,
                                 auto_offset_reset='latest', consumer_timeout_ms=1000 * parameters['timeout'],
                                 group_id="if_consumers")
        consumer.subscribe([topic])
        parseConsumerMessages(consumer)
        consumer.close()

    except KeyboardInterrupt:
        print "Interrupt from keyboard"

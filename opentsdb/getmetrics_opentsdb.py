#!/usr/bin/env python
import sys
from optparse import OptionParser
import ConfigParser
import os
import requests
import json
import logging
import re
import socket
import random
import time
from datetime import datetime

'''
this script gathers system info from opentsdb and use http api to send to server
'''


def getParameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-c", "--chunkSize",
                      action="store", dest="chunkSize", help="Metrics per chunk")
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
    if options.chunkSize is None:
        parameters['chunkSize'] = 50
    else:
        parameters['chunkSize'] = int(options.chunkSize)
    return parameters


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


def getOpentsdbConfig(parameters, datadir):
    """Read and parse Open TSDB config from config.txt"""
    openTsdbConfig = {}
    if os.path.exists(os.path.join(parameters['homepath'], datadir, "config.txt")):
        cp = ConfigParser.SafeConfigParser()
        cp.read(os.path.join(parameters['homepath'], datadir, "config.txt"))
        openTsdbConfig = {
            "OPENTSDB_URL": cp.get('opentsdb', 'OPENTSDB_URL'),
        }
    return openTsdbConfig


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


def getMetricList(config):
    """Get available metric list from Open TSDB API"""
    metricList = []
    url = config["OPENTSDB_URL"] + "/api/suggest?type=metrics&q="
    response = requests.get(url)
    if response.status_code == 200:
        metricList = response.json()
        logger.debug("Get metric list from opentsdb: " + str(metricList))
    return metricList


def getMetricListFromFile(config, filePath):
    """Get available metric list from File"""
    metricList = set()
    with open(filePath, 'r') as f:
        for line in f:
            m = re.search(r'(?P<metric>\d\.\d\..+):', line)
            if m:
                metric = m.groupdict().get('metric')
                metricList.add(metric)
                logger.debug("Get metric list from file: " + str(metricList))
    return list(metricList)


def getMetricData(config, metricList, grouping_map, startTime, endTime):
    """Get metric data from Open TSDB API"""

    def fullData(d):
        valueMap = {}
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

        valueMap[header_field] = str(metric_value)
        valueMap['timestamp'] = str(mtime * 1000)

        return valueMap

    openTsdbMetricList = []
    json_data = {
        "token": '77b96664b77b110e01ff6fa8199ac262acfb62ca',
        "start": startTime,
        "end": endTime,
        "queries": map(lambda m: {
            "aggregator": "avg",
            "downsample": "1m-avg",
            "metric": m.encode('ascii')
        }, metricList)
    }

    url = config["OPENTSDB_URL"] + "/api/query"
    response = requests.post(url, data=json.dumps(json_data))
    if response.status_code == 200:
        rawDataList = response.json()
        logger.debug("Get metric data from opentsdb: " + str(len(rawDataList)))

        # completion metric data
        openTsdbMetricList = map(lambda d: fullData(d), rawDataList)

    return openTsdbMetricList


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
    toSendDataDict["agentType"] = "custom"

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


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in xrange(0, len(l), n):
        yield l[i:i + n]


def setloggerConfig(logLevel):
    """Set up logging according to the defined log level"""
    # Get the root logger
    logger = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger.setLevel(logLevel)
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
    GROUPING_START = 15000
    GROUPING_END = 20000

    logLevel = logging.INFO
    logger = setloggerConfig(logLevel)
    dataDirectory = 'data'
    parameters = getParameters()
    agentConfigVars = getAgentConfigVars()
    reportingConfigVars = getReportingConfigVars()
    grouping_map = load_grouping()

    # get agent configuration details
    agent_config = getOpentsdbConfig(parameters, dataDirectory)
    for item in agent_config.values():
        if not item:
            logger.error("config error, check data/config.txt")
            sys.exit("config error, check config.txt")

    # get data by cron
    dataEndTimestamp = int(time.time())
    intervalInSecs = int(reportingConfigVars['reporting_interval'] * 60)
    dataStartTimestamp = dataEndTimestamp - intervalInSecs
    timeList = [(dataStartTimestamp, dataEndTimestamp)]

    # get data from special date
    # startDay = '2018-06-1'
    # endDay = '2018-06-3'
    # startDayObj = datetime.strptime(startDay, "%Y-%m-%d")
    # startTimeStamp = int(time.mktime(startDayObj.timetuple()))
    # endDayObj = datetime.strptime(endDay, "%Y-%m-%d")
    # endTimeStamp = int(time.mktime(endDayObj.timetuple()))
    # timeInterval = (endTimeStamp - startTimeStamp) / 60
    # timeList = [(startTimeStamp + i * 60, startTimeStamp + (i + 1) * 60) for i in range(timeInterval)]

    for dataStartTimestamp, dataEndTimestamp in timeList:
        try:
            logger.debug("Start to send metric data: {}-{}".format(dataStartTimestamp, dataEndTimestamp))
            # get metric list from opentsdb
            # metricList = getMetricList(agent_config)
            filePath = './metrics.txt'
            metricListAll = getMetricListFromFile(agent_config, filePath)
            if len(metricListAll) == 0:
                logger.error("No metrics to get data for.")
                sys.exit()

            chunked_metric_list = chunks(metricListAll, parameters['chunkSize'])
            for sub_list in chunked_metric_list:
                # get metric data from opentsdb every SAMPLING_INTERVAL
                metricDataList = getMetricData(agent_config, sub_list, grouping_map, dataStartTimestamp,
                                               dataEndTimestamp)
                if len(metricDataList) == 0:
                    logger.error("No data for metrics received from Open TSDB.")
                    sys.exit()
                # send metric data to insightfinder
                sendData(metricDataList)
                save_grouping(grouping_map)

            logger.info("Send metric date for {} - {}.".format(dataStartTimestamp, dataEndTimestamp))
        except Exception as e:
            logger.error("Error send metric data to insightfinder: {}-{}".format(dataStartTimestamp, dataEndTimestamp))
            logger.error(e)

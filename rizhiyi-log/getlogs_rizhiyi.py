#!/usr/bin/env python
import sys
import os
import time
import json
import socket
import logging
import hashlib
import ConfigParser
from optparse import OptionParser

import requests

'''
this script gathers logs from rizhiyi and use http api to send to server
'''


def getParameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
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


def getRizhiyiConfig(parameters, datadir):
    """Read and parse rizhiyi config from config.txt"""
    rizhiyiConfig = {}
    if os.path.exists(os.path.join(parameters['homepath'], datadir, "config.txt")):
        cp = ConfigParser.SafeConfigParser()
        cp.read(os.path.join(parameters['homepath'], datadir, "config.txt"))
        rizhiyiConfig = {
            "RIZHIYI_URL": cp.get('rizhiyi', 'RIZHIYI_URL'),
            "RIZHIYI_ACCESS_KEY": cp.get('rizhiyi', 'RIZHIYI_ACCESS_KEY'),
            "RIZHIYI_SECURE_KEY": cp.get('rizhiyi', 'RIZHIYI_SECURE_KEY'),
            "RIZHIYI_SOURCE_GROUP": cp.get('rizhiyi', 'RIZHIYI_SOURCE_GROUP'),
        }
    return rizhiyiConfig


def _compute_sign(origin_params, secure_key, query_time):
    sign_arr = []

    def _md5(i_str):
        h = hashlib.md5()
        h.update(i_str)
        return h.hexdigest()[0:32]

    def _sorted_query_str(query_hash):
        return "&".join([k + "=" + query_hash[k] for k in sorted(query_hash.keys())])

    sign_arr.append(str(query_time))
    sign_arr.append(_sorted_query_str(origin_params))
    sign_arr.append(secure_key)

    return _md5("".join(sign_arr))


def get_rizhiyi_logs(config, start_timestamp, end_timestamp, page, size):
    origin_params = {
        'source_group': config.get("RIZHIYI_SOURCE_GROUP", 'all'),
        'time_range': "{},{}".format(start_timestamp, end_timestamp),
        'query': '*',
        'order': 'asc',
        'page': str(page),
        'size': str(size),
    }

    qtime = int(time.time() * 1000)
    sign = _compute_sign(origin_params, config["RIZHIYI_SECURE_KEY"], qtime)
    additional_params = {
        'qt': qtime,
        'sign': sign,
        'ak': config["RIZHIYI_ACCESS_KEY"],
    }
    req_params = dict(origin_params.items() + additional_params.items())

    logs = []
    total = 0
    min_time, max_time = 0, 0
    try:
        url = config["RIZHIYI_URL"] + "/v0/search/events"
        response = requests.get(url, params=req_params)
        if response.status_code == 200:
            res = response.json()
            result = res.get('result')
            if result is True:
                events = res.get('events', [])
                for ev in events:
                    timestamp = ev.get('timestamp')
                    min_time = min(min_time, long(timestamp))
                    max_time = max(max_time, long(timestamp))
                    hostname = ev.get('hostname')
                    raw_message = ev.get('raw_message')
                    logs.append({
                        'eventId': str(timestamp),
                        'tag': hostname,
                        'data': raw_message
                    })
                total = long(res.get('total'))

    except Exception as e:
        print e

    return logs, min_time, max_time, total


def sendData(logsData, minTimestamp, maxTimestamp):
    """Send rizhiyi log data to the InsightFinder application"""
    sendDataTime = time.time()
    # prepare data for metric streaming agent
    toSendDataDict = {}
    toSendDataDict["metricData"] = json.dumps(logsData)
    toSendDataDict["licenseKey"] = agentConfigVars['licenseKey']
    toSendDataDict["projectName"] = agentConfigVars['projectName']
    toSendDataDict["userName"] = agentConfigVars['userName']
    toSendDataDict["instanceName"] = socket.gethostname().partition(".")[0]
    toSendDataDict["samplingInterval"] = str(int(reportingConfigVars['reporting_interval'] * 60))
    toSendDataDict['agentType'] = 'LogStreaming'
    toSendDataDict['minTimestamp'] = str(minTimestamp)
    toSendDataDict['maxTimestamp'] = str(maxTimestamp)
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
    logLevel = logging.INFO
    logger = setloggerConfig(logLevel)
    dataDirectory = 'data'
    parameters = getParameters()
    agentConfigVars = getAgentConfigVars()
    reportingConfigVars = getReportingConfigVars()

    # get agent configuration details
    agent_config = getRizhiyiConfig(parameters, dataDirectory)
    for item in agent_config.values():
        if not item:
            logger.error("config error, check data/config.txt")
            sys.exit("config error, check config.txt")

    dataEndTimestamp = int(time.time())
    intervalInSecs = int(reportingConfigVars['reporting_interval'] * 60)
    dataStartTimestamp = dataEndTimestamp - intervalInSecs

    try:
        logger.debug("Start to send logs data: {}-{}".format(dataStartTimestamp, dataEndTimestamp))
        # get logs data from rizhiyi every SAMPLING_INTERVAL
        # max number or records per min per day
        logSize = 1440
        logsData, minTime, maxTime, logTotal = get_rizhiyi_logs(agent_config, dataStartTimestamp, dataEndTimestamp, 0,
                                                                logSize)
        if len(logsData) == 0:
            logger.error("No data for logs received from rizhiyi.")
            sys.exit()
        # send logs data to insightfinder
        sendData(logsData, minTime, maxTime)

    except Exception as e:
        logger.error("Error send logs data to insightfinder: {}-{}".format(dataStartTimestamp, dataEndTimestamp))
        logger.error(e)

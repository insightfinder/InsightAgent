#!/usr/bin/env python
# -*- coding: utf-8 -*-
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
import requests
import socket
import pandas as pd
import pytz
from time import gmtime, strftime

def setLoggerConfig():
    # Get the root logger
    logger = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger.setLevel(logging.DEBUG)
    # route INFO and DEBUG logging to stdout from stderr
    loggingHandlerOut = logging.StreamHandler(sys.stdout)
    loggingHandlerOut.setLevel(logging.DEBUG)
    loggingHandlerOut.addFilter(LessThanFilter(logging.WARNING))
    logger.addHandler(loggingHandlerOut)

    loggingHandlerErr = logging.StreamHandler(sys.stderr)
    loggingHandlerErr.setLevel(logging.WARNING)
    logger.addHandler(loggingHandlerErr)
    return logger

class LessThanFilter(logging.Filter):
    def __init__(self, exclusive_maximum, name=""):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        # non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0

def getParameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-l", "--chunkLines",
                      action="store", dest="chunkLines", help="Max number of lines in chunk")
    parser.add_option("-m", "--MaxInTag",
                      action="store", dest="MaxInTag", help="Max number of one tag can have")
    (options, args) = parser.parse_args()

    parameters = {}
    if options.homepath is None:
        parameters['homepath'] = os.getcwd()
    else:
        parameters['homepath'] = options.homepath
    if options.serverUrl == None:
        #parameters['serverUrl'] = 'http://stg.insightfinder.com'
        parameters['serverUrl'] = 'http://127.0.0.1:8080'
    else:
        parameters['serverUrl'] = options.serverUrl
    if options.chunkLines is None:
        parameters['chunkLines'] = 1000
    else:
        parameters['chunkLines'] = int(options.chunkLines)
    if options.MaxInTag is None:
        parameters['MaxInTag'] = 200
    else:
        parameters['MaxInTag'] = int(options.MaxInTag)
    return parameters


def is_time_format(time_string, datetime_format):
    """
    Determines the validity of the input date-time string according to the given format
    Parameters:
    - `timeString` : datetime string to check validity
    - `temp_id` : datetime format to compare with
    """
    try:
        datetime.strptime(str(time_string), datetime_format)
        return True
    except ValueError:
        return False


def get_timestamp_for_zone(date_string, time_zone, datetime_format):
    dtexif = datetime.strptime(date_string, datetime_format)
    tz = pytz.timezone(time_zone)
    tztime = tz.localize(dtexif)
    epoch = long((tztime - datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()) * 1000
    return epoch

def getAgentConfigVars():
    configVars = {}
    try:
        if os.path.exists(os.path.join(parameters['homepath'], "pufaAgent", "config.ini")):
            parser = SafeConfigParser()
            parser.read(os.path.join(parameters['homepath'], "pufaAgent", "config.ini"))
            tag = parser.get('pufa', 'tag')
            fileName = parser.get('pufa', 'file_name')
            licenseKey = parser.get('pufa', 'insightFinder_license_key')
            projectName = parser.get('pufa', 'insightFinder_project_name')
            userName = parser.get('pufa', 'insightFinder_user_name')
            samplingInterval = parser.get('pufa', 'sampling_interval')
            if len(tag) == 0:
                logger.error("Agent not correctly configured(tag name). Check config file.")
                sys.exit(1)
            if len(fileName) == 0:
                logger.error("Agent not correctly configured(file name). Check config file.")
                sys.exit(1)
            if len(licenseKey) == 0:
                logger.error("Agent not correctly configured(license key). Check config file.")
                sys.exit(1)
            if len(projectName) == 0:
                logger.error("Agent not correctly configured(project name). Check config file.")
                sys.exit(1)
            if len(userName) == 0:
                logger.error("Agent not correctly configured(user name). Check config file.")
                sys.exit(1)
            if len(samplingInterval) == 0:
                logger.error("Agent not correctly configured(sampling interval). Check config file.")
                sys.exit(1)
            configVars['tag'] = tag
            configVars['fileName'] = fileName
            configVars['licenseKey'] = licenseKey
            configVars['projectName'] = projectName
            configVars['userName'] = userName
            if samplingInterval[-1:] == 's':
                configVars['samplingInterval'] = float(float(samplingInterval[:-1]) / 60.0)
            else:
                configVars['samplingInterval'] = int(samplingInterval)
    except IOError:
        logger.error("config.ini file is missing")
    return configVars


def parseMessage():
    collectedLogsMap = {}

    file = parameters['homepath'] + '/data/' + configVars['fileName']

    readFile = pd.read_excel(file, sheet_name='Sheet1')

    for i in readFile.index:
        tag = readFile[configVars['tag']][i]
        hostAddress = readFile['host_address'][i]
        hostName = readFile['host_name'][i]
        eventContent = readFile['event_content'][i]
        timeStamp = strftime("%Y-%m-%d %H:%M:%S", gmtime())
        timeStamp = timeStamp.replace(" ", "T")
        pattern = "%Y-%m-%dT%H:%M:%S"

        if is_time_format(timeStamp, pattern):
            try:
                epoch = get_timestamp_for_zone(timeStamp, "GMT", pattern)
            except ValueError:
                continue
        currentLogMsg = dict()
        currentLogMsg['timeStamp'] = epoch
        currentLogMsg['tag'] = str(tag)
        currentLogMsg['data'] = "event content:" + str(eventContent) + " host address:" + str(hostAddress) + " host name:" + str(hostName)
        if tag not in collectedLogsMap:
            collectedLogsMap[tag] = []
        collectedLogsMap[tag].append(currentLogMsg)
        if len(collectedLogsMap[tag])>=parameters['MaxInTag']:
            sendData(collectedLogsMap[tag])
            collectedLogsMap.pop(tag)
        elif len(collectedLogsMap)>=parameters['chunkLines']:
            for key in collectedLogsMap:
                sendData(collectedLogsMap[key])
            collectedLogsMap = {}

    for key in collectedLogsMap:
        sendData(collectedLogsMap[key])


def sendData(metric_data):
    """ Sends parsed metric data to InsightFinder """
    sendDataTime = time.time()
    # prepare data for metric streaming agent
    toSendDataDict = dict()
    toSendDataDict["metricData"] = json.dumps(metric_data)
    toSendDataDict["licenseKey"] = configVars['licenseKey']
    toSendDataDict["projectName"] = configVars['projectName']
    toSendDataDict["userName"] = configVars['userName']
    toSendDataDict["instanceName"] = socket.gethostname().partition(".")[0]
    toSendDataDict["samplingInterval"] = str(int(configVars['samplingInterval'] * 60))
    toSendDataDict["agentType"] = "LogStreaming"

    toSendDataJson = json.dumps(toSendDataDict)
    # logger.debug("TotalData: " + str(len(bytearray(toSendDataJson))))
    # logger.debug("Data: " + str(toSendDataJson))

    # send the data
    postUrl = parameters['serverUrl'] + "/customprojectrawdata"
    response = requests.post(postUrl, data=json.loads(toSendDataJson))
    if response.status_code == 200:
        logger.info(str(len(bytearray(toSendDataJson))) + " bytes of data are reported.")
    else:
        logger.info("Failed to send data.")
    logger.info("--- Send data time: %s seconds ---" % (time.time() - sendDataTime))


if __name__ == "__main__":
    reload(sys)
    sys.setdefaultencoding('utf-8')
    logger = setLoggerConfig()
    parameters = getParameters()
    configVars = getAgentConfigVars()
    try:
        parseMessage()
    except KeyboardInterrupt:
        print "Interrupt from keyboard"

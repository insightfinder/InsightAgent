#!/usr/bin/python
import math
from common import reportMetrics, configReader
from optparse import OptionParser
import os
import json
import time
import socket
import requests
import datetime
import pytz
import logging
import sys
import thread


def getParameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-z", "--timeZone",
                      action="store", dest="timeZone", help="Time Zone")
    parser.add_option("-c", "--chunkSize",
                      action="store", dest="chunkSize", help="Chunk Size")
    parser.add_option("-r", "--logFolder",
                      action="store", dest="logFolder", help="Folder to read log files from")
    (options, args) = parser.parse_args()

    parameters = {}
    if options.homepath is None:
        parameters['homepath'] = os.getcwd()
    else:
        parameters['homepath'] = options.homepath
    if options.serverUrl is None:
        parameters['serverUrl'] = 'https://app.insightfinder.com'
    else:
        parameters['serverUrl'] = options.serverUrl
    if options.timeZone is None:
        parameters['timeZone'] = 'UTC'
    else:
        parameters['timeZone'] = options.timeZone
    if options.logFolder is None:
        parameters['logFolder'] = "/usr/local/var/log/hbase/"
    else:
        parameters['logFolder'] = options.logFolder
    if options.logFolder is None:
        parameters['chunkSize'] = 4000000
    else:
        parameters['chunkSize'] = int(options.chunkSize)
    return parameters


def getReportingConfigVars():
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
    return reportingConfigVars


def sendData(metricData, minTimestamp, maxTimestamp):
    sendDataTime = time.time()
    # prepare data for metric streaming agent
    toSendDataDict = {}
    toSendDataDict["metricData"] = json.dumps(metricData)
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


# change python timestamp to unix timestamp in millis
def current_milli_time(): return int(round(time.time() * 1000))


def getDateForZone(timestamp, datatimeZone, localTimezone, format):
    dateObject = datetime.datetime.fromtimestamp(timestamp / 1000)
    localTimeZone = pytz.timezone(localTimezone)
    dataTimeZone = pytz.timezone(datatimeZone)
    localTimeObject = localTimeZone.localize(dateObject)
    dataTimeObject = localTimeObject.astimezone(dataTimeZone)
    dateString = dataTimeObject.strftime(format)
    return dateString

# update prev_endtime in config file
def update_timestamp(prev_endtime):
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), 'r') as f:
        config = json.load(f)
    config['prev_endtime'] = prev_endtime
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), "w") as f:
        json.dump(config, f)


def getDataStartTime():
    if reportingConfigVars['prev_endtime'] != "0":
        startTime = reportingConfigVars['prev_endtime']
        # pad a second after prev_endtime
        startTimeEpoch = 1000 + long(1000 * time.mktime(time.strptime(startTime, "%Y%m%d%H%M%S")));
        end_time_epoch = startTimeEpoch + 1000 * 60 * reportingConfigVars['reporting_interval']
    else:  # prev_endtime == 0
        end_time_epoch = int(time.time()) * 1000
        startTimeEpoch = end_time_epoch - 1000 * 60 * reportingConfigVars['reporting_interval']
    return startTimeEpoch


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


def getFileListForDirectory(rootPath):
    fileList = []
    for name in os.listdir(rootPath):
        if "log" in name or "out" in name:
            fileList.append(os.path.join(rootPath, name))
#    for path, subdirs, files in os.walk(rootPath):
#        for name in files:
#	    logger.info(name)
#            if "log" in name or "out" in name:
#            fileList.append(os.path.join(path, name))
                #fileList.append(os.path.join(path, name))

    return fileList


def monitorFile(thefile):
    thefile.seek(0, 2)
    while True:
        line = thefile.readline()
        if not line:
            time.sleep(0.1)
            continue
        yield line


def isTimeFormat(input):
    try:
        datetime.datetime.strptime(str(input), "%Y-%m-%d %H:%M:%S")
        return True
    except ValueError:
        return False


def getTimestampForZone(dateObj, timeZone):
    # Example format: 2018-03-06 03:17:05.822
    dtexif = dateObj
    tz = pytz.timezone(timeZone)
    tztime = tz.localize(dtexif)
    epoch = long((tztime - datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()) * 1000
    return epoch


def getTimestampForZone(dateString, timeZone, format):
    dtexif = datetime.datetime.strptime(dateString, format)
    tz = pytz.timezone(timeZone)
    tztime = tz.localize(dtexif)
    epoch = long((tztime - datetime.datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()) * 1000
    return epoch


def processLogFiles(filePath):
    logger.debug("Starting thread for " + str(filePath))
    logfile = open(filePath, "r")
    logFileLines = monitorFile(logfile)
    result = []
    flag = False
    stringTemp = ""
    count = 0
    filename = os.path.basename(filePath)
    fileTag = filename.split(".",2)[0]
    for line in logFileLines:
        print line
        line = line.decode('latin1').encode('utf8')
        timestampRaw = line[0:19]
        if isTimeFormat(timestampRaw):
            if flag:
                count = count + 1
                obj = {}
                obj["data"] = stringTemp
                obj["eventId"] = epoch
                obj["tag"] = fileTag
                result.append(obj)
                stringTemp = ""
                flag = False
            data = line[30:]
            stringTemp += line[30:]
            pattern = "%Y-%m-%d %H:%M:%S"
            try:
                epoch = getTimestampForZone(timestampRaw, parameters['timeZone'], pattern)
            except ValueError:
                continue
            flag = True
        else:
            stringTemp += line
        logger.debug("Size of current result: " + str(len(bytearray(str(result)))) + " bytes")
        if len(bytearray(str(result))) >= parameters['chunkSize']:
            sendData(result, "", "")
	    result = []
            logger.debug("Total rows " + str(count) + " to send for " + str(filePath))
    if flag:
        count = count + 1
        obj = {}
        obj["data"] = stringTemp
        obj["eventId"] = epoch
        result.append(obj)



if __name__ == '__main__':
    logger = setloggerConfig()
    parameters = getParameters()
    agentConfigVars = configReader.getAgentConfigVars(parameters['homepath'])
    reportingConfigVars = getReportingConfigVars()

    # get log data from folder
    fileList = getFileListForDirectory(parameters['logFolder'])
    logger.debug(fileList)
    for filePath in fileList:
        thread.start_new_thread(processLogFiles, (filePath,))
    while True:
        time.sleep(1)
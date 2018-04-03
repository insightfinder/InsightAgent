#!/usr/bin/python

import hashlib
from optparse import OptionParser
import os
import time
import logging
import sys
import json
import datetime
import csv
import math
import socket
import subprocess
import random

'''
This script reads reporting_config.json and .agent.bashrc
and opens daily metric file and reports header + rows within
window of reporting interval after prev endtime
if prev endtime is 0, report most recent reporting interval
till now from today's metric file (may or may not be present)
assumping gmt epoch timestamp and local date daily file. 

This also allows you to replay old log and metric files 
'''

def getParameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-f", "--fileInput",
                      action="store", dest="inputFile", help="Input data file (overriding daily data file)")
    parser.add_option("-r", "--logFolder",
                      action="store", dest="logFolder", help="Folder to read log files from")
    parser.add_option("-m", "--mode",
                      action="store", dest="mode", help="Running mode: live or metricFileReplay or logFileReplay")
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-t", "--agentType",
                      action="store", dest="agentType", help="Agent type")
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-s", "--splitID",
                      action="store", dest="splitID", help="The split ID to use when grouping results on the server")
    parser.add_option("-g", "--splitBy",
                      action="store", dest="splitBy",
                      help="The 'split by' to use when grouping results on the server. Examples: splitByEnv, splitByGroup")
    parser.add_option("-z", "--timeZone",
                      action="store", dest="timeZone", help="Time Zone")
    parser.add_option("-c", "--chunkSize",
                      action="store", dest="chunkSize", help="Max chunk size in KB")
    parser.add_option("-l", "--chunkLines",
                      action="store", dest="chunkLines", help="Max number of lines in chunk")
    (options, args) = parser.parse_args()

    parameters = {}
    if options.homepath is None:
        parameters['homepath'] = os.getcwd()
    else:
        parameters['homepath'] = options.homepath
    if options.mode is None:
        parameters['mode'] = "live"
    else:
        parameters['mode'] = options.mode
    if options.agentType is None:
        parameters['agentType'] = ""
    else:
        parameters['agentType'] = options.agentType
    if options.serverUrl is None:
        parameters['serverUrl'] = 'https://app.insightfinder.com'
    else:
        parameters['serverUrl'] = options.serverUrl
    if options.inputFile is None:
        parameters['inputFile'] = None
    else:
        parameters['inputFile'] = options.inputFile
    if options.logFolder is None:
        parameters['logFolder'] = None
    else:
        parameters['logFolder'] = options.logFolder
    if options.timeZone is None:
        parameters['timeZone'] = "GMT"
    else:
        parameters['timeZone'] = options.timeZone
    if options.chunkLines is None and parameters['agentType'] == 'metricFileReplay':
        parameters['chunkLines'] = 100
    elif options.chunkLines is None:
        parameters['chunkLines'] = 40000
    else:
        parameters['chunkLines'] = int(options.chunkLines)
    # Optional split id and split by for metric file replay
    if options.splitID is None:
        parameters['splitID'] = None
    else:
        parameters['splitID'] = options.splitID
    if options.splitBy is None:
        parameters['splitBy'] = None
    else:
        parameters['splitBy'] = options.splitBy
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
    return reportingConfigVars

def updateDataStartTime():
    if "FileReplay" in parameters['mode'] and reportingConfigVars['prev_endtime'] != "0" and len(
            reportingConfigVars['prev_endtime']) >= 8:
        startTime = reportingConfigVars['prev_endtime']
        # pad a second after prev_endtime
        startTimeEpoch = 1000 + long(1000 * time.mktime(time.strptime(startTime, "%Y%m%d%H%M%S")));
        end_time_epoch = startTimeEpoch + 1000 * 60 * reportingConfigVars['reporting_interval']
    elif reportingConfigVars['prev_endtime'] != "0":
        startTime = reportingConfigVars['prev_endtime']
        # pad a second after prev_endtime
        startTimeEpoch = 1000 + long(1000 * time.mktime(time.strptime(startTime, "%Y%m%d%H%M%S")));
        end_time_epoch = startTimeEpoch + 1000 * 60 * reportingConfigVars['reporting_interval']
    else:  # prev_endtime == 0
        end_time_epoch = int(time.time()) * 1000
        startTimeEpoch = end_time_epoch - 1000 * 60 * reportingConfigVars['reporting_interval']
    return startTimeEpoch

# update prev_endtime in config file
def update_timestamp(prev_endtime):
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), 'r') as f:
        config = json.load(f)
    config['prev_endtime'] = prev_endtime
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), "w") as f:
        json.dump(config, f)

def getIndexForColumnName(col_name):
    if col_name == "CPU":
        return 1
    elif col_name == "DiskRead" or col_name == "DiskWrite":
        return 2
    elif col_name == "DiskUsed":
        return 3
    elif col_name == "NetworkIn" or col_name == "NetworkOut":
        return 4
    elif col_name == "MemUsed":
        return 5

def getEC2InstanceType():
    url = "http://169.254.169.254/latest/meta-data/instance-type"
    try:
        response = requests.post(url)
    except requests.ConnectionError, e:
        logger.error("Error finding instance-type")
        return
    if response.status_code != 200:
        logger.error("Error finding instance-type")
        return
    return response.text

def sendData(metricDataDict, filePath):
    sendDataTime = time.time()
    # prepare data for metric streaming agent
    toSendDataDict = {}
    if parameters['mode'] == "metricFileReplay":
        toSendDataDict["metricData"] = json.dumps(metricDataDict[0])
    else:
        toSendDataDict["metricData"] = json.dumps(metricDataDict)

    toSendDataDict["licenseKey"] = agentConfigVars['licenseKey']
    toSendDataDict["projectName"] = agentConfigVars['projectName']
    toSendDataDict["userName"] = agentConfigVars['userName']
    toSendDataDict["instanceName"] = socket.gethostname().partition(".")[0]
    toSendDataDict["samplingInterval"] = str(int(reportingConfigVars['reporting_interval'] * 60))
    if parameters['agentType'] == "ec2monitoring":
        toSendDataDict["instanceType"] = getEC2InstanceType()
    #additional data to send for replay agents
    if "FileReplay" in parameters['mode']:
        toSendDataDict["fileID"] = hashlib.md5(filePath).hexdigest()
        if parameters['mode'] == "logFileReplay":
            toSendDataDict["agentType"] = "LogFileReplay"
            toSendDataDict["minTimestamp"] = ""
            toSendDataDict["maxTimestamp"] = ""
        if parameters['mode'] == "metricFileReplay":
            toSendDataDict["agentType"] = "MetricFileReplay"
            toSendDataDict["minTimestamp"] = str(metricDataDict[1])
            toSendDataDict["maxTimestamp"] = str(metricDataDict[2])
            toSendDataDict["chunkSerialNumber"] = str(random.randint(1,10))
        if ('splitID' in parameters.keys() and 'splitBy' in parameters.keys()):
            toSendDataDict["splitID"] = parameters['splitID']
            toSendDataDict["splitBy"] = parameters['splitBy']

    toSendDataJSON = json.dumps(toSendDataDict)
    logger.debug("Chunksize: " + str(len(bytearray(str(metricDataDict)))))
    logger.debug("TotalData: " + str(len(bytearray(toSendDataJSON))))

    #send the data
    postUrl = parameters['serverUrl'] + "/customprojectrawdata"
    if parameters['agentType'] == "hypervisor":
        response = urllib.urlopen(postUrl, data=urllib.urlencode(toSendDataDict))
        if response.getcode() == 200:
            logger.info(str(len(bytearray(toSendDataJSON))) + " bytes of data are reported.")
        else:
            # retry once for failed data and set chunkLines to half if succeeded
            logger.error("Failed to send data. Retrying once.")
            dataSplit1 = metricDataDict[0:len(metricDataDict) / 2]
            toSendDataDict["metricData"] = json.dumps(dataSplit1)
            response = urllib.urlopen(postUrl, data=urllib.urlencode(toSendDataDict))
            if response.getcode() == 200:
                logger.info(str(len(bytearray(toSendDataJSON))) + " bytes of data are reported.")
                parameters['chunkLines'] = parameters['chunkLines'] / 2
                # since succeeded send the rest of the chunk
                dataSplit2 = metricDataDict[len(metricDataDict) / 2:]
                toSendDataDict["metricData"] = json.dumps(dataSplit2)
                response = urllib.urlopen(postUrl, data=urllib.urlencode(toSendDataDict))
            else:
                logger.info("Failed to send data.")

    else:
        response = requests.post(postUrl, data=json.loads(toSendDataJSON))
        if response.status_code == 200:
            logger.info(str(len(bytearray(toSendDataJSON))) + " bytes of data are reported.")
        else:
            logger.info("Failed to send data.")
            dataSplit1 = metricDataDict[0:len(metricDataDict) / 2]
            toSendDataDict["metricData"] = json.dumps(dataSplit1)
            toSendDataJSON = json.dumps(toSendDataDict)
            response = requests.post(postUrl, data=json.loads(toSendDataJSON))
            if response.status_code == 200:
                logger.info(str(len(bytearray(toSendDataJSON))) + " bytes of data are reported.")
                parameters['chunkLines'] = parameters['chunkLines'] / 2
                # since succeeded send the rest of the chunk
                dataSplit2 = metricDataDict[len(metricDataDict) / 2:]
                toSendDataDict["metricData"] = json.dumps(dataSplit2)
                toSendDataJSON = json.dumps(toSendDataDict)
                response = requests.post(postUrl, data=json.loads(toSendDataJSON))
            else:
                logger.info("Failed to send data.")
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - sendDataTime))

def processStreaming(newPrevEndtimeEpoch):
    metricData = []
    dates = []
    # get dates to read files for
    for i in range(0, 3 + int(float(reportingConfigVars['reporting_interval']) / 24 / 60)):
        dates.append(time.strftime("%Y%m%d", time.localtime(startTimeEpoch / 1000 + 60 * 60 * 24 * i)))
    # append current date to dates
    currentDate = time.strftime("%Y%m%d", time.gmtime())
    if currentDate not in dates:
        dates.append(currentDate)

    # read all selected daily files for data
    for date in dates:
        filenameAddition = ""
        if parameters['agentType'] == "kafka":
            filenameAddition = "_kafka"
        elif parameters['agentType'] == "elasticsearch-storage":
            filenameAddition = "_es"

        dataFilePath = os.path.join(parameters['homepath'], dataDirectory + date + filenameAddition + ".csv")
        if os.path.isfile(dataFilePath):
            with open(dataFilePath) as dailyFile:
                try:
                    dailyFileReader = csv.reader(dailyFile)
                except IOError:
                    print "No data-file for " + str(date) + "!"
                    continue
                fieldnames = []
                for csvRow in dailyFileReader:
                    if dailyFileReader.line_num == 1:
                        # Get all the metric names
                        fieldnames = csvRow
                        for i in range(0, len(fieldnames)):
                            if fieldnames[i] == "timestamp":
                                timestamp_index = i
                    elif dailyFileReader.line_num > 1:
                        # skip lines which are already sent
                        try:
                            if long(csvRow[timestamp_index]) < long(startTimeEpoch):
                                continue
                        except ValueError:
                            continue
                        # Read each line from csv and generate a json
                        currentCSVRowData = {}
                        for i in range(0, len(csvRow)):
                            if fieldnames[i] == "timestamp":
                                newPrevEndtimeEpoch = csvRow[timestamp_index]
                                currentCSVRowData[fieldnames[i]] = csvRow[i]
                            else:
                                # fix incorrectly named columns
                                colname = fieldnames[i]
                                if colname.find("]") == -1:
                                    colname = colname + "[" + parameters['hostname'] + "]"
                                if colname.find(":") == -1:
                                    colname = colname + ":" + str(getIndexForColumnName(fieldnames[i]))
                                currentCSVRowData[colname] = csvRow[i]
                        metricData.append(currentCSVRowData)
    # update endtime in config
    if newPrevEndtimeEpoch == 0:
        print "No data is reported"
    else:
        newPrevEndtimeInSec = math.ceil(long(newPrevEndtimeEpoch) / 1000.0)
        new_prev_endtime = time.strftime("%Y%m%d%H%M%S", time.localtime(long(newPrevEndtimeInSec)))
        update_timestamp(new_prev_endtime)
        sendData(metricData, None)

def processReplay(filePath):
    if os.path.isfile(filePath):
        logger.info("Replaying file: " + filePath)
        # log file replay processing
        if parameters['mode'] == "logFileReplay":
            output = subprocess.check_output(
                'cat ' + filePath + ' | jq -c ".[]" > ' + filePath + ".mod",
                shell=True)
            with open(filePath + ".mod") as logfile:
                lineCount = 0
                chunkCount = 0
                currentRow = []
                start_time = time.time()
                for line in logfile:
                    if lineCount == parameters['chunkLines']:
                        logger.debug("--- Chunk creation time: %s seconds ---" % (time.time() - start_time))
                        sendData(currentRow, filePath)
                        currentRow = []
                        chunkCount += 1
                        lineCount = 0
                        start_time = time.time()
                    currentRow.append(json.loads(line.rstrip()))
                    lineCount += 1
                if len(currentRow) != 0:
                    logger.debug("--- Chunk creation time: %s seconds ---" % (time.time() - start_time))
                    sendData(currentRow, filePath)
                    chunkCount += 1
                logger.debug("Total chunks created: " + str(chunkCount))
            output = subprocess.check_output(
                "rm " + filePath + ".mod",
                shell=True)
        else:  # metric file replay processing
            with open(filePath) as metricFile:
                metricCSVReader = csv.reader(metricFile)
                toSendMetricData = []
                fieldnames = []
                currentLineCount = 1
                chunkCount = 0
                minTimestampEpoch = 0
                maxTimestampEpoch = -1
                for row in metricCSVReader:
                    if metricCSVReader.line_num == 1:
                        # Get all the metric names from header
                        fieldnames = row
                        # get index of the timestamp column
                        for i in range(0, len(fieldnames)):
                            if fieldnames[i] == "timestamp":
                                timestampIndex = i
                    elif metricCSVReader.line_num > 1:
                        # Read each line from csv and generate a json
                        currentRow = {}
                        if currentLineCount == parameters['chunkLines']:
                            sendData([toSendMetricData, minTimestampEpoch, maxTimestampEpoch], filePath)
                            toSendMetricData = []
                            currentLineCount = 0
                            chunkCount += 1
                        for i in range(0, len(row)):
                            if fieldnames[i] == "timestamp":
                                currentRow[fieldnames[i]] = row[i]
                                if minTimestampEpoch == 0 or minTimestampEpoch > long(row[i]):
                                    minTimestampEpoch = long(row[i])
                                if maxTimestampEpoch == 0 or maxTimestampEpoch < long(row[i]):
                                    maxTimestampEpoch = long(row[i])
                            else:
                                colname = fieldnames[i]
                                if colname.find("]") == -1:
                                    colname = colname + "[-]"
                                if colname.find(":") == -1:
                                    groupid = i
                                    colname = colname + ":" + str(groupid)
                                currentRow[colname] = row[i]
                        toSendMetricData.append(currentRow)
                        currentLineCount += 1
                # send final chunk
                if len(toSendMetricData) != 0:
                    sendData([toSendMetricData, minTimestampEpoch, maxTimestampEpoch], filePath)
                    chunkCount += 1
                logger.debug("Total chunks created: " + str(chunkCount))

def setloggerConfig():
    # Get the root logger
    logger = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger.setLevel(logging.INFO)
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
        #non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0

def getFileListForDirectory(rootPath):
    fileList = []
    for path, subdirs, files in os.walk(rootPath):
        for name in files:
            if parameters['agentType'] == "metricFileReplay" and "csv" in name:
                fileList.append(os.path.join(path, name))
            if parameters['agentType'] == "LogFileReplay" and "json" in name:
                fileList.append(os.path.join(path, name))
    return fileList
if __name__ == '__main__':
    prog_start_time = time.time()
    logger = setloggerConfig()
    dataDirectory = 'data/'
    parameters = getParameters()
    agentConfigVars = getAgentConfigVars()
    reportingConfigVars = getReportingConfigVars()

    if parameters['agentType'] == "hypervisor":
        import urllib
    else:
        import requests

    # locate time range and date range
    prevEndtimeEpoch = reportingConfigVars['prev_endtime']
    newPrevEndtimeEpoch = 0
    startTimeEpoch = 0
    startTimeEpoch = updateDataStartTime()

    if parameters['inputFile'] is None and parameters['logFolder'] is None:
        processStreaming(newPrevEndtimeEpoch)
    else:
        if parameters['logFolder'] is None:
            inputFilePath = os.path.join(parameters['homepath'], parameters['inputFile'])
            processReplay(inputFilePath)
        else:
            fileList = getFileListForDirectory(parameters['logFolder'])
            for filePath in fileList:
                processReplay(filePath)

    logger.info("--- Total runtime: %s seconds ---" % (time.time() - prog_start_time))
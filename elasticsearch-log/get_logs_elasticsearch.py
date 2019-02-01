#!/usr/bin/python
import datetime
import json
import logging
import math
import os
import socket
import sys
import time
from optparse import OptionParser

import pytz
import requests
from elasticsearch import Elasticsearch
from ConfigParser import SafeConfigParser


def getParameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-z", "--timeZone",
                      action="store", dest="timeZone", help="Time Zone")
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
    return parameters


def getElasticConfigVars():
    reportingConfigVars = {}
    with open(os.path.join(parameters['homepath'], "elasticsearch-log", "config.json"), 'r') as f:
        config = json.load(f)
    reportingConfigVars['elasticsearchIndex'] = str(config['elasticsearchIndex'])
    reportingConfigVars['elasticsearchHost'] = str(config['elasticsearchHost'])
    reportingConfigVars['elasticsearchPort'] = int(config['elasticsearchPort'])
    reportingConfigVars['timeFieldName'] = str(config['timeFieldName'])
    reportingConfigVars['isTimestamp'] = bool(config['isTimestamp'])
    reportingConfigVars['hostNameField'] = str(config['hostNameField'])
    if not reportingConfigVars['isTimestamp']:
        reportingConfigVars['dateFormatES'] = str(config['dateFormatInJodaTime'])
        reportingConfigVars['dateFormatPython'] = str(config['dateFormatInStrptime'])
        if 'dataTimeZone' in config and 'localTimeZone' in config:
            reportingConfigVars['dataTimeZone'] = str(config['dataTimeZone'])
            reportingConfigVars['localTimeZone'] = str(config['localTimeZone'])
    return reportingConfigVars

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

    #send the data
    postUrl = parameters['serverUrl'] + "/customprojectrawdata"
    response = requests.post(postUrl, data=json.loads(toSendDataJSON))
    if response.status_code == 200:
        logger.info(str(len(bytearray(toSendDataJSON))) + " bytes of data are reported.")
    else:
        logger.info("Failed to send data.")
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - sendDataTime))


def getElasticSearchConnection(elasticsearchConfigVars):
    try:
        es = Elasticsearch([{'host': elasticsearchConfigVars['elasticsearchHost'], 'port': elasticsearchConfigVars['elasticsearchPort']}])
    except:
        logger.error("Unable to get data connect to elasticsearch.")
        exit()
    return es

# change python timestamp to unix timestamp in millis
def current_milli_time(): return int(round(time.time() * 1000))

def getDateForZone(timestamp, datatimeZone, localTimezone,format):
    dateObject = datetime.datetime.fromtimestamp(timestamp / 1000)
    localTimeZone = pytz.timezone(localTimezone)
    dataTimeZone = pytz.timezone(datatimeZone)
    localTimeObject = localTimeZone.localize(dateObject)
    dataTimeObject = localTimeObject.astimezone(dataTimeZone)
    dateString = dataTimeObject.strftime(format)
    return dateString

def getLogsFromElastic(elasticsearch, elasticsearchConfigVars):
    if elasticsearchConfigVars['isTimestamp']:
        start_time = getDataStartTime()
        end_time = current_milli_time()
        query_body = {"query":
            {"range":
                {elasticsearchConfigVars['timeFieldName']:
                    {"from": start_time, "to": str(end_time)}
                }
            },
            "sort": [
                {elasticsearchConfigVars['timeFieldName']: "desc"}
            ],
            "size": 1440 # max number or records per min per day
        }
    else:
        start_time = getDataStartTime()
        end_time = current_milli_time()
        if elasticsearchConfigVars['dataTimeZone'] is not None:
            start_date = getDateForZone(start_time, elasticsearchConfigVars['dataTimeZone'],elasticsearchConfigVars['localTimeZone'],elasticsearchConfigVars['dateFormatPython'])
            end_date = getDateForZone(end_time, elasticsearchConfigVars['dataTimeZone'],elasticsearchConfigVars['localTimeZone'],elasticsearchConfigVars['dateFormatPython'])
        else:
            start_date = datetime.datetime.fromtimestamp(start_time/1000).strftime(elasticsearchConfigVars['dateFormatPython'])
            end_date = datetime.datetime.fromtimestamp(int(start_time/1000)).strftime(elasticsearchConfigVars['dateFormatPython'])
        query_body = {"query":
            {"range":
                {elasticsearchConfigVars['timeFieldName']:
                    {"gte": start_date,
                    "lte": end_date,
                    "format": elasticsearchConfigVars['dateFormatES']}
                }
            },
            "sort": [
                {elasticsearchConfigVars['timeFieldName']: "desc"}
            ],
            "size": 1440 # max number or records per min per day
        }
    try:
        res2 = elasticsearch.search(index=elasticsearchConfigVars['elasticsearchIndex'], body=query_body)
    except:
        logger.error("Unable to get data from elasticsearch. Check config file.")
        exit()
    jsonData = []
    minTimeStamp = sys.maxsize+1
    maxTimeStamp = 0
    if len(res2['hits']['hits']) != 0: # if there are updated values after the last read record
        currentLog = {}
        latest_time = res2['hits']['hits'][0]['sort'][0]  # update the last read record timestamp
        currentLog['eventId'] = latest_time
        minTimeStamp = min(minTimeStamp, long(latest_time))
        maxTimeStamp = max(maxTimeStamp, long(latest_time))
        currentLog['data'] = json.dumps(res2['hits']['hits'][0]["_source"])
        try:
            currentLog['tag'] = res2['hits']['hits'][0]["_source"][elasticsearchConfigVars['hostNameField']]
        except:
            currentLog['tag'] = res2['hits']['hits'][0]["_source"]['beat']['hostname']
        jsonData.append(currentLog)
    if len(jsonData) != 0:
        newPrevEndtimeInSec = math.ceil(long(end_time) / 1000.0)
        newPrevEndtime = time.strftime("%Y%m%d%H%M%S", time.localtime(long(newPrevEndtimeInSec)))
        update_timestamp(newPrevEndtime)
    return jsonData, minTimeStamp, maxTimeStamp

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
        #non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0


def getAgentConfigVars(homepath=os.getcwd()):
    config_vars = {}
    try:
        if os.path.exists(os.path.join(homepath, "elasticsearch-log", "config.ini")):
            parser = SafeConfigParser()
            parser.read(os.path.join(homepath, "elasticsearch-log", "config.ini"))
            insightfinder_license_key = parser.get('elasticsearch-log', 'insightFinder_license_key')
            insightfinder_project_name = parser.get('elasticsearch-log', 'insightFinder_project_name')
            insightfinder_user_name = parser.get('elasticsearch-log', 'insightFinder_user_name')
            sampling_interval = parser.get('elasticsearch-log', 'sampling_interval')
            if len(insightfinder_license_key) == 0:
                logger.error("Agent not correctly configured(license key). Check config file.")
                sys.exit(1)
            if len(insightfinder_project_name) == 0:
                logger.error("Agent not correctly configured(project name). Check config file.")
                sys.exit(1)
            if len(insightfinder_user_name) == 0:
                logger.error("Agent not correctly configured(username). Check config file.")
                sys.exit(1)
            if len(sampling_interval) == 0:
                logger.error("Agent not correctly configured(sampling interval). Check config file.")
                sys.exit(1)
            config_vars['licenseKey'] = insightfinder_license_key
            config_vars['projectName'] = insightfinder_project_name
            config_vars['userName'] = insightfinder_user_name
            config_vars['samplingInterval'] = sampling_interval
    except IOError:
        logger.error("config.ini file is missing")
    return config_vars

if __name__ == '__main__':
    logger = setloggerConfig()
    parameters = getParameters()
    agentConfigVars = getAgentConfigVars(parameters['homepath'])
    elasticsearchConfigVars = getElasticConfigVars()
    reportingConfigVars = getReportingConfigVars()
    elasticsearch = getElasticSearchConnection(elasticsearchConfigVars)
    logData, minTimestamp, maxTimestamp = getLogsFromElastic(elasticsearch, elasticsearchConfigVars)

    if len(logData) == 0:
        logger.info("No data to send.")
    else:
        sendData(logData, minTimestamp, maxTimestamp)


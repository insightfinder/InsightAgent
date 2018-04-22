#!/usr/bin/python
import math
from common import reportMetrics, ifLogger, configReader
from optparse import OptionParser
from elasticsearch import Elasticsearch
import os
import json
import time
import socket
import requests
import datetime
import pytz
import logging

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
    if options.timeZone is None:
        parameters['timeZone'] = "GMT"
    else:
        parameters['timeZone'] = options.timeZone
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
    es = Elasticsearch([{'host': elasticsearchConfigVars['elasticsearchHost'], 'port': elasticsearchConfigVars['elasticsearchPort']}])
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

    res2 = elasticsearch.search(index=elasticsearchConfigVars['elasticsearchIndex'], body=query_body)
    jsonData = []
    if len(res2['hits']['hits']) != 0: # if there are updated values after the last read record
        currentLog = {}
        latest_time = res2['hits']['hits'][0]["_source"][elasticsearchConfigVars['timeFieldName']] # update the last read record timestamp
        header_fields = res2['hits']['hits'][0]["_source"]['message']
        currentLog['eventId'] = latest_time
        currentLog['data'] = json.dumps(res2['hits']['hits'][0]["_source"])
        currentLog['tag'] =  res2['hits']['hits'][0]["_source"][elasticsearchConfigVars['hostNameField']]
        jsonData.append(currentLog)
    if len(jsonData) != 0:
        newPrevEndtimeInSec = math.ceil(long(end_time) / 1000.0)
        newPrevEndtime = time.strftime("%Y%m%d%H%M%S", time.localtime(long(newPrevEndtimeInSec)))
        update_timestamp(newPrevEndtime)
    return jsonData

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

if __name__ == '__main__':
    logger = ifLogger.setloggerConfig()
    parameters = getParameters()
    agentConfigVars = configReader.getAgentConfigVars(parameters['homepath'])
    elasticsearchConfigVars = getElasticConfigVars()
    reportingConfigVars = getReportingConfigVars()
    elasticsearch = getElasticSearchConnection(elasticsearchConfigVars)
    logData = getLogsFromElastic(elasticsearch, elasticsearchConfigVars)

    if len(logData) == 0:
        logger.info("No data to send.")
    else:
        sendData(logData)


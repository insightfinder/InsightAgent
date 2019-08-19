# !/usr/bin/python
from datetime import datetime
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
import elasticsearch
from elasticsearch import Elasticsearch
import ConfigParser


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-l", "--logLevel",
                      action="store", dest="logLevel", help="Change log verbosity(WARNING: 0, INFO: 1, DEBUG: 2)")
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    (options, args) = parser.parse_args()

    params = dict()

    if options.homepath is None:
        params['homepath'] = os.getcwd()
    if options.serverUrl is None:
        params['serverUrl'] = 'http://stg.insightfinder.com'
    else:
        params['serverUrl'] = options.serverUrl

    params['logLevel'] = logging.INFO
    if options.logLevel == '0':
        params['logLevel'] = logging.WARNING
    elif options.logLevel == '1':
        params['logLevel'] = logging.INFO
    elif options.logLevel >= '2':
        params['logLevel'] = logging.DEBUG

    return params


def time_converter(time_string):
    utc_time = datetime.strptime(time_string, "%Y-%m-%dT%H:%M:%S.%fZ")
    epoch_time = (utc_time - datetime(1970, 1, 1)).total_seconds()
    return int(epoch_time) * 1000


def get_agent_config_vars():
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            user_name = config_parser.get('insightfinder', 'user_name')
            license_key = config_parser.get('insightfinder', 'license_key')
            project_name = config_parser.get('insightfinder', 'project_name')
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            server_url = config_parser.get('reporting_parameters', 'serverUrl')
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
            reporting_interval = config_parser.get('reporting_parameters', 'reporting_interval')

        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        if server_url is '':
            server_url = 'http://stg.insightfinder.com'

        if len(user_name) == 0:
            logger.warning(
                "Agent not correctly configured(user_name). Check config file.")
            sys.exit(1)
        if len(license_key) == 0:
            logger.warning(
                "Agent not correctly configured(license_key). Check config file.")
            sys.exit(1)
        if len(project_name) == 0:
            logger.warning(
                "Agent not correctly configured(project_name). Check config file.")
            sys.exit(1)
        if len(reporting_interval) == 0:
            logger.warning(
                "Agent not correctly configured(sampling_interval). Check config file.")
            sys.exit(1)

        config_vars = {
            "userName": user_name,
            "licenseKey": license_key,
            "projectName": project_name,
            "httpProxy": if_http_proxy,
            "httpsProxy": if_https_proxy,
            "serverUrl": server_url,
            "reporting_interval": reporting_interval,
            "sampling_interval": sampling_interval
        }

        return config_vars
    else:
        print("Agent not correctly configured")
        logger.error(
            "Agent not correctly configured. Check config file.")
        sys.exit(1)


def set_logger_config(level):
    """Set up logging according to the defined log level"""
    # Get the root logger
    logger_obj = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger_obj.setLevel(level)
    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
    # create a logging format
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(process)d - %(threadName)s - %(levelname)s - %(message)s')
    logging_handler_out.setFormatter(formatter)
    logger_obj.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logger_obj.addHandler(logging_handler_err)
    return logger_obj


def get_elastic_config():
    reportingConfigVars = {}
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.json"))):
        with open(os.path.join(parameters['homepath'], "config.json"), 'r') as f:
            config = json.load(f)
    try:
        reportingConfigVars['elasticsearchIndex'] = str(config['elasticsearchIndex'])
        reportingConfigVars['elasticsearchHost'] = str(config['elasticsearchHost'])
        reportingConfigVars['elasticsearchPort'] = int(config['elasticsearchPort'])
        reportingConfigVars['timeFieldName'] = str(config['timeFieldName'])
        reportingConfigVars['isTimestamp'] = bool(config['isTimestamp'])
        reportingConfigVars['hostNameField'] = str(config['hostNameField'])
        reportingConfigVars['prev_endtime'] = str(config['prev_endtime'])
    except ConfigParser.NoOptionError:
        logger.error(
            "Required configuration parameters are missing. Check config.Json.")
        sys.exit(1)
    if not reportingConfigVars['isTimestamp']:
        reportingConfigVars['dateFormatES'] = str(config['dateFormatInJodaTime'])
        reportingConfigVars['dateFormatPython'] = str(config['dateFormatInStrptime'])
        if 'dataTimeZone' in config and 'localTimeZone' in config:
            reportingConfigVars['dataTimeZone'] = str(config['dataTimeZone'])
            reportingConfigVars['localTimeZone'] = str(config['localTimeZone'])
    return reportingConfigVars


def getElasticSearchConnection(elasticsearchConfigVars):
    try:
        es = Elasticsearch([{'host': elasticsearchConfigVars['elasticsearchHost'],
                             'port': elasticsearchConfigVars['elasticsearchPort']}])
    except:
        logger.error("Unable to connect to elastic search.Check if config parameters are valid")
        exit()
    return es


def getDataStartTime(elasticsearchConfigVars):
    if elasticsearchConfigVars['prev_endtime'] != "0":
        startTime = elasticsearchConfigVars['prev_endtime']
        # pad a second after prev_endtime
        startTimeEpoch = 1000 + long(1000 * time.mktime(time.strptime(startTime, "%Y%m%d%H%M%S")));
        end_time_epoch = startTimeEpoch + 1000 * 60 * int(agent_config_vars['reporting_interval'])
    else:  # prev_endtime == 0
        end_time_epoch = int(time.time()) * 1000
        startTimeEpoch = end_time_epoch - 1000 * 60 * int(agent_config_vars['reporting_interval'])
    return startTimeEpoch


def current_milli_time(): return int(round(time.time() * 1000))


def getDateForZone(timestamp, datatimeZone, localTimezone, format):
    dateObject = datetime.datetime.fromtimestamp(timestamp / 1000)
    localTimeZone = pytz.timezone(localTimezone)
    dataTimeZone = pytz.timezone(datatimeZone)
    localTimeObject = localTimeZone.localize(dateObject)
    dataTimeObject = localTimeObject.astimezone(dataTimeZone)
    dateString = dataTimeObject.strftime(format)
    return dateString


# def update_timestamp(prev_endtime,elasticsearchConfigVars):
#    with open(os.path.join(elasticsearchConfigVars['homepath'], "config.json"), 'r') as f:
#        config = json.load(f)
#    config['prev_endtime'] = prev_endtime
#    with open(os.path.join(elasticsearchConfigVars['homepath'], "config.json"), "w") as f:
#        json.dump(config, f)

def getLogsFromElastic(elasticsearch, elasticsearchConfigVars):
    if elasticsearchConfigVars['isTimestamp']:
        start_time = getDataStartTime(elasticsearchConfigVars)
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
                      "size": 1440  # max number or records per min per day
                      }
    else:
        start_time = getDataStartTime()
        end_time = current_milli_time()
        if elasticsearchConfigVars['dataTimeZone'] is not None:
            start_date = getDateForZone(start_time, elasticsearchConfigVars['dataTimeZone'],
                                        elasticsearchConfigVars['localTimeZone'],
                                        elasticsearchConfigVars['dateFormatPython'])
            end_date = getDateForZone(end_time, elasticsearchConfigVars['dataTimeZone'],
                                      elasticsearchConfigVars['localTimeZone'],
                                      elasticsearchConfigVars['dateFormatPython'])
        else:
            start_date = datetime.datetime.fromtimestamp(start_time / 1000).strftime(
                elasticsearchConfigVars['dateFormatPython'])
            end_date = datetime.datetime.fromtimestamp(int(start_time / 1000)).strftime(
                elasticsearchConfigVars['dateFormatPython'])
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
                      "size": 1440  # max number or records per min per day
                      }
    try:
        res2 = elasticsearch.search(index=elasticsearchConfigVars['elasticsearchIndex'], body=query_body)
    except:
        logger.error("Unable to get data from elasticsearch. Check config file.")
        exit()
    jsonData = []
    #

    #    res2["hits"]["hits"][n]["_source"]["groupdata"][k]["data"]

    for n in range(0, len(res2["hits"]["hits"])):
        logentry = {}
        #	logentry["timestamp"] = res2["hits"]["hits"][n]['sort'][0]
        #	logentry["tag"] ="ip-172-31-22-90"
        #	for entry in range(0,len(res2['hits']['hits'][n]["_source"]["groupdata"][
        logentry["data"] = res2["hits"]["hits"][n]["_source"]["groupdata"]
        logentry["timestamp"] = res2["hits"]["hits"][n]['sort'][0]
        logentry["tag"] = "ip-172-31-22-90"
        jsonData.append(logentry)

    #    minTimeStamp = sys.maxsize+1
    #    maxTimeStamp = 0
    #    print(res2)
    #    if len(res2['hits']['hits']) != 0: # if there are updated values after the last read record
    #        currentLog = {}
    #        latest_time = res2['hits']['hits'][0]['sort'][0]  # update the last read record timestamp
    #        currentLog['eventId'] = latest_time
    #        minTimeStamp = min(minTimeStamp, long(latest_time))
    #        maxTimeStamp = max(maxTimeStamp, long(latest_time))
    #        currentLog['data'] = json.dumps(res2['hits']['hits'][0]["_source"])

    #        try:
    #            currentLog['tag'] = res2['hits']['hits'][0]["_source"]['groupdata']
    #
    #        except:
    #            logger.error("Unable to get data from elasticsearch. Check config file.")
    #    print(res2)
    #   for keys in res2.keys():
    #	print(keys)
    #    jsonData=res2["hits"]["hits"][0]["_source"]["groupdata"]
    #    if len(jsonData) != 0:
    #        newPrevEndtimeInSec = math.ceil(long(end_time) / 1000.0)
    #        newPrevEndtime = time.strftime("%Y%m%d%H%M%S", time.localtime(long(newPrevEndtimeInSec)))
    # update_timestamp(newPrevEndtime)
    return jsonData


def sendData(metricData):
    sendDataTime = time.time()
    # prepare data for metric streaming agent
    toSendDataDict = {}

    toSendDataDict["userName"] = agent_config_vars['userName']
    toSendDataDict["projectName"] = agent_config_vars['projectName']
    toSendDataDict["licenseKey"] = agent_config_vars['licenseKey']
    # toSendDataDict["instanceName"] = socket.gethostname().partition(".")[0]
    # toSendDataDict["samplingInterval"] = str(int(agent_config_vars['reporting_interval'] * 60))
    toSendDataDict['agentType'] = 'LogStreaming'
    toSendDataDict["metricData"] = json.dumps(metricData)
    #    toSendDataDict['minTimestamp'] = str(minTimestamp)
    #    toSendDataDict['maxTimestamp'] = str(maxTimestamp)
    toSendDataJSON = json.dumps(toSendDataDict)
    logger.debug("TotalData: " + str(len(bytearray(toSendDataJSON))))

    # send the data

    postUrl = "http://stg.insightfinder.com" + "/customprojectrawdata"
    print(postUrl)
    response = requests.post(postUrl, data=json.loads(toSendDataJSON))
    print(toSendDataJSON)
    if response.status_code == 200:

        logger.info(str(len(bytearray(toSendDataJSON))) + " bytes of data are reported.")
    else:
        logger.info("Failed to send data.")
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - sendDataTime))


if __name__ == "__main__":

    parameters = get_parameters()
    log_level = parameters['logLevel']
    logger = set_logger_config(log_level)
    agent_config_vars = get_agent_config_vars()

    elasticsearchConfigVars = get_elastic_config()

    # sampling_interval_secs= int(agent_config_vars['samplingInterval'])*60
    parameters = get_parameters()

    elasticsearch = getElasticSearchConnection(elasticsearchConfigVars)
    logData = getLogsFromElastic(elasticsearch, elasticsearchConfigVars)

    if len(logData) == 0:
        logger.info("No data to send.")
    else:
        sendData(logData)

#!/usr/bin/python
from datetime import datetime
import json
import logging
import math
import os
import socket
import sys
import time
from optparse import OptionParser
import urlparse
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
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", help="Enable verbose logging")
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    (options, args) = parser.parse_args()

    params = dict()

    if options.serverUrl is None:
        params['serverUrl'] = 'https://app.insightfinder.com'
    else:
        params['serverUrl'] = options.serverUrl

    if options.homepath is None:
        params['homepath'] = os.getcwd()
    params['logLevel'] = logging.INFO
    if options.verbose:
        params['log_level'] = logging.DEBUG

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
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')

        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

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
        if len(sampling_interval) == 0:
            logger.warning(
                "Agent not correctly configured(sampling_interval). Check config file.")
            sys.exit(1)

        config_vars = {
            "userName": user_name,
            "licenseKey": license_key,
            "projectName": project_name,
            "httpProxy": if_http_proxy,
            "httpsProxy": if_https_proxy,
            "sampling_interval": sampling_interval,
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
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            reportingConfigVars['elasticsearchIndex'] = str(config_parser.get('elastic_search', 'elasticsearchIndex'))
            reportingConfigVars['elasticsearchHost'] = str(config_parser.get('elastic_search', 'elasticsearchHost'))
            reportingConfigVars['elasticsearchPort'] = int(config_parser.get('elastic_search', 'elasticsearchPort'))
            reportingConfigVars['timeFieldName'] = str(config_parser.get('elastic_search', 'timeFieldName'))
            reportingConfigVars['isTimestamp'] = bool(config_parser.get('elastic_search', 'isTimestamp'))
            reportingConfigVars['hostNameField'] = str(config_parser.get('elastic_search', 'hostNameField'))
        except ConfigParser.NoOptionError:
            logger.error("Required configuration parameters are missing.Check config.ini")
            sys.exit(1)
    if not reportingConfigVars['isTimestamp']:
        reportingConfigVars['dateFormatES'] = str(config_parser.get('elastic_search', 'dateFormatInJodaTime', raw=True))
        reportingConfigVars['dateFormatPython'] = str(config_parser.get('elastic_search', 'dateFormatInStrptime', raw=True))
        if config_parser.get('elastic_search', 'dataTimeZone') and config_parser.get('elastic_search', 'localTimeZone'):
            reportingConfigVars['dataTimeZone'] = str(config_parser.get('elastic_search', 'dataTimeZone'))
            reportingConfigVars['localTimeZone'] = str(config_parser.get('elastic_search', 'localTimeZone'))
    return reportingConfigVars


def getElasticSearchConnection(elasticsearchConfigVars):
    try:
        es = Elasticsearch([{'host': elasticsearchConfigVars['elasticsearchHost'],
                             'port': elasticsearchConfigVars['elasticsearchPort']}])
    except:
        logger.error("Unable to connect to elastic search.Check if config parameters are valid")
        exit()
    return es


def getDataStartTime():

    end_time_epoch = int(time.time()) * 1000
    startTimeEpoch = end_time_epoch - 1000 * 60 * int(agent_config_vars['sampling_interval'])
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


def getLogsFromElastic(elasticsearch,index, elasticsearchConfigVars):

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
            end_date = datetime.datetime.fromtimestamp(int(end_time / 1000)).strftime(
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

        res2 = elasticsearch.search(index=index, body=query_body)
    except:
        logger.error("Unable to get data from elasticsearch. Check config file.")
        exit()
    jsonData = []
    #

    #    res2["hits"]["hits"][n]["_source"]["groupdata"][k]["data"]
    if len(res2["hits"]["hits"]) > 0:
        for n in range(0, len(res2["hits"]["hits"])):
            logentry = {}
            # print(res2["hits"]["hits"][n]["_source"].keys())
            logentry["data"] = res2["hits"]["hits"][n]["_source"]["message"]
            logentry["tag"] = res2["hits"]["hits"][n]["_source"]['host']
            logentry["timestamp"] = time_converter(res2["hits"]["hits"][n]["_source"]["@timestamp"])
            jsonData.append(logentry)

    return jsonData


def sendData(metricData):
    sendDataTime = time.time()
    # prepare data for metric streaming agent
    toSendDataDict = {}

    toSendDataDict["userName"] = agent_config_vars['userName']
    toSendDataDict["projectName"] = agent_config_vars['projectName']
    toSendDataDict["licenseKey"] = agent_config_vars['licenseKey']
    toSendDataDict['agentType'] = 'LogStreaming'
    toSendDataDict["metricData"] = json.dumps(metricData)
    toSendDataJSON = json.dumps(toSendDataDict)
    logger.debug("TotalData: " + str(len(bytearray(toSendDataJSON))))

    # send the data

    postUrl = urlparse.urljoin(parameters['serverUrl'], "/customprojectrawdata")
    response = requests.post(postUrl, data=json.loads(toSendDataJSON))

    if response.status_code == 200:

        logger.info(str(len(bytearray(toSendDataJSON))) + " bytes of data are reported.")
    else:
        logger.info("Failed to send data.")
    logger.info(str(toSendDataJSON))
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - sendDataTime))




if __name__ == "__main__":

    parameters = get_parameters()
    log_level = parameters['logLevel']
    logger = set_logger_config(log_level)
    agent_config_vars = get_agent_config_vars()

    elasticsearchConfigVars = get_elastic_config()

    parameters = get_parameters()

    elasticsearch = getElasticSearchConnection(elasticsearchConfigVars)
    index_all = elasticsearchConfigVars['elasticsearchIndex']
    indexnames = index_all.split(',')

    for index in indexnames:
        logData = getLogsFromElastic(elasticsearch,index, elasticsearchConfigVars)

        if len(logData) == 0:
            logger.info("No data to send.")
        else:
            sendData(logData)

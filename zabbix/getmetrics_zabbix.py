#!/usr/bin/env python
import time
import sys
from optparse import OptionParser
import ConfigParser
import os
import requests
import json
import logging
from pyzabbix.api import ZabbixAPI

'''
this script gathers system info from zabbix and use http api to send to server
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


def getZabbixConfig(parameters, datadir):
    """Read and parse Zabbix config from config.txt"""
    zabbixConfig = {}
    if os.path.exists(os.path.join(parameters['homepath'], datadir, "config.txt")):
        cp = ConfigParser.SafeConfigParser()
        cp.read(os.path.join(parameters['homepath'], datadir, "config.txt"))
        zabbixConfig = {
            "ZABBIX_URL": cp.get('zabbix', 'ZABBIX_URL'),
            "ZABBIX_USER": cp.get('zabbix', 'ZABBIX_USER'),
            "ZABBIX_PASSWORD": cp.get('zabbix', 'ZABBIX_PASSWORD'),
        }
    return zabbixConfig


def getInstanceListFromFile(config, filePath):
    """Get available instance list from File"""
    dataList = set()
    with open(filePath, 'r') as f:
        for line in f:
            if line:
                dataList.add(line.replace('\n', ''))
    logger.debug("Get instance list from file: " + str(dataList))
    return list(dataList)


def getMetricData(config, hosts, startTime, endTime):
    """Get metric data from Zabbix API"""
    # connection to zabbix
    zapi = ZabbixAPI(url=config['ZABBIX_URL'], user=config['ZABBIX_USER'], password=config['ZABBIX_PASSWORD'])
    logger.info("Get connection from zabbix success")

    # get hosts
    hosts_map = {}
    hosts_ids = []
    hosts_res = zapi.do_request('host.get', {
        'filter': {
            "host": hosts,
        },
        "sortfield": "name",
        'output': 'extend'
    })
    for item in hosts_res['result']:
        host_id = item['hostid']
        host = item['host']
        hosts_ids.append(host_id)
        hosts_map[host_id] = host
    logger.info("Get hosts from zabbix: " + str(hosts_ids))

    # get items by hosts
    items_map = {}
    items_ids = []
    items_res = zapi.do_request('item.get', {
        'filter': {
            "host": hosts,
            # "type": "0"
        },
        "search": {
            # "key_": "system"
        },
        "sortfield": "name",
        'output': 'extend'
    })
    for item in items_res['result']:
        item_id = item['itemid']
        host_id = item['hostid']
        items_ids.append(item_id)
        name = item['name']
        key = item['key_']
        if '[' in key:
            keys = key.split('[')[1].split(']')[0].split(',')
            if len(keys) > 0:
                for i, k in enumerate(keys):
                    name = name.replace('$' + str(i + 1), keys[i])
        items_map[item_id] = {
            "name": name,
            "host": hosts_map.get(host_id)
        }
    logger.info("Get items from zabbix: " + str(len(items_ids)))

    # get metric data
    metrics_data = {}
    result = zapi.do_request('history.get', {
        "history": 3,
        "hostids": hosts_ids,
        "itemids": items_ids,
        'time_from': startTime,
        'time_till': endTime,
        'output': 'extend'
    })
    for info in result['result']:
        itemid = info['itemid']
        host = items_map.get(itemid, {}).get('host')
        item_name = items_map.get(itemid, {}).get('name')
        ts = info['clock']
        value = float(info['value'])
        if itemid in metrics_data:
            metrics_data[itemid]["value"].append([str(ts), value])
        else:
            metrics_data[itemid] = {
                'metric': item_name,
                'host': host,
                "value": [[str(ts), value]],
            }

    # parse data to opentsdb format
    zabbixMetricList = []
    for item_id, log in metrics_data.items():
        zabbixMetricList.append({
            "metric": log.get('metric'),
            "tags": {
                "host": log.get('host')
            },
            "aggregatedTags": [],
            "dps": log.get('value')
        })

    logger.info("Get metric data from zabbix: " + str(len(zabbixMetricList)))
    return metrics_data


def sendData(metricData):
    """Send Zabbix metric data to the InsightFinder application"""
    sendDataTime = time.time()
    # prepare data for metric streaming agent
    toSendDataDict = {}
    toSendDataDict["metricData"] = json.dumps(metricData)
    toSendDataDict["licenseKey"] = agentConfigVars['licenseKey']
    toSendDataDict["projectName"] = agentConfigVars['projectName']
    toSendDataDict["userName"] = agentConfigVars['userName']
    toSendDataDict["samplingInterval"] = str(int(reportingConfigVars['reporting_interval'] * 60))
    toSendDataDict["agentType"] = "custom"

    toSendDataJSON = json.dumps(toSendDataDict)
    logger.debug("TotalData: " + str(len(bytearray(toSendDataJSON))) + " Bytes")

    # send the data
    postUrl = parameters['serverUrl'] + "/opentsdbdata"
    response = requests.post(postUrl, data=json.loads(toSendDataJSON))
    if response.status_code == 200:
        logger.info(str(len(bytearray(toSendDataJSON))) + " bytes of data are reported.")
        logger.debug("--- Send data time: %s seconds ---" % (time.time() - sendDataTime))
    else:
        logger.info("Failed to send data.")


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
    logLevel = logging.INFO
    logger = setloggerConfig(logLevel)
    dataDirectory = 'data'
    parameters = getParameters()
    agentConfigVars = getAgentConfigVars()
    reportingConfigVars = getReportingConfigVars()

    # get agent configuration details
    agent_config = getZabbixConfig(parameters, dataDirectory)
    for item in agent_config.values():
        if not item:
            logger.error("config error, check data/config.txt")
            sys.exit("config error, check config.txt")

    dataEndTimestamp = int(time.time())
    intervalInSecs = int(reportingConfigVars['reporting_interval'] * 60)
    dataStartTimestamp = dataEndTimestamp - intervalInSecs

    try:
        logger.debug("Start to send metric data: {}-{}".format(dataStartTimestamp, dataEndTimestamp))
        # get instance list from file
        filePath = '/tmp/instances.txt'
        instanceList = getInstanceListFromFile(agent_config, filePath)
        if len(instanceList) == 0:
            logger.error("No instances to get data for.")
            sys.exit()

        chunked_list = chunks(instanceList, parameters['chunkSize'])
        for sub_list in chunked_list:
            # get metric data from zabbix every SAMPLING_INTERVAL
            metricDataList = getMetricData(agent_config, sub_list, dataStartTimestamp, dataEndTimestamp)
            if len(metricDataList) == 0:
                logger.error("No data for metrics received from Zabbix.")
                sys.exit()
            # send metric data to insightfinder
            sendData(metricDataList)
    except Exception as e:
        logger.error("Error send metric data to insightfinder: {}-{}".format(dataStartTimestamp, dataEndTimestamp))
        logger.error(e)

#!/usr/bin/env python
import collections
import json
import logging
import os
import socket
import sys
import time
from ConfigParser import SafeConfigParser
from datetime import datetime
from optparse import OptionParser
from multiprocessing import Process
import pytz
import requests
from kafka import KafkaConsumer

'''
this script gathers metrics from kafka and send to InsightFinder
'''


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-t", "--timeout",
                      action="store", dest="timeout", help="Timeout in seconds. Default is 30")
    parser.add_option("-p", "--topic",
                      action="store", dest="topic", help="Kafka topic to read data from")
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-l", "--chunkLines",
                      action="store", dest="chunkLines", help="Max number of lines in chunk")
    parser.add_option("-s", "--logLevel",
                      action="store", dest="logLevel", help="Change log verbosity(WARNING: 0, INFO: 1, DEBUG: 2)")
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
    if options.topic == None:
        parameters['topic'] = 'insightfinder_csv'
    else:
        parameters['topic'] = options.topic
    if options.timeout == None:
        parameters['timeout'] = 300
    else:
        parameters['timeout'] = int(options.timeout)
    if options.chunkLines is None:
        parameters['chunkLines'] = 10
    else:
        parameters['chunkLines'] = int(options.chunkLines)
    parameters['logLevel'] = logging.INFO
    if options.logLevel == '0':
        parameters['logLevel'] = logging.WARNING
    elif options.logLevel == '1':
        parameters['logLevel'] = logging.INFO
    elif options.logLevel >= '2':
        parameters['logLevel'] = logging.DEBUG

    return parameters


def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(os.path.join(parameters['homepath'], "kafka", "config.ini")):
            parser = SafeConfigParser()
            parser.read(os.path.join(parameters['homepath'], "kafka", "config.ini"))
            insightFinder_license_key = parser.get('kafka', 'insightFinder_license_key')
            insightFinder_project_name = parser.get('kafka', 'insightFinder_project_name')
            insightFinder_user_name = parser.get('kafka', 'insightFinder_user_name')
            sampling_interval = parser.get('kafka', 'sampling_interval')
            group_id = parser.get('kafka', 'group_id')
            client_id = parser.get('kafka', 'client_id')
            data_send_timeout = parser.get('kafka', 'data_send_timeout')
            # SSL
            security_protocol = parser.get('kafka', 'security_protocol')
            ssl_context = parser.get('kafka','ssl_context')
            ssl_check_hostname = parser.get('kafka','ssl_check_hostname')
            ssl_ca = parser.get('kafka','ssl_ca')
            ssl_certificate = parser.get('kafka','ssl_certificate')
            ssl_key = parser.get('kafka','ssl_key')
            ssl_password = parser.get('kafka','ssl_password')
            ssl_crl = parser.get('kafka','ssl_crl')
            ssl_ciphers = parser.get('kafka','ssl_ciphers')

            # SASL
            sasl_mechanism = parser.get('kafka', 'sasl_mechanism')
            sasl_plain_username = parser.get('kafka', 'sasl_plain_username')
            sasl_plain_password = parser.get('kafka', 'sasl_plain_password')
            sasl_kerberos_service_name = parser.get('kafka', 'sasl_kerberos_service_name')
            sasl_kerberos_domain_name = parser.get('kafka', 'sasl_kerberos_domain_name')
            sasl_oauth_token_provider = parser.get('kafka', 'sasl_oauth_token_provider')

            if len(insightFinder_license_key) == 0:
                logger.error("Agent not correctly configured(license key). Check config file.")
                sys.exit(1)
            if len(insightFinder_project_name) == 0:
                logger.error("Agent not correctly configured(project name). Check config file.")
                sys.exit(1)
            if len(insightFinder_user_name) == 0:
                logger.error("Agent not correctly configured(username). Check config file.")
                sys.exit(1)
            if len(sampling_interval) == 0:
                logger.error("Agent not correctly configured(sampling interval). Check config file.")
                sys.exit(1)
            if len(group_id) == 0:
                logger.error("Agent not correctly configured(group id). Check config file.")
                sys.exit(1)
            if len(data_send_timeout) == 0:
                if int(sampling_interval) == 0:
                    data_send_timeout = 60
                else:
                    data_send_timeout = int(sampling_interval)
            else:
                data_send_timeout = int(data_send_timeout)

            if len(security_protocol) == 0:
                logger.info('security_protocol not defined, assuming PLAINTEXT')
                security_protocol = 'PLAINTEXT'

            config_vars['licenseKey'] = insightFinder_license_key
            config_vars['projectName'] = insightFinder_project_name
            config_vars['userName'] = insightFinder_user_name
            config_vars['samplingInterval'] = int(sampling_interval)
            config_vars['groupId'] = group_id
            config_vars['clientId'] = client_id
            config_vars['dataSendTimeout'] = data_send_timeout    

            # SSL
            config_vars['security_protocol'] = security_protocol
            config_vars['ssl_context'] = ssl_context
            config_vars['ssl_check_hostname'] = ssl_check_hostname
            config_vars['ssl_ca'] = ssl_ca
            config_vars['ssl_certificate'] = ssl_certificate
            config_vars['ssl_key'] = ssl_key
            config_vars['ssl_password'] = ssl_password
            config_vars['ssl_crl'] = ssl_crl
            config_vars['ssl_ciphers'] = ssl_ciphers
 
            #SASL
            config_vars['sasl_mechanism'] = sasl_mechanism
            config_vars['sasl_plain_username'] = sasl_plain_username
            config_vars['sasl_plain_password'] = sasl_plain_password
            config_vars['sasl_kerberos_service_name'] = sasl_kerberos_service_name
            config_vars['sasl_kerberos_domain_name'] = sasl_kerberos_domain_name
            config_vars['sasl_oauth_token_provider'] = sasl_oauth_token_provider
    except IOError:
        logger.error("config.ini file is missing")
    return config_vars


def get_reporting_config_vars():
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


def getKafkaConfig():
    if os.path.exists(os.path.join(parameters['homepath'], "kafka", "config.ini")):
        parser = SafeConfigParser()
        parser.read(os.path.join(parameters['homepath'], "kafka", "config.ini"))
        bootstrap_servers = parser.get('kafka', 'bootstrap_servers').split(",")
        topic = parser.get('kafka', 'topic')
        filter_hosts = parser.get('kafka', 'filter_hosts').split(",")
        all_metrics = parser.get('kafka', 'all_metrics').split(",")
        all_metrics_set = set()
        if len(bootstrap_servers) == 0:
            logger.info("Using default server localhost:9092")
            bootstrap_servers = ['localhost:9092']
        if len(topic) == 0:
            print "using default topic"
            topic = 'insightfinder_metric'
        if len(filter_hosts[0]) == 0:
            filter_hosts = []
        if len(all_metrics[0]) != 0:
            for metric in all_metrics:
                all_metrics_set.add(metric)
    else:
        bootstrap_servers = ['localhost:9092']
        topic = 'insightfinder_metrics'
        filter_hosts = []
    return (bootstrap_servers, topic, filter_hosts, all_metrics_set)


def sendData(metricData):
    sendDataTime = time.time()
    # prepare data for metric streaming agent
    toSendDataDict = {}
    toSendDataDict["metricData"] = json.dumps(metricData)
    toSendDataDict["licenseKey"] = agent_config_vars['licenseKey']
    toSendDataDict["projectName"] = agent_config_vars['projectName']
    toSendDataDict["userName"] = agent_config_vars['userName']
    toSendDataDict["instanceName"] = socket.gethostname().partition(".")[0]
    toSendDataDict["samplingInterval"] = str(int(agent_config_vars['samplingInterval']) * 60)
    toSendDataDict["agentType"] = "kafka"

    toSendDataJSON = json.dumps(toSendDataDict)
    # logger.debug("TotalData: " + str(len(bytearray(toSendDataJSON))))

    # send the data
    postUrl = parameters['serverUrl'] + "/customprojectrawdata"
    response = requests.post(postUrl, data=json.loads(toSendDataJSON))
    if response.status_code == 200:
        logger.info(str(len(bytearray(toSendDataJSON))) + " bytes of data are reported.")
        # updateLastSentFiles(pcapFileList)
    else:
        logger.info("Failed to send data.")
    # logger.debug("--- Send data time: %s seconds ---" % (time.time() - sendDataTime))


def isTimeFormat(timeString, format):
    """
    Determines the validity of the input date-time string according to the given format
    Parameters:
    - `timeString` : datetime string to check validity
    - `temp_id` : datetime format to compare with
    """
    try:
        datetime.strptime(str(timeString), format)
        return True
    except ValueError:
        return False


def getTimestampForZone(dateString, timeZone, format):
    dtexif = datetime.strptime(dateString, format)
    tz = pytz.timezone(timeZone)
    tztime = tz.localize(dtexif)
    epoch = long((tztime - datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()) * 1000
    return epoch

def isReceivedAllMetrics(collectedMetrics, all_metrics):
    if len(all_metrics) == 0:
        return True
    for metric in all_metrics:
        if metric not in collectedMetrics:
            return False
    return True

def parseConsumerMessages(consumer, all_metrics_set, filter_hosts):
    raw_data_map = collections.OrderedDict()
    metric_data = []
    chunk_number = 0
    collected_values = 0
    collected_metrics_map = {}
    completed_rows_timestamp_set = set()
    buffer_time = time.time()

    for message in consumer:
        try:
            json_message = json.loads(message.value)
            logger.debug(json_message)
            timestamp = json_message.get('@timestamp', {})[:-5]
            host_name = json_message.get('beat', {}).get('hostname', {})
            metric_module = json_message.get('metricset', {}).get('module', {})
            metric_class = json_message.get('metricset', {}).get('name', {})
            if len(filter_hosts) != 0 and host_name not in filter_hosts:
                continue
            pattern = "%Y-%m-%dT%H:%M:%S"
            if isTimeFormat(timestamp, pattern):
                epoch = getTimestampForZone(timestamp, "GMT", pattern)

            # get previous collected values for timestamp if available
            # get previous collected metrics name for timestamp if available
            if epoch in raw_data_map:
                value_map = raw_data_map[epoch]
                collected_metrics_set = collected_metrics_map[epoch]
            else:
                value_map = {}
                collected_metrics_set = set()
            if metric_module == "system":
                if metric_class == "cpu":
                    cpuMetricsList = ["idle", "iowait", "irq", "nice", "softirq", "steal", "system", "user"]
                    for metric in cpuMetricsList:
                        metric_value = json_message.get('system', {}).get('cpu', {}).get(metric, {}).get('pct', '')
                        metric_name = "cpu-" + metric
                        # skip the metric that are not in the config file
                        if len(all_metrics_set) > 0 and metric_name not in all_metrics_set:
                            continue
                        header_field = metric_name + "[" + host_name + "]"
                        add_valuemap(header_field, metric_value, value_map)
                        raw_data_map[epoch] = value_map
                        # add collected metric name
                        collected_values += 1
                        collected_metrics_set.add(metric_name)
                        # update the collected metrics for this timestamp
                        collected_metrics_map[epoch] = collected_metrics_set
                elif metric_class == "memory":
                    memory_metrics_list = ["actual", "swap"]
                    for metric in memory_metrics_list:
                        metric_value = json_message.get('system', {}).get('memory', {}).get(metric, {}).get('used',{}).get(
                            'bytes', '')
                        metric_name = "memory-" + metric
                        # skip the metric that are not in the config file
                        if len(all_metrics_set) > 0 and metric_name not in all_metrics_set:
                            continue
                        header_field = metric_name + "[" + host_name + "]"
                        add_valuemap(header_field, metric_value, value_map)
                        raw_data_map[epoch] = value_map
                        # add collected metric name
                        collected_values += 1
                        collected_metrics_set.add(metric_name)
                        # update the collected metrics for this timestamp
                        collected_metrics_map[epoch] = collected_metrics_set
                elif metric_class == "filesystem":
                    if json_message.get('system', {}).get('filesystem', {}).get('mount_point', {}) != "/":
                        # logger.info("Skipping: " +  json_message.get('system', {}).get('filesystem', {}).get('mount_point', {}))
                        continue
                    # add used-bytes
                    metric_name_bytes = "filesystem/used-bytes"
                    # skip the metric that are not in the config file
                    if metric_name_bytes in all_metrics_set or len(all_metrics_set) == 0:
                        metric_value_bytes = json_message.get('system', {}).get(
                            'filesystem', {}).get('used', {}).get('bytes', '')
                        header_field_bytes = metric_name_bytes + "[" + host_name + "]"
                        add_valuemap(header_field_bytes, metric_value_bytes, value_map)
                        # add collected metric name
                        collected_metrics_set.add(metric_name_bytes)

                    # add used-pct
                    metric_name_pct = "filesystem/used-pct"
                    # skip the metric that are not in the config file
                    if metric_name_pct in all_metrics_set or len(all_metrics_set) == 0:
                        metric_value_pct = json_message.get('system', {}).get(
                            'filesystem', {}).get('used', {}).get('pct', '')
                        header_field_pct = metric_name_pct + "[" + host_name + "]"
                        add_valuemap(header_field_pct, metric_value_pct, value_map)
                        # add collected metric name
                        collected_metrics_set.add(metric_name_pct)
                    # add to raw data map
                    raw_data_map[epoch] = value_map
                    collected_values += 1
                    # update the collected metrics for this timestamp
                    collected_metrics_map[epoch] = collected_metrics_set

            # check whether collected all metrics basd on the config file
            time_diff = time.time() - buffer_time
            if (isReceivedAllMetrics(collected_metrics_set, all_metrics_set) or time_diff > agent_config_vars[
                'dataSendTimeout']):
                # add the completed timestamp into set
                completed_rows_timestamp_set.add(epoch)
                # print "All metrics collected for timestamp " + str(epoch) + " Completed rows count: " + str(len(completedRowsTimestampSet))
            number_of_completed_rows = len(completed_rows_timestamp_set)
            # check whether the number of completed rows is greater than 100
            if number_of_completed_rows >= CHUNK_METRIC_VALUES or time_diff > agent_config_vars['dataSendTimeout']:
                # go through all completed timesamp data and add to the buffer
                completed_count = 0
                if number_of_completed_rows >= CHUNK_METRIC_VALUES:
                    #if the completed Rows are exceed the chunk lines limit
                    start = str(min(completed_rows_timestamp_set))
                    end = str(max(completed_rows_timestamp_set))
                    for timestamp in completed_rows_timestamp_set:
                        # get and delete the data of the timestamp
                        if timestamp in finished_timestamp:
                            logger.debug("timestamp: " + str(timestamp) + " has already there")
                            continue
                        value_map = raw_data_map.pop(timestamp)
                        # remove recorded metric for the timestamp
                        collected_metrics_map.pop(timestamp)
                        value_map['timestamp'] = str(timestamp)
                        finished_timestamp.add(timestamp)
                        metric_data.append(value_map)
                        completed_count += 1
                else:
                    #flush the chunk here
                    for timestamp in raw_data_map.keys():
                        if timestamp in finished_timestamp:
                            logger.debug("timestamp: " + str(timestamp) + " has already there")
                            continue
                        completed_count += 1
                        value_map = raw_data_map.pop(timestamp)
                        value_map['timestamp'] = str(timestamp)
                        collected_metrics_map.pop(timestamp)
                        metric_data.append(value_map)
                        finished_timestamp.add(timestamp)
                        completed_count += 1
                chunk_number += 1
                if completed_count > 0:
                    logger.debug("Sending Chunk Number: " + str(chunk_number))
                    sendData(metric_data)
                else:
                    logger.debug("Not send Data because all data have been sent before")
                # clean the buffer and completed row set
                buffer_time = time.time()
                metric_data = []
                completed_rows_timestamp_set = set()
                collected_values = 0
        except ValueError:
            logger.error("Error parsing metric json")
            continue
    # send final chunk
    completed_count = 0
    for timestamp in raw_data_map.keys():
        if timestamp in finished_timestamp:
            logger.debug("timestamp: " + str(timestamp) + " has already there")
            continue
        completed_count += 1
        value_map = raw_data_map[timestamp]
        value_map['timestamp'] = str(timestamp)
        metric_data.append(value_map)
        finished_timestamp.add(timestamp)
    if len(metric_data) == 0:
        logger.info("No data remaining to send")
    else:
        chunk_number += 1
        if completed_count > 0:
            logger.debug("Sending Final Chunk: " + str(chunk_number))
            sendData(metric_data)
        else:
            logger.debug("Not send Data because all data have been sent before")


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


class LessThanFilter(logging.Filter):
    def __init__(self, exclusive_maximum, name=""):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        # non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0

def add_valuemap(header_field, metric_value, valueMap):
    # use the next non-null value to overwrite the prev value
    # for the same metric in the same timestamp
    if header_field in valueMap.keys():
        if metric_value is not None and len(str(metric_value)) > 0:
            valueMap[header_field] = str(metric_value)
    else:
        valueMap[header_field] = str(metric_value)

def kafka_data_consumer(consumer_id):
    (brokers, topic, filter_hosts, all_metrics_set) = getKafkaConfig()
    # initialize shared kwargs 
    kafka_kwargs = {
            'bootstrap_servers': brokers,
            'auto_offset_reset': 'latest',
            'consumer_timeout_ms': 1000 * parameters['timeout'],
            'group_id': agent_config_vars['groupId'],
            'api_version': (0, 9)
            }

    # add client ID if given
    if agent_config_vars["clientId"] != "":
        kafka_kwargs['client_id'] = agent_config_vars["clientId"]

    # add SSL info
    if agent_config_vars['security_protocol'] == 'SSL': 
        kafka_kwargs['security_protocol'] = 'SSL'
        if agent_config_vars['ssl_context'] != "":
            kafka_kwargs['ssl_context'] = agent_config_vars['ssl_context']
        if agent_config_vars['ssl_check_hostname'] == "False":
            kafka_kwargs['ssl_check_hostname'] = False
        if agent_config_vars['ssl_ca'] != "":
            kafka_kwargs['ssl_cafile'] = agent_config_vars['ssl_ca']
        if agent_config_vars['ssl_certificate'] != "":
            kafka_kwargs['ssl_certfile'] = agent_config_vars['ssl_certificate']
        if agent_config_vars['ssl_key'] != "":
            kafka_kwargs['ssl_keyfile'] = agent_config_vars['ssl_key']
        if agent_config_vars['ssl_password'] != "":
            kafka_kwargs['ssl_password'] = agent_config_vars['ssl_password'].strip()
        if agent_config_vars['ssl_crl'] != "":
            kafka_kwargs['ssl_crlfile'] = agent_config_vars['ssl_crl']
        if agent_config_vars['ssl_ciphers'] != "":
            kafka_kwargs['ssl_ciphers'] = agent_config_vars['ssl_ciphers']
        
    # add SASL info
    if len(agent_config_vars['sasl_mechanism']) != 0:
        kafka_kwargs['sasl_mechanism'] = agent_config_vars['sasl_mechanism']

        if agent_config_vars['sasl_plain_username'] != "":
            kafka_kwargs['sasl_plain_username'] = agent_config_vars['sasl_plain_username'] 
            
        if agent_config_vars['sasl_plain_password'] != "":
            kafka_kwargs['sasl_plain_password'] = agent_config_vars['sasl_plain_password'] 

        if agent_config_vars['sasl_kerberos_service_name'] != "": 
            kafka_kwargs['sasl_kerberos_service_name'] = agent_config_vars['sasl_kerberos_service_name'] 

        if agent_config_vars['sasl_kerberos_domain_name'] != "": 
            kafka_kwargs['sasl_kerberos_domain_name'] = agent_config_vars['sasl_kerberos_domain_name'] 

        if agent_config_vars['sasl_oauth_token_provider '] != "":
            kafka_kwargs['sasl_oauth_token_provider '] = agent_config_vars['sasl_oauth_token_provider '] 

    logger.debug(kafka_kwargs)
    consumer = KafkaConsumer(**kafka_kwargs)
    logger.info("Started metric consumer number " + consumer_id)
    consumer.subscribe([topic])
    parseConsumerMessages(consumer, all_metrics_set, filter_hosts)
    consumer.close()
    logger.info("Closed log consumer number " + consumer_id)


if __name__ == "__main__":
    GROUPING_START = 15000
    parameters = get_parameters()
    log_level = parameters['logLevel']
    CHUNK_METRIC_VALUES = parameters['chunkLines']
    logger = set_logger_config(log_level)
    agent_config_vars = get_agent_config_vars()
    finished_timestamp = set()
    # reporting_config_vars = get_reporting_config_vars()

    # path to write the daily csv file
    data_directory = 'data/'
    prev_csv_header_list = "timestamp,"
    hostname = socket.gethostname().partition(".")[0]
    try:
        t1 = Process(target=kafka_data_consumer, args=('1',))
        t2 = Process(target=kafka_data_consumer, args=('2',))
        t1.start()
        t2.start()
    except KeyboardInterrupt:
        print "Interrupt from keyboard"

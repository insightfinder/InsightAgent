#!/usr/bin/env python
import json
import logging
import os
import socket
import sys
import time
from ConfigParser import SafeConfigParser
from datetime import datetime
from multiprocessing import Process
from optparse import OptionParser

import pytz
import requests
from kafka import KafkaConsumer

'''
this script gathers logs from kafka and send to InsightFinder
'''


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-t", "--timeout",
                      action="store", dest="timeout", help="Timeout in seconds. Default is 30")
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-l", "--chunkLines",
                      action="store", dest="chunkLines", help="Max number of lines in chunk")
    parser.add_option("-p", "--project",
                      action="store", dest="project", help="Insightfinder Project to send data to")
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
    if options.timeout is None:
        parameters['timeout'] = 86400
    else:
        parameters['timeout'] = int(options.timeout)
    if options.chunkLines is None:
        parameters['chunk_lines'] = 1000
    else:
        parameters['chunk_lines'] = int(options.chunkLines)
    if options.project is None:
        parameters['project'] = None
    else:
        parameters['project'] = options.project

    return parameters

def get_reporting_config_vars():
    reporting_config_vars = {}
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), 'r') as f:
        config = json.load(f)
    reporting_interval_string = config['reporting_interval']
    if reporting_interval_string[-1:] == 's':
        reporting_interval = float(config['reporting_interval'][:-1])
        reporting_config_vars['reporting_interval'] = float(reporting_interval / 60.0)
    else:
        reporting_config_vars['reporting_interval'] = int(config['reporting_interval'])
        reporting_config_vars['keep_file_days'] = int(config['keep_file_days'])
        reporting_config_vars['prev_endtime'] = config['prev_endtime']
        reporting_config_vars['deltaFields'] = config['delta_fields']

    reporting_config_vars['keep_file_days'] = int(config['keep_file_days'])
    reporting_config_vars['prev_endtime'] = config['prev_endtime']
    reporting_config_vars['deltaFields'] = config['delta_fields']
    return reporting_config_vars


def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(os.path.join(parameters['homepath'], "kafka_logs", "config.ini")):
            parser = SafeConfigParser()
            parser.read(os.path.join(parameters['homepath'], "kafka_logs", "config.ini"))
            licenseKey = parser.get('kafka', 'insightFinder_license_key')
            projectName = parser.get('kafka', 'insightFinder_project_name')
            userName = parser.get('kafka', 'insightFinder_user_name')
            samplingInterval = parser.get('kafka', 'sampling_interval')
            groupId = parser.get('kafka', 'group_id')
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
            config_vars['licenseKey'] = licenseKey
            config_vars['projectName'] = projectName
            config_vars['userName'] = userName
            config_vars['samplingInterval'] = samplingInterval
            config_vars['groupId'] = groupId
    except IOError:
        logger.error("config.ini file is missing")
    return config_vars


def get_kafka_config():
    if os.path.exists(os.path.join(parameters['homepath'], "kafka_logs", "config.ini")):
        parser = SafeConfigParser()
        parser.read(os.path.join(parameters['homepath'], "kafka_logs", "config.ini"))
        bootstrap_servers = parser.get('kafka', 'bootstrap_servers').split(",")
        topic = parser.get('kafka', 'topic')
        filter_hosts = parser.get('kafka', 'filter_hosts').split(",")

        if len(bootstrap_servers) == 0:
            logger.info("Using default server localhost:9092")
            bootstrap_servers = ['localhost:9092']
        if len(topic) == 0:
            print "using default topic"
            topic = 'insightfinder_logs'
        if len(filter_hosts[0]) == 0:
            filter_hosts = []
    else:
        bootstrap_servers = ['localhost:9092']
        topic = 'insightfinder_logs'
        filter_hosts = []
    return bootstrap_servers, topic, filter_hosts


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


def send_data(metric_data):
    """ Sends parsed metric data to InsightFinder """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = dict()
    to_send_data_dict["metricData"] = json.dumps(metric_data)
    to_send_data_dict["licenseKey"] = agentConfigVars['licenseKey']
    if parameters['project'] is None:
        to_send_data_dict["projectName"] = agentConfigVars['projectName']
    else:
        to_send_data_dict["projectName"] = parameters['project']
    to_send_data_dict["userName"] = agentConfigVars['userName']
    to_send_data_dict["instanceName"] = socket.gethostname().partition(".")[0]
    to_send_data_dict["samplingInterval"] = str(int(reportingConfigVars['reporting_interval'] * 60))
    to_send_data_dict["agentType"] = "LogStreaming"

    to_send_data_json = json.dumps(to_send_data_dict)
    # logger.debug("TotalData: " + str(len(bytearray(to_send_data_json))))
    # logger.debug("Data: " + str(to_send_data_json))

    # send the data
    post_url = parameters['serverUrl'] + "/customprojectrawdata"
    response = requests.post(post_url, data=json.loads(to_send_data_json))
    if response.status_code == 200:
        logger.info(str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
    else:
        logger.info("Failed to send data.")
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - send_data_time))


def parse_consumer_messages(consumer, filter_hosts):
    line_count = 0
    chunk_count = 0
    current_row = []
    start_time = time.time()
    for message in consumer:
        try:
            json_message = json.loads(message.value)
            # logger.info(json_message)
            host_name = json_message.get('beat', {}).get('hostname', {})
            message = json_message.get('message', {})
            timestamp = json_message.get('@timestamp', {})[:-5]

            if len(filter_hosts) != 0 and host_name.upper() not in (filter_host.upper() for filter_host in
                                                                    filter_hosts):
                continue

            if line_count == parameters['chunk_lines']:
                logger.debug("--- Chunk creation time: %s seconds ---" % (time.time() - start_time))
                send_data(current_row)
                current_row = []
                chunk_count += 1
                line_count = 0
                start_time = time.time()

            pattern = "%Y-%m-%dT%H:%M:%S"
            if is_time_format(timestamp, pattern):
                try:
                    epoch = get_timestamp_for_zone(timestamp, "GMT", pattern)
                except ValueError:
                    continue

            current_log_msg = dict()
            current_log_msg['timestamp'] = epoch
            current_log_msg['tag'] = host_name
            current_log_msg['data'] = message
            current_row.append(current_log_msg)
            line_count += 1
        except:
            continue

    if len(current_row) != 0:
        logger.debug("--- Chunk creation time: %s seconds ---" % (time.time() - start_time))
        send_data(current_row)
        chunk_count += 1
    logger.debug("Total chunks created: " + str(chunk_count))


def set_logger_config():
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


def kafka_data_consumer(consumer_id):
    logger.info("Started log consumer number " + consumer_id)
    # Kafka consumer configuration
    (brokers, topic, filter_hosts) = get_kafka_config()
    consumer = KafkaConsumer(bootstrap_servers=brokers,
                             auto_offset_reset='latest', consumer_timeout_ms=1000 * parameters['timeout'],
                             group_id=agentConfigVars['groupId'])
    consumer.subscribe([topic])
    parse_consumer_messages(consumer, filter_hosts)
    consumer.close()
    logger.info("Closed log consumer number " + consumer_id)


if __name__ == "__main__":
    logger = set_logger_config()
    parameters = get_parameters()
    agentConfigVars = get_agent_config_vars()
    reportingConfigVars = get_reporting_config_vars()

    try:
        t1 = Process(target=kafka_data_consumer, args=('1',))
        t2 = Process(target=kafka_data_consumer, args=('2',))
        t1.start()
        t2.start()
    except KeyboardInterrupt:
        print "Interrupt from keyboard"

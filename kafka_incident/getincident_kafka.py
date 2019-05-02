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
import subprocess
import pytz
import requests
from kafka import KafkaConsumer
import re

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
    return reporting_config_vars


def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(os.path.join(parameters['homepath'], "kafka_incident", "config.ini")):
            parser = SafeConfigParser()
            parser.read(os.path.join(parameters['homepath'], "kafka_incident", "config.ini"))
            license_key = parser.get('insightfinder', 'license_key')
            project_name = parser.get('insightfinder', 'project_name')
            user_name = parser.get('insightfinder', 'user_name')
            token = parser.get('insightfinder', 'token')
            url = parser.get('insightfinder', 'url')
            sampling_interval = parser.get('kafka', 'sampling_interval')
            client_id = parser.get('kafka', 'client_id')
            group_id = parser.get('kafka', 'group_id')
            host_name_field = parser.get('kafka', 'host_name_field')
            timestamp_field = parser.get('kafka', 'timestamp_field')
            message_field = parser.get('kafka', 'message_field').split(",")
            app_name_field = parser.get('kafka', 'app_name_field')
            group_name_field = parser.get('kafka', 'group_name_field')
            if len(license_key) == 0:
                logger.error("Agent not correctly configured(license key). Check config file.")
                sys.exit(1)
            if len(project_name) == 0:
                logger.error("Agent not correctly configured(project name). Check config file.")
                sys.exit(1)
            if len(user_name) == 0:
                logger.error("Agent not correctly configured(username). Check config file.")
                sys.exit(1)
            if len(sampling_interval) == 0:
                logger.error("Agent not correctly configured(sampling interval). Check config file.")
                sys.exit(1)
            if len(group_id) == 0:
                logger.error("Agent not correctly configured(group id). Check config file.")
                sys.exit(1)
            if len(host_name_field) == 0:
                logger.error("Agent not correctly configured(host_name_field). Check config file.")
                sys.exit(1)
            if len(timestamp_field) == 0:
                logger.error("Agent not correctly configured(timestamp_field). Check config file.")
                sys.exit(1)
            if len(message_field[0]) == 0:
                logger.error("Agent not correctly configured(message_field). Check config file.")
                sys.exit(1)
            config_vars['hostName'] = host_name_field
            config_vars['timestamp'] = timestamp_field
            config_vars['messageField'] = message_field
            config_vars['appName'] = app_name_field
            config_vars['groupName'] = group_name_field
            config_vars['licenseKey'] = license_key
            config_vars['projectName'] = project_name
            config_vars['userName'] = user_name
            config_vars['samplingInterval'] = sampling_interval
            config_vars['groupId'] = group_id
            config_vars['clientId'] = client_id
            config_vars['token'] = token
            config_vars['url'] = url
    except IOError:
        logger.error("config.ini file is missing")
    return config_vars


def get_kafka_config():
    if os.path.exists(os.path.join(parameters['homepath'], "kafka_incident", "config.ini")):
        parser = SafeConfigParser()
        parser.read(os.path.join(parameters['homepath'], "kafka_incident", "config.ini"))
        bootstrap_servers = parser.get('kafka', 'bootstrap_servers').split(",")
        topic = parser.get('kafka', 'topic')
        filter_hosts = parser.get('kafka', 'filtered_hosts').split(",")
        filter_apps = parser.get('kafka', 'filtered_apps').split(",")

        if len(bootstrap_servers) == 0:
            logger.info("Using default server localhost:9092")
            bootstrap_servers = ['localhost:9092']
        if len(topic) == 0:
            print "using default topic"
            topic = 'insightfinder_incident'
        if len(filter_hosts[0]) == 0:
            filter_hosts = []
        if len(filter_apps[0]) == 0:
            filter_apps = []
    else:
        bootstrap_servers = ['localhost:9092']
        topic = 'insightfinder_incident'
        filter_hosts = []
        filter_apps = []
    return bootstrap_servers, topic, filter_hosts, filter_apps


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


def get_json_info(json_message):
    host_name = ""
    message = {}
    timestamp = ""
    host_name_json = json_message
    app_name_json = json_message
    group_name_json = json_message
    timestamp_json = json_message
    host_name_field = config_vars['hostName'].split("->")
    timestamp_field = config_vars['timestamp'].split("->")
    message_fields = config_vars['messageField']
    app_name_field = config_vars['appName'].split("->")
    group_name_field = config_var['groupName'].split("->")
    
    for host_name_parameter in host_name_field:
        host_name_json = host_name_json.get(host_name_parameter.strip(), {})
        if len(host_name_json) == 0:
            break
    host_name = host_name_json.strip()

    if len(app_name_field) > 0:
        for app_name_parameter in app_name_field:
            app_name_json = app_name_json.get(app_name_parameter.strip(), {})
            if len(app_name_json) == 0:
                break
        app_name = app_name_json.strip()
    else:
        app_name = ''

    if len(group_name_field) > 0:
        for group_name_parameter in group_name_field:
            group_name_json = group_name_json.get(group_name_parameter.strip(), {})
            if len(group_name_json) == 0:
                break
        group_name = group_name_json.strip()
    else:
        group_name = ''

    for timestamp_parameter in timestamp_field:
        timestamp_json = timestamp_json.get(timestamp_parameter.strip(), {})
        if len(timestamp_json) == 0:
            break
    timestamp = timestamp_json
    
    for message_field in message_fields:
        message_field = message_field.split("->")
        message_json = json_message
        prefix = ""
        for message_field_parameter in message_field:
            message_json = message_json.get(message_field_parameter.strip(), {})
            prefix = str(message_field_parameter.strip())
            if len(message_json) == 0:
                break
        if len(message_json) != 0:
            message[prefix] = message_json
    timestamp = timestamp.replace(" ", "T")
    return host_name, message, timestamp, app_name, group_name


def safe_project_name(name):
    safe_name = re.sub(r'[^0-9a-zA-Z\_\-]+', '-', name)
    return safe_name


def safe_group_name(name):
    safe_name = re.sub(r'[\_]+', '-', name)
    return safe_name


def get_fallback_project_name(host_name):
    fallback_project = host_name
    if fallback_project == '':
        if parameters['project'] is None:
            fallback_project = config_vars['projectName']
        else:
            fallback_project = parameters['project']
    return fallback_project


def send_data(metric_data, app_name, group_name):
    """ Sends parsed metric data to InsightFinder """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = dict()
    to_send_data_dict["incidentData"] = json.dumps(metric_data)
    to_send_data_dict["licenseKey"] = config_vars['licenseKey']
    to_send_data_dict["projectName"] = get_fallback_project_name('')
    to_send_data_dict["userName"] = config_vars['userName']
    to_send_data_dict["instanceName"] = socket.gethostname().partition(".")[0]
    to_send_data_dict["samplingInterval"] = config_vars['samplingInterval']
    to_send_data_dict["agentType"] = "LogStreaming"
    if len(config_vars['url']) > 0:
        url = config_vars['url']
    else:
        url = parameters['serverUrl']

    to_send_data_json = json.dumps(to_send_data_dict)
    # logger.debug("TotalData: " + str(len(bytearray(to_send_data_json))))
    # logger.debug("Data: " + str(to_send_data_json))

    # check for existing project
    if 'token' in config_vars.keys() and config_vars['token'] is not None:
        fallback_project_name = to_send_data_dict["projectName"]
        to_send_data_dict["projectName"] = safe_project_name(app_name)
        try:
            output_check_project = subprocess.check_output('curl "' + url + '/api/v1/getprojectstatus?userName=' + config_vars['userName'] + '&token=' + config_vars['token'] + '&projectList=%5B%7B%22projectName%22%3A%22' + to_send_data_dict["projectName"] + '%22%2C%22customerName%22%3A%22' + config_vars['userName'] + '%22%2C%22projectType%22%3A%22CUSTOM%22%7D%5D&tzOffset=-14400000"', shell=True)
            # create project if no existing project
            if to_send_data_dict["projectName"] not in output_check_project:
                output_create_project = subprocess.check_output('no_proxy= curl -d "userName=' + config_vars['userName'] + '&token=' + config_vars['token'] + '&projectName=' + to_send_data_dict["projectName"] + '&instanceType=PrivateCloud&projectCloudType=PrivateCloud&dataType=Incident&samplingInterval=1&samplingIntervalInSeconds=60&zone=&email=&access-key=&secrete-key=&insightAgentType=Custom" -H "Content-Type: application/x-www-form-urlencoded" -X POST ' + url + ':8080/api/v1/add-custom-project?tzOffset=-18000000', shell=True)
                
                # try to add new project to system
                if len(group_name) != 0:
                    output_update_project = subprocess.check_output('no_proxy= curl -d "userName=' + config_vars['userName'] + '&token=' + config_vars['token'] + '&operation=updateprojsettings&projectName=' + to_send_data_dict["projectName"] + '&systemName=' + safe_group_name(group_name) + '" -H "Content-Type: application/x-www-form-urlencoded" -X POST ' + url + ':8080/api/v1/projects/update?tzOffset=-18000000', shell=True)
        except subprocess.CalledProcessError as e:
            logger.error("Unable to create project for " + to_send_data_dict["projectName"] + '. Data will be sent to ' + to_send_data_dict["fallback_projectName"])
            to_send_data_dict["projectName"] = fallback_project_name
    
    # send the data
    post_url = url + "/incidentdatareceive"
    response = requests.post(post_url, data=json.loads(to_send_data_json))
    if response.status_code == 200:
        logger.info(str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
    else:
        logger.info("Failed to send data.")
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - send_data_time))


def parse_consumer_messages(consumer, filter_hosts, filter_apps):
    line_count = dict()
    chunk_count = 0
    current_row = dict()
    start_time = time.time()
    for message in consumer:
        try:
            json_message = json.loads(message.value)
            if 'u_table' not in json_message or json_message.get('u_table', {}).strip() != 'problem':
                continue
            (host_name, message, timestamp, app_name, group_name) = get_json_info(json_message)
            if len(host_name) == 0 or len(message) == 0 or len(timestamp) == 0 or
                 (len(filter_hosts) != 0 and host_name.upper() not in (filter_host.upper().strip() for filter_host in filter_hosts)) or
                 (app_name != '' and len(filter_apps) != 0 and app_name.upper() not in (filter_app.upper().strip() for filter_app in filter_apps)):
                continue
            
            # if no app_name found, use host_name
            if len(app_name) == 0:
                app_name = host_name

            # set line count
            if app_name in line_count:
                line_count[app_name] += 1
            else:
                line_count[app_name] = 1
                current_row[app_name] = []
                
            if line_count[app_name] >= parameters['chunk_lines']:
                logger.debug("--- Chunk creation time: %s seconds ---" % (time.time() - start_time))
                send_data(current_row[app_name], app_name, group_name)
                current_row[app_name] = []
                chunk_count += 1
                line_count[app_name] = 0
                start_time = time.time()

            pattern = "%Y-%m-%dT%H:%M:%S"
            if is_time_format(timestamp, pattern):
                try:
                    epoch = get_timestamp_for_zone(timestamp, "GMT", pattern)
                except ValueError:
                    continue
            current_log_msg = dict()
            current_log_msg['timestamp'] = epoch
            current_log_msg['instanceName'] = host_name
            current_log_msg['data'] = json.dumps(message)
            current_row[app_name].append(current_log_msg)
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
    (brokers, topic, filter_hosts, filter_apps) = get_kafka_config()
    if config_vars['clientId'] == "":
        consumer = KafkaConsumer(bootstrap_servers=brokers,
                                 auto_offset_reset='latest', consumer_timeout_ms=1000 * parameters['timeout'],
                                 group_id=config_vars['groupId'])
    else:
        consumer = KafkaConsumer(bootstrap_servers=brokers,
                                 auto_offset_reset='latest', consumer_timeout_ms=1000 * parameters['timeout'],
                                 group_id=config_vars['groupId'], client_id=config_vars['clientId'])
    consumer.subscribe([topic])
    parse_consumer_messages(consumer, filter_hosts, filter_apps)
    consumer.close()
    logger.info("Closed log consumer number " + consumer_id)


if __name__ == "__main__":
    logger = set_logger_config()
    parameters = get_parameters()
    config_vars = get_agent_config_vars()
    #reporting_config_vars = get_reporting_config_vars()

    try:
        t1 = Process(target=kafka_data_consumer, args=('1',))
        t2 = Process(target=kafka_data_consumer, args=('2',))
        t1.start()
        t2.start()
    except KeyboardInterrupt:
        print "Interrupt from keyboard"

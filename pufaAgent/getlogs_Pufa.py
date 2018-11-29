#!/usr/bin/env python
# -*- coding: utf-8 -*-
import collections
import json
import logging
import os
import random
import socket
import sys
import time
from ConfigParser import SafeConfigParser
from datetime import datetime
from optparse import OptionParser
import requests
import socket
import pandas as pd
import pytz
from time import gmtime, strftime

def set_logger_config():
    # Get the root logger
    logger = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger.setLevel(logging.DEBUG)
    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.INFO)
    logging_handler_out.addFilter(less_than_filter(logging.WARNING))
    logger.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logger.addHandler(logging_handler_err)
    return logger


class less_than_filter(logging.Filter):
    def __init__(self, exclusive_maximum, name=""):
        super(less_than_filter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        # non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0

def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-w", "--server_url",
                      action="store", dest="server_url", help="Server Url")
    parser.add_option("-l", "--chunk_lines",
                      action="store", dest="chunk_lines", help="Max number of lines in chunk")
    parser.add_option("-m", "--max_in_tag",
                      action="store", dest="max_in_tag", help="Max number of one tag can have")
    (options, args) = parser.parse_args()

    parameters = {}
    if options.homepath is None:
        parameters['homepath'] = os.getcwd()
    else:
        parameters['homepath'] = options.homepath
    if options.server_url == None:
        parameters['server_url'] = 'https://app.insightfinder.com'
    else:
        parameters['server_url'] = options.server_url
    if options.chunk_lines is None:
        parameters['chunk_lines'] = 1000
    else:
        parameters['chunk_lines'] = int(options.chunk_lines)
    if options.max_in_tag is None:
        parameters['max_in_tag'] = 200
    else:
        parameters['max_in_tag'] = int(options.max_in_tag)
    return parameters


def is_time_format(time_string, datetime_format):
    """
    Determines the validity of the input date-time string according to the given format
    Parameters:
    - `time_string` : datetime string to check validity
    - `datetime_format` : datetime format to compare with
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

def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(os.path.join(parameters['homepath'], "pufaAgent", "config.ini")):
            parser = SafeConfigParser()
            parser.read(os.path.join(parameters['homepath'], "pufaAgent", "config.ini"))
            tag = parser.get('pufa', 'tag')
            file_name = parser.get('pufa', 'file_name')
            license_key = parser.get('pufa', 'insightFinder_license_key')
            project_name = parser.get('pufa', 'insightFinder_project_name')
            user_name = parser.get('pufa', 'insightFinder_user_name')
            sampling_interval = parser.get('pufa', 'sampling_interval')
            if len(tag) == 0:
                logger.error("Agent not correctly configured(tag name). Check config file.")
                sys.exit(1)
            if len(file_name) == 0:
                logger.error("Agent not correctly configured(file name). Check config file.")
                sys.exit(1)
            if len(license_key) == 0:
                logger.error("Agent not correctly configured(license key). Check config file.")
                sys.exit(1)
            if len(project_name) == 0:
                logger.error("Agent not correctly configured(project name). Check config file.")
                sys.exit(1)
            if len(user_name) == 0:
                logger.error("Agent not correctly configured(user name). Check config file.")
                sys.exit(1)
            if len(sampling_interval) == 0:
                logger.error("Agent not correctly configured(sampling interval). Check config file.")
                sys.exit(1)
            config_vars['tag'] = tag
            config_vars['file_name'] = file_name
            config_vars['license_key'] = license_key
            config_vars['project_name'] = project_name
            config_vars['user_name'] = user_name
            if sampling_interval[-1:] == 's':
                config_vars['sampling_interval'] = float(float(sampling_interval[:-1]) / 60.0)
            else:
                config_vars['sampling_interval'] = int(sampling_interval)
    except IOError:
        logger.error("config.ini file is missing")
    return config_vars


def read_message():
    collected_logs_map = {}

    file = parameters['homepath'] + '/data/' + config_vars['file_name']

    read_file = pd.read_excel(file, sheet_name='Sheet1')

    for i in read_file.index:
        tag = read_file[config_vars['tag']][i]
        host_address = read_file['host_address'][i]
        host_name = read_file['host_name'][i]
        event_content = read_file['event_content'][i]
        timestamp = strftime("%Y-%m-%d %H:%M:%S", gmtime())
        timestamp = timestamp.replace(" ", "T")
        pattern = "%Y-%m-%dT%H:%M:%S"

        if is_time_format(timestamp, pattern):
            try:
                epoch = get_timestamp_for_zone(timestamp, "GMT", pattern)
            except ValueError:
                continue
        current_log_msg = dict()
        current_log_msg['timestamp'] = epoch
        current_log_msg['tag'] = str(tag)
        current_log_msg['data'] = "event content:" + str(event_content) + " host address:" + str(host_address) + " host name:" + str(host_name)
        if tag not in collected_logs_map:
            collected_logs_map[tag] = []
        collected_logs_map[tag].append(current_log_msg)
        if len(collected_logs_map[tag])>=parameters['max_in_tag']:
            send_data(collected_logs_map[tag])
            collected_logs_map.pop(tag)
        elif len(collected_logs_map)>=parameters['chunk_lines']:
            for key in collected_logs_map:
                send_data(collected_logs_map[key])
            collected_logs_map = {}

    for key in collected_logs_map:
        send_data(collected_logs_map[key])


def send_data(metric_data):
    """ Sends parsed metric data to InsightFinder """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = dict()
    #for backend so this is the camel case in to_send_data_dict
    to_send_data_dict["metricData"] = json.dumps(metric_data)
    to_send_data_dict["licenseKey"] = config_vars['license_key']
    to_send_data_dict["projectName"] = config_vars['project_name']
    to_send_data_dict["userName"] = config_vars['user_name']
    to_send_data_dict["instanceName"] = socket.gethostname().partition(".")[0]
    to_send_data_dict["samplingInterval"] = str(int(config_vars['sampling_interval'] * 60))
    to_send_data_dict["agentType"] = "LogStreaming"

    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = parameters['server_url'] + "/customprojectrawdata"
    response = requests.post(post_url, data=json.loads(to_send_data_json))
    if response.status_code == 200:
        logger.info(str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
    else:
        logger.error("Failed to send data.")
    logger.info("--- Send data time: %s seconds ---" % (time.time() - send_data_time))


if __name__ == "__main__":
    reload(sys)
    sys.setdefaultencoding('utf-8')
    logger = set_logger_config()
    parameters = get_parameters()
    config_vars = get_agent_config_vars()
    try:
        read_message()
    except KeyboardInterrupt:
        logger.info("Interrupt from keyboard")

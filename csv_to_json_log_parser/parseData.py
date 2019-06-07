#!/usr/bin/env python
# -*- coding: utf-8 -*-
import collections
import csv
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
import codecs
from xlrd import open_workbook
from time import gmtime, strftime

directory = "Config"
file_name_key = 'file_name'
project_name_key = 'project_name'
user_name_key = 'user_name'
instance_name_key = 'instance_name'
timestamp_key = 'timestamp'
timestamp_pattern_key = 'timestamp_pattern'
keys_to_filter_key = 'keys_to_filter'

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

    #utc_time = datetime.strptime(date_string, datetime_format)
    #epoch_time = (utc_time - datetime(1970, 1, 1)).total_seconds()
    return epoch

def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(os.path.join(parameters['homepath'], "config.ini")):
            parser = SafeConfigParser()
            parser.read(os.path.join(parameters['homepath'], "config.ini"))
            file_name = parser.get(directory, 'file_name')
            license_key = parser.get(directory, 'insightFinder_license_key')
            project_name = parser.get(directory, 'insightFinder_project_name')
            user_name = parser.get(directory, 'insightFinder_user_name')
            sampling_interval = parser.get(directory, 'sampling_interval')
            timestamp = parser.get(directory, 'timestamp_key')
            timestamp_pattern = parser.get(directory, 'timestamp_pattern')
            instance_name = parser.get(directory, 'instance_name_key')
            keys_to_filter = json.loads(parser.get(directory, 'keys_to_filter'))
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
            if len(timestamp) == 0:
                logger.error("Agent not correctly configured(timestamp). Check config file.")
                sys.exit(1)
            if len(timestamp_pattern) == 0:
                logger.error("Agent not correctly configured(timestamp pattern). Check config file.")
                sys.exit(1)
            if len(instance_name) == 0:
                logger.error("Agent not correctly configured(instance name). Check config file.")
                sys.exit(1)
            config_vars[file_name_key] = file_name
            config_vars['license_key'] = license_key
            config_vars[project_name_key] = project_name
            config_vars[user_name_key] = user_name
            config_vars[timestamp_key] = timestamp
            config_vars[timestamp_pattern_key] = timestamp_pattern
            config_vars[instance_name_key] = instance_name
            config_vars[keys_to_filter_key] = keys_to_filter
            if sampling_interval[-1:] == 's':
                config_vars['sampling_interval'] = float(float(sampling_interval[:-1]) / 60.0)
            else:
                config_vars['sampling_interval'] = int(sampling_interval)
    except IOError:
        logger.error("config.ini file is missing")
    return config_vars

def read_message():
    collected_logs_map = {}
    json_keys = []
    file_path = parameters['homepath'] + '/' + config_vars[file_name_key]
    wb = open_workbook(file_path)
    count = 0
    keys_to_filter_list = config_vars[keys_to_filter_key]
    for sheet in wb.sheets():
        for row in range(sheet.nrows):
            timestamp = 0
            raw_data = {}
            current_log_msg = dict()
            for col in range (sheet.ncols):
                value = sheet.cell(row, col).value
                if (count == 0):
                    json_keys.append(value)
                else:
                    if (json_keys[col] == config_vars[timestamp_key]):
                        timestamp = value
                        continue
                    if (json_keys[col] not in keys_to_filter_list):
                        raw_data[json_keys[col]] = value
            if (timestamp == 0 and count != 0):
                logger.info("Corrupted timestamp field.")
                continue
            tag = "unknownApplication"
            if (count != 0):
                tag = raw_data[config_vars[instance_name_key]]
                current_log_msg['timestamp'] = get_timestamp_for_zone(timestamp, "GMT", config_vars[timestamp_pattern_key])
                current_log_msg['tag'] = tag
                current_log_msg['data'] = raw_data
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
            count += 1
            
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

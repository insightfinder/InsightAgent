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
from openpyxl import load_workbook
import pytz
#
# def set_logger_config():
#     # Get the root logger
#     logger = logging.getLogger(__name__)
#     # Have to set the root logger level, it defaults to logging.WARNING
#     logger.setLevel(logging.DEBUG)
#     # route INFO and DEBUG logging to stdout from stderr
#     logging_handler_out = logging.StreamHandler(sys.stdout)
#     logging_handler_out.setLevel(logging.DEBUG)
#     logging_handler_out.addFilter(LessThanFilter(logging.WARNING))
#     logger.addHandler(logging_handler_out)
#
#     logging_handler_err = logging.StreamHandler(sys.stderr)
#     logging_handler_err.setLevel(logging.WARNING)
#     logger.addHandler(logging_handler_err)
#     return logger

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
    (options, args) = parser.parse_args()

    parameters = {}
    if options.homepath is None:
        parameters['homepath'] = os.getcwd()
    else:
        parameters['homepath'] = options.homepath
    if options.serverUrl == None:
        parameters['serverUrl'] = 'http://stg.insightfinder.com'
        #parameters['serverUrl'] = 'http://127.0.0.1:8080'
    else:
        parameters['serverUrl'] = options.serverUrl
    if options.timeout == None:
        parameters['timeout'] = 300
    else:
        parameters['timeout'] = int(options.timeout)
    if options.chunkLines is None:
        parameters['chunkLines'] = 10
    else:
        parameters['chunkLines'] = int(options.chunkLines)

    return parameters


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

# def parseXlsx():
#     line_count = 0
#     chunk_count = 0
#     current_row = []
#     start_time = time.time()
#
#     file = 'event.xlsx'
#
#     df = pd.read_excel(file, sheet_name='Sheet1')
#
#     for i in df.index:
#         host_address = df['host_address'][i]
#         host_name = df['host_name'][i]
#         event_content = df['event_content'][i]
#         cmdb_application = df['cmdb_application'][i]
#         timestamp = "2018-11-05 13:26:41"
#         timestamp = timestamp.replace(" ", "T")
#         if line_count == parameters['chunkLines']:
#             print("--- Chunk creation time: %s seconds ---" % (time.time() - start_time))
#             send_data(current_row)
#             current_row = []
#             chunk_count += 1
#             line_count = 0
#             start_time = time.time()
#
#         pattern = "%Y-%m-%dT%H:%M:%S"
#         if is_time_format(timestamp, pattern):
#             try:
#                 epoch = get_timestamp_for_zone(timestamp, "GMT", pattern)
#             except ValueError:
#                 continue
#         current_log_msg = dict()
#         current_log_msg['timestamp'] = epoch
#         current_log_msg['tag'] = host_name
#         current_log_msg['data'] = event_content
#         current_row.append(current_log_msg)
#         line_count += 1


def parseXlsx():
    line_count = 0
    chunk_count = 0
    current_row = []
    start_time = time.time()
    collectedLogsMap = {}

    file = 'event.xlsx'

    df = pd.read_excel(file, sheet_name='Sheet1')

    for i in df.index:
        host_address = df['host_address'][i]
        host_name = df['host_name'][i]
        event_content = df['event_content'][i]
        cmdb_application = df['cmdb_application'][i]
        # timestamp = str(df['createtime'][i]).replace("/", "-")
        # timestamp = timestamp.replace(" ","T")
        timestamp = "2018-11-25 13:26:41"
        timestamp = timestamp.replace(" ", "T")
        pattern = "%Y-%m-%dT%H:%M:%S"
        if is_time_format(timestamp, pattern):
            try:
                epoch = get_timestamp_for_zone(timestamp, "GMT", pattern)
            except ValueError:
                continue
        current_log_msg = dict()
        current_log_msg['timestamp'] = epoch
        current_log_msg['tag'] = str(cmdb_application)
        current_log_msg['data'] = "event content:" + str(event_content) + " host address:" + str(host_address) + " host name:" + str(host_name)
        if cmdb_application not in collectedLogsMap:
            collectedLogsMap[cmdb_application] = []
        collectedLogsMap[cmdb_application].append(current_log_msg)
        if len(collectedLogsMap[cmdb_application])>=200:
            send_data(collectedLogsMap[cmdb_application])
            collectedLogsMap.pop(cmdb_application)
        elif len(collectedLogsMap)>=2000:
            for key in collectedLogsMap:
                send_data(collectedLogsMap[key])
            collectedLogsMap = {}

    for key in collectedLogsMap:
        send_data(collectedLogsMap[key])


def send_data(metric_data):
    """ Sends parsed metric data to InsightFinder """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = dict()
    to_send_data_dict["metricData"] = json.dumps(metric_data)
    to_send_data_dict["licenseKey"] = config_vars['licenseKey']
    to_send_data_dict["projectName"] = config_vars['projectName']
    to_send_data_dict["userName"] = config_vars['userName']
    to_send_data_dict["instanceName"] = socket.gethostname().partition(".")[0]
    to_send_data_dict["samplingInterval"] = str(int(config_vars['samplingInterval']))
    to_send_data_dict["agentType"] = "LogStreaming"

    to_send_data_json = json.dumps(to_send_data_dict)
    # logger.debug("TotalData: " + str(len(bytearray(to_send_data_json))))
    # logger.debug("Data: " + str(to_send_data_json))

    # send the data
    post_url = parameters['serverUrl'] + "/customprojectrawdata"
    response = requests.post(post_url, data=json.loads(to_send_data_json))
    if response.status_code == 200:
        print(str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
    else:
        print("Failed to send data.")
    print("--- Send data time: %s seconds ---" % (time.time() - send_data_time))


if __name__ == "__main__":
    CHUNK_METRIC_VALUES = 10
    reload(sys)
    sys.setdefaultencoding('utf-8')
    # logger = set_logger_config()
    parameters = get_parameters()
    config_vars = {}
    #config_vars['licenseKey'] = '42761d1f3286aae33e1ddff48fc30db48d5a0ae3'
    config_vars['licenseKey'] = '566e00303ade3d4e1c31355aea68364fbe3d922f'
    config_vars['projectName'] = 'pufaTest2'
    config_vars['userName'] = 'yqian10'
    config_vars['samplingInterval'] = '1000'
    try:
        parseXlsx()
    except KeyboardInterrupt:
        print "Interrupt from keyboard"

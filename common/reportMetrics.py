#!/usr/bin/python

import hashlib
from optparse import OptionParser
import os
import time
import logging
import sys
import json
import datetime
import csv
import math
import socket
import subprocess
import random
from ConfigParser import SafeConfigParser

'''
This script reads reporting_config.json and .agent.bashrc
and opens daily metric file and reports header + rows within
window of reporting interval after prev endtime
if prev endtime is 0, report most recent reporting interval
till now from today's metric file (may or may not be present)
assumping gmt epoch timestamp and local date daily file. 

This also allows you to replay old log and metric files 
'''


def getParameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-f", "--fileInput",
                      action="store", dest="inputFile", help="Input data file (overriding daily data file)")
    parser.add_option("-r", "--logFolder",
                      action="store", dest="logFolder", help="Folder to read log files from")
    parser.add_option("-m", "--mode",
                      action="store", dest="mode", help="Running mode: live or metricFileReplay or logFileReplay")
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-t", "--agentType",
                      action="store", dest="agentType", help="Agent type")
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-s", "--splitID",
                      action="store", dest="splitID", help="The split ID to use when grouping results on the server")
    parser.add_option("-g", "--splitBy",
                      action="store", dest="splitBy",
                      help="The 'split by' to use when grouping results on the server. Examples: splitByEnv, splitByGroup")
    parser.add_option("-z", "--timeZone",
                      action="store", dest="timeZone", help="Time Zone")
    parser.add_option("-c", "--chunkSize",
                      action="store", dest="chunkSize", help="Max chunk size in KB")
    parser.add_option("-l", "--chunkLines",
                      action="store", dest="chunkLines", help="Max number of lines in chunk")
    (options, args) = parser.parse_args()

    parameters = {}
    if options.homepath is None:
        parameters['homepath'] = os.getcwd()
    else:
        parameters['homepath'] = options.homepath
    if options.mode is None:
        parameters['mode'] = "live"
    else:
        parameters['mode'] = options.mode
    if options.agentType is None:
        parameters['agentType'] = ""
    else:
        parameters['agentType'] = options.agentType
    if options.serverUrl is None:
        parameters['serverUrl'] = 'https://app.insightfinder.com'
    else:
        parameters['serverUrl'] = options.serverUrl
    if options.inputFile is None:
        parameters['inputFile'] = None
    else:
        parameters['inputFile'] = options.inputFile
    if options.logFolder is None:
        parameters['logFolder'] = None
    else:
        parameters['logFolder'] = options.logFolder
    if options.timeZone is None:
        parameters['timeZone'] = "GMT"
    else:
        parameters['timeZone'] = options.timeZone
    if options.chunkLines is None and parameters['agentType'] == 'metricFileReplay':
        parameters['chunkLines'] = 100
    elif options.chunkLines is None:
        parameters['chunkLines'] = 40000
    else:
        parameters['chunkLines'] = int(options.chunkLines)
    # Optional split id and split by for metric file replay
    if options.splitID is None:
        parameters['splitID'] = None
    else:
        parameters['splitID'] = options.splitID
    if options.splitBy is None:
        parameters['splitBy'] = None
    else:
        parameters['splitBy'] = options.splitBy
    return parameters


def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(os.path.join(parameters['homepath'], "common", "config.ini")):
            parser = SafeConfigParser()
            parser.read(os.path.join(parameters['homepath'], "common", "config.ini"))
            license_key = parser.get('insightfinder', 'license_key')
            project_name = parser.get('insightfinder', 'project_name')
            user_name = parser.get('insightfinder', 'user_name')
            sampling_interval = parser.get('metrics', 'sampling_interval')
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
            config_vars['licenseKey'] = license_key
            config_vars['projectName'] = project_name
            config_vars['userName'] = user_name
            config_vars['samplingInterval'] = sampling_interval
    except IOError:
        logger.error("config.ini file is missing")
    return config_vars


def getReportingConfigVars():
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


def update_data_start_time():
    if "FileReplay" in parameters['mode'] and reporting_config_vars['prev_endtime'] != "0" and len(
            reporting_config_vars['prev_endtime']) >= 8:
        start_time = reporting_config_vars['prev_endtime']
        # pad a second after prev_endtime
        start_time_epoch = 1000 + long(1000 * time.mktime(time.strptime(start_time, "%Y%m%d%H%M%S")));
        end_time_epoch = start_time_epoch + 1000 * 60 * reporting_config_vars['reporting_interval']
    elif reporting_config_vars['prev_endtime'] != "0":
        start_time = reporting_config_vars['prev_endtime']
        # pad a second after prev_endtime
        start_time_epoch = 1000 + long(1000 * time.mktime(time.strptime(start_time, "%Y%m%d%H%M%S")));
        end_time_epoch = start_time_epoch + 1000 * 60 * reporting_config_vars['reporting_interval']
    else:  # prev_endtime == 0
        end_time_epoch = int(time.time()) * 1000
        start_time_epoch = end_time_epoch - 1000 * 60 * reporting_config_vars['reporting_interval']
    return start_time_epoch


# update prev_endtime in config file
def update_timestamp(prev_endtime):
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), 'r') as f:
        config = json.load(f)
    config['prev_endtime'] = prev_endtime
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), "w") as f:
        json.dump(config, f)


def get_index_for_column_name(col_name):
    if col_name == "CPU":
        return 1
    elif col_name == "DiskRead" or col_name == "DiskWrite":
        return 2
    elif col_name == "DiskUsed":
        return 3
    elif col_name == "NetworkIn" or col_name == "NetworkOut":
        return 4
    elif col_name == "MemUsed":
        return 5


def getEC2InstanceType():
    url = "http://169.254.169.254/latest/meta-data/instance-type"
    try:
        response = requests.post(url)
    except requests.ConnectionError, e:
        logger.error("Error finding instance-type")
        return
    if response.status_code != 200:
        logger.error("Error finding instance-type")
        return
    return response.text


def send_data(metric_data_dict, filePath, chunkSerialNumber):
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = {}
    if parameters['mode'] == "metricFileReplay":
        to_send_data_dict["metricData"] = json.dumps(metric_data_dict[0])
    else:
        to_send_data_dict["metricData"] = json.dumps(metric_data_dict)

    to_send_data_dict["licenseKey"] = agent_config_vars['licenseKey']
    to_send_data_dict["projectName"] = agent_config_vars['projectName']
    to_send_data_dict["userName"] = agent_config_vars['userName']
    to_send_data_dict["instanceName"] = socket.gethostname().partition(".")[0]
    to_send_data_dict["samplingInterval"] = str(int(reporting_config_vars['reporting_interval'] * 60))
    if parameters['agentType'] == "ec2monitoring":
        to_send_data_dict["instanceType"] = getEC2InstanceType()
    # additional data to send for replay agents
    if "FileReplay" in parameters['mode']:
        to_send_data_dict["fileID"] = hashlib.md5(filePath).hexdigest()
        if parameters['mode'] == "logFileReplay":
            to_send_data_dict["agentType"] = "LogFileReplay"
            to_send_data_dict["minTimestamp"] = ""
            to_send_data_dict["maxTimestamp"] = ""
        if parameters['mode'] == "metricFileReplay":
            to_send_data_dict["agentType"] = "MetricFileReplay"
            to_send_data_dict["minTimestamp"] = str(metric_data_dict[1])
            to_send_data_dict["maxTimestamp"] = str(metric_data_dict[2])
            to_send_data_dict["chunkSerialNumber"] = str(chunkSerialNumber)
        if ('splitID' in parameters.keys() and 'splitBy' in parameters.keys()):
            to_send_data_dict["splitID"] = parameters['splitID']
            to_send_data_dict["splitBy"] = parameters['splitBy']

    to_send_data_json = json.dumps(to_send_data_dict)
    logger.debug("Chunksize: " + str(len(bytearray(str(metric_data_dict)))))
    logger.debug("TotalData: " + str(len(bytearray(to_send_data_json))))

    # send the data
    postUrl = parameters['serverUrl'] + "/customprojectrawdata"
    if parameters['agentType'] == "hypervisor":
        response = urllib.urlopen(postUrl, data=urllib.urlencode(to_send_data_dict))
        if response.getcode() == 200:
            logger.info(str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
        else:
            # retry once for failed data and set chunkLines to half if succeeded
            logger.error("Failed to send data. Retrying once.")
            data_split1 = metric_data_dict[0:len(metric_data_dict) / 2]
            to_send_data_dict["metricData"] = json.dumps(data_split1)
            response = urllib.urlopen(postUrl, data=urllib.urlencode(to_send_data_dict))
            if response.getcode() == 200:
                logger.info(str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
                parameters['chunkLines'] = parameters['chunkLines'] / 2
                # since succeeded send the rest of the chunk
                data_split2 = metric_data_dict[len(metric_data_dict) / 2:]
                to_send_data_dict["metricData"] = json.dumps(data_split2)
                response = urllib.urlopen(postUrl, data=urllib.urlencode(to_send_data_dict))
            else:
                logger.info("Failed to send data.")

    else:
        response = requests.post(postUrl, data=json.loads(to_send_data_json))
        if response.status_code == 200:
            logger.info(str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
        else:
            logger.info("Failed to send data.")
            data_split1 = metric_data_dict[0:len(metric_data_dict) / 2]
            to_send_data_dict["metricData"] = json.dumps(data_split1)
            to_send_data_json = json.dumps(to_send_data_dict)
            response = requests.post(postUrl, data=json.loads(to_send_data_json))
            if response.status_code == 200:
                logger.info(str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
                parameters['chunkLines'] = parameters['chunkLines'] / 2
                # since succeeded send the rest of the chunk
                data_split2 = metric_data_dict[len(metric_data_dict) / 2:]
                to_send_data_dict["metricData"] = json.dumps(data_split2)
                to_send_data_json = json.dumps(to_send_data_dict)
                response = requests.post(postUrl, data=json.loads(to_send_data_json))
            else:
                logger.info("Failed to send data.")
    logger.debug("--- Send data time: %s seconds ---" % (time.time() - send_data_time))


def process_streaming(new_prev_endtime_epoch):
    metric_data = []
    dates = []
    # get dates to read files for
    for i in range(0, 3 + int(float(reporting_config_vars['reporting_interval']) / 24 / 60)):
        dates.append(time.strftime("%Y%m%d", time.localtime(start_time_epoch / 1000 + 60 * 60 * 24 * i)))
    # append current date to dates
    current_date = time.strftime("%Y%m%d", time.gmtime())
    if current_date not in dates:
        dates.append(current_date)

    # read all selected daily files for data
    for date in dates:
        filename_addition = ""
        if parameters['agentType'] == "kafka":
            filename_addition = "_kafka"
        elif parameters['agentType'] == "elasticsearch-storage":
            filename_addition = "_es"

        data_file_path = os.path.join(parameters['homepath'], data_directory + date + filename_addition + ".csv")
        if os.path.isfile(data_file_path):
            with open(data_file_path) as dailyFile:
                try:
                    daily_file_reader = csv.reader(dailyFile)
                except IOError:
                    print "No data-file for " + str(date) + "!"
                    continue
                field_names = []
                for csvRow in daily_file_reader:
                    if daily_file_reader.line_num == 1:
                        # Get all the metric names
                        field_names = csvRow
                        for i in range(0, len(field_names)):
                            if field_names[i] == "timestamp":
                                timestamp_index = i
                    elif daily_file_reader.line_num > 1:
                        # skip lines which are already sent
                        try:
                            if long(csvRow[timestamp_index]) < long(start_time_epoch):
                                continue
                        except ValueError:
                            continue
                        # Read each line from csv and generate a json
                        currentCSVRowData = {}
                        for i in range(0, len(csvRow)):
                            if field_names[i] == "timestamp":
                                new_prev_endtime_epoch = csvRow[timestamp_index]
                                currentCSVRowData[field_names[i]] = csvRow[i]
                            else:
                                # fix incorrectly named columns
                                colname = field_names[i]
                                if colname.find("]") == -1:
                                    colname = colname + "[" + parameters['hostname'] + "]"
                                if colname.find(":") == -1:
                                    colname = colname + ":" + str(get_index_for_column_name(field_names[i]))
                                currentCSVRowData[colname] = csvRow[i]
                        metric_data.append(currentCSVRowData)
    # update endtime in config
    if new_prev_endtime_epoch == 0:
        print "No data is reported"
    else:
        new_prev_endtime_in_sec = math.ceil(long(new_prev_endtime_epoch) / 1000.0)
        new_prev_endtime = time.strftime("%Y%m%d%H%M%S", time.localtime(long(new_prev_endtime_in_sec)))
        update_timestamp(new_prev_endtime)
        send_data(metric_data, None, None)


def process_replay(filePath):
    if os.path.isfile(filePath):
        logger.info("Replaying file: " + filePath)
        # log file replay processing
        if parameters['mode'] == "logFileReplay":
            output = subprocess.check_output(
                'cat ' + filePath + ' | jq -c ".[]" > ' + filePath + ".mod",
                shell=True)
            with open(filePath + ".mod") as logfile:
                line_count = 0
                chunk_count = 0
                current_row = []
                start_time = time.time()
                for line in logfile:
                    if line_count == parameters['chunkLines']:
                        logger.debug("--- Chunk creation time: %s seconds ---" % (time.time() - start_time))
                        send_data(current_row, filePath, None)
                        current_row = []
                        chunk_count += 1
                        line_count = 0
                        start_time = time.time()
                    current_row.append(json.loads(line.rstrip()))
                    line_count += 1
                if len(current_row) != 0:
                    logger.debug("--- Chunk creation time: %s seconds ---" % (time.time() - start_time))
                    send_data(current_row, filePath, None)
                    chunk_count += 1
                logger.debug("Total chunks created: " + str(chunk_count))
            output = subprocess.check_output(
                "rm " + filePath + ".mod",
                shell=True)
        else:  # metric file replay processing
            with open(filePath) as metricFile:
                metric_csv_reader = csv.reader(metricFile)
                to_send_metric_data = []
                field_names = []
                current_line_count = 1
                chunk_count = 0
                min_timestamp_epoch = 0
                max_timestamp_epoch = -1
                for row in metric_csv_reader:
                    if metric_csv_reader.line_num == 1:
                        # Get all the metric names from header
                        field_names = row
                        # get index of the timestamp column
                        for i in range(0, len(field_names)):
                            if field_names[i] == "timestamp":
                                timestampIndex = i
                    elif metric_csv_reader.line_num > 1:
                        # Read each line from csv and generate a json
                        current_row = {}
                        if current_line_count == parameters['chunkLines']:
                            send_data([to_send_metric_data, min_timestamp_epoch, max_timestamp_epoch], filePath, chunk_count + 1)
                            to_send_metric_data = []
                            current_line_count = 0
                            chunk_count += 1
                        for i in range(0, len(row)):
                            if field_names[i] == "timestamp":
                                current_row[field_names[i]] = row[i]
                                if min_timestamp_epoch == 0 or min_timestamp_epoch > long(row[i]):
                                    min_timestamp_epoch = long(row[i])
                                if max_timestamp_epoch == 0 or max_timestamp_epoch < long(row[i]):
                                    max_timestamp_epoch = long(row[i])
                            else:
                                colname = field_names[i]
                                if colname.find("]") == -1:
                                    colname = colname + "[-]"
                                if colname.find(":") == -1:
                                    groupid = i
                                    colname = colname + ":" + str(groupid)
                                current_row[colname] = row[i]
                        to_send_metric_data.append(current_row)
                        current_line_count += 1
                # send final chunk
                if len(to_send_metric_data) != 0:
                    send_data([to_send_metric_data, min_timestamp_epoch, max_timestamp_epoch], filePath, chunk_count + 1)
                    chunk_count += 1
                logger.debug("Total chunks created: " + str(chunk_count))


def setloggerConfig():
    # Get the root logger
    logger = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger.setLevel(logging.INFO)
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


def getFileListForDirectory(rootPath):
    file_list = []
    for path, subdirs, files in os.walk(rootPath):
        for name in files:
            if parameters['agentType'] == "metricFileReplay" and "csv" in name:
                file_list.append(os.path.join(path, name))
            if parameters['agentType'] == "LogFileReplay" and "json" in name:
                file_list.append(os.path.join(path, name))
    return file_list


if __name__ == '__main__':
    prog_start_time = time.time()
    logger = setloggerConfig()
    data_directory = 'data/'
    parameters = getParameters()
    agent_config_vars = get_agent_config_vars()
    reporting_config_vars = getReportingConfigVars()

    if parameters['agentType'] == "hypervisor":
        import urllib
    else:
        import requests

    # locate time range and date range
    prev_endtime_epoch = reporting_config_vars['prev_endtime']
    new_prev_endtime_epoch = 0
    start_time_epoch = 0
    start_time_epoch = update_data_start_time()

    if parameters['inputFile'] is None and parameters['logFolder'] is None:
        process_streaming(new_prev_endtime_epoch)
    else:
        if parameters['logFolder'] is None:
            input_file_path = os.path.join(parameters['homepath'], parameters['inputFile'])
            process_replay(input_file_path)
        else:
            file_list = getFileListForDirectory(parameters['logFolder'])
            for file_path in file_list:
                process_replay(file_path)

    logger.info("--- Total runtime: %s seconds ---" % (time.time() - prog_start_time))

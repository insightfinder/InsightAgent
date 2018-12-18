#!/usr/bin/python
import csv
import json
import os
import sys
import time
import datetime
import socket
from ConfigParser import SafeConfigParser
from optparse import OptionParser
import math
import logging

import validators

'''
this script reads reporting interval and prev endtime config2
and opens daily log file and reports header + rows within
window of reporting interval after prev endtime
if prev endtime is 0, report most recent reporting interval
till now from today's log file (may or may not be present)
assumping gmt epoch timestamp and local date daily file
'''


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-f", "--fileInput",
                      action="store", dest="inputFile", help="Input data file (overriding daily data file)")
    parser.add_option("-m", "--mode",
                      action="store", dest="mode", help="Running mode: live or metricFileReplay or logFileReplay")
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-t", "--agentType",
                      action="store", dest="agentType", help="Agent type")
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-l", "--log_level",
                      action="store", dest="log_level", help="Change log verbosity(WARNING: 0, INFO: 1, DEBUG: 2)")
    (options, args) = parser.parse_args()

    params = {}

    params['homepath'] = os.getcwd() if not options.homepath else options.homepath
    params['mode'] = "live" if not options.mode else options.mode
    params['agentType'] = "" if not options.agentType else options.agentType
    params['serverUrl'] = 'https://agent-data.insightfinder.com' if not options.serverUrl else options.serverUrl

    params['log_level'] = logging.INFO
    if options.log_level == '0':
        params['log_level'] = logging.WARNING
    elif options.log_level == '1':
        params['log_level'] = logging.INFO
    elif options.log_level >= '2':
        params['log_level'] = logging.DEBUG
    return params


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


def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(os.path.join(parameters['homepath'], "common", "config.ini")):
            parser = SafeConfigParser()
            parser.read(os.path.join(parameters['homepath'], "common", "config.ini"))
            insightfinder_license_key = parser.get('insightfinder', 'insightfinder_license_key')
            insightfinder_project_name = parser.get('insightfinder', 'insightfinder_project_name')
            insightfinder_user_name = parser.get('insightfinder', 'insightfinder_user_name')

            if not (len(insightfinder_license_key) and len(insightfinder_project_name) and len(
                    insightfinder_user_name)):
                logger.error("Agent not correctly configured. Check config file.")
                sys.exit(1)

            config_vars['license_key'] = insightfinder_license_key
            config_vars['project_name'] = insightfinder_project_name
            config_vars['user_name'] = insightfinder_user_name
    except IOError:
        logger.error("config.ini file is missing")
    return config_vars


def get_index(col_name):
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


# update prev_endtime in config file
def update_timestamp(prev_endtime):
    with open(os.path.join(parameters['homepath'], "proxy_reporting_config.json"), 'r') as f_l:
        config = json.load(f_l)
    config[agent_config_vars['user_name'] + "_" + agent_config_vars['project_name']]['prev_endtime'] = prev_endtime
    with open(os.path.join(parameters['homepath'], "proxy_reporting_config.json"), "w") as f_l:
        json.dump(config, f_l)
    return


def get_total_size(i_file):
    file_json = open(os.path.join(parameters['homepath'], i_file))
    all_json_data = []
    json_data = json.load(file_json)
    for row_l in json_data:
        all_json_data.append(row_l)
    file_json.close()
    return len(bytearray(json.dumps(all_json_data)))


def ec2_instance_type():
    url = "http://169.254.169.254/latest/meta-data/instance-type"
    try:
        response = requests.post(url)
    except requests.ConnectionError:
        print "Error finding instance-type"
        return
    if response.status_code != 200:
        print "Error finding instance-type"
        return
    instance_type = response.text
    return instance_type


# send data to insightfinder
def send_data():
    global metric_data
    if len(metric_data) == 0:
        return
    # update projectKey, userName in dict
    alldata["metricData"] = json.dumps(metric_data)
    alldata["licenseKey"] = agent_config_vars['license_key']
    alldata["projectName"] = agent_config_vars['project_name']
    alldata["userName"] = agent_config_vars['user_name']
    alldata["instanceName"] = parameters['hostname']
    if parameters['agentType'] == "ec2monitoring":
        alldata["instanceType"] = ec2_instance_type()

    # print the json
    json_data = json.dumps(alldata)
    if "FileReplay" in parameters['mode']:
        parameters['reported_data_size'] += len(bytearray(json.dumps(metric_data)))
        if not parameters['first_data']:
            parameters['chunk_size'] = parameters['reported_data_size']
            parameters['first_data'] = True
            parameters['total_chunks'] = int(math.ceil(float(parameters['total_size'])/float(parameters['chunk_size'])))
        reported_data_per = (float(parameters['reported_data_size'])/float(parameters['total_size']))*100

        logger.info(str(min(100.0, math.ceil(reported_data_per))) + "% of data are reported")

        alldata["chunkSerialNumber"] = str(parameters['current_chunk'])
        alldata["chunkTotalNumber"] = str(parameters['total_chunks'])
        parameters['current_chunk'] += 1
        if parameters['mode'] == "logFileReplay":
            alldata["agentType"] = "LogFileReplay"
    else:
        print str(len(bytearray(json_data))) + " bytes data are reported"
    # print the json
    json_data = json.dumps(alldata)
    logger.info(json_data)
    url = parameters['serverUrl'] + "/customprojectrawdata"
    if parameters['agentType'] == "hypervisor":
        response = urllib.urlopen(url, data=urllib.urlencode(alldata))
    else:
        send_http_request(url, "post", json.loads(json_data))


def send_http_request(url, type_l, data, succ_message="Request successful!", fail_message="Request Failed"):
    try:
        if validators.url(url):
            if type_l == "get":
                response = requests.get(url, data)
            else:
                response = requests.post(url, data)

            if response.status_code == 200:
                logger.info(succ_message)
                return True
            logger.info(fail_message)
            return False
        else:
            logger.info("Url not correct : " + url)
    except Exception:
        logger.warning(fail_message)
    return True


def update_agent_data_range():
    # update projectKey, userName in dict
    alldata["licenseKey"] = agent_config_vars['license_key']
    alldata["projectName"] = agent_config_vars['project_name']
    alldata["userName"] = agent_config_vars['user_name']
    alldata["operation"] = "updateAgentDataRange"
    alldata["minTimestamp"] = parameters['min_timestamp_epoch']
    alldata["maxTimestamp"] = parameters['max_timestamp_epoch']

    # print the json
    json_data = json.dumps(alldata)
    logger.info(json_data)
    url = parameters['serverUrl'] + "/agentdatahelper"
    # response = requests.post(url, data=json.loads(json_data))
    send_http_request(url, "post", json.loads(json_data))


def send_data_to_backend():
    global metric_data
    # locate time range and date range
    new_prev_endtime_epoch = 0
    reporting_interval, start_time_epoch = set_parameters_from_file()

    if parameters['inputfile'] is None:
        new_prev_endtime_epoch = handle_when_inputfile_is_not_specified(new_prev_endtime_epoch, reporting_interval,
                                                                        start_time_epoch)
    else:
        if os.path.isfile(os.path.join(parameters['homepath'], parameters['inputfile'])):
            file_l = open(os.path.join(parameters['homepath'], parameters['inputfile']))
            if parameters['mode'] == "logFileReplay":
                new_prev_endtime_epoch = handle_log_file_replay(file_l, new_prev_endtime_epoch)
            else:
                new_prev_endtime_epoch = handle_all_other_files(file_l, new_prev_endtime_epoch)
            file_l.close()
            update_agent_data_range()

    # update endtime in config
    if new_prev_endtime_epoch == 0:
        print "No data is reported"
    else:
        new_prev_endtimeinsec = math.ceil(long(new_prev_endtime_epoch)/1000.0)
        parameters['new_prev_endtime'] = time.strftime("%Y%m%d%H%M%S", time.localtime(long(new_prev_endtimeinsec)))
        update_timestamp(parameters['new_prev_endtime'])
        send_data()
    return


def set_parameters_from_file():
    with open(os.path.join(parameters['homepath'], "proxy_reporting_config.json"), 'r') as f:
        config = json.load(f)[agent_config_vars['user_name'] + "_" + agent_config_vars['project_name']]
    reporting_interval = int(config['reporting_interval'])
    parameters['keep_file_days'] = int(config['keep_file_days'])
    parameters['prev_endtime'] = config['prev_endtime']
    parameters['new_prev_endtime'] = parameters['prev_endtime']
    # deltaFields = config['delta_fields']
    if "FileReplay" in parameters['mode'] and parameters['prev_endtime'] != "0" and len(
            parameters['prev_endtime']) >= 8:
        start_time = parameters['prev_endtime']
        # pad a second after prev_endtime
        start_time_epoch = 1000 + long(1000 * time.mktime(time.strptime(start_time, "%Y%m%d%H%M%S")))
        # end_time_epoch = start_time_epoch + 1000*60*reporting_interval
    elif parameters['prev_endtime'] != "0":
        start_time = parameters['prev_endtime']
        # pad a second after prev_endtime
        start_time_epoch = 1000 + long(1000 * time.mktime(time.strptime(start_time, "%Y%m%d%H%M%S")))
        # end_time_epoch = start_time_epoch + 1000*60*reporting_interval
    else:  # prev_endtime == 0
        end_time_epoch = int(time.time()) * 1000
        start_time_epoch = end_time_epoch - 1000 * 60 * reporting_interval
    return reporting_interval, start_time_epoch


def handle_log_file_replay(file_l, new_prev_endtime_epoch):
    global metric_data
    metric_data_size_known = False
    metric_data_size = 0
    json_data = json.load(file_l)
    # numlines = len(json_data)
    for row in json_data:
        new_prev_endtime_epoch = row[row.keys()[0]]
        if parameters['min_timestamp_epoch'] == 0 or parameters['min_timestamp_epoch'] > long(new_prev_endtime_epoch):
            parameters['min_timestamp_epoch'] = long(new_prev_endtime_epoch)
        if parameters['max_timestamp_epoch'] == 0 or parameters['max_timestamp_epoch'] < long(new_prev_endtime_epoch):
            parameters['max_timestamp_epoch'] = long(new_prev_endtime_epoch)
        metric_data.append(row)
        if not metric_data_size_known:
            metric_data_size = len(bytearray(json.dumps(metric_data)))
            metric_data_size_known = True
            parameters['total_size'] = get_total_size(parameters['inputfile'])
        # Not using exact 750KB as some data will be padded later
        if (len(bytearray(json.dumps(metric_data))) + metric_data_size) < 700000:
            continue
        else:
            send_data()
            metric_data = []
    return new_prev_endtime_epoch


def handle_all_other_files(file, new_prev_endtime_epoch):
    global metric_data, alldata
    metric_data_size_known = False
    metric_data_size = 0
    numlines = len(open(os.path.join(parameters['homepath'], parameters['inputfile'])).readlines())
    fileReader = csv.reader(file)
    for row in fileReader:
        if fileReader.line_num == 1:
            # Get all the metric names
            fieldnames = row
            for i in range(0, len(fieldnames)):
                if fieldnames[i] == "timestamp":
                    timestamp_index = i
        elif fileReader.line_num > 1:
            # Read each line from csv and generate a json
            this_data = {}
            for i in range(0, len(row)):
                if fieldnames[i] == "timestamp":
                    new_prev_endtime_epoch = row[timestamp_index]
                    this_data[fieldnames[i]] = row[i]
                    # update min/max timestamp epoch
                    if parameters['min_timestamp_epoch'] == 0 or parameters['min_timestamp_epoch'] > long(
                            new_prev_endtime_epoch):
                        parameters['min_timestamp_epoch'] = long(new_prev_endtime_epoch)
                    if parameters['max_timestamp_epoch'] == 0 or parameters['max_timestamp_epoch'] < long(
                            new_prev_endtime_epoch):
                        parameters['max_timestamp_epoch'] = long(new_prev_endtime_epoch)
                else:
                    colname = fieldnames[i]
                    if colname.find("]") == -1:
                        colname = colname + "[-]"
                    if colname.find(":") == -1:
                        groupid = i
                        colname = colname + ":" + str(groupid)
                    this_data[colname] = row[i]
            metric_data.append(this_data)
            if not metric_data_size_known:
                metric_data_size = len(bytearray(json.dumps(metric_data)))
                metric_data_size_known = True
                parameters['total_size'] = metric_data_size * (numlines - 1)  # -1 for header
        # Not using exact 750KB as some data will be padded later
        if (len(bytearray(json.dumps(metric_data))) + metric_data_size) < 700000:
            continue
        else:
            send_data()
            metric_data = []
            alldata = {}
    return new_prev_endtime_epoch


def handle_when_inputfile_is_not_specified(new_prev_endtime_epoch, reporting_interval, start_time_epoch):
    global metric_data
    dates = []
    idxdate = 0
    for i in range(0, 2 + int(float(reporting_interval) / 24 / 60)):
        dates.append(time.strftime("%Y%m%d", time.localtime(start_time_epoch / 1000 + 60 * 60 * 24 * i)))
    for date in dates:
        if os.path.isfile(os.path.join(parameters['homepath'], os.path.join(parameters['datadir'], date + ".csv"))):
            daily_file = open(
                os.path.join(parameters['homepath'], os.path.join(parameters['datadir'], date + ".csv")))
            daily_file_reader = csv.reader(daily_file)
            # print dailyFileReader
            # print "hi"
            for row in daily_file_reader:
                if idxdate == 0 and daily_file_reader.line_num == 1:
                    # Get all the metric names
                    fieldnames = row
                    for i in range(0, len(fieldnames)):
                        if fieldnames[i] == "timestamp":
                            timestamp_index = i
                elif daily_file_reader.line_num > 1:
                    if long(row[timestamp_index]) < long(start_time_epoch):
                        continue
                    # Read each line from csv and generate a json
                    this_data = {}
                    for i in range(0, len(row)):
                        if fieldnames[i] == "timestamp":
                            new_prev_endtime_epoch = row[timestamp_index]
                            this_data[fieldnames[i]] = row[i]
                        else:
                            colname = fieldnames[i]
                            if colname.find("]") == -1:
                                colname = colname + "[" + parameters['hostname'] + "]"
                            if colname.find(":") == -1:
                                groupid = get_index(fieldnames[i])
                                colname = colname + ":" + str(groupid)
                            this_data[colname] = row[i]
                    metric_data.append(this_data)
            daily_file.close()
            idxdate += 1
    return new_prev_endtime_epoch


def remove_old_files(keep_file_days):
    # old file cleaning
    for dirpath, dirnames, filenames in os.walk(os.path.join(parameters['homepath'], parameters['datadir'])):
        for file_l in filenames:
            if ".csv" not in file_l:
                continue
            curpath = os.path.join(dirpath, file_l)
            file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(curpath))
            if datetime.datetime.now() - file_modified > datetime.timedelta(days=keep_file_days):
                os.rename(curpath, os.path.join("/tmp", file_l))
    return


if __name__ == '__main__':
    parameters = get_parameters()
    agent_config_vars = get_agent_config_vars()
    log_level = parameters['log_level']
    logger = set_logger_config(log_level)
    meta_data = {}
    alldata = {}
    metric_data = []

    parameters['max_timestamp_epoch'] = 0
    parameters['min_timestamp_epoch'] = 0
    parameters['hostname'] = socket.gethostname().partition(".")[0]
    parameters['first_data'] = False
    parameters['reported_data_size'] = 0
    parameters['total_size'] = 0
    parameters['chunk_size'] = 0
    parameters['total_chunks'] = 0
    parameters['current_chunk'] = 1
    parameters['prev_endtime'] = "0"
    parameters['datadir'] = os.path.join('data', os.path.join(agent_config_vars['user_name'],
                                                              agent_config_vars['project_name']))
    if parameters['agentType'] == "hypervisor":
        import urllib
    else:
        import requests

    send_data_to_backend()
    remove_old_files(parameters['keep_file_days'])
    exit(0)
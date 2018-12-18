#!/usr/bin/python
import json
import os
import glob
import time
import socket
from ConfigParser import SafeConfigParser
from optparse import OptionParser
import math
import requests
import sys
import logging
import validators

'''
this script reads reporting interval and prev endtime config2
and opens daily log file and reports header + rows within
window of reporting interval after prev endtime
if prev endtime is 0, report most recent reporting interval
till now from today's log file (may or may not be present)
assuming gmt epoch timestamp and local date daily file
'''


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-f", "--fileInput",
                      action="store", dest="inputFile", help="Input data file (overriding daily data file)")
    parser.add_option("-m", "--mode",
                      action="store", dest="mode",
                      help="Running mode: live or metricFileReplay or logFileReplay or logStreaming")
    parser.add_option("-t", "--agentType",
                      action="store", dest="agentType", help="Agent type")
    parser.add_option("-w", "--hostname",
                      action="store", dest="serverUrl", help="Server IP")
    parser.add_option("-l", "--log_level",
                      action="store", dest="log_level", help="Change log verbosity(WARNING: 0, INFO: 1, DEBUG: 2)")
    (options, args) = parser.parse_args()

    params = {}

    params['homepath'] = os.getcwd() if not options.homepath else options.homepath
    params['datapath'] = '/tmp'
    params['inputfile'] = max(glob.iglob(os.path.join(params['datapath'], 'insightfinder-log*')),
                              key=os.path.getmtime) if not options.inputFile else options.inputFile
    params['mode'] = "live" if not options.mode else options.mode
    params['agentType'] = "" if not options.agentType else options.agentType
    params['serverUrl'] = "" if not options.serverUrl else options.serverUrl

    params['log_level'] = logging.INFO
    if options.log_level == '0':
        params['log_level'] = logging.WARNING
    elif options.log_level == '1':
        params['log_level'] = logging.INFO
    elif options.log_level >= '2':
        params['log_level'] = logging.DEBUG

    return params


# command = ['bash', '-c', 'source ' + str(parameters['homepath']) + '/.agent.bashrc && env']
# proc = subprocess.Popen(command, stdout=subprocess.PIPE)
#
# for line in proc.stdout:
#   (key, _, value) = line.partition("=")
#   os.environ[key] = value.strip()
# proc.communicate()


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


# LICENSEKEY = os.environ["INSIGHTFINDER_LICENSE_KEY"]
# PROJECTNAME = os.environ["INSIGHTFINDER_PROJECT_NAME"]
# USERNAME = os.environ["INSIGHTFINDER_USER_NAME"]


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
    return

#
# def delete_content(pfile):
#     with open(os.path.join(parameters['homepath'], parameters['inputfile']), 'w') as fd:
#         fd.close()
#     return


# update prev_endtime in config file
def update_timestamp(prev_endtime_l):
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), 'r') as f:
        config_l = json.load(f)
    config_l['prev_endtime'] = prev_endtime_l
    with open(os.path.join(parameters['homepath'], "reporting_config.json"), "w") as f:
        json.dump(config_l, f)
    return


def get_log_meta_data():
    with open(os.path.join(parameters['homepath'], "log_meta_data.json"), 'r') as f:
        meta_data_l = json.load(f)
    if agent_config_vars['project_name'] + agent_config_vars['user_name'] in meta_data_l:
        project_data = meta_data_l[parameters['project_name'] + parameters['user_name']]
        parameters['total_size'] = project_data["totalSize"]
        parameters['total_chunks'] = project_data["totalChunks"]
        parameters['current_chunk'] = project_data["currentChunk"]
        parameters['reported_data_size'] = project_data["reportedDataSize"]
        parameters['prev_endtime'] = project_data["prev_endtime"]
    return


def store_log_meta_data():
    meta_data[agent_config_vars['project_name'] + agent_config_vars['user_name']] = {
        "totalSize": parameters['total_size'],
        "currentChunk": parameters['current_chunk'],
        "totalChunks": parameters['total_chunks'],
        "reportedDataSize": parameters['reported_data_size'],
        "prev_endtime": parameters['prev_endtime']}
    with open(os.path.join(parameters['homepath'], "log_meta_data.json"), 'w') as f_l:
        json.dump(meta_data, f_l)
    return


def get_total_size(i_file):
    file_json = open(os.path.join(parameters['homepath'], i_file))
    all_json_data = []
    if '.json' in i_file:
        json_data = json.load(file_json)
    else:
        json_data = []
        for line_l in file_json:
            line_l = line_l[line_l.find("{"):]
            json_data.append(json.loads(line_l))
    for row_l in json_data:
        all_json_data.append(row_l)

    file_json.close()
    return len(bytearray(json.dumps(all_json_data)))


# send data to insightfinder
def send_data(min_timestamp_epoch, max_timestamp_epoch):
    if len(metric_data) == 0:
        return
    # update projectKey, userName in dict
    alldata["metricData"] = json.dumps(metric_data)
    alldata["licenseKey"] = agent_config_vars['license_key']
    alldata["projectName"] = agent_config_vars['project_name']
    alldata["userName"] = agent_config_vars['user_name']
    alldata["instanceName"] = parameters['hostname']
    # print the json
    # json_data = json.dumps(alldata)
    parameters['reported_data_size'] += len(bytearray(json.dumps(metric_data)))
    if not parameters['first_data']:
        parameters['chunk_size'] = parameters['reported_data_size']
        parameters['first_data'] = True
        parameters['total_chunks'] += int(float(parameters['total_size'])/float(parameters['chunk_size']))
    # print reportedDataSize, total size, totalChunks
    logger.info(parameters['reported_data_size'], parameters['total_size'], parameters['total_chunks'])
    reported_data_per = (float(parameters['reported_data_size'])/float(parameters['total_size']))*100
    logger.info(str(min(100.0, math.ceil(reported_data_per))) + "% of data are reported")

    alldata["chunkSerialNumber"] = str(parameters['current_chunk'])
    alldata["chunkTotalNumber"] = str(parameters['total_chunks'])
    if parameters['mode'] == "logStreaming":
        alldata["minTimestamp"] = str(min_timestamp_epoch)
        alldata["maxTimestamp"] = str(max_timestamp_epoch)
        alldata["agentType"] = "LogStreaming"
    else:
        alldata["agentType"] = "LogFileReplay"

    parameters['current_chunk'] += 1
    # print the json
    json_data = json.dumps(alldata)
    logger.info(json_data)
    url = parameters['serverUrl'] + "/customprojectrawdata"
    logger.info(alldata["chunkTotalNumber"] + " ^^^^ " + alldata["chunkSerialNumber"])
    logger.info("sending data to url : " + url)
    # response = requests.post(url, data=json.loads(json_data))
    send_http_request(url, "post", json.loads(json_data))
    return


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


def update_agent_data_range(min_ts, max_ts):
    # update projectKey, userName in dict
    alldata["licenseKey"] = agent_config_vars['license_key']
    alldata["projectName"] = agent_config_vars['project_name']
    alldata["userName"] = agent_config_vars['user_name']
    alldata["operation"] = "updateAgentDataRange"
    alldata["minTimestamp"] = min_ts
    alldata["maxTimestamp"] = max_ts
    # print the json
    json_data = json.dumps(alldata)
    # print json_data
    url = parameters['serverUrl'] + "/agentdatahelper"
    send_http_request(url, "post", json.loads(json_data))
    # response = requests.post(url, data=json.loads(json_data))


def some_before_main_menthod():
    # main
    # with open(os.path.join(parameters['homepath'], "reporting_config.json"), 'r') as f:
    #     config = json.load(f)
    # reporting_interval = int(config['reporting_interval'])
    # keep_file_days = int(config['keep_file_days'])
    # deltaFields = config['delta_fields']

    if os.path.isfile(os.path.join(parameters['homepath'], "log_meta_data.json")):
        get_log_meta_data()
    # locate time range and date range
    parameters['new_prev_endtime'] = parameters['prev_endtime']
    parameters['new_prev_endtime_epoch'] = 0
    # dates = []
    if ("FileReplay" in parameters['mode'] or "logStreaming" in parameters['mode']) and parameters['prev_endtime'] != "0" and len(parameters['prev_endtime']) >= 8:
        start_time = parameters['prev_endtime']
        # pad a second after prev_endtime
        parameters['start_time_epoch'] = 1000+long(1000*time.mktime(time.strptime(start_time, "%Y%m%d%H%M%S")))
        # end_time_epoch = start_time_epoch + 1000*60*reporting_interval
    elif parameters['prev_endtime'] != "0":
        start_time = parameters['prev_endtime']
        # pad a second after prev_endtime
        parameters['start_time_epoch'] = 1000+long(1000*time.mktime(time.strptime(start_time, "%Y%m%d%H%M%S")))
        # end_time_epoch = start_time_epoch + 1000*60*reporting_interval
    else:  # prev_endtime == 0
        # end_time_epoch = int(time.time())*1000
        parameters['start_time_epoch'] = 0  # end_time_epoch - 1000*60*reporting_interval


def get_total_size_json(json_data):
    temp = []
    for row in json_data:
        if 'timestamp' in row:
            if parameters['mode'] == "logStreaming":
                row['timestamp'] = long(row['timestamp'])*1000
            if long(row['timestamp']) < long(parameters['start_time_epoch']):
                continue
            temp.append(row)
    return len(bytearray(json.dumps(temp))), temp


def some_main_method():
    global metric_data
    min_timestamp_epoch = 0
    max_timestamp_epoch = 0
    if os.path.isfile(os.path.join('/tmp', parameters['inputfile'])):
        # numlines = len(open(os.path.join('/tmp', parameters['inputfile'])).readlines())
        file_l = open(os.path.join('/tmp', parameters['inputfile']))
        metric_data_size_known = False
        metric_data_size = 0
        # count = 0
        first_chunk_size = 0
        if '.json' in parameters['inputfile']:
            json_data = json.load(file_l)
        else:
            json_data = []
            for line in file_l:
                line = line[line.find("{"):]
                json_data.append(json.loads(line))
        # numlines = len(json_data)
        size, json_data = get_total_size_json(json_data)
        parameters['total_size'] += size
        for row in json_data:
            metric_data.append(row)
            parameters['new_prev_endtime_epoch'] = row[row.keys()[0]]
            if min_timestamp_epoch == 0 or min_timestamp_epoch > long(parameters['new_prev_endtime_epoch']):
                min_timestamp_epoch = long(parameters['new_prev_endtime_epoch'])
            if max_timestamp_epoch == 0 or max_timestamp_epoch < long(parameters['new_prev_endtime_epoch']):
                max_timestamp_epoch = long(parameters['new_prev_endtime_epoch'])

            if not metric_data_size_known:
                metric_data_size = len(bytearray(json.dumps(metric_data)))
                metric_data_size_known = True
            # Not using exact 750KB as some data will be padded later
            if (len(bytearray(json.dumps(metric_data))) + metric_data_size) < 700000:
                continue
            else:
                first_chunk_size = len(bytearray(json.dumps(metric_data)))
                send_data(min_timestamp_epoch, max_timestamp_epoch)
                metric_data = []

        # Send the last chunk
        remaining_data_size = len(bytearray(json.dumps(metric_data)))
        if remaining_data_size > 0:
            if remaining_data_size < first_chunk_size:
                parameters['total_chunks'] += 1
            send_data(min_timestamp_epoch, max_timestamp_epoch)
        # save json file
        file_l.close()
        # deleteContent(options.inputFile)
        if parameters['new_prev_endtime_epoch'] == 0:
            logger.info("No data is reported!")
        else:
            new_prev_endtimeinsec = math.ceil(long(parameters['new_prev_endtime_epoch']) / 1000.0)
            parameters['new_prev_endtime'] = time.strftime("%Y%m%d%H%M%S", time.localtime(long(new_prev_endtimeinsec)))
            parameters['prev_endtime'] = parameters['new_prev_endtime']
            store_log_meta_data()
            update_agent_data_range(min_timestamp_epoch, max_timestamp_epoch)
    else:
        logger.warning("Invalid Input File")


if __name__ == '__main__':
    parameters = get_parameters()
    agent_config_vars = get_agent_config_vars()

    log_level = parameters['log_level']
    logger = set_logger_config(log_level)

    parameters['hostname'] = socket.gethostname().partition(".")[0]
    parameters['first_data'] = False
    parameters['reported_data_size'] = 0
    parameters['total_size'] = 0
    parameters['chunk_size'] = 0
    parameters['total_chunks'] = 0
    parameters['current_chunk'] = 1
    parameters['prev_endtime'] = "0"

    meta_data = {}
    alldata = {}
    metric_data = []

    some_before_main_menthod()

    some_main_method()

    exit(0)

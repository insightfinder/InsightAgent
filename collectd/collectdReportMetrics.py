import collections
import csv
import datetime
import itertools
import json
import logging
import math
import os
import socket
import sys
import time
from ConfigParser import ConfigParser
from optparse import OptionParser

import requests

home_path = ''
server_url = ''
data_dir = ''
logger = None
previous_results_filename = "previous_results.json"


def get_input_from_user():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-w", "--server_url",
                      action="store", dest="server_url", help="Server Url")
    parser.add_option("-l", "--log_level",
                      action="store", dest="log_level", help="Change log verbosity(WARNING: 0, INFO: 1, DEBUG: 2)")
    (options, args) = parser.parse_args()

    params = {}

    params['homepath'] = os.getcwd() if not options.homepath else options.homepath
    params['server_url'] = 'http://127.0.0.1:8080' if not options.server_url else options.server_url
    # For calling reportCustomMetrics from '../common' directory.
    sys.path.insert(0, os.path.join(params['homepath'], 'common'))

    params['log_level'] = logging.INFO
    if options.log_level == '0':
        params['log_level'] = logging.WARNING
    elif options.log_level == '1':
        params['log_level'] = logging.INFO
    elif options.log_level >= '2':
        params['log_level'] = logging.DEBUG

    params['datadir'] = "data/"
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


def set_info_from_config_ini_file():
    config_vars = {}
    if os.path.exists(os.path.join(home_path, "collectd", "config.ini")):
        try:
            parser = ConfigParser()
            parser.read(os.path.join(home_path, "collectd", "config.ini"))
            config_vars['license_key'] = parser.get('insightfinder', 'license_key')
            config_vars['project_name'] = parser.get('insightfinder', 'project_name')
            config_vars['user_name'] = parser.get('insightfinder', 'user_name')

            if len(config_vars['license_key']) == 0 or len(config_vars['project_name']) == 0 or len(
                    config_vars['user_name']) == 0:
                logger.error("Agent not correctly configured. Check config file.")
                sys.exit(1)

            # setting config var for python
            os.environ["INSIGHTFINDER_LICENSE_KEY"] = config_vars['license_key']
            os.environ["INSIGHTFINDER_PROJECT_NAME"] = config_vars['project_name']
            os.environ["INSIGHTFINDER_USER_NAME"] = config_vars['user_name']

        except IOError:
            logger.error("Agent not correctly configured. Check config file.")
            sys.exit(1)
    else:
        logger.error("Agent not correctly configured. Check config file.")
        sys.exit(1)

    return config_vars


def set_from_reporting_config_json():
    # global hostname, hostnameShort
    report_file_name = "reporting_config.json"

    # reading file form reporting_config.json
    with open(os.path.join(home_path, report_file_name), 'r') as f:
        config = json.load(f)

    reporting_interval_string = config['reporting_interval']
    # is_second_reporting = False
    if reporting_interval_string[-1:] == 's':
        # is_second_reporting = True
        reporting_interval_l = float(config['reporting_interval'][:-1])
        reporting_interval_l = float(reporting_interval_l / 60)
    else:
        reporting_interval_l = int(config['reporting_interval'])

    # keep_file_days = int(config['keep_file_days'])
    prev_endtime_l = config['prev_endtime']
    # deltaFields_l = config['delta_fields']

    hostname_l = socket.getfqdn()
    hostname_short_l = socket.gethostname().partition(".")[0]
    csvpath_l = "/var/lib/collectd/csv/" + hostname_short_l

    if not os.path.exists(csvpath_l):
        csvpath_l = "/var/lib/collectd/csv/" + hostname_l
    if not os.path.exists(csvpath_l):
        directory_list = os.listdir("/var/lib/collectd/csv")
        if len(directory_list) > 0:
            csvpath_l = "/var/lib/collectd/csv/" + directory_list[0]

    date_l = time.strftime("%Y-%m-%d")
    return reporting_interval_l, hostname_l, hostname_short_l, prev_endtime_l, csvpath_l, date_l


# deletes old csv files from a directory
def remove_old_files(directory, filetype):
    now = datetime.datetime.now()
    now_time = now.time()
    # time between which each day the deletion is done
    if datetime.time(06, 30) <= now_time <= datetime.time(20, 35):
        # data directory path
        data_file_path = directory
        # data_file_path = os.path.join(homepath,datadir)
        now = time.time()
        for f in os.listdir(data_file_path):
            data_file = os.path.join(data_file_path, f)
            # check files older than 3 days
            if os.stat(data_file).st_mtime < now - 2 * 86400:
                # only delete csv files
                if filetype is None:
                    if os.path.isfile(data_file):
                        os.remove(data_file)
                else:
                    if str(filetype) in str(os.path.splitext(data_file)[1]):
                        # print data_file
                        if os.path.isfile(data_file):
                            os.remove(data_file)


def getindex(col_name):
    if col_name == "CPU":
        return 7001
    elif col_name == "DiskRead" or col_name == "DiskWrite":
        return 7002
    elif col_name == "DiskUsed":
        return 7003
    elif col_name == "NetworkIn" or col_name == "NetworkOut":
        return 7004
    elif col_name == "MemUsed":
        return 7005
    elif "DiskUsed" in col_name:
        return 7006
    elif "LoadAvg" in col_name:
        return 7007
    elif "Process" in col_name:
        return 7008


def update_results(lists):
    with open(os.path.join(home_path, data_dir + previous_results_filename), 'w') as f:
        json.dump(lists, f)


def get_previous_results():
    with open(os.path.join(home_path, data_dir + previous_results_filename), 'r') as f:
        return json.load(f)


def set_epoch_time(reporting_interval_l, prev_endtime_l):
    if prev_endtime_l != "0":
        start_time = prev_endtime_l
        # pad a second after prev_end_time
        start_time_epoch_l = 1000 + long(1000 * time.mktime(time.strptime(start_time, "%Y%m%d%H%M%S")))
        # end_time_epoch = start_time_epoch_l + 1000 * 60 * reporting_interval_l
        start_time_epoch_l = start_time_epoch_l / 1000
    else:  # prev_endtime == 0
        end_time_epoch = int(time.time()) * 1000
        start_time_epoch_l = end_time_epoch - 1000 * 60 * reporting_interval_l
        start_time_epoch_l = start_time_epoch_l / 1000
    return reporting_interval_l, start_time_epoch_l, prev_endtime_l


# update prev_endtime in config file
def update_timestamp(prev_endtime_l):
    with open(os.path.join(home_path, "reporting_config.json"), 'r') as f:
        config = json.load(f)
    config['prev_endtime'] = prev_endtime_l
    with open(os.path.join(home_path, "reporting_config.json"), "w") as f:
        json.dump(config, f)


# send data to insightfinder
def send_data(metric_data_l, reporting_interval_l, hostname_l):
    if len(metric_data_l) == 0:
        return
    collectd = 'collectd'

    # update projectKey, userName in dict
    all_data = {"metricData": json.dumps(metric_data_l), "licenseKey": agent_config_vars['license_key'],
                "projectName": agent_config_vars['project_name'],
                "userName": agent_config_vars['user_name'], "instanceName": hostname_l, "insightAgentType": collectd,
                "samplingInterval": str(int(reporting_interval_l * 60))}

    json_data = json.dumps(all_data)
    # logging the results
    logger.info("Json date to send is : " + json_data + "\n" + "Number of bytes reported are: " + str(
        len(bytearray(json_data))))

    custom_project_url = "/customprojectrawdata"
    url = server_url + custom_project_url
    response = requests.post(url, data=json.loads(json_data))

    if response.status_code != 200:
        logger.error("post request to " + url + " failed.")
    else:
        logger.info("Post request to  " + url + " successful!")

    return


def aggregate_results_into_raw_data(start_time_epoch_l, new_prev_endtime_epoch_l, date_l):
    raw_data_l = collections.OrderedDict()
    filenames = {'cpu/percent-active-': ['CPU'], 'memory/memory-used-': ['MemUsed'],
                 'load/load-': ['LoadAvg1', 'LoadAvg5', 'LoadAvg15'], 'df-root/percent_bytes-used-': ['DiskUsed'],
                 'processes/ps_state-blocked-': ['BlockedProcess'], 'processes/ps_state-paging-': ['PagingProcess'],
                 'processes/ps_state-running-': ['RunningProcess'],
                 'processes/ps_state-sleeping-': ['SleepingProcess'], 'processes/ps_state-stopped-': ['StoppedProcess'],
                 'processes/ps_state-zombies-': ['ZombieProcess']}

    all_latest_timestamps = []
    # Calculate average CPU
    aggregate_cpu = remove_old_files_and_update_filesnames(filenames)
    # Collect info from /var/lib/collectd/
    set_raw_data_from_collectd_dir(aggregate_cpu, all_latest_timestamps, date_l, filenames, new_prev_endtime_epoch_l,
                                   raw_data_l, start_time_epoch_l)
    # update endtime_epoch from recent data load
    new_prev_endtime_epoch_l = max(all_latest_timestamps)
    return new_prev_endtime_epoch_l, raw_data_l


def remove_old_files_and_update_filesnames(filenames):
    all_directories = os.listdir(csvpath)
    # aggregate cou for collectd version < 5.5
    aggregate_cpu = False
    # remove old csv files in datadir
    remove_old_files(os.path.join(home_path, data_dir), 'csv')

    for each_dir in all_directories:
        # remove old collectd log files
        remove_old_files(os.path.join(csvpath, each_dir), None)

        if "disk" in each_dir:
            filenames[each_dir + "/disk_octets-"] = [each_dir +
                                                     '_DiskWrite', each_dir + '_DiskRead']
        if "interface" in each_dir:
            filenames[each_dir + "/if_octets-"] = [each_dir +
                                                   '_NetworkIn', each_dir + '_NetworkOut']

    for fEntry in os.walk(os.path.join(csvpath)):
        if "cpu-" in fEntry[0]:
            aggregate_cpu = True
            filenames['aggregation-cpu-average/cpu-system-'] = ['CPU']

    return aggregate_cpu


def set_raw_data_from_collectd_dir(aggregate_cpu, all_latest_timestamps, date_l, filenames, new_prev_endtime_epoch_l,
                                   raw_data_l, start_time_epoch_l):
    for each_file in filenames:
        if "cpu/percent-active" in each_file and aggregate_cpu:
            continue
        if "aggregation-cpu-average/cpu-system" in each_file and aggregate_cpu:
            new_prev_endtime_epoch_l = calculate_avg_cpu_values(all_latest_timestamps, each_file, filenames,
                                                                new_prev_endtime_epoch_l, raw_data_l,
                                                                start_time_epoch_l, date_l)
            aggregate_cpu = False
        else:
            new_prev_endtime_epoch_l = calculate_disk_load_values(all_latest_timestamps, each_file, filenames,
                                                                  new_prev_endtime_epoch_l, raw_data_l,
                                                                  start_time_epoch_l, date_l)


def calculate_avg_cpu_values(all_latest_timestamps, each_file, filenames, new_prev_endtime_epoch_l, raw_data_l,
                             start_time_epoch_l, date_l):
    try:
        csv_file_1 = open(os.path.join(csvpath, each_file + date_l))
        csv_file_2 = open(os.path.join(
            csvpath, 'aggregation-cpu-average/cpu-user-' + date_l))
        csv_file_3 = open(os.path.join(
            csvpath, 'aggregation-cpu-average/cpu-idle-' + date_l))
        reader1 = csv.reader(csv_file_1)
        reader2 = csv.reader(csv_file_2)
        reader3 = csv.reader(csv_file_3)

        for row, row1, row2 in itertools.izip(reader1, reader2, reader3):
            if reader1.line_num > 1:
                if long(int(float(row[0]))) < long(start_time_epoch_l):
                    continue
                timestamp_str = str(int(float(row[0])))
                new_prev_endtime_epoch_l = long(timestamp_str) * 1000.0
                if timestamp_str in raw_data_l:
                    value_list = raw_data_l[timestamp_str]
                    total = float(row[1]) + float(row1[1]) + float(row2[1])
                    idle = float(row2[1])
                    # result = 1 - round(float(idle / total), 4)
                    value_list[filenames[each_file][0]] = str(
                        round((1 - float(idle / total)) * 100, 4))
                    raw_data_l[timestamp_str] = value_list
                else:
                    value_list = {}
                    total = float(row[1]) + float(row1[1]) + float(row2[1])
                    idle = float(row2[1])
                    # result = 1 - round(float(idle / total), 4)
                    value_list[filenames[each_file][0]] = str(
                        round((1 - float(idle / total)) * 100, 4))
                    raw_data_l[timestamp_str] = value_list
        all_latest_timestamps.append(new_prev_endtime_epoch_l)

    except IOError:
        print ""
    return new_prev_endtime_epoch_l


def calculate_disk_load_values(all_latest_timestamps, each_file, filenames, new_prev_endtime_epoch_l, raw_data_l,
                               start_time_epoch_l, date_l):
    try:
        csvfile = open(os.path.join(csvpath, each_file + date_l))
        reader = csv.reader(csvfile)

        for row in reader:
            if reader.line_num > 1:
                if long(int(float(row[0]))) < long(start_time_epoch_l):
                    continue
                timestamp_str = str(int(float(row[0])))
                new_prev_endtime_epoch_l = long(timestamp_str) * 1000.0
                if timestamp_str in raw_data_l:
                    value_list = raw_data_l[timestamp_str]
                    value_list[filenames[each_file][0]] = row[1]
                    if ("disk" in each_file) or ("interface" in each_file):
                        value_list[filenames[each_file][1]] = row[2]
                    elif "load" in each_file:
                        value_list[filenames[each_file][1]] = row[2]
                        value_list[filenames[each_file][2]] = row[3]
                    raw_data_l[timestamp_str] = value_list
                else:
                    value_list = {filenames[each_file][0]: row[1]}
                    if ("disk" in each_file) or ("interface" in each_file):
                        value_list[filenames[each_file][1]] = row[2]
                    elif "load" in each_file:
                        value_list[filenames[each_file][1]] = row[2]
                        value_list[filenames[each_file][2]] = row[3]
                    raw_data_l[timestamp_str] = value_list
        all_latest_timestamps.append(new_prev_endtime_epoch_l)
    except IOError:
        pass
    return new_prev_endtime_epoch_l


def is_str_in_keys(my_dict, my_str):
    for key in my_dict.keys():
        if my_str in key:
            return True
    return False


def fill_metric_data_to_send(raw_data_l, hostname_short_l):
    metric_data_l = []
    metric_list = ["CPU", "MemUsed", "DiskWrite", "DiskRead", "DiskUsed", "NetworkIn", "NetworkOut", "LoadAvg1",
                   "LoadAvg5", "LoadAvg15",
                   "BlockedProcess", "PagingProcess", "RunningProcess", "SleepingProcess", "StoppedProcess",
                   "ZombieProcess"]
    delta_fields = ["DiskRead", "DiskWrite", "NetworkIn", "NetworkOut"]

    if not os.path.isfile(os.path.join(home_path, data_dir + previous_results_filename)):
        previous_result_l = {}
    else:
        previous_result_l = get_previous_results()

    if not bool(raw_data_l):
        logger.error("No data is reported. Exiting.")
        sys.exit()

    for each_timestamp in raw_data_l:
        data = raw_data_l[each_timestamp]
        # print "Data: " + str(data)
        this_data = {'timestamp': str(int(each_timestamp) * 1000)}
        # this_data['timestamp'] = str(int(each_timestamp) * 1000)
        disk_read = disk_write = network_in = network_out = 0  # diskused

        new_result, this_data = get_new_object_from_disk_and_network_details(data, delta_fields, disk_read, disk_write,
                                                                             hostname_short_l, metric_list, network_in,
                                                                             network_out,
                                                                             previous_result_l, this_data)
        previous_result_l = new_result
        metric_data_l.append(this_data)
    return metric_data_l, previous_result_l


def get_new_object_from_disk_and_network_details(data, delta_fields, disk_read, disk_write, hostname_short_l,
                                                 metric_list, network_in, network_out,
                                                 previous_result_l, this_data):
    new_result = {}
    for each_metric in metric_list:
        if each_metric == "DiskWrite" or each_metric == "DiskRead" \
                or each_metric == "NetworkIn" or each_metric == "NetworkOut":
            for each_data in data:
                if "DiskWrite" in each_data:
                    disk_write += float(data[each_data])
                if "DiskRead" in each_data:
                    disk_read += float(data[each_data])
                if "NetworkIn" in each_data:
                    network_in = float(data[each_data])
                if "NetworkOut" in each_data:
                    network_out = float(data[each_data])
        if (not is_str_in_keys(data, each_metric)) and each_metric != "DiskRead" and each_metric != "DiskWrite" \
                and each_metric != "NetworkIn" and each_metric != "NetworkOut":
            final_metric_name = str(
                each_metric) + "[" + str(hostname_short_l) + "]:" + str(getindex(each_metric))
            this_data[final_metric_name] = "NaN"
            continue
        else:
            final_metric_name = str(
                each_metric) + "[" + str(hostname_short_l) + "]:" + str(getindex(each_metric))
            if each_metric == "DiskWrite":
                this_data[final_metric_name] = str(
                    float(float(disk_write) / (1024 * 1024)))
            elif each_metric == "DiskRead":
                this_data[final_metric_name] = str(
                    float(float(disk_read) / (1024 * 1024)))
            elif each_metric == "NetworkIn":
                this_data[final_metric_name] = str(
                    float(float(network_in) / (1024 * 1024)))
            elif each_metric == "NetworkOut":
                this_data[final_metric_name] = str(
                    float(float(network_out) / (1024 * 1024)))
            elif each_metric == "MemUsed":
                this_data[final_metric_name] = str(
                    float(float(data[each_metric]) / (1024 * 1024)))
            else:
                this_data[final_metric_name] = str(data[each_metric])
            new_result[final_metric_name] = this_data[final_metric_name]
            if each_metric in delta_fields:
                if final_metric_name in previous_result_l:
                    this_data[final_metric_name] = str(
                        abs(float(this_data[final_metric_name]) - float(previous_result_l[final_metric_name])))
                else:
                    this_data[final_metric_name] = "NaN"
    return new_result, this_data


# update endtime in config
def update_endtime_in_config(metric_data_l, reporting_interval_l, new_prev_endtime_epoch_l, hostname_l):
    if new_prev_endtime_epoch_l == 0:
        print "No data is reported"
    else:
        new_prev_endtimeinsec = math.ceil(long(new_prev_endtime_epoch_l) / 1000.0)
        new_prev_endtime = time.strftime(
            "%Y%m%d%H%M%S", time.localtime(long(new_prev_endtimeinsec)))
        update_timestamp(new_prev_endtime)
        send_data(metric_data_l, reporting_interval_l, hostname_l)
    return


if __name__ == "__main__":
    parameters = get_input_from_user()

    server_url = parameters['server_url']
    home_path = parameters['homepath']
    data_dir = parameters['datadir']
    log_level = parameters['log_level']
    # setting log level
    logger = set_logger_config(log_level)
    agent_config_vars = set_info_from_config_ini_file()

    new_prev_endtime_epoch = 0

    reporting_interval, hostname, hostname_short, prev_endtime, csvpath, date = set_from_reporting_config_json()

    reporting_interval, start_time_epoch, prev_endtime = set_epoch_time(reporting_interval, prev_endtime)

    new_prev_endtime_epoch, raw_data = aggregate_results_into_raw_data(start_time_epoch, new_prev_endtime_epoch, date)

    metric_data, previous_result = fill_metric_data_to_send(raw_data, hostname_short)

    update_results(previous_result)

    update_endtime_in_config(metric_data, reporting_interval, new_prev_endtime_epoch, hostname)

    exit(0)

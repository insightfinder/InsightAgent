#!/usr/bin/python

import json
import time
import os
from optparse import OptionParser
import socket
import psutil

'''
this script gathers system info using psutil and adds to daily csv file in data directory
'''


def list_to_csv(metric_list):
    metric_csv = ''
    for i in range(0, len(metric_list)):
        metric_csv = metric_csv + str(metric_list[i])
        if (i + 1 != len(metric_list)):
            metric_csv = metric_csv + ','
    return metric_csv


def get_metric_group_id(col_name):
    if col_name == "CPU":
        return 1001
    elif col_name == "DiskRead" or col_name == "DiskWrite":
        return 1002
    elif col_name == "DiskUsed":
        return 1003
    elif col_name == "NetworkIn" or col_name == "NetworkOut":
        return 1004
    elif "Mem" in col_name:
        return 1005
    elif "DiskUsed" in col_name:
        return 1006
    elif "LoadAvg" in col_name:
        return 1007
    elif "InOctets" in col_name or "OutOctets" in col_name:
        return 1008
    elif "InDiscards" in col_name or "OutDiscards" in col_name:
        return 1009
    elif "InErrors" in col_name or "OutErrors" in col_name:
        return 1010
    elif "SwapUsed" in col_name or "SwapTotal" in col_name:
        return 1011

def update_previous_results_json(values_dict):
    prev_results_file_path = os.path.join(homepath, datadir + "previous_results.json")
    with open(prev_results_file_path, 'w+') as prev_results_file:
        json.dump(values_dict, prev_results_file)


def get_previous_results():
    prev_results_file_path = os.path.join(homepath, datadir + "previous_results.json")
    if os.path.exists(prev_results_file_path):
        with open(prev_results_file_path, 'r') as prev_results_file:
            if os.stat(prev_results_file_path).st_size == 0:
                return None
            else:
                return json.load(prev_results_file)
    else:
        return None


def calculate_delta(fieldname, value):
    previous_result = get_previous_results()
    if previous_result is None:
        return value
    delta = float(value) - previous_result[fieldname]
    delta = abs(delta)
    return round(delta, 4)


def generate_csv_header(metric_names):
    csv_header = []
    hostname = socket.gethostname().partition(".")[0]
    for metric in metric_names:
        if (metric != "timestamp"):
            group_id = get_metric_group_id(metric)
            field = metric + "[" + hostname + "]:" + str(group_id)
        else:
            field = metric
        csv_header.append(field)
    return csv_header


def is_delta_field(field):
    with open(os.path.join(homepath, "reporting_config.json"), 'r') as f:
        config_lists = json.load(f)
    delta_fields = config_lists['delta_fields']
    for delta_field in delta_fields:
        if (delta_field in field):
            return True
    return False


if __name__ == "__main__":
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    (options, args) = parser.parse_args()

    if options.homepath is None:
        homepath = os.getcwd()
    else:
        homepath = options.homepath
    datadir = 'data/'

    try:
        current_date = time.strftime("%Y%m%d")
        data_file_path = os.path.join(homepath, datadir)
        if not os.path.exists(data_file_path):
            os.makedirs(data_file_path)
        csv_data_file = open(os.path.join(homepath, datadir + current_date + ".csv"), 'a+')
        csv_data_file_content = csv_data_file.readlines()
        csv_data_file_lines = len(csv_data_file_content)
        current_time_millis = int(round(time.time() * 1000))
        csv_values = []
        csv_header_fields = []
        metric_value_dict = {}
        metric_names = ["timestamp", "CPU", "DiskRead", "DiskWrite", "NetworkIn", "NetworkOut", "MemUsed"]

        csv_header_fields = generate_csv_header(metric_names)

        hostname = socket.gethostname().partition(".")[0]

        for metric in metric_names:
            #get metric values
            metric_value = ""
            if metric == "timestamp":
                metric_value = str(int(round(time.time() * 1000)))
            elif metric == "CPU":
                metric_value = str(psutil.cpu_percent())
            elif metric == "DiskRead":
                disk_vals = psutil.disk_io_counters()
                metric_value = disk_vals.read_bytes / (1024 * 1024)
            elif metric == "DiskWrite":
                disk_vals = psutil.disk_io_counters()
                metric_value = disk_vals.write_bytes / (1024 * 1024)
            elif metric == "NetworkIn":
                network_values = psutil.net_io_counters()
                metric_value = network_values.bytes_recv / ((1024 * 1024))
            elif metric == "NetworkOut":
                network_values = psutil.net_io_counters()
                metric_value = network_values.bytes_sent / ((1024 * 1024))
            elif metric == "MemUsed":
                memory_values = psutil.virtual_memory()
                metric_value = memory_values.used / ((1024 * 1024))

            #calculate delta from previous results for delta fields
            if is_delta_field(metric) is True:
                delta_value = calculate_delta(metric, metric_value)
                csv_values.append(delta_value)
                # Actual values need to be stored in dict and not delta values
                metric_value_dict[metric] = float(
                    metric_value)
            else:
                if (metric == "timestamp"):
                    csv_values.append(metric_value)
                else:
                    csv_values.append(round(float(metric_value), 4))
                metric_value_dict[metric] = float(metric_value)

        if (csv_data_file_lines < 1):
            header_csv = list_to_csv(csv_header_fields)
            csv_data_file.write("%s\n" % (header_csv))
        else:
            header_csv = csv_data_file_content[0]
            header_fields_list = header_csv.split("\n")[0].split(",")
            # If there are new fields added, then copy the fields from date.csv to date.time.csv and add new fields to date.csv
            if cmp(header_fields_list, csv_header_fields) != 0:
                old_csv_filename = os.path.join(homepath, datadir + current_date + ".csv")
                new_csv_filename = os.path.join(homepath,
                                                datadir + current_date + "." + time.strftime("%Y%m%d%H%M%S") + ".csv")
                os.rename(old_csv_filename, new_csv_filename)
                csv_data_file = open(os.path.join(homepath, datadir + current_date + ".csv"), 'a+')
                header_csv = list_to_csv(csv_header_fields)
                csv_data_file.write("%s\n" % (header_csv))

        value_csv = list_to_csv(csv_values)
        csv_data_file.write("%s\n" % (value_csv))
        csv_data_file.flush()
        csv_data_file.close()
        update_previous_results_json(metric_value_dict)

    except KeyboardInterrupt:
        print "Interrupt from keyboard"

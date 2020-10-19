#!/bin/python
import subprocess
import json
import os
import time
from optparse import OptionParser
import csv
from ConfigParser import SafeConfigParser
import requests

COMMA_DELIMITER = ","
NEWLINE_DELIMITER = "\n"
os_metrics = {'Memory': {'NonHeapMemoryUsage': ['max', 'committed', 'init', 'used'],
                         'HeapMemoryUsage': ['max', 'committed', 'init', 'used']},
              'OperatingSystem': ['ProcessCpuLoad', 'SystemCpuLoad', 'MaxFileDescriptorCount',
                                  'OpenFileDescriptorCount'], 'Threading': ['ThreadCount']}
cassandra_metrics = {
    'org.apache.cassandra.metrics:name=TotalLatency,scope=Read,type=ClientRequest': ['Count'],
    'org.apache.cassandra.metrics:name=TotalLatency,scope=Write,type=ClientRequest': ['Count'],
    'org.apache.cassandra.metrics:name=Latency,scope=Read,type=ClientRequest': ['Count'],
    'org.apache.cassandra.metrics:name=Latency,scope=Write,type=ClientRequest': ['Count'],
    'org.apache.cassandra.metrics:name=Timeouts,scope=Read,type=ClientRequest': ['Count'],
    'org.apache.cassandra.metrics:name=Timeouts,scope=Write,type=ClientRequest': ['Count'],
    'org.apache.cassandra.metrics:name=Unavailables,scope=Read,type=ClientRequest': ['Count'],
    'org.apache.cassandra.metrics:name=Unavailables,scope=Write,type=ClientRequest': ['Count'],
    'org.apache.cassandra.metrics:name=Failures,scope=Read,type=ClientRequest': ['Count'],
    'org.apache.cassandra.metrics:name=Failures,scope=Write,type=ClientRequest': ['Count']
}


def get_name_from_id(mbean_id):
    full_path = mbean_id.split(":")[1]
    path_vals = full_path.split(",")
    metric_name = ""
    for entry in path_vals:
        metric_name += entry.split("=")[1] + "_"
    metric_name = metric_name[:-1]
    return metric_name


def getInstanceDetails(filename):
    instances = []
    with open(filename, 'rb') as csvFile:
        instancereader = csv.reader(csvFile, delimiter=',')
        for row in instancereader:
            if len(row) == 0:
                continue
            instance = []
            instance.append(row[0])
            instance.append(row[1])
            instances.append(instance)
    return instances


def getindex(col_name):
    if col_name == "NonHeapMemoryUsage":
        return 9001
    elif col_name == "HeapMemoryUsage":
        return 9002
    elif col_name == "ProcessCpuLoad":
        return 9003
    elif col_name == "SystemCpuLoad":
        return 9004
    elif "ClientRequest" in col_name:
        return 9200

def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(os.path.join(homepath, "config.ini")):
            parser = SafeConfigParser()
            parser.read(os.path.join(homepath, "config.ini"))
            #file_name = parser.get('InsightFinder', 'file_name')
            license_key = parser.get('InsightFinder', 'insightFinder_license_key')
            project_name = parser.get('InsightFinder', 'insightFinder_project_name')
            user_name = parser.get('InsightFinder', 'insightFinder_user_name')
            server_url = parser.get('InsightFinder', 'insightFinder_server_url')
            #if len(file_name) == 0:
            #    print "Agent not correctly configured(file name). Check config file."
            #    sys.exit(1)
            if len(license_key) == 0:
                print "Agent not correctly configured(license key). Check config file."
                sys.exit(1)
            if len(project_name) == 0:
                print "Agent not correctly configured(project name). Check config file."
                sys.exit(1)
            if len(user_name) == 0:
                print "Agent not correctly configured(user name). Check config file."
                sys.exit(1)
            if len(server_url) == 0:
                print "Agent not correctly configured(server url). Check config file."
                sys.exit(1)
            #config_vars['file_name'] = file_name
            config_vars['license_key'] = license_key
            config_vars['project_name'] = project_name
            config_vars['user_name'] = user_name
            config_vars['server_url'] = server_url
    except IOError:
        print "config.ini file is missing"
    return config_vars


def send_data(metric_data):
    """ Sends parsed metric data to InsightFinder """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = dict()
    # for backend so this is the camel case in to_send_data_dict
    to_send_data_dict["metricData"] = json.dumps(metric_data)
    to_send_data_dict["licenseKey"] = config_vars['license_key']
    to_send_data_dict["projectName"] = config_vars['project_name']
    to_send_data_dict["userName"] = config_vars['user_name']
    to_send_data_dict["agentType"] = "custom"

    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = config_vars['server_url'] + "/customprojectrawdata"
    response = requests.post(post_url, data=json.loads(to_send_data_json), verify=False)
    if response.status_code == 200:
        print str(len(bytearray(to_send_data_json))) + " bytes of data are reported."
    else:
        print "Failed to send data."
    print "--- Send data time: %s seconds ---" + str(time.time() - send_data_time)


requestJson = {}
requestJson["type"] = "read"
requestJson["mbean"] = "java.lang:type=*"

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
date = time.strftime("%Y%m%d")
header = 'timestamp'

instances = getInstanceDetails(os.path.join(homepath, "jolokia", "instancelist.csv"))

for instance in instances:
    for metric in os_metrics['Memory']:
        for path in os_metrics['Memory'][metric]:
            header = header + COMMA_DELIMITER
            header = header + metric + "-" + path + "[" + instance[0] + "]"

    for cpuMetric in os_metrics['OperatingSystem']:
        header = header + COMMA_DELIMITER
        header = header + cpuMetric + "[" + instance[0] + "]"

    for thread_metric in os_metrics['Threading']:
        header = header + COMMA_DELIMITER
        header = header + thread_metric + "[" + instance[0] + "]"

    for cassandra_metric in cassandra_metrics.iterkeys():
        for value_name in cassandra_metrics[cassandra_metric]:
            header = header + COMMA_DELIMITER
            header = header + get_name_from_id(cassandra_metric) + "_" + value_name + "[" + instance[0] + "]"

header += NEWLINE_DELIMITER

line = ""
proc = subprocess.Popen(['curl -H "Content-Type: application/json" -X POST -d \'' + json.dumps(
    requestJson) + '\' ' + str(instances[0][1]) + "/jolokia/"], stdout=subprocess.PIPE, shell=True)
(out, err) = proc.communicate()
output = json.loads(out)
line += str(output['timestamp'] * 1000)

for instance in instances:
    proc = subprocess.Popen(['curl -H "Content-Type: application/json" -X POST -d \'' + json.dumps(
        requestJson) + '\' ' + instance[1] + "/jolokia/"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    output = json.loads(out)

    ##Cassandra metrics request json
    cassandraMbeanJSON = {}
    cassandraMbeanJSON["type"] = "read"
    cassandraMbeanJSON["mbean"] = "org.apache.cassandra.metrics:type=*,scope=*,name=*"

    proc2 = subprocess.Popen(['curl -H "Content-Type: application/json" -X POST -d \'' + json.dumps(
        cassandraMbeanJSON) + '\' ' + instance[1] + "/jolokia/"], stdout=subprocess.PIPE, shell=True)
    (cassandra_out, err) = proc2.communicate()
    cassandra_metrics_json = json.loads(cassandra_out)

    for metric in os_metrics['Memory']:
        for path in os_metrics['Memory'][metric]:
            line += COMMA_DELIMITER
            line += str(output['value']['java.lang:type=Memory'][metric][path])

    for cpuMetric in os_metrics['OperatingSystem']:
        line += COMMA_DELIMITER
        metric = output['value']['java.lang:type=OperatingSystem'][cpuMetric]
        if 'load' in str(cpuMetric):
            line += str(output['value']['java.lang:type=OperatingSystem'][cpuMetric] * 100)
        else:
            line += str(output['value']['java.lang:type=OperatingSystem'][cpuMetric])

    for thread_metric in os_metrics['Threading']:
        line += COMMA_DELIMITER
        line += str(output['value']['java.lang:type=Threading'][thread_metric])

    for cassandra_metric in cassandra_metrics.iterkeys():
        for value_name in cassandra_metrics[cassandra_metric]:
            line += COMMA_DELIMITER
            line += str(cassandra_metrics_json['value'][cassandra_metric][value_name])

line += NEWLINE_DELIMITER

config_vars = get_agent_config_vars()
data = []
header = map(lambda x: x.strip(), header.split(','))
line = map(lambda x: x.strip(), line.split(','))
data.append(dict(zip(header, line)))
print data
send_data(data)

# -*- coding: utf-8 -*-
import json
import os
import socket
import sys
import time
import requests
import urllib3
from ConfigParser import SafeConfigParser


MAX_RETRY_NUM = 10
RETRY_WAIT_TIME_IN_SEC = 30

def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(os.path.join(os.getcwd(), "config.ini")):
            parser = SafeConfigParser()
            parser.read(os.path.join(os.getcwd(), "config.ini"))
            file_name = parser.get('InsightFinder', 'file_name')
            license_key = parser.get('InsightFinder', 'insightFinder_license_key')
            project_name = parser.get('InsightFinder', 'insightFinder_project_name')
            user_name = parser.get('InsightFinder', 'insightFinder_user_name')
            server_url = parser.get('InsightFinder', 'insightFinder_server_url')
            if len(file_name) == 0:
                print "Agent not correctly configured(file name). Check config file."
                sys.exit(1)
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
            config_vars['file_name'] = file_name
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
    to_send_data_dict["agentType"] = "MetricFileReplay"

    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = config_vars['server_url'] + "/customprojectrawdata"
    send_data_to_receiver(post_url, to_send_data_json, len(metric_data))
    print "--- Send data time: %s seconds ---" + str(time.time() - send_data_time)

def send_data_to_receiver(post_url, to_send_data, num_of_message):
    attempts = 0
    while attempts < MAX_RETRY_NUM:
        response_code = -1
        attempts += 1
        try:
            response = requests.post(post_url, data=json.loads(to_send_data), verify=False)
            response_code = response.status_code
        except:
            print "Attempts: %d. Fail to send data, response code: %d wait %d sec to resend." % (
                attempts, response_code, RETRY_WAIT_TIME_IN_SEC)
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
            continue
        if response_code == 200:
            print "Data send successfully. Number of events: %d" % num_of_message
            break
        else:
            print "Attempts: %d. Fail to send data, response code: %d wait %d sec to resend." % (
                attempts, response_code, RETRY_WAIT_TIME_IN_SEC)
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
    if attempts == MAX_RETRY_NUM:
        sys.exit(1)

if __name__ == "__main__":
    urllib3.disable_warnings()
    reload(sys)
    sys.setdefaultencoding('utf-8')
    config_vars = get_agent_config_vars()
    # chunk size is 2Mb
    CHUNK_SIZE = 2 * 1024 * 1024
    with open(config_vars["file_name"]) as json_data:
        data = []
        count = 0
        header_str = json_data.readline()
        header = map(lambda x: x.strip(), header_str.split(','))
        for line in json_data:
            entry = map(lambda x: x.strip(), line.split(','))
            new_entry = dict(zip(header, entry))
            data.append(new_entry)
            count += 1
            if count % 10 == 0 and len(bytearray(json.dumps(data))) >= CHUNK_SIZE:
                send_data(data)
                data = []
        if len(data) != 0:
            send_data(data)

    print "--- Total count: %s ---" + str(count)

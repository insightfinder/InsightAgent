# -*- coding: utf-8 -*-
import json
import os
import sys
import time
import copy
import urllib3
import importlib
from sys import getsizeof
from configparser import ConfigParser

import requests


def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(os.path.join(os.getcwd(), "config.ini")):
            parser = ConfigParser()
            parser.read(os.path.join(os.getcwd(), "config.ini"))
            file_name = parser.get('InsightFinder', 'file_name')
            license_key = parser.get('InsightFinder', 'insightFinder_license_key')
            project_name = parser.get('InsightFinder', 'insightFinder_project_name')
            user_name = parser.get('InsightFinder', 'insightFinder_user_name')
            server_url = parser.get('InsightFinder', 'insightFinder_server_url')
            if len(file_name) == 0:
                print("Agent not correctly configured(file name). Check config file.")
                sys.exit(1)
            if len(license_key) == 0:
                print("Agent not correctly configured(license key). Check config file.")
                sys.exit(1)
            if len(project_name) == 0:
                print("Agent not correctly configured(project name). Check config file.")
                sys.exit(1)
            if len(user_name) == 0:
                print("Agent not correctly configured(user name). Check config file.")
                sys.exit(1)
            if len(server_url) == 0:
                print("Agent not correctly configured(server url). Check config file.")
                sys.exit(1)
            config_vars['file_name'] = file_name
            config_vars['license_key'] = license_key
            config_vars['project_name'] = project_name
            config_vars['user_name'] = user_name
            config_vars['server_url'] = server_url
    except IOError:
        print("config.ini file is missing")
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
    to_send_data_dict["agentType"] = "LogFileReplay"

    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = config_vars['server_url'] + "/customprojectrawdata"
    response = requests.post(post_url, data=json.loads(to_send_data_json), verify=False)
    if response.status_code == 200:
        print(str(getsizeof(to_send_data_json)) + " bytes of data are reported.")
    else:
        print("Failed to send data.")
    print("--- Send data time: %s seconds ---" + str(time.time() - send_data_time))


if __name__ == "__main__":
    urllib3.disable_warnings()
    importlib.reload(sys)
    config_vars = get_agent_config_vars()
    CHUNK_SIZE = 1000
    with open(config_vars["file_name"]) as json_data:
        d = json.load(json_data)
        data = []
        count = 0
        for entry in d:
            new_entry = copy.deepcopy(entry)
            data.append(new_entry)
            count += 1
            if count >= CHUNK_SIZE:
                send_data(data)
                count = 0
                data = []
        if count != 0:
            send_data(data)

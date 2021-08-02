# -*- coding: utf-8 -*-
import json
import os
import sys
import time
import urllib3
import importlib
import random
from configparser import ConfigParser

import requests
import arrow

MAX_RETRY_NUM = 10
RETRY_WAIT_TIME_IN_SEC = 30


def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(os.path.join(os.getcwd(), "config.ini")):
            parser = ConfigParser()
            parser.read(os.path.join(os.getcwd(), "config.ini"))
            user_name = parser.get('InsightFinder', 'insightFinder_user_name')
            license_key = parser.get('InsightFinder', 'insightFinder_license_key')
            project_name = parser.get('InsightFinder', 'insightFinder_project_name')
            server_url = parser.get('InsightFinder', 'insightFinder_server_url')
            fake_data_time_range = parser.get('InsightFinder', 'fake_data_time_range')
            fake_data_interval = parser.get('InsightFinder', 'fake_data_interval')
            fake_data_instance_count = parser.get('InsightFinder', 'fake_data_instance_count')
            fake_data_metric_count = parser.get('InsightFinder', 'fake_data_metric_count')

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
            if len(fake_data_time_range) == 0:
                print("Agent not correctly configured(fake_data_time_range). Check config file.")
                sys.exit(1)
            if len(fake_data_interval) == 0:
                print("Agent not correctly configured(fake_data_interval). Check config file.")
                sys.exit(1)
            if len(fake_data_instance_count) == 0:
                print("Agent not correctly configured(fake_data_instance_count). Check config file.")
                sys.exit(1)
            if len(fake_data_metric_count) == 0:
                print("Agent not correctly configured(fake_data_metric_count). Check config file.")
                sys.exit(1)

            try:
                time_range = fake_data_time_range.split(',')
                time_range = [int(arrow.get(x.strip()).float_timestamp * 1000) for x in time_range]
            except Exception:
                print("Agent not correctly configured(fake_data_time_range). Check config file.")
                sys.exit(1)

            config_vars['license_key'] = license_key
            config_vars['project_name'] = project_name
            config_vars['user_name'] = user_name
            config_vars['server_url'] = server_url
            config_vars['time_range'] = time_range
            config_vars['interval'] = int(fake_data_interval.strip()) * 60 * 1000
            config_vars['instance_count'] = int(fake_data_instance_count.strip())
            config_vars['metric_count'] = int(fake_data_metric_count.strip())
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
    to_send_data_dict["agentType"] = "MetricFileReplay"

    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = config_vars['server_url'] + "/customprojectrawdata"
    send_data_to_receiver(post_url, to_send_data_json, len(metric_data))
    print("--- Send data time: %s seconds ---" + str(time.time() - send_data_time))


def send_data_to_receiver(post_url, to_send_data, num_of_message):
    attempts = 0
    while attempts < MAX_RETRY_NUM:
        response_code = -1
        attempts += 1
        try:
            response = requests.post(post_url, data=json.loads(to_send_data), verify=False)
            response_code = response.status_code
        except:
            print("Attempts: %d. Fail to send data, response code: %d wait %d sec to resend." % (
                attempts, response_code, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
            continue
        if response_code == 200:
            print("Data send successfully. Number of events: %d" % num_of_message)
            break
        else:
            print("Attempts: %d. Fail to send data, response code: %d wait %d sec to resend." % (
                attempts, response_code, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
    if attempts == MAX_RETRY_NUM:
        sys.exit(1)


if __name__ == "__main__":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    importlib.reload(sys)
    config_vars = get_agent_config_vars()
    # chunk size is 2Mb
    CHUNK_SIZE = 2 * 1024 * 1024

    # fake data info
    fake_data_map = {1: [0, 10], 2: [0, 20], 3: [0, 30], 9: [0, 100]}
    instance_count = config_vars['instance_count'] or 5000
    metric_count = config_vars['metric_count'] or 10
    start_time = config_vars['time_range'][0]
    end_time = config_vars['time_range'][1]
    timestamp = start_time
    need_anomaly = False
    has_anomaly = 0

    data = []
    count = 0
    while timestamp <= end_time:
        new_entry = {
            "timestamp": str(timestamp),
        }
        timestamp += config_vars['interval']
        count += 1

        # build anomaly count
        if need_anomaly:
            if count % 200 == 0 or has_anomaly:
                has_anomaly += 1
            if has_anomaly >= 5:
                has_anomaly = 0

        # build value
        for i_count in range(1, instance_count + 1):
            for m_count in range(1, metric_count + 1):
                random_key = random.randint(1, 3)
                random_list = fake_data_map[random_key] or [0, 10]
                val = str(random.randint(*random_list))

                # set anomaly value
                if has_anomaly and instance_count <= 10:
                    val = str(random.randint(*fake_data_map[9]))

                new_entry["metric{}[node{}]".format(m_count, i_count)] = val

        data.append(new_entry)
        if len(bytearray(json.dumps(data), 'utf8')) >= CHUNK_SIZE:
            send_data(data)
            data = []

    if len(data) != 0:
        send_data(data)

    print("--- Total count: %s ---" + str(count))

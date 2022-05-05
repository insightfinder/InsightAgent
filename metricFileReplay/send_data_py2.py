# -*- coding: utf-8 -*-
import json
import os
import sys
import time
import math
import requests
import urllib3
from ConfigParser import SafeConfigParser

MAX_RETRY_NUM = 10
RETRY_WAIT_TIME_IN_SEC = 30
# chunk size is 2Mb
CHUNK_SIZE = 2 * 1024 * 1024


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


def send_data(config_vars, metric_data, replay_status):
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
    # set maxTimestamp and minTimestamp for this chunk
    timestamps = [int(d['timestamp']) for d in metric_data]
    to_send_data_dict["maxTimestamp"] = max(timestamps) if len(timestamps) > 0 else None
    to_send_data_dict["minTimestamp"] = min(timestamps) if len(timestamps) > 0 else None
    # set replay status
    replay_status = {
        'tc': replay_status['total_chunk'],
        "cc": replay_status['current_chunk'],
        "dr": {"s": replay_status['start_timestamp'], "e": replay_status['end_timestamp']},
        "rt": replay_status['run_time'],
    }
    to_send_data_dict["metricReplayStatus"] = json.dumps(replay_status)

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


def get_replay_status(json_data, header):
    all_timestamps = []
    replay_data = []
    total_chunk = 0
    for line in json_data:
        entry = [x.strip() for x in line.split(',')]
        new_entry = dict(list(zip(header, entry)))
        timestamp = new_entry.get('timestamp', 0)
        all_timestamps.append(timestamp)

        replay_data.append(new_entry)
        if len(bytearray(json.dumps(replay_data), 'utf8')) >= CHUNK_SIZE:
            total_chunk += 1
            replay_data = []
    if len(replay_data) != 0:
        total_chunk += 1

    all_timestamps = [int(x) for x in all_timestamps]
    start_timestamp = min(all_timestamps) if len(all_timestamps) > 0 else None
    end_timestamp = max(all_timestamps) if len(all_timestamps) > 0 else None

    return {'total_chunk': total_chunk, 'start_timestamp': start_timestamp, 'end_timestamp': end_timestamp,
            'run_time': int(time.time() * 1000)}


def main():
    urllib3.disable_warnings()
    reload(sys)
    sys.setdefaultencoding('utf-8')
    config_vars = get_agent_config_vars()
    with open(config_vars["file_name"]) as json_data:
        header_str = json_data.readline()
        offset = len(header_str)
        header = [x.strip() for x in header_str.split(',')]

        # get replay status
        replay_status = get_replay_status(json_data, header)
        print "--- Replay status: %s ---" + str(replay_status)

        # seek to second line
        json_data.seek(offset)
        # read file and send data
        data = []
        count = 0
        current_chunk = 0
        for line in json_data:
            entry = [x.strip() for x in line.split(',')]
            new_entry = dict(list(zip(header, entry)))
            data.append(new_entry)
            count += 1
            if len(bytearray(json.dumps(data), 'utf8')) >= CHUNK_SIZE:
                current_chunk += 1
                replay_status['current_chunk'] = current_chunk
                send_data(config_vars, data, replay_status)
                data = []
        if len(data) != 0:
            current_chunk += 1
            replay_status['current_chunk'] = current_chunk
            send_data(config_vars, data, replay_status)

    print "--- Total count: %s ---" + str(count)


if __name__ == "__main__":
    main()

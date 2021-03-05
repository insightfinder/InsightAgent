# -*- coding: utf-8 -*-
import json
import os
import sys
import time
import urllib3
import importlib
import traceback
import threading
from configparser import ConfigParser
from requests.packages.urllib3.exceptions import InsecureRequestWarning

import requests
import arrow
from toolz import merge_with
from csv import reader

MAX_RETRY_NUM = 10
RETRY_WAIT_TIME_IN_SEC = 30
CHUNK_SIZE = 2 * 1024 * 1024  # chunk size is 2Mb


def func_check_buffer(lock, buffer_d, args_d):
    STOP = False
    metric_data_list = []
    interval = 30
    sample_interval = 5 * 60
    print(f"func_check_buffer: sleep every {interval} secs")

    def func_merge_vals(*args, **kwargs):
        # use sum
        return str(sum(map(lambda x: float(x) if x else 0, *args)))

    while True:
        time.sleep(interval)

        try:
            # check the buffer
            print(f"buffer_d keys={buffer_d.keys()}")

            # WITH MERGE: merge the messages with sample_interval
            if args_d['enable_merge'] and args_d['latest_msg_time'] - args_d['earliest_msg_time'] > sample_interval:
                expire_time = args_d['earliest_msg_time'] + sample_interval

                need_merge_list = []
                if lock.acquire():
                    for ts in list(filter(lambda x: x < expire_time, buffer_d.keys())):
                        ts_map = buffer_d.pop(ts)
                        need_merge_list.append(ts_map)
                    # reset earliest_msg_time
                    args_d['earliest_msg_time'] = expire_time
                    lock.release()

                # merge metrics values
                need_merge_map = {}
                merged_map = {}
                for ts_map in need_merge_list:
                    for ts_key in ts_map.keys():
                        instance = ts_key.split('@')[0]
                        if instance not in need_merge_map:
                            need_merge_map[instance] = []
                        need_merge_map[instance].append(ts_map[ts_key])
                for instance in need_merge_map.keys():
                    timestamp = need_merge_map[instance][0]['timestamp']
                    data_list = map(lambda x: x if x.pop('timestamp') else x, need_merge_map[instance])
                    merged_map[instance] = merge_with(func_merge_vals, *data_list)
                    merged_map[instance]['timestamp'] = timestamp

                metric_data_list += merged_map.values()

            # WITH NOT MERGE: send messages are too old comparing to latest message timestamp
            elif not args_d['enable_merge'] and args_d['latest_msg_time'] > 0:
                expire_time = args_d['latest_msg_time'] - sample_interval

                keys_to_drop = []
                if lock.acquire():
                    for ts in filter(lambda x: x < expire_time, buffer_d.keys()):
                        metric_data_list += buffer_d[ts].values()
                        keys_to_drop.append(ts)
                    for ts in keys_to_drop:
                        buffer_d.pop(ts)
                    lock.release()

            # flush buffer if process is stop
            elif args_d['process_stop']:
                if lock.acquire():
                    for key_item in buffer_d.values():
                        metric_data_list += key_item.values()
                    buffer_d.clear()
                    lock.release()
                STOP = True

            # send data with chunk
            metric_data_size = get_buffer_size(metric_data_list)
            print(f"metric_data_list length={len(metric_data_list)} size={metric_data_size}")

            # if STOP or metric_data_size > CHUNK_SIZE:
            for chunk in data_chunks(metric_data_list,
                                     metric_data_size,
                                     CHUNK_SIZE):
                send_data(chunk)
            metric_data_list.clear()

        except Exception:
            print("-" * 60)
            traceback.print_exc(file=sys.stdout)
            print("-" * 60)

        # stop while if process stop
        if STOP:
            break


def get_buffer_size(data):
    """ input : list of dicts, return size in bytes """
    return len(json.dumps(data))


def data_chunks(metric_data, data_size, chunk_size):
    """ generate chunks of data from metric data """
    chunks = data_size // chunk_size + 1
    num_msgs_per_chunk = max(1, len(metric_data) // chunks)
    for i in range(0, len(metric_data), num_msgs_per_chunk):
        yield metric_data[i:i + num_msgs_per_chunk]


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

    with open(config_vars["file_name"]) as json_data:
        count = 0
        csv_reader = reader(json_data)
        next(csv_reader)  # skip header 

        # share with threads
        buffer_dict = {}
        args_dict = {'earliest_msg_time': sys.maxsize, 'latest_msg_time': 0, 'process_stop': False,
                     'enable_merge': True}
        # start an thread to check the buffer
        thread_lock = threading.Lock()
        thread1 = threading.Thread(target=func_check_buffer,
                                   args=(thread_lock, buffer_dict, args_dict))
        thread1.start()

        for line in csv_reader:
            time_bucket, service_alias, client_alias, http_status, svc_mean, tx_mean, \
                req_count, value = line

            timestamp = arrow.get(time_bucket).timestamp
            # update latest messages time
            args_dict['latest_msg_time'] = max(args_dict['latest_msg_time'], timestamp)
            args_dict['earliest_msg_time'] = min(args_dict['earliest_msg_time'], timestamp)

            if timestamp not in buffer_dict:
                buffer_dict[timestamp] = {}

            instance = "{}_{}".format(client_alias, service_alias)
            key = f'{instance}@{timestamp}'
            if key not in buffer_dict[timestamp]:
                buffer_dict[timestamp][key] = {}

            metric_vals = {}

            if http_status != '2xx':
                metric_vals = {
                    'timestamp': str(timestamp * 1000),
                    f'{http_status}_req_count[{instance}]': req_count or '0'
                }
            else:
                metric_vals = {
                    'timestamp': str(timestamp * 1000),
                    f'svc_mean[{instance}]': svc_mean,
                    f'tx_mean[{instance}]': tx_mean,
                    # f'value[{instance}]': value,
                    f'{http_status}_req_count[{instance}]': req_count or '0'
                }

            # combine metrics data
            buffer_dict[timestamp][key].update(metric_vals)

            count += 1

        print("--- Process stop ---")
        args_dict['process_stop'] = True
        thread1.join()

    print("--- Total count: %s ---" + str(count))

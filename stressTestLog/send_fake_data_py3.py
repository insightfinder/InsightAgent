# -*- coding: utf-8 -*-
import json
import os
import sys
import time
import urllib3
import importlib
import signal
import urllib.parse
import http.client
from sys import getsizeof
from random import choice
from configparser import ConfigParser
from threading import Thread, Lock
import multiprocessing
from multiprocessing import Pool, Process, Queue

import requests
import arrow

ATTEMPTS = 3
RETRY_WAIT_TIME_IN_SEC = 30
SAMPLE_LOGS = [
    '{"state":"WA","api":"api/v1/checkout","user":"Mary","status":504}',
    '{"state":"WA","api":"api/v1/paymentupdate","user":"James","status":404}',
    '{"state":"NY","api":"api/v1/settingchange","user":"Robert","status":200}',
    '{"state":"NY","api":"api/v1/shoppinglist","user":"Jennifer","status":200}',
]


def get_agent_config_vars():
    config_vars = {}
    try:
        if os.path.exists(os.path.join(os.getcwd(), "config.ini")):
            parser = ConfigParser()
            parser.read(os.path.join(os.getcwd(), "config.ini"))
            user_name = parser.get('InsightFinder', 'insightFinder_user_name')
            license_key = parser.get('InsightFinder', 'insightFinder_license_key')
            if_url = parser.get('InsightFinder', 'insightFinder_server_url')
            if_http_proxy = parser.get('InsightFinder', 'if_http_proxy')
            if_https_proxy = parser.get('InsightFinder', 'if_https_proxy')

            project_name = parser.get('InsightFinder', 'project_name')
            system_name = parser.get('InsightFinder', 'system_name')
            sampling_interval = parser.get('InsightFinder', 'sampling_interval')
            chunk_size_kb = parser.get('InsightFinder', 'chunk_size_kb')
            fake_data_instance_prefix = parser.get('InsightFinder', 'fake_data_instance_prefix')
            fake_data_instance_count_per_project = parser.get('InsightFinder', 'fake_data_instance_count_per_project')
            fake_data_logs_total_count_per_minute = parser.get('InsightFinder', 'fake_data_logs_total_count_per_minute')

            if len(user_name) == 0:
                print("Agent not correctly configured(user name). Check config file.")
                sys.exit(1)
            if len(license_key) == 0:
                print("Agent not correctly configured(license key). Check config file.")
                sys.exit(1)
            if len(if_url) == 0:
                print("Agent not correctly configured(server url). Check config file.")
                sys.exit(1)

            if len(project_name) == 0:
                print("Agent not correctly configured(project_name). Check config file.")
                sys.exit(1)
            if len(sampling_interval) == 0:
                print("Agent not correctly configured(sampling_interval). Check config file.")
                sys.exit(1)
            if len(fake_data_instance_prefix) == 0:
                print("Agent not correctly configured(fake_data_instance_prefix). Check config file.")
                sys.exit(1)
            if len(fake_data_instance_count_per_project) == 0:
                print("Agent not correctly configured(fake_data_instance_count_per_project). Check config file.")
                sys.exit(1)
            if len(fake_data_logs_total_count_per_minute) == 0:
                print("Agent not correctly configured(fake_data_logs_total_count_per_minute). Check config file.")
                sys.exit(1)

            if sampling_interval.endswith('s'):
                sampling_interval = int(sampling_interval[:-1])
            else:
                sampling_interval = int(sampling_interval) * 60

            # defaults
            if len(chunk_size_kb) == 0:
                chunk_size_kb = 2048  # 2MB chunks by default

            # set IF proxies
            if_proxies = dict()
            if len(if_http_proxy) > 0:
                if_proxies['http'] = if_http_proxy
            if len(if_https_proxy) > 0:
                if_proxies['https'] = if_https_proxy

            config_vars['user_name'] = user_name
            config_vars['license_key'] = license_key
            config_vars['if_url'] = if_url
            config_vars['if_proxies'] = if_proxies

            config_vars['project_list'] = [x.strip() for x in project_name.split(',') if x.strip()]
            config_vars['system_name'] = system_name
            config_vars['sampling_interval'] = int(sampling_interval)  # as seconds
            config_vars['instance_prefix'] = fake_data_instance_prefix
            config_vars['chunk_size'] = int(chunk_size_kb) * 1024  # as bytes
            config_vars['instance_count'] = int(fake_data_instance_count_per_project.strip())
            config_vars['logs_total_count'] = int(fake_data_logs_total_count_per_minute.strip())
    except IOError:
        print("config.ini file is missing")
    return config_vars


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    # return len(bytearray(json.dumps(json_data)))
    return getsizeof(json.dumps(json_data))


def send_request(url, mode='GET', failure_message='Failure!', success_message='Success!',
                 **request_passthrough):
    """ sends a request to the given url """
    # determine if post or get (default)
    req = requests.get
    if mode.upper() == 'POST':
        req = requests.post

    req_num = 0
    for req_num in range(ATTEMPTS):
        try:
            response = req(url, **request_passthrough)
            if response.status_code == http.client.OK:
                return response
            else:
                print(failure_message)
                print('Response Code: {}\nTEXT: {}'.format(
                    response.status_code, response.text))
        # handle various exceptions
        except requests.exceptions.Timeout:
            print('Timed out. Reattempting...')
            continue
        except requests.exceptions.TooManyRedirects:
            print('Too many redirects.')
            break
        except requests.exceptions.RequestException as e:
            print('Exception ' + str(e))
            break

        # retry after sleep
        time.sleep(RETRY_WAIT_TIME_IN_SEC)

    print('Failed! Gave up after {} attempts.'.format(req_num + 1))
    return -1


def send_data(config_vars, metric_data):
    """ Sends parsed metric data to InsightFinder """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = dict()
    # for backend so this is the camel case in to_send_data_dict
    to_send_data_dict["metricData"] = json.dumps(metric_data)
    to_send_data_dict["licenseKey"] = config_vars['license_key']
    to_send_data_dict["projectName"] = config_vars['project_name']
    to_send_data_dict["userName"] = config_vars['user_name']
    to_send_data_dict["agentType"] = "LogStreaming"

    data_to_post = to_send_data_dict

    # send the data
    post_url = config_vars['if_url'] + "/customprojectrawdata"
    send_request(post_url, 'POST', 'Could not send request to IF',
                 str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.',
                 data=data_to_post, verify=False, proxies=config_vars['if_proxies'])
    print('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def check_project_exist(if_config_vars, project_name):
    is_project_exist = False
    try:
        print('Starting check project: ' + project_name)
        params = {
            'operation': 'check',
            'userName': if_config_vars['user_name'],
            'licenseKey': if_config_vars['license_key'],
            'projectName': project_name,
        }
        url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
        response = send_request(url, 'POST', data=params, verify=False, proxies=if_config_vars['if_proxies'])
        if response == -1:
            print('Check project error: ' + project_name)
        else:
            result = response.json()
            if result['success'] is False or result['isProjectExist'] is False:
                print('Check project error: ' + project_name)
            else:
                is_project_exist = True
                print('Check project success: ' + project_name)

    except Exception as e:
        print(e)
        print('Check project error: ' + project_name)

    create_project_sucess = False
    if not is_project_exist:
        try:
            print('Starting add project: ' + project_name)
            params = {
                'operation': 'create',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': project_name,
                'systemName': if_config_vars['system_name'] or project_name,
                'instanceType': 'PrivateCloud',
                'projectCloudType': 'PrivateCloud',
                'dataType': 'Log',
                'insightAgentType': 'Custom',
                'samplingInterval': int(if_config_vars['sampling_interval'] / 60),
                'samplingIntervalInSeconds': if_config_vars['sampling_interval'],
            }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'])
            if response == -1:
                print('Add project error: ' + project_name)
            else:
                result = response.json()
                if result['success'] is False:
                    print('Add project error: ' + project_name)
                else:
                    create_project_sucess = True
                    print('Add project success: ' + project_name)

        except Exception as e:
            print(e)
            print('Add project error: ' + project_name)

    if create_project_sucess:
        # if create project is success, sleep 10s and check again
        time.sleep(10)
        try:
            print('Starting check project: ' + project_name)
            params = {
                'operation': 'check',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': project_name,
            }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'])
            if response == -1:
                print('Check project error: ' + project_name)
            else:
                result = response.json()
                if result['success'] is False or result['isProjectExist'] is False:
                    print('Check project error: ' + project_name)
                else:
                    is_project_exist = True
                    print('Check project success: ' + project_name)

        except Exception as e:
            print(e)
            print('Check project error: ' + project_name)

    return is_project_exist


def handle_send_data_project(args):
    (config_vars, project_name, log_count_per_instance) = args

    # check and auto create project
    is_project_exist = check_project_exist(config_vars, project_name)
    if not is_project_exist:
        return f"--- Check project {project_name} failed ---"

    # all data
    data = []
    count = 0
    send_data_time = time.time()
    threads = []
    for i in range(1, config_vars['instance_count'] + 1):
        utc_time_now = int(arrow.utcnow().float_timestamp) * 1000
        instance = f"{config_vars['instance_prefix']}{i}"
        for x in range(0, log_count_per_instance):
            entry = {
                "tag": instance,
                "eventId": utc_time_now,
                "entry": choice(SAMPLE_LOGS)
            }
            data.append(entry)
            count += 1

            # use number 1000 for check the size
            if count % 1000 == 0 and get_json_size_bytes(data) >= config_vars['chunk_size']:
                # send data
                loop_thead = Thread(target=send_data, args=(config_vars, data))
                loop_thead.start()
                threads.append(loop_thead)
                data = []

    if len(data) != 0:
        loop_thead = Thread(target=send_data, args=(config_vars, data))
        loop_thead.start()
        threads.append(loop_thead)

    for thread in threads:
        thread.join()

    return f"--- Total count for {project_name}: {count}. Use {round(time.time() - send_data_time, 2)} seconds ---"


def handle_send_data(config_vars):
    logs_total_count = config_vars['logs_total_count']
    project_list = config_vars['project_list']
    log_count_per_instance = int(logs_total_count / len(project_list) / config_vars['instance_count'])

    # get args
    arg_list = [(config_vars, project_name, log_count_per_instance) for project_name in project_list]

    # start sub process by pool
    print(f"--- Start of send log data at {arrow.utcnow()} ---")
    try:
        pool = Pool(min(len(project_list), multiprocessing.cpu_count()))
        pool_result = pool.map_async(handle_send_data_project, arg_list)
        pool.close()

        results = pool_result.get()
        pool.join()

        for result in results:
            print(result)
    except KeyboardInterrupt:
        print('(%s) main exception' % os.getpid())

    print(f"--- End of send log data at {arrow.utcnow()} ---")


def int_handler(signum, frame):
    print('(%s) int_handler' % os.getpid())
    raise KeyboardInterrupt()


def main():
    # monitor SIGTERM
    signal.signal(signal.SIGTERM, int_handler)

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    importlib.reload(sys)
    config_vars = get_agent_config_vars()

    while True:
        buffer_check_thead = Thread(target=handle_send_data,
                                    args=(config_vars,))
        buffer_check_thead.start()
        buffer_check_thead.join()
        # run with 1 minute interval
        time.sleep(60)


if __name__ == "__main__":
    main()

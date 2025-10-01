import importlib
import json
import os
import sys
import time
from datetime import datetime, timezone
import requests
from configparser import ConfigParser
from concurrent.futures import ThreadPoolExecutor
from ifobfuscate import decode

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.122 Safari/537.36"

def log_in(host, user_name, password):
    url = host + '/api/v1/login-check'
    headers = {"User-Agent": USER_AGENT}
    data = {"userName": user_name, "password": password}

    try:
        start = time.time()
        resp = requests.post(url, data=data, headers=headers, timeout=10)
        end = time.time()

        if resp.status_code == 200:
            response_time = (end - start) * 1000  # convert to MS
            headers = {"User-Agent": USER_AGENT, "X-CSRF-Token": json.loads(resp.text)["token"]}
        else:
            sys.exit("Login Failed: Status Code: %d" % resp.status_code)

    except requests.exceptions.RequestException as e:
        sys.exit(str(e))

    return resp.cookies, headers, response_time

def run_endpoint_request(url, headers, cookies):
    print("[Endpoint Request] Start request: ", url, "")
    try:
        start = time.time()
        resp = requests.get(url, headers=headers, cookies=cookies, timeout=10)
        end = time.time()

        if resp.status_code == 200:
            response_time = (end - start) * 1000  # convert to MS
        else:
            print("[Endpoint Request] Response failed with status code: ", resp.status_code)
            response_time = None
    except requests.exceptions.RequestException as e:
        print("[Endpoint Request] Request failed with exception: ", str(e))
        response_time = None

    print("[Endpoint Request] Request finished for: ", url, "Response time: ", response_time)
    return response_time


def get_time():
    timestamp = datetime.now(timezone.utc)
    epoch = (int(timestamp.timestamp()) * 1000)
    return epoch


def format_data(host, response_time, timestamp):
    header = ["timestamp"]
    entry = [str(timestamp)]

    for result in response_time:
        if response_time[result]:
            header.append(result + "[" + host + "]")
            entry.append(str(round(response_time[result], 4)))

    return [dict(list(zip(header, entry)))]


def get_agent_config_vars():
    try:
        if os.path.exists(os.path.join(os.getcwd(), "config.ini")):
            parser = ConfigParser()
            parser.read(os.path.join(os.getcwd(), "config.ini"))
            license_key = parser.get('InsightFinder', 'license_key')
            project_name = parser.get('InsightFinder', 'project_name')
            user_name = parser.get('InsightFinder', 'user_name')
            server_url = parser.get('InsightFinder', 'server_url')

            # agent settings
            url = parser.get('agent', 'url')

            login_user = parser.get('agent', 'login_user')
            login_pass = decode(parser.get('agent', 'login_pass'))

            monitor_urls = json.loads(parser.get('agent', 'monitor_urls', raw=True))

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
            if len(url) == 0:
                print("Agent not correctly configured(url). Check config file.")
                sys.exit(1)
            if len(login_user) == 0:
                print("Agent not correctly configured(login_user). Check config file.")
                sys.exit(1)
            if len(login_pass) == 0:
                print("Agent not correctly configured(login_pass). Check config file.")
                sys.exit(1)
            if len(monitor_urls) == 0:
                print("Agent not correctly configured(monitor_urls). Check config file.")
                sys.exit(1)
    except IOError:
        print("config.ini file is missing")

    config_vars = {
        'license_key': license_key,
        'project_name': project_name,
        'user_name': user_name,
        'server_url': server_url,
        'url': url,
        'login_user': login_user,
        'login_pass': login_pass,
        'monitor_urls': monitor_urls
    }
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
    response = requests.post(post_url, data=json.loads(to_send_data_json))
    if response.status_code == 200:
        print(str(sys.getsizeof(to_send_data_json)) + " bytes of data are reported.")
    else:
        print("Failed to send data.")


def run_endpoints(config_vars):
    response_time = {}
    url = config_vars['url']
    (cookies, headers, response_time['Login']) = log_in(url, config_vars['login_user'], config_vars['login_pass'])

    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all tasks and store futures
        futures = {}
        for monitor_url in config_vars['monitor_urls']:
            key = next(iter(monitor_url.keys()))
            futures[key] = executor.submit(run_endpoint_request, url + monitor_url[key], headers, cookies)

        # Wait for all tasks to complete and get results
        for key, future in futures.items():
            response_time[key] = future.result()

    return response_time

if __name__ == "__main__":
    print("---------Starting program at time: ", get_time(), ":", time.strftime("%H:%M:%S "), "----------------")
    importlib.reload(sys)
    config_vars = get_agent_config_vars()
    start_time = get_time()
    start_time_ns = time.time_ns()

    response_time = run_endpoints(config_vars)

    url = config_vars['url']
    host = ''.join(url.split('//')[1:])
    metric_data = format_data(host, response_time, start_time)
    print(metric_data)
    send_data(metric_data)

    end_time_ns = time.time_ns()
    print("Total time taken from start to finish is:", (end_time_ns - start_time_ns) / 1000000, "ms")
import importlib
import json
import os
import sys
import time
from datetime import datetime, timezone
import requests
from configparser import ConfigParser
from concurrent.futures import ThreadPoolExecutor, wait
from ifobfuscate import decode

def generate_user_agent():
    timestamp = datetime.now().strftime("%Y.%m.%d.%H.%M")
    user_agent = f"ResponseTimeAgent/{timestamp} (Linux; x86_64)"
    print("Generated the UserAgent:",user_agent)
    return user_agent

USER_AGENT = generate_user_agent()


def log_in(host, user_name, password):
    url = host + '/api/v1/login-check'
    headers = {"User-Agent": USER_AGENT}
    data = {"userName": user_name, "password": password}

    try:
        start = time.time()
        resp = requests.post(url, data=data, headers=headers, timeout=60)
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
        resp = requests.get(url, headers=headers, cookies=cookies, timeout=60)
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
            genai_url = parser.get('agent', 'genai_url')
            genaichat_url = parser.get('agent', 'genaichat_url')
            llmjudge_url = parser.get('agent', 'llmjudge_url')


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
        'genai_url': genai_url,
        'genaichat_url': genaichat_url,
        'llmjudge_url': llmjudge_url,
        'login_user': login_user,
        'login_pass': login_pass,
        'monitor_urls': monitor_urls
    }
    return config_vars


def send_data(if_endpoint, metric_data, start_time):
    """ Sends parsed metric data to InsightFinder """

    # Build the metric data points array
    metric_data_points = []
    for key, value in metric_data.items():
        metric_data_points.append({
            "m": key,
            "v": value
        })

    # Create the instance data map with if_endpoint as the instance name
    idm = {
        if_endpoint: {  # Use instance name as key
            "in": if_endpoint,
            "dit": {
                str(start_time): {
                    "t": start_time,
                    "metricDataPointSet": metric_data_points  # All metrics here
                }
            }
        }
    }

    to_send_data_dict = {
        "userName": config_vars['user_name'],
        "licenseKey": config_vars['license_key'],
        "data": {
            "projectName": config_vars['project_name'],
            "userName": config_vars['user_name'],
            "iat": "Custom",
            "ct": "PrivateCloud",
            "idm": idm
        }
    }

    # send the data
    post_url = config_vars['server_url'] + "/api/v2/metric-data-receive"
    response = requests.post(post_url, json=to_send_data_dict)
    if response.status_code == 200:
        print(str(sys.getsizeof(to_send_data_dict)) + " bytes of data are reported.")
    else:
        print("Failed to send data.")


def run_if_endpoints(start_time, config_vars):
    results = {}
    url = config_vars['url']
    host = ''.join(url.split('//')[1:])

    (cookies, headers, results['Login']) = log_in(url, config_vars['login_user'], config_vars['login_pass'])

    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all tasks and store futures
        futures = {}
        for monitor_url in config_vars['monitor_urls']:
            key = next(iter(monitor_url.keys()))
            futures[key] = executor.submit(run_endpoint_request, url + monitor_url[key], headers, cookies)

        # Wait for all tasks to complete and get results
        for key, future in futures.items():
            results[key] = future.result()

    print(results)
    send_data(host, results, start_time)


def run_llm_endpoints(start_time, if_endpoint, llm_endpoint,metric_name ):
    result = {}

    incident_summary_recommandation_url = llm_endpoint + "/incident-investigation/SummaryAndRecommendations"
    incident_summary_recommandation_body = {
        "system_name": "dev",
        "occurrence_time": "2024-06-25T10:00:00Z",
        "incident_description": "System outage due to network failure",
        "root_cause_list": [
            {
                "root_cause": "Network misconfiguration",
                "time": "2024-06-25T10:00:00Z"
            },
            {
                "root_cause": "Hardware failure",
                "time": "2024-06-25T11:00:00Z"
            }
        ],
        "recommended_actions": [
            {
                "action": "Reconfigure network settings"
            },
            {
                "action": "Replace faulty hardware"
            }
        ],
        "cloud_events": "Incidents",
        "data_gap_status": [
            {
                "is_missing_anomaly": False,
                "missing_component_name": "Database",
                "project_name": "ProjectA"
            },
            {
                "is_missing_anomaly": True,
                "missing_component_name": "Database",
                "project_name": "ProjectB"
            }
        ],
        "flags": "",
        "version": "1.0.0",
        "feature_flag": "",
        "model_name": "",
        "use_rag": True,
        "rag_config": {
            "feature": [],
            "dataset_id": [
                "Microsoft_Documents"
            ],
            "company": [
                "_public"
            ],
            "zone_info": []
        },
        "username": "test_user",
        "service_now_ticket_number": "INC12345",
        "past_incident_contexts": [
            {
                "timestamp": 1678886400000,
                "description": "System performance degraded due to high CPU",
                "service_now_ticket_number": "INC98765",
                "service_now_url": "https://instance.service-now.com/nav_to.do?uri=incident.do?sys_id=..."
            }
        ]
    }
    print("[LLM Request] Start request:", llm_endpoint, "")
    try:
        start = time.time()
        resp = requests.post(incident_summary_recommandation_url, json=incident_summary_recommandation_body, timeout=60)
        end = time.time()

        if resp.status_code == 200:
            response_time = (end - start) * 1000  # convert to MS
        else:
            print("[LLM Request] Response failed with status code: ", resp.status_code)
            print(resp.text)
            response_time = None
    except requests.exceptions.RequestException as e:
        print("[LLM Request] Request failed with exception: ", str(e))
        response_time = None

    print("[LLM Request] Request finished for: ", incident_summary_recommandation_url, "Response time: ", response_time)
    if response_time is not None:
        result[metric_name] = response_time

    print(result)
    send_data(if_endpoint, result, start_time)


if __name__ == "__main__":
    print("---------Starting program at time: ", get_time(), ":", time.strftime("%H:%M:%S "), "----------------")
    importlib.reload(sys)
    config_vars = get_agent_config_vars()
    start_time = get_time()
    start_time_ns = time.time_ns()

    if_host = ''.join(config_vars['url'].split('//')[1:])
    genai_url = config_vars['genai_url']
    genaichat_url = config_vars['genaichat_url']
    llmjudge_url = config_vars['llmjudge_url']

    # Use multiple threads to run multiple endpoints concurrently
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(run_llm_endpoints, start_time, if_host, genai_url,
                            "Incident Summary and Recommendation LLM"),
            executor.submit(run_llm_endpoints, start_time, if_host, genaichat_url,
                            "Realtime Chatbot LLM"),
            executor.submit(run_llm_endpoints, start_time, if_host, llmjudge_url,
                            "LLM Evaluation Service"),

            executor.submit(run_if_endpoints, start_time, config_vars)
        ]

        # Wait for all tasks to complete
        wait(futures)


    end_time_ns = time.time_ns()
    print("Total time taken from start to finish is:", (end_time_ns - start_time_ns) / 1000000, "ms")
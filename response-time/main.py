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
            
            # Incident Summary and Recommendation LLM parameters
            system_name = parser.get('agent', 'system_name')
            customer_name = parser.get('agent', 'customer_name')
            root_cause_chain_size = parser.get('agent', 'root_cause_chain_size')
            root_cause_entry = parser.get('agent', 'root_cause_entry', raw=True)

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
        'monitor_urls': monitor_urls,
        'system_name': system_name,
        'customer_name': customer_name,
        'root_cause_chain_size': root_cause_chain_size,
        'root_cause_entry': root_cause_entry
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

    with ThreadPoolExecutor(max_workers=7) as executor:
        # Submit all tasks and store futures
        futures = {}
        
        # Add regular endpoint monitoring tasks
        for monitor_url in config_vars['monitor_urls']:
            key = next(iter(monitor_url.keys()))
            futures[key] = executor.submit(run_endpoint_request, url + monitor_url[key], headers, cookies)
        
        # Add LLM Chatbot endpoint task
        futures['Realtime Chatbot LLM'] = executor.submit(
            run_llm_chatbot_endpoint, url, headers, cookies
        )
        
        # Add Incident Summary and Recommendation LLM endpoint task
        futures['Incident Summary and Recommendation LLM'] = executor.submit(
            run_incident_summary_recommendation_llm, url, headers, cookies, config_vars
        )

        # Wait for all tasks to complete and get results
        for key, future in futures.items():
            result = future.result()
            if result is not None:
                results[key] = result

    print(results)
    send_data(host, results, start_time)


def run_llm_chatbot_endpoint(llm_endpoint, headers, cookies):
    """Helper function to run chatbot endpoint and return response time"""
    chatbot_url = llm_endpoint + "/api/v1/llama2-root-cause?tzOffset=-18000000"
    chatbot_payload = {
        "mode": "0",
        "context": "00000000-0000-0000-0000-000000000000",
        "message": "Explain me about the error code 0x14f",
    }
    
    # Required keywords to validate in response
    required_keywords = ["PDC_WATCHDOG_TIMEOUT", "Windows"]
    
    print("[LLM Chatbot Request] Start request:", llm_endpoint, "")
    try:
        start = time.time()
        resp = requests.post(chatbot_url, data=chatbot_payload, headers=headers, cookies=cookies, timeout=60)
        end = time.time()

        if resp.status_code == 200:
            response_time = (end - start) * 1000  # convert to MS
            
            # Validate response content
            try:
                response_json = json.loads(resp.text)
                response_text = str(response_json)
                
                # Check if required keywords are present in response
                keywords_found = all(keyword.lower() in response_text.lower() for keyword in required_keywords)
                
                if keywords_found:
                    return response_time
                else:
                    print("[LLM Chatbot Request] ✗ Response validation failed - Missing required keywords")
                    print(f"[LLM Chatbot Request] Required keywords: {required_keywords}")
                    print(f"[LLM Chatbot Request] Keywords found: {[kw for kw in required_keywords if kw.lower() in response_text.lower()]}")
                    print(f"[LLM Chatbot Request] Full response: {resp.text}")
                    return None
                    
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[LLM Chatbot Request] ✗ Response validation failed - Invalid JSON: {str(e)}")
                print(f"[LLM Chatbot Request] Full response: {resp.text}")
                return None
        else:
            print("[LLM Chatbot Request] Response failed with status code: ", resp.status_code)
            print(f"[LLM Chatbot Request] Response: {resp.text}")
            return None
    except requests.exceptions.RequestException as e:
        print("[LLM Chatbot Request] Request failed with exception: ", str(e))
        return None

def run_incident_summary_recommendation_llm(llm_endpoint, headers, cookies, config_vars):
    """Function to run Incident Summary and Recommendation LLM endpoint and return response time"""
    
    incident_summary_url = llm_endpoint + "/api/v1/llama2-root-cause?tzOffset=-18000000"
    
    # Build payload from config parameters - convert rootCauseEntry to JSON string for form data
    incident_summary_payload = {
        "systemName": config_vars['system_name'],
        "customerName": config_vars['customer_name'],
        "rootCauseEntry": config_vars['root_cause_entry'], 
        "rootCauseChainSize": config_vars['root_cause_chain_size'],
        "mode": "3"
    }
    
    # Required keywords to validate in response
    required_keywords = ["Root Cause Analysis", "Potential Actions"]
    
    print("[Incident Summary LLM Request] Start request:", llm_endpoint, "")
    try:
        start = time.time()
        # Use data= instead of json= to send as form data
        resp = requests.post(incident_summary_url, data=incident_summary_payload, headers=headers, cookies=cookies, timeout=60)
        end = time.time()

        if resp.status_code == 200:
            response_time = (end - start) * 1000  # convert to MS
            
            # Validate response content
            try:
                response_json = json.loads(resp.text)
                response_text = str(response_json)
                
                # Check if required keywords are present in response
                keywords_found = all(keyword.lower() in response_text.lower() for keyword in required_keywords)
                
                if keywords_found:
                    print("[Incident Summary LLM Request] ✓ Response validation successful")
                    return response_time
                else:
                    print("[Incident Summary LLM Request] ✗ Response validation failed - Missing required keywords")
                    print(f"[Incident Summary LLM Request] Required keywords: {required_keywords}")
                    print(f"[Incident Summary LLM Request] Keywords found: {[kw for kw in required_keywords if kw.lower() in response_text.lower()]}")
                    print(f"[Incident Summary LLM Request] Full response: {resp.text}")
                    return None
                    
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[Incident Summary LLM Request] ✗ Response validation failed - Invalid JSON: {str(e)}")
                print(f"[Incident Summary LLM Request] Full response: {resp.text}")
                return None
        else:
            print("[Incident Summary LLM Request] Response failed with status code: ", resp.status_code)
            print(f"[Incident Summary LLM Request] Response: {resp.text}")
            return None
    except requests.exceptions.RequestException as e:
        print("[Incident Summary LLM Request] Request failed with exception: ", str(e))
        return None

def run_llm_judge_endpoint(start_time, if_endpoint, llm_endpoint, metric_name):
    result = {}

    incident_summary_recommandation_url = llm_endpoint + "/llm-as-judge/LLMJudgeHallucination"
    incident_summary_recommandation_body = {
        "system_name": "dev",
        "trace_id": "1744654956758",
        "llm_judge_input": {
            "prompt": "what is error code 0x14f?",
            "response": "Error code 0x14f is a Device Manager error code that indicates a problem with the hardware or driver of a device connected to your computer. The code 0x14f specifically means \"This device is causing a problem due to a bad or incompatible driver.\"\nThis error can occur for various reasons, such as:\nOutdated, corrupt, or incompatible device drivers\nHardware issues or conflicts with the device\nIncorrect installation of the device or its drivers."
        },
        "flags": [
            "hallucination",
            "answer_irrelevance",
            "logical_inconsistency",
            "factual_inaccuracy"
        ],
        "version": "1.0.0",
        "feature_flag": "",
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
        "custom_judge_prompts": {
            "additionalProp1": {
            "customPrompt": "string",
            "description": "string",
            "scale": "string",
            "instruction": "string"
            },
            "additionalProp2": {
            "customPrompt": "string",
            "description": "string",
            "scale": "string",
            "instruction": "string"
            },
            "additionalProp3": {
            "customPrompt": "string",
            "description": "string",
            "scale": "string",
            "instruction": "string"
            }
        },
        "confidence_thresholds": {
            "all": 3
        }
    }
    print("[LLM Judge Request] Start request:", llm_endpoint, "")
    try:
        start = time.time()
        resp = requests.post(incident_summary_recommandation_url, json=incident_summary_recommandation_body, timeout=60)
        end = time.time()

        if resp.status_code == 200:
            response_time = (end - start) * 1000  # convert to MS
            
            # Validate response content
            try:
                response_json = json.loads(resp.text)
                
                # Required keywords to check
                required_keywords = ["PDC_WATCHDOG_TIMEOUT", "0x14f", "Device Manager"]
                
                # Fields to check for keywords
                hallucination_exp = response_json.get("hallucination_explanation", "")
                answer_relevance_exp = response_json.get("answer_relevance_explanation", "")
                factual_inaccuracy_exp = response_json.get("factual_inaccuracy_explanation", "")
                
                # Check if all required keywords are present in at least one of the explanation fields
                combined_text = f"{hallucination_exp} {answer_relevance_exp} {factual_inaccuracy_exp}"
                keywords_found = all(keyword in combined_text for keyword in required_keywords)

                if not keywords_found:
                    print("[LLM Judge Request] ✗ Response validation failed - Missing required keywords")
                    print(f"[LLM Judge Request] Required keywords: {required_keywords}")
                    print(f"[LLM Judge Request] Keywords found: {[kw for kw in required_keywords if kw in combined_text]}")
                    print(f"[LLM Judge Request] Full response: {resp.text}")
                    response_time = None
                    
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[LLM Judge Request] ✗ Response validation failed - Invalid JSON or missing fields: {str(e)}")
                print(f"[LLM Judge Request] Full response: {resp.text}")
                response_time = None
        else:
            print("[LLM Judge Request] Response failed with status code: ", resp.status_code)
            print(resp.text)
            response_time = None
    except requests.exceptions.RequestException as e:
        print("[LLM Judge Request] Request failed with exception: ", str(e))
        response_time = None

    print("[LLM Judge Request] Request finished for: ", incident_summary_recommandation_url, "Response time: ", response_time)
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
            executor.submit(run_llm_judge_endpoint, start_time, if_host, llmjudge_url,
                            "LLM Evaluation Service"),

            executor.submit(run_if_endpoints, start_time, config_vars)
        ]

        # Wait for all tasks to complete
        wait(futures)


    end_time_ns = time.time_ns()
    print("Total time taken from start to finish is:", (end_time_ns - start_time_ns) / 1000000, "ms")
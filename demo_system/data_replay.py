# -*- coding: utf-8 -*-
import json
import time
import datetime
import pytz
import random
import sys
import os
import requests
import urllib3
import logging
import utility
import constant
from configparser import SafeConfigParser


def get_agent_config_vars():
    configs = {}
    config_file_name = utility.get_config_file_name(user_name)
    try:
        if os.path.exists(os.path.join(os.getcwd(), config_file_name)):
            parser = SafeConfigParser()
            parser.read(os.path.join(os.getcwd(), config_file_name))
            # DEMO user config
            license_key = parser.get(constant.IF, constant.LICENSE_KEY)
            server_url = parser.get(constant.IF, constant.SERVER_URL)
            data_type = parser.get(constant.IF, constant.DATA_TYPE)
            start_time_str = parser.get(constant.IF, constant.START_TIME)
            normal_time_str = parser.get(constant.IF, constant.NORMAL_TIME)
            abnormal_time_str = parser.get(constant.IF, constant.ABNORMAL_TIME)
            reverse_deployment = parser.getboolean(constant.IF, constant.REVERSE_DEPLOYMENT)
            time_zone = parser.get(constant.IF, constant.TIME_ZONE)
            buggy_deploy = parser.get(constant.IF, constant.BUGGY_DEPLOY)
            buggy_deploy_start_time = parser.get(constant.IF, constant.BUGGY_DP_START_TIME)
            # DEMO project names config
            log_project_name = parser.get(constant.LOG, constant.PROJECT_NAME)
            deployment_project_name = parser.get(constant.DEPLOYMENT, constant.PROJECT_NAME)
            web_project_name = parser.get(constant.WEB, constant.PROJECT_NAME)
            metric_project_name = parser.get(constant.METRIC, constant.PROJECT_NAME)
            alert_project_name = parser.get(constant.ALERT, constant.PROJECT_NAME)
            if len(license_key) == 0:
                logging.warning("Demo agent not correctly configured(license key). Check config file.")
                sys.exit(1)
            if len(server_url) == 0:
                logging.warning("Demo agent not correctly configured(server url). Check config file.")
                sys.exit(1)
            if len(start_time_str) == 0:
                logging.warning("Demo agent not correctly configured(start time). Check config file.")
                sys.exit(1)
            if len(log_project_name) == 0:
                logging.warning("Demo agent not correctly configured(Log project name). Check config file.")
                sys.exit(1)
            if len(deployment_project_name) == 0:
                logging.warning("Demo agent not correctly configured(Deployment project name). Check config file.")
                sys.exit(1)
            if len(web_project_name) == 0:
                logging.warning("Demo agent not correctly configured(Web project name). Check config file.")
                sys.exit(1)
            if len(metric_project_name) == 0:
                logging.warning("Demo agent not correctly configured(Metric project name). Check config file.")
                sys.exit(1)
            if len(start_time_str) == 0:
                # If there's no start time, set it to current time.
                buggy_deploy_start_time = get_current_date_minute()
            if not time_zone:
                time_zone = "GMT"
            if not buggy_deploy or len(buggy_deploy)==0:
                buggy_deploy = constant.BUGGY_DEPLOY_FALSE
            configs[constant.TIME_ZONE] = time_zone
            configs[constant.BUGGY_DEPLOY] = buggy_deploy
            configs[constant.BUGGY_DP_START_TIME] = datetime.datetime.strptime(buggy_deploy_start_time, '%Y-%m-%dT%H:%M:%S')
            configs[constant.LICENSE_KEY] = license_key
            configs[constant.USER_NAME] = user_name
            configs[constant.SERVER_URL] = server_url
            configs[constant.START_TIME] = datetime.datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M:%S')
            configs[constant.NORMAL_TIME] = datetime.datetime.strptime(normal_time_str, '%Y-%m-%dT%H:%M:%S')
            if abnormal_time_str == "0" :
                configs[constant.ABNORMAL_TIME] = 0
            else:
                configs[constant.ABNORMAL_TIME] = datetime.datetime.strptime(abnormal_time_str, '%Y-%m-%dT%H:%M:%S')
            configs[constant.DATA_TYPE] = data_type
            configs[constant.REVERSE_DEPLOYMENT] = reverse_deployment
            configs[constant.LOG] = log_project_name
            configs[constant.DEPLOYMENT] = deployment_project_name
            configs[constant.WEB] = web_project_name
            configs[constant.METRIC] = metric_project_name
            configs[constant.ALERT] = alert_project_name
    except IOError:
        logging.warning("config.ini file is missing")
    return configs, parser


def get_current_time():
    return datetime.datetime.now(pytz.timezone(configs[constant.TIME_ZONE])).replace(tzinfo=None)


def get_current_date_minute():
    return get_current_time().strftime(constant.DATE_TIME_FORMAT_MINUTE)


def to_epochtime_minute(time):
    epoch = datetime.datetime.utcfromtimestamp(0)
    timestamp = int((time - epoch).total_seconds()) * 1000
    return (timestamp // constant.MINUTE) * constant.MINUTE


def to_epochtime_second(time):
    epoch = datetime.datetime.utcfromtimestamp(0)
    return int((time - epoch).total_seconds()) * 1000

def get_log_data_with_instance(timestamp, tag, data):
    data = "[" + constant.LOG_INSTANCE_LIST[random.randint(0, 9)] + "]\n" + data
    log_data = {constant.EVENT_ID: timestamp, constant.TAG: tag, constant.DATA: data}
    return log_data

def get_log_data(timestamp, tag, data):
    log_data = {constant.EVENT_ID: timestamp, constant.TAG: tag, constant.DATA: data}
    return log_data


def get_deployment_data(timestamp, instance_name, data):
    return {constant.TIMESTAMP: timestamp, constant.INSTANCE_NAME: instance_name, constant.DATA: data}


def get_time_delta_minute(time_delta):
    return (time_delta.seconds // constant.ONE_MINUTE_SEC) % 60


def get_time_delta_hour(time_delta):
    return time_delta.seconds // constant.ONE_HOUR_SEC


'''
Send deployemt data based on the hour
'''
def send_deployment_demo_data(time, is_abnormal):
    timestamp = to_epochtime_minute(time - datetime.timedelta(hours=3))
    minute = time.minute
    hour = time.hour
    if hour not in constant.DEPLOYMENT_DATA_INDEX:
        return
    # buggy deployment happened 00：31, 08:31 and 16:31
    index = constant.DEPLOYMENT_DATA_INDEX[hour]
    if is_abnormal and hour in [0, 8, 16] and minute == 31:
        data = get_deployment_data(timestamp, constant.DEP_INSTANCE, constant.DEPLOYMENT_DATA_BUGGY[index])
        replay_deployment_data(configs[constant.DEPLOYMENT], [data], "Deployment buggy data")
    # normal deployment happened 4:31, 12:31, and 20:31
    elif hour in [4, 12, 20] and minute == 31:
        data = get_deployment_data(timestamp, constant.DEP_INSTANCE, constant.DEPLOYMENT_DATA[index])
        replay_deployment_data(configs[constant.DEPLOYMENT], [data], "Deployment normal data")



'''
Send incident start from 01:25 to 01:29 or 09:25 to 09:29
'''
def send_web_or_incident_data(time, is_abnormal):
    timestamp = to_epochtime_minute(time)
    minute = time.minute
    hour = time.hour
    if is_abnormal:
        if hour in [1, 9, 17] and minute in [25, 26, 27, 28, 29]:
            data = get_log_data(timestamp, constant.INSTANCE_ALERT, constant.ALERT_INCIDENT_DATA)
            replay_log_data(configs[constant.ALERT], [data], "Alert incident data")
    normal_num = random.randint(100, 500)
    error_num = random.randint(0, 25)
    data_array = []
    status = is_abnormal and minute <= 25
    for i in range(0, normal_num):
        data = get_log_data(timestamp + i * 1000, constant.INSTANCE_ALERT, generate_web_data(False))
        data_array.append(data)
    for i in range(0, error_num):
        data = get_log_data(timestamp + i * 1000, constant.INSTANCE_ALERT, generate_web_data(True))
        data_array.append(data)
    if status:
        # burst error
        for i in range(0, random.randint(100, 150)):
            data = get_log_data(timestamp + i * 100, constant.INSTANCE_ALERT, generate_error_web_data("James", "api/v1/settingchange", "NY"))
            data_array.append(data)
            data = get_log_data(timestamp + i * 100, constant.INSTANCE_ALERT, generate_error_web_data("Robert", "api/v1/checkout", "NY"))
            data_array.append(data)
    replay_log_data(configs[constant.WEB], data_array, "Web data")


'''
Send exception data start at 1:00, 1:10, 1:20 or 9:00, 9:10, 9:20
'''
def send_log_data(time, is_abnormal):
    timestamp = to_epochtime_minute(time)
    minute = time.minute
    hour = time.hour
    if is_abnormal:
        if hour in [1, 9, 17] and minute in [0, 10, 20]:
            num_message = 1
            data_array = []
            for i in range(0, num_message):
                data = get_log_data(timestamp + i, constant.INSTANCE_CORE_SERVER, constant.EXCEPTION_LOG_DATA)
                data_array.append(data)
            replay_log_data(configs[constant.LOG], data_array, "Log exception data")
    num_message = random.randint(1, 3)
    data_array = []
    for i in range(0, num_message):
        for data in constant.NORMAL_LOG_DATA:
            log_data = get_log_data_with_instance(timestamp + i, constant.INSTANCE_CORE_SERVER, data)
            data_array.append(log_data)
    # stream some exception data
    for i in range(0, random.randint(1,3)):
        exception_data = get_log_data(timestamp + i, constant.INSTANCE_CORE_SERVER, constant.NORMAL_EXCEPTION_DATA[0])
        data_array.append(exception_data)
    for i in range(0, random.randint(1,3)):
        exception_data = get_log_data(timestamp + i, constant.INSTANCE_CORE_SERVER, constant.NORMAL_EXCEPTION_DATA[1])
        data_array.append(exception_data)
    for i in range(0, random.randint(1,3)):
        exception_data = get_log_data(timestamp + i, constant.INSTANCE_CORE_SERVER, constant.NORMAL_EXCEPTION_DATA[2])
        data_array.append(exception_data)
    replay_log_data(configs[constant.LOG], data_array, "Log normal data")


def read_metric_data(timestamp, index, metric_file_name, msg):
    with open(metric_file_name) as json_data:
        data = []
        header = map(lambda x: x.strip(), constant.HEADER.split(','))
        count = 0
        for line in json_data:
            if count == index:
                new_line = str(timestamp) + "," + line
                entry = map(lambda x: x.strip(), new_line.split(','))
                new_entry = dict(zip(header, entry))
                data.append(new_entry)
                replay_metric_data(configs[constant.METRIC], data, msg)
                break
            count += 1

def send_metric_data(time, is_abnormal):
    timestamp = to_epochtime_minute(time - datetime.timedelta(hours=3))
    minute = time.minute
    hour = time.hour
    if is_abnormal:
        if hour in [0, 1, 8, 9, 16, 17]:
            index = (minute + 30) % 60
            read_metric_data(timestamp, index, constant.ABNORMAL_DATA_FILENAME, "Metric abnormal data")
    else:
        # 180 lines in the normal data
        index = (hour * 60 + minute) % 180
        read_metric_data(timestamp, index, constant.NORMAL_DATA_FILENAME, "Metric normal data")

def send_data_to_receiver(post_url, to_send_data, log_msg, num_of_message):
    attempts = 0
    while attempts < 12:
        response_code = -1
        attempts += 1
        try:
            logging.info("Start send message.")
            response = requests.post(post_url, data=json.loads(to_send_data), verify=False)
            response_code = response.status_code
        except:
            logging.warning(
                "[%s]Attempts: %d. Fail to send data, response code: %d wait 5 sec to resend." % (
                    log_msg, attempts, response_code))
            time.sleep(5)
            continue
        if response_code == 200:
            logging.info("[%s]Data send successfully. Number of log events: %d" % (log_msg, num_of_message))
            break
        else:
            logging.warning("[%s]Attempts: %d. Fail to send data, response code: %d wait 5 sec to resend." % (
                log_msg, attempts, response_code))
            time.sleep(5)
    if attempts == 12:
        sys.exit(1)


def replay_deployment_data(project_name, deployment_data, log_msg):
    to_send_data = {"deploymentData": json.dumps(deployment_data), "licenseKey": configs[constant.LICENSE_KEY],
                    "projectName": project_name,
                    "userName": user_name}
    to_send_data = json.dumps(to_send_data)
    post_url = configs[constant.SERVER_URL] + "/api/v1/deploymentEventReceive"
    send_data_to_receiver(post_url, to_send_data, log_msg, len(deployment_data))


def replay_log_data(project_name, data, log_msg):
    to_send_data = {"metricData": json.dumps(data), "licenseKey": configs[constant.LICENSE_KEY],
                    "projectName": project_name,
                    "userName": user_name, "agentType": "LogFileReplay"}
    to_send_data = json.dumps(to_send_data)
    post_url = configs[constant.SERVER_URL] + "/customprojectrawdata"
    send_data_to_receiver(post_url, to_send_data, log_msg, len(data))

def replay_metric_data(project_name, data, msg):
    to_send_data = {"metricData": json.dumps(data), "licenseKey": configs[constant.LICENSE_KEY],
                    "projectName": project_name,
                    "userName": user_name, "agentType": "MetricFileReplay"}
    to_send_data = json.dumps(to_send_data)
    post_url = configs[constant.SERVER_URL] + "/customprojectrawdata"
    send_data_to_receiver(post_url, to_send_data, msg, len(data))


def logging_setting():
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        filename='replay_data_log.out',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')


def get_time_delta(cur_time):
    start_time = configs[constant.START_TIME]
    is_abnormal = False
    if configs[constant.DATA_TYPE] == 'normal':
        start_time = configs[constant.NORMAL_TIME]
    elif configs[constant.DATA_TYPE] == 'abnormal':
        is_abnormal = True
        start_time = configs[constant.ABNORMAL_TIME]
    time_delta = cur_time - start_time
    config_file_name = utility.get_config_file_name(user_name)
    config = SafeConfigParser()
    config.read(config_file_name)
    time = get_current_date_minute()
    if time_delta.seconds // constant.ONE_MINUTE_SEC > 180 and not is_abnormal:
            config[constant.IF][constant.DATA_TYPE] = 'abnormal'
            config[constant.IF][constant.ABNORMAL_TIME] = time
            is_abnormal = True
            utility.save_config_file(config_file_name, config)
            start_time = datetime.datetime.strptime(time, '%Y-%m-%dT%H:%M:%S')
            time_delta = cur_time - start_time
    elif time_delta.seconds // constant.ONE_MINUTE_SEC > 60 and is_abnormal:
            config[constant.IF][constant.DATA_TYPE] = 'normal'
            config[constant.IF][constant.NORMAL_TIME] = time
            is_abnormal = False
            utility.save_config_file(config_file_name, config)
            start_time = datetime.datetime.strptime(time, '%Y-%m-%dT%H:%M:%S')
            time_delta = cur_time - start_time
    return time_delta, is_abnormal


def is_abnormal_period(cur_time):
    config_file_name = utility.get_config_file_name(user_name)
    config = SafeConfigParser()
    config.read(config_file_name)
    is_abnormal = config[constant.IF][constant.DATA_TYPE] == 'abnormal'
    is_reverse = config[constant.IF][constant.REVERSE_DEPLOYMENT] == "True"
    if (cur_time.hour == 8 and cur_time.minute >= 30) or (cur_time.hour == 9 and cur_time.minute < 30):
        if not is_abnormal:
            config[constant.IF][constant.DATA_TYPE] = 'abnormal'
            config[constant.IF][constant.REVERSE_DEPLOYMENT] = 'False'
            utility.save_config_file(config_file_name, config)
        is_abnormal = True
    elif (cur_time.hour in [0, 16] and cur_time.minute >= 30) or (cur_time.hour in [1, 17] and cur_time.minute < 30):
        if is_reverse:
            config[constant.IF][constant.DATA_TYPE] = 'normal'
            utility.save_config_file(config_file_name, config)
            is_abnormal = False
        elif not is_reverse and not is_abnormal:
            config[constant.IF][constant.DATA_TYPE] = 'abnormal'
            utility.save_config_file(config_file_name, config)
            is_abnormal = True
    else:
        if is_reverse or is_abnormal:
            config[constant.IF][constant.DATA_TYPE] = 'normal'
            config[constant.IF][constant.REVERSE_DEPLOYMENT] = 'False'
            utility.save_config_file(config_file_name, config)
        is_abnormal = False
    return is_abnormal


def get_random_from_list(list):
    return list[random.randint(0, len(list) - 1)]


def generate_web_data(is_abnormal_flag):
    user = get_random_from_list(constant.WEB_USER)
    state = get_random_from_list(constant.WEB_ENV)
    api = get_random_from_list(constant.WEB_API)
    api_data = {"user": user,"state": state, "api": api, "status":200}
    if is_abnormal_flag:
        api_data["status"] = get_random_from_list(constant.WEB_ERROR_CODE)
    return api_data

def generate_error_web_data(user, api, state):
    return {"user": user,"state": state, "api": api, "status":500}

def send_normal_log_data(timestamp):
    num_message = random.randint(1, 3)
    data_array = []
    for i in range(0, num_message):
        for data in constant.NORMAL_LOG_DATA:
            log_data = get_log_data_with_instance(timestamp + i, constant.INSTANCE_CORE_SERVER, data)
            data_array.append(log_data)
    # stream some exception data
    for i in range(0, random.randint(1,3)):
        exception_data = get_log_data(timestamp + i, constant.INSTANCE_CORE_SERVER, constant.NORMAL_EXCEPTION_DATA[0])
        data_array.append(exception_data)
    for i in range(0, random.randint(1,3)):
        exception_data = get_log_data(timestamp + i, constant.INSTANCE_CORE_SERVER, constant.NORMAL_EXCEPTION_DATA[1])
        data_array.append(exception_data)
    for i in range(0, random.randint(1,3)):
        exception_data = get_log_data(timestamp + i, constant.INSTANCE_CORE_SERVER, constant.NORMAL_EXCEPTION_DATA[2])
        data_array.append(exception_data)
    replay_log_data(configs[constant.LOG], data_array, "Log normal data")

def send_abnormal_log_data(timestamp):
    data_array = []
    data = get_log_data(timestamp, constant.INSTANCE_CORE_SERVER, constant.EXCEPTION_LOG_DATA)
    data_array.append(data)
    replay_log_data(configs[constant.LOG], data_array, "Log exception data")

def send_web_data(timestamp):
    normal_num = random.randint(100, 500)
    error_num = random.randint(0, 25)
    data_array = []
    for i in range(0, normal_num):
        data = get_log_data(timestamp + i * 1000, constant.INSTANCE_ALERT, generate_web_data(False))
        data_array.append(data)
    for i in range(0, error_num):
        data = get_log_data(timestamp + i * 1000, constant.INSTANCE_ALERT, generate_web_data(True))
        data_array.append(data)

    # burst error 
    for i in range(0, random.randint(100, 150)):
        data = get_log_data(timestamp + i * 100, constant.INSTANCE_ALERT, generate_error_web_data("James", "api/v1/settingchange", "NY"))
        data_array.append(data)
        data = get_log_data(timestamp + i * 100, constant.INSTANCE_ALERT, generate_error_web_data("Robert", "api/v1/checkout", "NY"))
        data_array.append(data)
    replay_log_data(configs[constant.WEB], data_array, "Web data")

def send_incident_data(timestamp):
    data = get_log_data(timestamp, constant.INSTANCE_ALERT, constant.ALERT_INCIDENT_DATA)
    replay_log_data(configs[constant.ALERT], [data], "Alert incident data")
    
def send_log_data_for_buggy_dp(timestamp):
    send_abnormal_log_data(timestamp)
    send_normal_log_data(timestamp)

def send_web_incident_data_for_buggy_dp(lasting_time, timestamp):
    # Send incident if the abnormal lasts for longer than 14 min
    if lasting_time > 14 and lasting_time < 20:
        send_incident_data(timestamp)
    send_web_data(timestamp)

def send_abnormal_metric_data(timestamp, lasting_time):
    # We will start the ingestion from the 26th row abnormal data.
    index = lasting_time + 26
    read_metric_data(timestamp, index, constant.ABNORMAL_DATA_FILENAME, "Metric abnormal data")

def buggy_deploy():
    b_start_time = configs[constant.BUGGY_DP_START_TIME]
    current_time = get_current_time()
    timestamp = to_epochtime_minute(current_time)
    lasting_time =  current_time - b_start_time
    # Get the time gap in minute
    lasting_time = lasting_time.total_seconds() // 60
    if lasting_time > 15:
        # Stop the buggy deployment after running for 15 mins.
        parser.set(constant.IF, constant.BUGGY_DEPLOY, constant.BUGGY_DEPLOY_FALSE)
        config_file_name = utility.get_config_file_name(user_name)
        utility.save_config_file(config_file_name, parser)
        return
    # Do things based on the current lasting_time
    if lasting_time < 1:
        # Trigger the buggy deployment.
        data = get_deployment_data(timestamp, constant.DEP_INSTANCE, constant.DEPLOYMENT_DATA_BUGGY[0])
        replay_deployment_data(configs[constant.DEPLOYMENT], [data], "Deployment buggy data")

    # after 15 mins , ingest incident.
    send_web_incident_data_for_buggy_dp(lasting_time,timestamp)
    # the normal and abnormal logs are streaming all the time
    send_log_data_for_buggy_dp(timestamp)
    # Send abnormal metric right after the deployment 
    send_abnormal_metric_data(timestamp, lasting_time)

if __name__ == "__main__":
    logging_setting()
    urllib3.disable_warnings()
    user_name = utility.get_username()
    configs, parser = get_agent_config_vars()
    if configs[constant.BUGGY_DEPLOY] == constant.BUGGY_DEPLOY_TRUE:
        logging.info("==========Buggy Deployment Triggered==========")
        buggy_deploy()
    else:
        cur_time = get_current_time() + datetime.timedelta(hours=3)
        is_abnormal_flag = is_abnormal_period(cur_time)
        logging.info("==========New Data Send Round==========")
        logging.info("Current time: " + str(cur_time) + ", status: " + str(is_abnormal_flag))
        send_web_or_incident_data(cur_time, is_abnormal_flag)
        send_log_data(cur_time, is_abnormal_flag)
        send_deployment_demo_data(cur_time, is_abnormal_flag)
        send_metric_data(cur_time, is_abnormal_flag)

import json
import time
import datetime
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
            # DEMO project names config
            log_project_name = parser.get(constant.LOG, constant.PROJECT_NAME)
            deployment_project_name = parser.get(constant.DEPLOYMENT, constant.PROJECT_NAME)
            web_project_name = parser.get(constant.WEB, constant.PROJECT_NAME)
            metric_project_name = parser.get(constant.METRIC, constant.PROJECT_NAME)
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
    except IOError:
        logging.warning("config.ini file is missing")
    return configs


def get_current_time():
    return datetime.datetime.now()


def get_current_date_minute():
    return datetime.datetime.now().strftime(constant.DATE_TIME_FORMAT_MINUTE)


def to_epochtime_minute(time):
    epoch = datetime.datetime.utcfromtimestamp(0)
    timestamp = int((time - epoch).total_seconds()) * 1000
    return (timestamp // constant.MINUTE) * constant.MINUTE


def to_epochtime_second(time):
    epoch = datetime.datetime.utcfromtimestamp(0)
    return int((time - epoch).total_seconds()) * 1000

def get_log_data(timestamp, tag, data):
    log_data = {constant.EVENT_ID: timestamp, constant.TAG: tag, constant.DATA: data}
    return log_data


def get_deployment_data(timestamp, instance_name, data):
    return {constant.TIMESTAMP: timestamp, constant.INSTANCE_NAME: instance_name, constant.DATA: data}


def get_time_delta_minute(time_delta):
    return (time_delta.seconds // constant.ONE_MINUTE_SEC) % 60


def get_time_delta_hour(time_delta):
    return (time_delta.seconds // constant.ONE_HOUR_SEC) % 4


def change_reverse_status():
    config_file_name = utility.get_config_file_name(user_name)
    config = SafeConfigParser()
    config.read(config_file_name)
    config[constant.IF][constant.REVERSE_DEPLOYMENT] = 'False'
    utility.save_config_file(config_file_name, config)

'''
Send deployemt data at 1 minutes in 4th hour, send reverse deployment data in 1 minute in even hour
'''
def send_deployment_demo_data(time, time_delta, is_abnormal):
    timestamp = to_epochtime_minute(time)
    minute = get_time_delta_minute(time_delta)
    hour = get_time_delta_hour(time_delta)
    if configs[constant.REVERSE_DEPLOYMENT]:
        #data = get_deployment_data(timestamp, constant.DEP_INSTANCE, constant.DEPLOYMENT_DATA_REVERSE)
        #replay_deployment_data(configs[constant.DEPLOYMENT], [data], "Deployment reverse data")
        change_reverse_status()
        return
    if is_abnormal and minute == 1 and hour == 0:
        data = get_deployment_data(timestamp, constant.DEP_INSTANCE, constant.DEPLOYMENT_DATA)
        replay_deployment_data(configs[constant.DEPLOYMENT], [data], "Deployment data")


'''
Send incident data at 59 minutes 4th hour, otherwise normal log
'''
def send_web_data(time, time_delta, is_abnormal):
    timestamp = to_epochtime_minute(time)
    minute = get_time_delta_minute(time_delta)
    hour = get_time_delta_hour(time_delta)
    if is_abnormal:
        if minute == 59 and hour == 0:
            data = get_log_data(timestamp, constant.WEB_INSTANCE, constant.WEB_INCIDENT_DATA)
            replay_log_data(configs[constant.WEB], [data], "Web incident data")
    else:
        num_message = random.randint(1, 3)
        data_array = []
        for i in range(0, num_message):
            data = get_log_data(timestamp + i, constant.WEB_INSTANCE, constant.WEB_NORMAL_DATA[random.randint(0, 3)])
            data_array.append(data)
        replay_log_data(configs[constant.WEB], data_array, "Web normal data")


'''
Send exception data start at 35,45,55 minutes in 4th hour.
'''
def send_log_data(time, time_delta, is_abnormal):
    timestamp = to_epochtime_minute(time)
    minute = get_time_delta_minute(time_delta)
    hour = get_time_delta_hour(time_delta)
    if is_abnormal:
        if minute in [35,45,55] and hour == 0:
            num_message = 1
            data_array = []
            for i in range(0, num_message):
                data = get_log_data(timestamp + i, constant.LOG_INSTANCE, constant.EXCEPTION_LOG_DATA)
                data_array.append(data)
            replay_log_data(configs[constant.LOG], data_array, "Log exception data")
    else:
        num_message = random.randint(2, 5)
        data_array = []
        for i in range(0, num_message):
            data_write = get_log_data(timestamp + i, constant.LOG_INSTANCE, constant.NORMAL_LOG_DATA[0])
            data_finished = get_log_data(timestamp + i + 50, constant.LOG_INSTANCE, constant.NORMAL_LOG_DATA[1])
            data_array.append(data_write)
            data_array.append(data_finished)
        # stream some exception data
        for i in range(0, random.randint(0,2)):
            exception_data = get_log_data(timestamp + i, constant.LOG_INSTANCE, constant.NORMAL_EXCEPTION_DATA[0])
            data_array.append(exception_data)
        for i in range(0, random.randint(0,2)):
            exception_data = get_log_data(timestamp + i, constant.LOG_INSTANCE, constant.NORMAL_EXCEPTION_DATA[1])
            data_array.append(exception_data)
        for i in range(0, random.randint(0,2)):
            exception_data = get_log_data(timestamp + i, constant.LOG_INSTANCE, constant.NORMAL_EXCEPTION_DATA[2])
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

def send_metric_data(time, time_delta, is_abnormal):
    timestamp = to_epochtime_minute(time)
    minute = get_time_delta_minute(time_delta)
    hour = get_time_delta_hour(time_delta)
    if is_abnormal:
        if hour == 0:
            index = minute
            read_metric_data(timestamp, index, constant.ABNORMAL_DATA_FILENAME, "Metric abnormal data")
        #else:
        #    index = 59
        #    read_metric_data(timestamp, index, constant.ABNORMAL_DATA_FILENAME, "Metric abnormal data")
    else:
        index = minute + hour * 60
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


if __name__ == "__main__":
    logging_setting()
    urllib3.disable_warnings()
    user_name = utility.get_username()
    configs = get_agent_config_vars()
    cur_time = get_current_time()
    time_delta, is_abnormal = get_time_delta(cur_time)
    send_log_data(cur_time, time_delta, is_abnormal)
    send_web_data(cur_time, time_delta, is_abnormal)
    send_deployment_demo_data(cur_time, time_delta, is_abnormal)
    send_metric_data(cur_time, time_delta, is_abnormal)

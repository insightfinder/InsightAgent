# -*- coding: utf-8 -*-
import constant
import utility
import datetime
import random
import logging
import json
from configparser import SafeConfigParser
from optparse import OptionParser


def get_parameters():
    parser = OptionParser(usage="Usage: %prog [options]")
    parser.add_option("-l", "--license_key",
                      action="store", dest="license_key", help="User's license key")
    parser.add_option("-u", "--user_name",
                      action="store", dest="user_name", help="User account's name")
    parser.add_option("-s", "--server_url",
                      action="store", dest="server_url", help="Server url to stream data")
    parser.add_option("-d", "--data_type",
                      action="store", dest="data_type", help="The data type of the data to stream")
    parser.add_option("-b", "--buggy_deploy",
                      action="store", dest="buggy_deploy", help="The manual triggered buggy deployment")
    (options, args) = parser.parse_args()
    parameters = {}
    if options.license_key is not None:
        parameters[constant.LICENSE_KEY] = options.license_key
    if options.user_name is not None:
        parameters[constant.USER_NAME] = options.user_name
    if options.server_url is not None:
        parameters[constant.SERVER_URL] = options.server_url
    if options.data_type is not None:
        parameters[constant.DATA_TYPE] = options.data_type
    else:
        parameters[constant.DATA_TYPE] = None
    if options.buggy_deploy is not None:
        parameters[constant.BUGGY_DEPLOY] = options.buggy_deploy
    else:
        parameters[constant.BUGGY_DEPLOY] = constant.BUGGY_DEPLOY_FALSE
    return parameters


def get_current_time():
    current_time = datetime.datetime.now()
    epoch = datetime.datetime.utcfromtimestamp(0)
    timestamp = int((current_time - epoch).total_seconds()) * 1000
    return (timestamp // constant.MINUTE) * constant.MINUTE


def get_current_date_minute():
    return datetime.datetime.now().strftime(constant.DATE_TIME_FORMAT_MINUTE)


def get_current_day():
    return datetime.datetime.now().strftime(constant.DATE_TIME_FORMAT_DAY)


def action_filter(config):
    map = json.loads(config[constant.IF][constant.ACTION_TRIGGERED_MAP])
    cur_day = get_current_day()
    # Clean the previous day's record
    for day in list(map):
        if day != cur_day:
            del map[day]
    # Randomly choose need to reverse or not
    is_reverse = random.randint(0, 1) > 0
    if cur_day not in map:
        map[cur_day] = [is_reverse]
    else:
        success = 0
        fail = 0
        for val in map[cur_day]:
            if val:
                success += 1
            else:
                fail += 1
        if success < fail - 1:
            is_reverse = True
        if fail < success - 1:
            is_reverse = False
        map[cur_day].append(is_reverse)
    config[constant.IF][constant.ACTION_TRIGGERED_MAP] = json.dumps(map)
    return is_reverse


def modified_config_file():
    user_name = parameters[constant.USER_NAME]
    config_file_name = utility.get_config_file_name(user_name)
    config = SafeConfigParser()
    config.read(config_file_name)
    current_data_type = config[constant.IF][constant.DATA_TYPE]
    # Update the buggy deployment flag if it's different
    if config[constant.IF][constant.BUGGY_DEPLOY] != parameters[constant.BUGGY_DEPLOY]:
        logging.info(
            "Buggy deployment flag needs to be updated from " +
            config[constant.IF][constant.BUGGY_DEPLOY] +" to " + parameters[constant.BUGGY_DEPLOY]
        )
        if parameters[constant.BUGGY_DEPLOY] == constant.BUGGY_DEPLOY_TRUE:
            config[constant.IF][constant.BUGGY_DP_START_TIME] = get_current_date_minute()
            logging.info("Manual buggy deployment triggered.")
            config[constant.IF][constant.BUGGY_DEPLOY] = constant.BUGGY_DEPLOY_TRUE
        else:
            config[constant.IF][constant.BUGGY_DEPLOY] = constant.BUGGY_DEPLOY_FALSE
            logging.info("Turn off buggy deployment.")
    else:
        logging.info("Current buggy deployment flag is: "+ config[constant.IF][constant.BUGGY_DEPLOY]+". Won't update it.")
    if current_data_type == 'abnormal' and parameters[constant.DATA_TYPE] == 'normal':
        is_reverse = True
        logging.info("Modification triggered: is_reverse is " + str(is_reverse))
        if is_reverse:
            # Action triggered switch to normal data
            config[constant.IF][constant.REVERSE_DEPLOYMENT] = 'True'
            config[constant.IF][constant.NORMAL_TIME] = get_current_date_minute()
            config[constant.IF][constant.DATA_TYPE] = parameters[constant.DATA_TYPE]
            logging.info("Reverse buggy deployment action triggered.")
    utility.save_config_file(config_file_name, config)


def generate_config_file():
    user_name = parameters[constant.USER_NAME]
    config_file_name = utility.get_config_file_name(user_name)
    time = get_current_date_minute()
    config = SafeConfigParser()
    config[constant.IF] = {constant.LICENSE_KEY: parameters[constant.LICENSE_KEY],
                           constant.USER_NAME: user_name,
                           constant.SERVER_URL: parameters[constant.SERVER_URL],
                           constant.START_TIME: time,
                           constant.DATA_TYPE: constant.DATA_TYPE_NORMAL,
                           constant.REVERSE_DEPLOYMENT: 'False',
                           constant.BUGGY_DEPLOY: constant.BUGGY_DEPLOY_FALSE,
                           constant.NORMAL_TIME: time,
                           constant.ABNORMAL_TIME: 0,
                           constant.ACTION_TRIGGERED_MAP: {},
                           constant.TIME_ZONE: 'GMT'}
    config[constant.LOG] = {constant.PROJECT_NAME: constant.LOG_PROJECT_NAME}
    config[constant.DEPLOYMENT] = {constant.PROJECT_NAME: constant.DEPLOYMENT_PROJECT_NAME}
    config[constant.WEB] = {constant.PROJECT_NAME: constant.WEB_PROJECT_NAME}
    config[constant.METRIC] = {constant.PROJECT_NAME: constant.METRIC_PROJECT_NAME}
    config[constant.ALERT] = {constant.PROJECT_NAME: constant.ALERT_PROJECT_NAME}
    utility.save_config_file(config_file_name, config)


def is_initialized():
    return parameters[constant.DATA_TYPE] is None


def logging_setting():
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        filename='demo_controller.out',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')


if __name__ == "__main__":
    logging_setting()
    parameters = get_parameters()
    if is_initialized():
        generate_config_file()
    else:
        modified_config_file()

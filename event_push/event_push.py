import os
import sys
import time
import warnings
import glob
import json
import logging
import configparser
import urllib.parse
import http.client
import urllib3
import importlib
from time import sleep
from datetime import date, datetime
from optparse import OptionParser
from logging.handlers import QueueHandler
import multiprocessing
from multiprocessing.pool import ThreadPool
from multiprocessing import Pool, TimeoutError

import arrow
import requests

ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
ATTEMPTS = 3


def get_anomaly_data(logger, edge_vars, main_vars, if_config_vars):
    # Format Request
    params = {
        "customerName": edge_vars['user_name'],
        "licenseKey": edge_vars['license_key']
    }
    url = edge_vars['if_url'] + '/api/v2/projectanomalytransferall'
    logger.info(f"Start fetching data: {url} {params}")

    # Send Request
    resp = requests.get(url, params=params, verify=False)
    count = 0
    logger.debug(f"HTTP Response Code: {resp.status_code}")
    while resp.status_code not in [200, 204] and count < edge_vars['retry']:
        time.sleep(60)
        resp = requests.get(url, params=params, verify=False)
        logger.debug(f"HTTP Response Code: {resp.status_code}")
        count += 1

    result = {}
    try:
        result = resp.json()
        logger.info(f"Fetching data successfully.")
    except Exception as e:
        logger.error(e)
        logger.error(f"Fetching data error!")

    logger.debug(f"{result}")
    return result


def get_his_anomaly_data(args):
    logger, edge_vars, main_vars, if_config_vars, time_now, start_time, end_time = args

    # Send task
    params = {
        "customerName": edge_vars['user_name'],
        "licenseKey": edge_vars['license_key'],
        'startTime': start_time,
        "endTime": end_time
    }
    url = edge_vars['if_url'] + '/localcron/anomalytransfer'
    logger.info(f"Send fetching data task: {url} {params}")

    transfer_key = None
    resp = requests.get(url, params=params, verify=False)
    count = 0
    logger.debug(f"HTTP Response Code: {resp.status_code}")
    while resp.status_code != 200 and count < edge_vars['retry']:
        time.sleep(60)
        resp = requests.get(url, params=params, verify=False)
        logger.debug(f"HTTP Response Code: {resp.status_code}")
        count += 1
    transfer_key = resp.json().get('AnomalyTransferHistoricalStatusKey')
    logger.info(f"Transfer key: {transfer_key}")

    # check the status, and wait the timeout
    is_finished = False
    utc_time_check = int(arrow.utcnow().float_timestamp)
    time_wait_result = cli_config_vars['timeout'] - 60 if cli_config_vars['timeout'] > 60 else 0
    while not is_finished and utc_time_check - time_now < time_wait_result:
        params = {
            "customerName": edge_vars['user_name'],
            "licenseKey": edge_vars['license_key'],
            'anomalyTransferHistoricalStatusKeyStr': transfer_key
        }
        url = edge_vars['if_url'] + '/api/v2/projectanomalytransferstatus'
        logger.info(f"checking task status: {url} {params}")
        resp = requests.get(url, params=params, verify=False)
        count = 0
        logger.debug(f"HTTP Response Code: {resp.status_code}")
        while resp.status_code != 200 and count < edge_vars['retry']:
            time.sleep(60)
            resp = requests.get(url, params=params, verify=False)
            logger.debug(f"HTTP Response Code: {resp.status_code}")
            count += 1
        result = resp.json()
        is_finished = result.get('isFinished', False)
        total_task_number = result.get('totalTaskNumber', 0)
        finish_task_number = result.get('finishedTaskNumber', 0)
        logger.info(
            f"Task status: {'finished' if is_finished else 'Not finished'}. {finish_task_number}/{total_task_number}")

        # sleep if not finished
        if not is_finished:
            time.sleep(10)
            utc_time_check = int(arrow.utcnow().float_timestamp)

    if is_finished:
        logger.info(f'Task:{transfer_key} finished.')
    else:
        logger.warning(f'Task:{transfer_key} not finished!')

    # Get all data
    params = {
        "customerName": edge_vars['user_name'],
        "licenseKey": edge_vars['license_key'],
        'anomalyTransferHistoricalStatusKeyStr': transfer_key
    }
    url = edge_vars['if_url'] + '/api/v2/projectanomalytransferall'
    logger.info(f"Start fetching data with no wait: {url} {params}")

    resp = requests.get(url, params=params, verify=False)
    count = 0
    logger.debug(f"HTTP Response Code: {resp.status_code}")
    while resp.status_code not in [200, 204] and count < edge_vars['retry']:
        time.sleep(60)
        resp = requests.get(url, params=params, verify=False)
        logger.debug(f"HTTP Response Code: {resp.status_code}")
        count += 1

    result = {}
    try:
        result = resp.json()
        logger.info(f"Fetching data successfully.")
    except Exception as e:
        logger.error(e)
        logger.error(f"Fetching data error!")

    logger.debug(f"{result}")
    return result


def send_anomaly_data(args):
    logger, c_config, main_vars, project_edge_data = args

    # parse data
    transfer_data = project_edge_data.get("transferData")
    try:
        data = json.loads(transfer_data)
    except Exception as e:
        logger.error(e)
        return

    project_name = project_edge_data.get("projectName")
    user_name = project_edge_data.get("customerName")
    system_name = data.get('DATA', {}).get("systemName")
    data_type = data.get('DATA', {}).get("dataType")
    agent_type = data.get('DATA', {}).get("insightAgentType")
    large_project = data.get('DATA', {}).get("isLargeProject")
    sampling_interval = data.get('DATA', {}).get("sampleIntervalInMinutes")

    # do not send if only testing
    if c_config['testing']:
        return

    # check project and create
    check_project_vals = {
        'if_url': main_vars['if_url'],
        'user_name': main_vars['user_name'],
        "license_key": main_vars['license_key'],
        "if_proxies": main_vars['if_proxies'],
        "system_name": system_name,
        "project_name": project_name,
        "large_project": large_project or False,
        "dataType": data_type or 'Log',
        "insightAgentType": agent_type or 'Custom',
        "sampling_interval": int(sampling_interval or 10) * 60,
    }
    check_success = check_project_exist(logger, check_project_vals)
    if not check_success:
        return

    # send project data
    params = {
        'userName': main_vars['user_name'],
        "customerName": main_vars['user_name'],
        "licenseKey": main_vars['license_key']
    }
    url = main_vars['if_url'] + '/api/v2/projectanomalyreceive'
    logger.info(f"Start sending data: {url} {params}")
    resp = requests.post(url, params=params, json=data, verify=False)
    count = 0
    logger.debug(f"HTTP Response Code: {resp.status_code}")
    while resp.status_code != 200 and count < main_vars['retry']:
        time.sleep(60)
        resp = requests.post(url, params=params, json=data, verify=False)
        logger.debug(f"HTTP Response Code: {resp.status_code}")
        count += 1

    if resp.status_code in [200]:
        logger.info(f"Sending data successfully.")
    else:
        logger.error(f"Sending data error!")

    return resp.status_code


def get_debug_info(logger, c_config, edge_vars, main_vars, if_config_vars):
    # list all projects info
    if c_config.get('list-projects'):
        params = {
            "userName": edge_vars['user_name'],
            "licenseKey": edge_vars['license_key'],
        }
        url = edge_vars['if_url'] + '/api/v1/listallprojects'
        logger.info(f"Start fetching projects info: {url}")
        resp = requests.get(url, params=params, verify=False)
        count = 0
        logger.debug(f"HTTP Response Code: {resp.status_code}")
        while resp.status_code != 200 and count < edge_vars['retry']:
            time.sleep(60)
            resp = requests.get(url, params=None, verify=False)
            logger.debug(f"HTTP Response Code: {resp.status_code}")
            count += 1

        try:
            result = resp.json()
            logger.info(f"Fetching projects info successfully.")
            logger.info(f"Projects info: {result}")
        except Exception as e:
            logger.error(e)
            logger.error(f"Fetching projects info error!")

    elif c_config.get('debug-project'):
        params = {
            "userName": edge_vars['user_name'],
            "licenseKey": edge_vars['license_key'],
            'projectName': c_config.get('debug-project'),
            'projectType': c_config.get('project-type'),
            'includeModelDetail': c_config.get('includeModelDetail', False),
            'includeDetectionDetail': c_config.get('includeDetectionDetail', False),
            'includeOther': c_config.get('includeOther', False),
        }

        if c_config.get('timerange'):
            try:
                time_range = [x for x in c_config['timerange'].split(',') if x.strip()]
                time_range = [int(arrow.get(x).float_timestamp * 1000) for x in time_range]
                params['startTime'] = time_range[0]
                params['endTime'] = time_range[1]
            except Exception as e:
                logger.warning(e)
                logger.error('Error argument: timerange')

        # get project debug info
        url = edge_vars['if_url'] + '/api/v1/projectreport'
        logger.info(f"Start fetching debug info: {url} {params}")
        resp = requests.get(url, params=params, verify=False)
        count = 0
        logger.debug(f"HTTP Response Code: {resp.status_code}")
        while resp.status_code != 200 and count < edge_vars['retry']:
            time.sleep(60)
            resp = requests.get(url, params=params, verify=False)
            logger.debug(f"HTTP Response Code: {resp.status_code}")
            count += 1

        try:
            result = resp.json()
            logger.info(f"Fetching debug info successfully.")
            logger.info(f"Debug info: {result}")
        except Exception as e:
            logger.error(e)
            logger.error(f"Fetching debug info error!")


def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    """
    """
    parser.add_option('-c', '--config', action='store', dest='config', default=abs_path_from_cur('conf.d'),
                      help='Path to the config files to use. Defaults to {}'.format(abs_path_from_cur('conf.d')))
    parser.add_option('-p', '--processes', action='store', dest='processes', default=multiprocessing.cpu_count() * 4,
                      help='Number of processes to run')
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data).' +
                           ' Automatically turns on verbose logging')
    parser.add_option('--timeout', action='store', dest='timeout', default=5,
                      help='Minutes of timeout for all processes. Default is 5.')
    parser.add_option('--list-projects', action='store_true', dest='list-projects', default=False,
                      help='List all projects in edge server. ')
    parser.add_option('--debug-project', action='store', dest='debug-project',
                      help='The name of the project used to get debug information. '
                           + 'This can be get from field "projectName" in project list with option "--list-projects". '
                           + 'Please also specify "--project-type"  '
                           + 'belong to this project. '
                           + 'Example: --debug-project="test_project"')
    parser.add_option('--project-type', action='store', dest='project-type',
                      help='The type of the debug-project used to get debug information. '
                           + 'This can be get from field "dataType" in project list with option "--list-projects". '
                           + 'Example: --project-type="Log" or --project-type="Metric"')
    parser.add_option('--timerange', action='store', dest='timerange',
                      help='The range of times used to get details debug information. '
                           + 'Example: --timerange="2022-06-10 00:00:00,2022-06-11 00:00:00"')
    parser.add_option('--includeModelDetail', action='store_true', dest='includeModelDetail', default=False,
                      help='Check the models info belong to debug-project. '
                           + 'For metric project, If you set "--includeModelDetail", '
                           + 'but you don’t have "modelDetails" in your return, '
                           + 'it means your project don’t have model created for detection within these time range, '
                           + 'your detection will fail, '
                           + 'if rawCsvLength=0 or numberOfColumn=0 or numberOfRow=0, '
                           + 'it means your data in metric may have some problem, '
                           + 'this project didn’t receive any data for that range. ')
    parser.add_option('--includeDetectionDetail', action='store_true', dest='includeDetectionDetail', default=False,
                      help='Check the detections info belong to debug-project. ')
    parser.add_option('--includeOther', action='store_true', dest='includeOther', default=False,
                      help='Check the others info belong to debug-project. ')
    (options, args) = parser.parse_args()

    config_vars = {
        'config': options.config if os.path.isdir(options.config) else abs_path_from_cur('conf.d'),
        'processes': int(options.processes),
        'testing': False,
        'log_level': logging.INFO,
        'timeout': int(options.timeout) * 60,
        'debug-project': options.ensure_value('debug-project', None),
        'project-type': options.ensure_value('project-type', None),
        'timerange': options.ensure_value('timerange', None),
    }

    # handle some requirement info
    if config_vars['debug-project'] and not config_vars['project-type']:
        sys.exit(f'Error. If you want debug project info, please also specify "--project-type".')

    if options.testing:
        config_vars['testing'] = True

    if options.verbose:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING

    if options.ensure_value('list-projects', False):
        config_vars['list-projects'] = True
    if options.ensure_value('includeModelDetail', False):
        config_vars['includeModelDetail'] = True
    if options.ensure_value('includeDetectionDetail', False):
        config_vars['includeDetectionDetail'] = True
    if options.ensure_value('includeOther', False):
        config_vars['includeOther'] = True

    return config_vars


def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))


def get_config_vars(logger, config_ini):
    """ Read and parse config.ini """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False
    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)

        try:
            # Edge Node Parameters
            edge_user = config_parser.get('edge', 'user_name')
            edge_license = config_parser.get('edge', 'license_key')
            edge_url = config_parser.get('edge', 'if_url')
            edge_retry = config_parser.get('edge', 'retry') or 3
            edge_http_proxy = config_parser.get('edge', 'http_proxy')
            edge_https_proxy = config_parser.get('edge', 'https_proxy')

            # Main IF Parameters
            main_user = config_parser.get('main', 'user_name')
            main_license = config_parser.get('main', 'license_key')
            main_url = config_parser.get('main', 'if_url')
            main_retry = config_parser.get('main', 'retry') or 3
            main_http_proxy = config_parser.get('main', 'http_proxy')
            main_https_proxy = config_parser.get('main', 'https_proxy')

            # if config
            # time range
            his_time_range = config_parser.get('insightfinder', 'his_time_range')
            run_interval = config_parser.get('insightfinder', 'run_interval')

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        # set edge proxies
        edge_proxies = dict()
        if len(edge_http_proxy) > 0:
            edge_proxies['http'] = edge_http_proxy
        if len(edge_https_proxy) > 0:
            edge_proxies['https'] = edge_https_proxy

        # set main proxies
        main_proxies = dict()
        if len(main_http_proxy) > 0:
            main_proxies['http'] = main_http_proxy
        if len(main_https_proxy) > 0:
            main_proxies['https'] = main_https_proxy

        if not edge_user or not main_user:
            return config_error(logger, 'user_name')
        if not edge_license or not main_license:
            return config_error(logger, 'license_key')
        if not edge_url or not main_url:
            return config_error(logger, 'if_url')
        if edge_user != main_user:
            return config_error(logger, 'user_name should be same in microbrain and mainbrain')

        if len(his_time_range) != 0:
            his_time_range = [x for x in his_time_range.split(',') if x.strip()]
            his_time_range = [int(arrow.get(x).float_timestamp) for x in his_time_range]
        if len(run_interval) == 0:
            return config_error(logger, 'run_interval')
        if run_interval.endswith('s'):
            run_interval = int(run_interval[:-1])
        else:
            run_interval = int(run_interval) * 60

        edge = {
            'user_name': edge_user,
            'license_key': edge_license,
            'retry': edge_retry,
            'if_url': edge_url,
            'if_proxies': edge_proxies
        }

        main = {
            'user_name': main_user,
            'license_key': main_license,
            'retry': main_retry,
            'if_url': main_url,
            'if_proxies': main_proxies,
        }

        if_config_vars = {
            'his_time_range': his_time_range,
            'run_interval': int(run_interval),  # as seconds
        }

        return edge, main, if_config_vars


def config_error(logger, setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(
        info))
    return False


def print_summary_info(logger, edge_vars, main_vars, if_config_vars):
    # info to be sent to IF
    post_data_block = '\nIF edge cluster settings:'
    for ik, iv in sorted(edge_vars.items()):
        post_data_block += '\n\t{}: {}'.format(ik, iv)
    logger.debug(post_data_block)

    # variables from agent-specific config
    agent_data_block = '\nIF main cluster settings:'
    for jk, jv in sorted(main_vars.items()):
        agent_data_block += '\n\t{}: {}'.format(jk, jv)
    logger.debug(agent_data_block)

    # variables from crom config
    cron_data_block = '\nAgent settings:'
    for jk, jv in sorted(if_config_vars.items()):
        cron_data_block += '\n\t{}: {}'.format(jk, jv)
    logger.debug(cron_data_block)


def send_request(logger, url, mode='GET', failure_message='Failure!',
                 **request_passthrough):
    """ sends a request to the given url """
    # determine if post or get (default)
    requests.packages.urllib3.disable_warnings()
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
                logger.warn(failure_message)
                logger.info('Response Code: {}\nTEXT: {}'.format(
                    response.status_code, response.text))
        # handle various exceptions
        except requests.exceptions.Timeout:
            logger.exception('Timed out. Reattempting...')
            continue
        except requests.exceptions.TooManyRedirects:
            logger.exception('Too many redirects.')
            break
        except requests.exceptions.RequestException as e:
            logger.exception('Exception ' + str(e))
            break

    logger.error('Failed! Gave up after {} attempts.'.format(req_num + 1))
    return -1


def get_data_type_from_project_type(if_config_vars):
    """ use project type to determine data type """
    if 'METRIC' in if_config_vars.get('project_type'):
        return 'Metric'
    elif 'ALERT' in if_config_vars.get('project_type'):
        return 'Log'
    elif 'INCIDENT' in if_config_vars.get('project_type'):
        return 'Incident'
    elif 'DEPLOYMENT' in if_config_vars.get('project_type'):
        return 'Deployment'
    elif 'TRACE' in if_config_vars.get('project_type'):
        return 'Trace'
    else:  # LOG
        return 'Log'


def get_insight_agent_type_from_project_type(if_config_vars):
    if if_config_vars.get('containerize'):
        if 'METRIC' in if_config_vars.get('project_type'):
            if if_config_vars.get('is_replay'):
                return 'containerReplay'
            else:
                return 'containerStreaming'
        else:
            if if_config_vars.get('is_replay'):
                return 'ContainerHistorical'
            else:
                return 'ContainerCustom'
    elif if_config_vars.get('is_replay'):
        if 'METRIC' in if_config_vars.get('project_type'):
            return 'MetricFile'
        else:
            return 'LogFile'
    else:
        return 'Custom'


def check_project_exist(logger, if_config_vars):
    is_project_exist = False
    try:
        logger.info('Starting check project: ' + if_config_vars['project_name'])
        params = {
            'operation': 'check',
            'userName': if_config_vars['user_name'],
            'licenseKey': if_config_vars['license_key'],
            'projectName': if_config_vars['project_name'],
        }
        url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
        response = send_request(logger, url, 'POST', data=params, verify=False, proxies=if_config_vars['if_proxies'])
        if response == -1:
            logger.error('Check project error: ' + if_config_vars['project_name'])
        else:
            result = response.json()
            if result['success'] is False or result['isProjectExist'] is False:
                logger.error('Check project error: ' + if_config_vars['project_name'])
            else:
                is_project_exist = True
                logger.info('Check project success: ' + if_config_vars['project_name'])

    except Exception as e:
        logger.error(e)
        logger.error('Check project error: ' + if_config_vars['project_name'])

    create_project_sucess = False
    if not is_project_exist:
        try:
            logger.info('Starting add project: ' + if_config_vars['project_name'])
            params = {
                'operation': 'create',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': if_config_vars['project_name'],
                'systemName': if_config_vars['system_name'] or if_config_vars['project_name'],
                'largeProject': if_config_vars['large_project'] or False,
                'instanceType': 'Shadow',
                'projectCloudType': 'Shadow',
                'dataType': if_config_vars.get('dataType') or get_data_type_from_project_type(if_config_vars),
                'insightAgentType': if_config_vars.get('insightAgentType') or get_insight_agent_type_from_project_type(
                    if_config_vars),
                'samplingInterval': int(if_config_vars['sampling_interval'] / 60),
                'samplingIntervalInSeconds': if_config_vars['sampling_interval'],
            }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'])
            if response == -1:
                logger.error('Add project error: ' + if_config_vars['project_name'])
            else:
                result = response.json()
                if result['success'] is False:
                    logger.error('Add project error: ' + if_config_vars['project_name'])
                else:
                    create_project_sucess = True
                    logger.info('Add project success: ' + if_config_vars['project_name'])

        except Exception as e:
            logger.error(e)
            logger.error('Add project error: ' + if_config_vars['project_name'])

    if create_project_sucess:
        # if create project is success, sleep 10s and check again
        time.sleep(10)
        try:
            logger.info('Starting check project: ' + if_config_vars['project_name'])
            params = {
                'operation': 'check',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': if_config_vars['project_name'],
            }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'])
            if response == -1:
                logger.error('Check project error: ' + if_config_vars['project_name'])
            else:
                result = response.json()
                if result['success'] is False or result['isProjectExist'] is False:
                    logger.error('Check project error: ' + if_config_vars['project_name'])
                else:
                    is_project_exist = True
                    logger.info('Check project success: ' + if_config_vars['project_name'])

        except Exception as e:
            logger.error(e)
            logger.error('Check project error: ' + if_config_vars['project_name'])

    return is_project_exist


def listener_configurer():
    """ set up logging according to the defined log level """
    # create a logging format
    formatter = logging.Formatter(
        '{ts} [pid {pid}] {lvl} {mod}.{func}():{line} {msg}'.format(
            ts='%(asctime)s',
            pid='%(process)d',
            lvl='%(levelname)-8s',
            mod='%(module)s',
            func='%(funcName)s',
            line='%(lineno)d',
            msg='%(message)s'),
        ISO8601[0])

    # Get the root logger
    root = logging.getLogger()
    # No level or filter logic applied - just do it!
    # root.setLevel(level)

    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
    logging_handler_out.setFormatter(formatter)
    root.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logging_handler_err.setFormatter(formatter)
    root.addHandler(logging_handler_err)


def listener_process(q):
    listener_configurer()
    while True:
        while not q.empty():
            record = q.get()

            if record.name == 'KILL':
                return

            logger = logging.getLogger(record.name)
            logger.handle(record)
        sleep(1)


def worker_configurer(q, level):
    h = QueueHandler(q)  # Just the one handler needed
    root = logging.getLogger()
    root.addHandler(h)
    root.setLevel(level)


def worker_process(args):
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    importlib.reload(sys)

    (config_file, c_config, time_now, q) = args

    # start sub process
    worker_configurer(q, c_config['log_level'])
    logger = logging.getLogger('worker')
    logger.info("Setup logger in PID {}".format(os.getpid()))
    logger.info("Process start with config: {}".format(config_file))

    config_props = get_config_vars(logger, config_file)
    if not config_props:
        return
    (edge_vars, main_vars, if_config_vars) = config_props
    if not edge_vars:
        return
    if not main_vars:
        return
    if not if_config_vars:
        return
    print_summary_info(logger, edge_vars, main_vars, if_config_vars)

    # TODO: get debug info
    get_debug_info(logger, c_config, edge_vars, main_vars, if_config_vars)

    if c_config.get('list-projects') or c_config.get('debug-project'):
        logger.info("Process is done with debug arguments.")
        return True

    logger.debug('history range config: {}'.format(if_config_vars['his_time_range']))
    if if_config_vars['his_time_range']:
        logger.debug('Using time range for replay data')
        time_ranges = []
        for timestamp in range(if_config_vars['his_time_range'][0],
                               if_config_vars['his_time_range'][1],
                               if_config_vars['run_interval']):
            start_time = int(arrow.get(timestamp).float_timestamp * 1000)
            end_time = int(arrow.get(timestamp + if_config_vars['run_interval']).float_timestamp * 1000)
            time_ranges.append((start_time, end_time))

        # query his data
        thread_get_data_pool = ThreadPool(len(time_ranges))
        params = [(logger, edge_vars, main_vars, if_config_vars, time_now, tr[0], tr[1]) for tr in time_ranges]
        results = thread_get_data_pool.map(get_his_anomaly_data, params)
        thread_get_data_pool.close()
        thread_get_data_pool.join()

        # send his data
        for edge_data in results:
            # send data per project
            params = []
            for project_edge_data in edge_data:
                if project_edge_data.get("noResult"):
                    continue
                try:
                    params.append((logger, c_config, main_vars, project_edge_data))
                except Exception as e:
                    logger.error(f'Parse project: {project_edge_data.get("projectName")} transfer_data error.')
                    logger.error(e)
            if len(params) > 0:
                thread_send_data_pool = ThreadPool(len(params))
                thread_send_data_pool.map(send_anomaly_data, params)
                thread_send_data_pool.close()
                thread_send_data_pool.join()
                logger.info(f"Complete with send data.")
            logger.info(f"{len(params)} project have results. {len(edge_data) - len(params)} project no results.")

    else:
        logger.debug('Using current time for streaming data')

        # start run
        edge_data = get_anomaly_data(logger, edge_vars, main_vars, if_config_vars)

        # send data per project
        params = []
        for project_edge_data in edge_data:
            try:
                if not isinstance(project_edge_data, dict):
                    logger.warning("Invalid data:" + project_edge_data)
                    continue

                if project_edge_data.get("noResult"):
                    continue
                params.append((logger, c_config, main_vars, project_edge_data))
            except Exception as e:
                logger.error(f'Parse project: {project_edge_data.get("projectName")} transfer_data error.')
                logger.error(e)
        if len(params) > 0:
            thread_send_data_pool = ThreadPool(len(params))
            thread_send_data_pool.map(send_anomaly_data, params)
            thread_send_data_pool.close()
            thread_send_data_pool.join()
            logger.info(f"Complete with send data.")
        logger.info(f"{len(params)} project have results. {len(edge_data) - len(params)} project no results.")

    logger.info("Process is done with config: {}".format(config_file))
    return True


if __name__ == "__main__":
    # get config
    cli_config_vars = get_cli_config_vars()

    # logger
    m = multiprocessing.Manager()
    queue = m.Queue()
    listener = multiprocessing.Process(
        target=listener_process, args=(queue,))
    listener.start()

    # set up main logger following example from work_process
    worker_configurer(queue, cli_config_vars['log_level'])
    main_logger = logging.getLogger('main')

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)
    main_logger.info(cli_data_block)

    # get all config files
    files_path = os.path.join(cli_config_vars['config'], "*.ini")
    config_files = glob.glob(files_path)

    # get args
    utc_time_now = int(arrow.utcnow().float_timestamp)
    arg_list = [(f, cli_config_vars, utc_time_now, queue) for f in config_files]

    # start sub process by pool
    pool = Pool(cli_config_vars['processes'])
    pool_result = pool.map_async(worker_process, arg_list)
    pool.close()

    # wait 5 minutes for every worker to finish
    need_timeout = cli_config_vars['timeout'] > 0
    if need_timeout:
        pool_result.wait(timeout=cli_config_vars['timeout'])

    try:
        results = pool_result.get(timeout=1 if need_timeout else None)
        pool.join()
    except TimeoutError:
        main_logger.error("We lacked patience and got a multiprocessing.TimeoutError")
        pool.terminate()

    # end
    main_logger.info("Now the pool is closed and no longer available")

    # send kill signal
    time.sleep(1)
    kill_logger = logging.getLogger('KILL')
    kill_logger.info('KILL')
    listener.join()

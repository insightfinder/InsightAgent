import os
import sys
import time
import pytz
import glob
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
from multiprocessing import Pool, TimeoutError

import arrow
import requests

ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
ATTEMPTS = 3


def get_anomaly_data(logger, edge_vars, main_vars, if_config_vars, time_now):
    # Format Request
    if_url = edge_vars['if_url']

    end_time = (time_now + edge_vars['edge_timezone']) * 1000
    start_time = end_time - if_config_vars['run_interval'] * 1000

    data = {'projectName': edge_vars['project_name'], 'transferToProjectName': main_vars['project_name'],
            'transferToCustomerName': main_vars['user_name'],
            'startTime': start_time, 'endTime': end_time, 'licenseKey': edge_vars['license_key'],
            'userName': edge_vars['user_name']}

    url = if_url + '/api/v2/projectanomalytransfer'

    logger.info(f"{url} {data}")

    # Send Request
    resp = requests.get(url, params=data, verify=False)
    count = 0
    logger.info(f"HTTP Response Code: {resp.status_code}")
    while resp.status_code != 200 and count < edge_vars['retry']:
        time.sleep(60)
        resp = requests.post(url, data=data, verify=False)
        logger.info(f"HTTP Response Code: {resp.status_code}")
        count += 1

    result = {}
    try:
        result = resp.json()
    except Exception as e:
        logger.warning(e)

    logger.debug(f"{result}")
    return result


def send_anomaly_data(logger, c_config, main_vars, data):
    if_url = main_vars['if_url']
    url = if_url + '/api/v2/projectanomalyreceive'
    auth = {'licenseKey': main_vars['license_key'], 'userName': main_vars['user_name']}
    logger.info(f"{url} {auth} {data}")

    # do not send if only testing
    if c_config['testing']:
        return

    resp = requests.post(url, params=auth, json=data, verify=False)
    count = 0
    logger.info(f"HTTP Response Code: {resp.status_code}")
    while resp.status_code != 200 and count < main_vars['retry']:
        time.sleep(60)
        resp = requests.post(url, params=auth, json=data, verify=False)
        logger.info(f"HTTP Response Code: {resp.status_code}")
        count += 1
    return resp.status_code


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
                      help='Minutes of timeout for all processes')
    (options, args) = parser.parse_args()

    config_vars = {
        'config': options.config if os.path.isdir(options.config) else abs_path_from_cur('conf.d'),
        'processes': int(options.processes),
        'testing': False,
        'log_level': logging.INFO,
        'timeout': int(options.timeout) * 60,
    }

    if options.testing:
        config_vars['testing'] = True

    if options.verbose:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING

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
            edge_project_name = config_parser.get('edge', 'project_name')
            edge_project_type = config_parser.get('edge', 'project_type').upper()
            edge_timezone = config_parser.get('edge', 'timezone') or 'UTC'
            edge_url = config_parser.get('edge', 'if_url')
            edge_retry = config_parser.get('edge', 'retry') or 3
            edge_http_proxy = config_parser.get('edge', 'http_proxy')
            edge_https_proxy = config_parser.get('edge', 'https_proxy')

            # Main IF Parameters
            main_user = config_parser.get('main', 'user_name')
            main_license = config_parser.get('main', 'license_key')
            main_project_name = config_parser.get('main', 'project_name')
            main_project_type = config_parser.get('main', 'project_type').upper()
            system_name = config_parser.get('main', 'system_name')
            sampling_interval = config_parser.get('main', 'sampling_interval')
            main_url = config_parser.get('main', 'if_url')
            main_retry = config_parser.get('main', 'retry') or 3
            main_http_proxy = config_parser.get('main', 'http_proxy')
            main_https_proxy = config_parser.get('main', 'https_proxy')

            # if config
            run_interval = config_parser.get('insightfinder', 'run_interval')

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        # Placeholders for Metric as Metric is not configured
        if edge_project_type not in {
            'METRIC',
            'METRICREPLAY',
            'LOG',
            'LOGREPLAY',
            'INCIDENT',
            'INCIDENTREPLAY',
            'ALERT',
            'ALERTREPLAY',
            'DEPLOYMENT',
            'DEPLOYMENTREPLAY'
        }:
            return config_error(logger, 'project_type')
        if main_project_type not in {
            'METRIC',
            'METRICREPLAY',
            'LOG',
            'LOGREPLAY',
            'INCIDENT',
            'INCIDENTREPLAY',
            'ALERT',
            'ALERTREPLAY',
            'DEPLOYMENT',
            'DEPLOYMENTREPLAY'
        }:
            return config_error(logger, 'project_type')
        is_replay = 'REPLAY' in main_project_type

        if len(sampling_interval) == 0:
            if 'METRIC' in main_project_type:
                return config_error(logger, 'sampling_interval')
            else:
                # set default for non-metric
                sampling_interval = 10

        if sampling_interval.endswith('s'):
            sampling_interval = int(sampling_interval[:-1])
        else:
            sampling_interval = int(sampling_interval) * 60

        if len(edge_timezone) != 0:
            edge_timezone = int(arrow.now(edge_timezone).utcoffset().total_seconds())
        else:
            return config_error(logger, 'edge_timezone')

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

        if len(run_interval) == 0:
            return config_error(logger, 'run_interval')
        if run_interval.endswith('s'):
            run_interval = int(run_interval[:-1])
        else:
            run_interval = int(run_interval) * 60

        edge = {
            'user_name': edge_user,
            'license_key': edge_license,
            'project_name': edge_project_name,
            'project_type': edge_project_type,
            'edge_timezone': edge_timezone,
            'retry': edge_retry,
            'if_url': edge_url,
            'if_proxies': edge_proxies
        }

        main = {
            'user_name': main_user,
            'license_key': main_license,
            'project_name': main_project_name,
            'project_type': main_project_type,
            'system_name': system_name,
            'sampling_interval': int(sampling_interval),  # as seconds
            'retry': main_retry,
            'if_url': main_url,
            'if_proxies': main_proxies,
            'is_replay': is_replay
        }

        if_config_vars = {
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
    if 'METRIC' in if_config_vars['project_type']:
        return 'Metric'
    elif 'ALERT' in if_config_vars['project_type']:
        return 'Alert'
    elif 'INCIDENT' in if_config_vars['project_type']:
        return 'Incident'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'Deployment'
    elif 'TRACE' in if_config_vars['project_type']:
        return 'Trace'
    else:  # LOG
        return 'Log'


def get_agent_type_from_project_type(if_config_vars):
    """ use project type to determine agent type """
    if 'METRIC' in if_config_vars['project_type']:
        if if_config_vars['is_replay']:
            return 'MetricFile'
        else:
            return 'Custom'
    elif if_config_vars['is_replay']:
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
                'instanceType': '',
                'projectCloudType': 'Shadow',
                'dataType': get_data_type_from_project_type(if_config_vars),
                'insightAgentType': get_agent_type_from_project_type(if_config_vars),
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

    if not c_config['testing']:
        # check project name first
        check_success = check_project_exist(logger, main_vars)
        if not check_success:
            return

    # start run
    edge_data = get_anomaly_data(logger, edge_vars, main_vars, if_config_vars, time_now)
    send_anomaly_data(logger, c_config, main_vars, edge_data)

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
    pool_result.wait(timeout=cli_config_vars['timeout'])

    try:
        results = pool_result.get(timeout=1)
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
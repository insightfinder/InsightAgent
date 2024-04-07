import configparser
import glob
import logging
import multiprocessing
import os
import socket
import sys
import time
import urllib.parse
from logging.handlers import QueueHandler
from optparse import OptionParser
from pathlib import Path

import arrow
import regex

from utils import config_error, abs_path_from_cur, send_request

# declare a few vars
TRUE = regex.compile(r"T(RUE)?", regex.IGNORECASE)
FALSE = regex.compile(r"F(ALSE)?", regex.IGNORECASE)
SPACES = regex.compile(r"\s+")
SLASHES = regex.compile(r"\/+")
UNDERSCORE = regex.compile(r"\_+")
COLONS = regex.compile(r"\:+")
LEFT_BRACE = regex.compile(r"\[")
RIGHT_BRACE = regex.compile(r"\]")
PERIOD = regex.compile(r"\.")
COMMA = regex.compile(r"\,")
NON_ALNUM = regex.compile(r"[^a-zA-Z0-9]")
FORMAT_STR = regex.compile(r"{(.*?)}")
HOSTNAME = socket.gethostname().partition('.')[0]
ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
JSON_LEVEL_DELIM = '.'
CSV_DELIM = r",|\t"

PROJECT_CALL_TIMEOUT = 10

logging_formatter = logging.Formatter(
    '{ts} {name} [pid {pid}] {lvl} {func}:{line} {msg}'.format(ts='%(asctime)s', name='%(name)s', pid='%(process)d',
                                                               lvl='%(levelname)-8s', func='%(funcName)s',
                                                               line='%(lineno)d', msg='%(message)s'), ISO8601[0])


def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    """
    """
    parser.add_option('-c', '--config', action='store', dest='config', default=abs_path_from_cur('conf.d'),
                      help='Path to the config files to use. Defaults to {}'.format(abs_path_from_cur('conf.d')))
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data).' + ' Automatically turns on verbose logging')
    parser.add_option('--timeout', action='store', dest='timeout', help='Seconds of timeout for all processes')
    (options, args) = parser.parse_args()

    config_vars = {'config': options.config if os.path.isdir(options.config) else abs_path_from_cur('conf.d'),
                   'testing': False, 'log_level': logging.INFO, }

    if options.testing:
        config_vars['testing'] = True

    if options.verbose:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING

    config_vars['timeout'] = int(options.timeout) if options.timeout else 0

    return config_vars


def get_if_config_vars(logger, config_ini):
    """ get config.ini vars """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False

    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)
        try:
            user_name = config_parser.get('insightfinder', 'user_name')
            license_key = config_parser.get('insightfinder', 'license_key')
            token = config_parser.get('insightfinder', 'token')
            system_name = config_parser.get('insightfinder', 'system_name', fallback=None)
            project_name = config_parser.get('insightfinder', 'project_name')
            project_type = config_parser.get('insightfinder', 'project_type').upper()
            collector_type = config_parser.get('insightfinder', 'collector_type')
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            run_interval = config_parser.get('insightfinder', 'run_interval')
            chunk_size_kb = config_parser.get('insightfinder', 'chunk_size_kb')
            if_url = config_parser.get('insightfinder', 'if_url')
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger, )

        # check required variables
        if len(user_name) == 0:
            return config_error(logger, 'user_name')
        if len(license_key) == 0:
            return config_error(logger, 'license_key')
        if len(project_name) == 0:
            return config_error(logger, 'project_name')
        if len(project_type) == 0:
            return config_error(logger, 'project_type')

        if project_type not in {'METRIC', 'METRICREPLAY', 'LOG', 'LOGREPLAY', 'INCIDENT', 'INCIDENTREPLAY', 'ALERT',
                                'ALERTREPLAY', 'DEPLOYMENT', 'DEPLOYMENTREPLAY'}:
            return config_error(logger, 'project_type')

        is_replay = 'REPLAY' in project_type

        if collector_type not in {'centerity'}:
            return config_error(logger, 'collector_type')

        if len(sampling_interval) == 0:
            if 'METRIC' in project_type:
                return config_error(logger, 'sampling_interval')
            else:
                # set default for non-metric
                sampling_interval = 10

        if sampling_interval.endswith('s'):
            sampling_interval = int(sampling_interval[:-1])
        else:
            sampling_interval = int(sampling_interval) * 60

        if len(run_interval) == 0:
            return config_error(logger, 'run_interval')

        if run_interval.endswith('s'):
            run_interval = int(run_interval[:-1])
        else:
            run_interval = int(run_interval) * 60

        # defaults
        if len(chunk_size_kb) == 0:
            chunk_size_kb = 2048  # 2MB chunks by default
        if len(if_url) == 0:
            if_url = 'https://app.insightfinder.com'

        # set IF proxies
        if_proxies = dict()
        if len(if_http_proxy) > 0:
            if_proxies['http'] = if_http_proxy
        if len(if_https_proxy) > 0:
            if_proxies['https'] = if_https_proxy

        config_vars = {'user_name': user_name, 'license_key': license_key, 'token': token, 'system_name': system_name,
                       'project_name': project_name, 'project_type': project_type, 'collector_type': collector_type,
                       'sampling_interval': int(sampling_interval),  # as seconds
                       'run_interval': int(run_interval),  # as seconds
                       'chunk_size': int(chunk_size_kb) * 1024,  # as bytes
                       'if_url': if_url, 'if_proxies': if_proxies, 'is_replay': is_replay, }

        return config_vars


def print_summary_info(logger, if_config_vars, agent_config_vars):
    # info to be sent to IF
    post_data_block = '\nIF settings:'
    for ik, iv in sorted(if_config_vars.items()):
        post_data_block += '\n\t{}: {}'.format(ik, iv)
    logger.info(post_data_block)

    # variables from agent-specific config
    agent_data_block = '\nAgent settings:'
    for jk, jv in sorted(agent_config_vars.items()):
        agent_data_block += '\n\t{}: {}'.format(jk, jv)
    logger.info(agent_data_block)


def get_data_type_from_project_type(logger, if_config_vars):
    if 'METRIC' in if_config_vars['project_type']:
        return 'Metric'
    elif 'LOG' in if_config_vars['project_type']:
        return 'Log'
    elif 'ALERT' in if_config_vars['project_type']:
        return 'Alert'
    elif 'INCIDENT' in if_config_vars['project_type']:
        return 'Incident'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'Deployment'
    else:
        logger.warning('Project Type not correctly configured')
        sys.exit(1)


def get_insight_agent_type_from_project_type(agent_config_vars, if_config_vars):
    if 'containerize' in agent_config_vars and agent_config_vars['containerize']:
        if if_config_vars['is_replay']:
            return 'containerReplay'
        else:
            return 'containerStreaming'
    elif if_config_vars['is_replay']:
        if 'METRIC' in if_config_vars['project_type']:
            return 'MetricFile'
        else:
            return 'LogFile'
    else:
        return 'Custom'


def check_project_exist(logger, agent_config_vars, if_config_vars, project_name):
    is_project_exist = False
    system_name = if_config_vars['system_name']
    user_name = if_config_vars['user_name']
    license_key = if_config_vars['license_key']
    if_url = if_config_vars['if_url']
    if_proxies = if_config_vars['if_proxies']
    sampling_interval = if_config_vars['sampling_interval']

    try:
        logger.info('Starting check project: ' + project_name)
        params = {'operation': 'check', 'userName': user_name, 'licenseKey': license_key, 'projectName': project_name}
        url = urllib.parse.urljoin(if_url, 'api/v1/check-and-add-custom-project')
        response = send_request(logger, url, 'POST', data=params, verify=False, proxies=if_proxies,
                                timeout=PROJECT_CALL_TIMEOUT)
        if response == -1:
            logger.error('Check project error: ' + project_name)
        else:
            result = response.json()
            if result['success'] is False or result['isProjectExist'] is False:
                logger.error('Check project error: ' + project_name)
            else:
                is_project_exist = True
                logger.info('Check project success: ' + project_name)

    except Exception as e:
        logger.error(e)
        logger.error('Check project error: ' + project_name)

    create_project_success = False
    if not is_project_exist:
        try:
            params = {'operation': 'create', 'userName': user_name, 'licenseKey': license_key,
                      'projectName': project_name, 'systemName': system_name, 'instanceType': 'PrivateCloud',
                      'projectCloudType': 'PrivateCloud',
                      'dataType': get_data_type_from_project_type(logger, if_config_vars),
                      'insightAgentType': get_insight_agent_type_from_project_type(agent_config_vars, if_config_vars),
                      'samplingInterval': int(sampling_interval / 60), 'samplingIntervalInSeconds': sampling_interval}

            params_log = params.copy()
            params_log.pop('licenseKey')
            logger.info('Starting add project: {}/{}\n{}'.format(system_name, project_name, params_log))

            url = urllib.parse.urljoin(if_url, 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False, proxies=if_proxies,
                                    timeout=PROJECT_CALL_TIMEOUT)
            if response == -1:
                logger.error('Add project error: ' + project_name)
            else:
                result = response.json()
                if result['success'] is False:
                    logger.error('Add project error: {}/{}'.format(system_name, project_name))
                else:
                    create_project_success = True
                    logger.info('Add project success: {}/{}'.format(system_name, project_name))

        except Exception as e:
            logger.error(e)
            logger.error('Add project error: {}/{}'.format(system_name, project_name))

    if create_project_success:
        # if create project is success, sleep 10s and check again
        time.sleep(PROJECT_CALL_TIMEOUT)
        try:
            logger.info('Starting check project: ' + project_name)
            params = {'operation': 'check', 'userName': user_name, 'licenseKey': license_key,
                      'projectName': project_name, }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False, proxies=if_proxies,
                                    timeout=PROJECT_CALL_TIMEOUT)
            if response == -1:
                logger.error('Check project error: ' + project_name)
            else:
                result = response.json()
                if result['success'] is False or result['isProjectExist'] is False:
                    logger.error('Check project error: ' + project_name)
                else:
                    is_project_exist = True
                    logger.info('Check project success: ' + project_name)

        except Exception as e:
            logger.error(e)
            logger.error('Check project error: ' + project_name)

    return is_project_exist


def worker_process(args):
    (config_file, cli_config_vars, agent_start_time, logging_queue) = args

    config_name = Path(config_file).stem
    level = cli_config_vars['log_level']

    logging_handler = logging.handlers.QueueHandler(logging_queue)
    logger = logging.getLogger('worker.' + config_name)
    logger.setLevel(level)
    logger.addHandler(logging_handler)

    logger.info("Setup logger in PID {}".format(os.getpid()))
    logger.info("Process start with config: {}".format(config_file))

    if_config_vars = get_if_config_vars(logger, config_file)
    if not if_config_vars:
        return

    agent_config_vars = None
    collector_type = if_config_vars['collector_type']

    if collector_type == 'centerity':
        from collectors.centerity import get_agent_config_vars
        agent_config_vars = get_agent_config_vars(logger, config_file)

    if not agent_config_vars:
        logger.error("Agent config for collector {} not found.".format(collector_type))
        return

    print_summary_info(logger, if_config_vars, agent_config_vars)

    if not cli_config_vars['testing']:
        # check project first if project_name is set
        project_name = if_config_vars['project_name']
        if project_name:
            check_success = check_project_exist(logger, agent_config_vars, if_config_vars, project_name)
            if not check_success:
                return

    time.sleep(60)


def main():
    # get config
    cli_config_vars = get_cli_config_vars()

    # get all config file
    files_path = os.path.join(cli_config_vars['config'], "*.ini")
    config_files = glob.glob(files_path)

    if len(config_files) == 0:
        logging.error("Config files not found")
        sys.exit(1)

    # Create logging handlers
    logging_handler = logging.StreamHandler(sys.stdout)
    logging_handler.setLevel(logging.DEBUG)
    logging_handler.setFormatter(logging_formatter)

    # Create a logging queue
    logging_queue = multiprocessing.Manager().Queue()

    # Create a QueueListener attached to the queue and the console handler
    listener = logging.handlers.QueueListener(logging_queue, logging_handler)
    listener.start()

    logger_main = logging.getLogger('main')
    logger_main.setLevel(logging.INFO)
    logger_main.addHandler(logging_handler)

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)
    logger_main.info(cli_data_block)

    agent_start_time = int(arrow.utcnow().float_timestamp)
    timeout = cli_config_vars['timeout']
    arg_list = [(f, cli_config_vars, agent_start_time, logging_queue) for f in config_files]

    # start sub process by pool
    with multiprocessing.Pool(len(arg_list)) as pool:
        pool_result = pool.map_async(worker_process, arg_list)

        need_timeout = timeout > 0
        if need_timeout:
            pool_result.wait(timeout=timeout)

        try:
            pool_result.get(timeout=1 if need_timeout else None)
            pool.join()
        except multiprocessing.context.TimeoutError:
            logger_main.error("We lacked patience and got a multiprocessing.TimeoutError")
            pool.terminate()

    logger_main.info("Now the pool is closed and no longer available")
    listener.stop()


if __name__ == "__main__":
    main()

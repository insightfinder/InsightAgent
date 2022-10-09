#!/usr/bin/env python
import configparser
import http
import io
import json
import logging
import os
import socket
import sys
import time
import urllib
from optparse import OptionParser

import boto3
import requests

messages = []

MAX_RETRY_NUM = 10
RETRY_WAIT_TIME_IN_SEC = 30
MAX_PACKET_SIZE = 5000000
ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
RUNNING_INDEX_FILE = 'running_index.txt'
ATTEMPTS = 3


def config_error(logger, setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(info))
    return False


def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))


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
    (options, args) = parser.parse_args()

    config_vars = {'config': options.config if os.path.isdir(options.config) else abs_path_from_cur('conf.d'),
                   'testing': False, 'log_level': logging.INFO, }

    if options.testing:
        config_vars['testing'] = True

    if options.verbose:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING

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
            project_name = config_parser.get('insightfinder', 'project_name')
            system_name = config_parser.get('insightfinder', 'system_name')
            project_type = config_parser.get('insightfinder', 'project_type').upper()
            run_interval = config_parser.get('insightfinder', 'run_interval')
            if_url = config_parser.get('insightfinder', 'if_url')
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        # check required variables
        if len(user_name) == 0:
            return config_error(logger, 'user_name')
        if len(license_key) == 0:
            return config_error(logger, 'license_key')
        if len(project_name) == 0:
            return config_error(logger, 'project_name')
        if len(project_type) == 0:
            return config_error(logger, 'project_type')

        if project_type not in {'METRIC'}:
            return config_error(logger, 'project_type')

        if len(run_interval) == 0:
            return config_error(logger, 'run_interval')

        if run_interval.endswith('s'):
            run_interval = int(run_interval[:-1])
        else:
            run_interval = int(run_interval) * 60

        # defaults
        if len(if_url) == 0:
            if_url = 'https://app.insightfinder.com'

        # set IF proxies
        if_proxies = dict()
        if len(if_http_proxy) > 0:
            if_proxies['http'] = if_http_proxy
        if len(if_https_proxy) > 0:
            if_proxies['https'] = if_https_proxy

        config_vars = {'user_name': user_name, 'license_key': license_key, 'token': token, 'project_name': project_name,
                       'system_name': system_name, 'project_type': project_type, 'run_interval': int(run_interval),
                       'if_url': if_url, 'if_proxies': if_proxies}

        return config_vars


def get_agent_config_vars(logger, config_ini, if_config_vars):
    """ Read and parse config.ini """
    """ get config.ini vars """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False

    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)

        try:
            # aws s3 options
            aws_access_key_id = config_parser.get('agent', 'aws_access_key_id')
            aws_secret_access_key = config_parser.get('agent', 'aws_secret_access_key')
            aws_region = config_parser.get('agent', 'aws_region') or None
            aws_s3_bucket_name = config_parser.get('agent', 'aws_s3_bucket_name')
            aws_s3_object_prefix = config_parser.get('agent', 'aws_s3_object_prefix') or ''

            if not aws_access_key_id:
                return config_error(logger, 'aws_access_key_id')
            if not aws_secret_access_key:
                return config_error(logger, 'aws_secret_access_key')
            if not aws_s3_bucket_name:
                return config_error(logger, 'aws_s3_bucket_name')

            # message parsing
            instance_field = config_parser.get('agent', 'instance_field')
            grouping_field = config_parser.get('agent', 'grouping_field')

            # proxies
            agent_http_proxy = config_parser.get('agent', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('agent', 'agent_https_proxy')

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger)

        # proxies
        agent_proxies = dict()
        if len(agent_http_proxy) > 0:
            agent_proxies['http'] = agent_http_proxy
        if len(agent_https_proxy) > 0:
            agent_proxies['https'] = agent_https_proxy

        # add parsed variables to a global
        config_vars = {'aws_access_key_id': aws_access_key_id, 'aws_secret_access_key': aws_secret_access_key,
                       'aws_region': aws_region, 'aws_s3_bucket_name': aws_s3_bucket_name,
                       'aws_s3_object_prefix': aws_s3_object_prefix,
                       'instance_field': instance_field,
                       'grouping_field': grouping_field,
                       'proxies': agent_proxies, }

        return config_vars


def print_summary_info(logger, if_config_vars, agent_config_vars):
    # info to be sent to IF
    post_data_block = '\nIF settings:'
    for ik, iv in sorted(if_config_vars.items()):
        post_data_block += '\n\t{}: {}'.format(ik, iv)
    logger.debug(post_data_block)

    # variables from agent-specific config
    agent_data_block = '\nAgent settings:'
    for jk, jv in sorted(agent_config_vars.items()):
        agent_data_block += '\n\t{}: {}'.format(jk, jv)
    logger.debug(agent_data_block)


def logger_control(user, level):
    """ set up logging according to the defined log level """
    # create a logging format
    formatter = logging.Formatter(
        '{ts} [pid {pid}] {lvl} {mod}.{func}():{line} {msg}'.format(ts='%(asctime)s', pid='%(process)d',
                                                                    lvl='%(levelname)-8s', mod='%(module)s',
                                                                    func='%(funcName)s', line='%(lineno)d',
                                                                    msg='%(message)s'), ISO8601[0])

    # Get the root logger
    root = logging.getLogger(user)

    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
    logging_handler_out.setFormatter(formatter)
    root.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logging_handler_err.setFormatter(formatter)
    root.addHandler(logging_handler_err)
    root.setLevel(level)
    return root


def send_request(logger, url, mode='GET', failure_message='Failure!', success_message='Success!',
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
            print("fdsfds")
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


def process_get_data(logger, cli_config_vars, bucket, object_key):
    logger.info('start to process data from file: {}'.format(object_key))
    global messages

    buf = io.BytesIO()
    logger.info('downloading file: {}'.format(object_key))

    bucket.download_fileobj(object_key, buf)
    content = buf.getvalue()
    logger.info('download {} bytes from file: {}'.format(len(content), object_key))

    msgs = json.loads(content)
    messages.extend(msgs)

    logger.info('finish proces data from file: {}'.format(object_key))


def process_parse_data(logger, cli_config_vars, agent_config_vars):
    logger.info('start to parse data...')
    global messages

    instance_field = agent_config_vars['instance_field']
    grouping_field = agent_config_vars['grouping_field']

    grouping_dict = {}
    for row in messages:
        group_name = row[grouping_field]
        instance_name = row[instance_field]
        if group_name not in grouping_dict:
            grouping_dict[group_name] = ""
            grouping_dict[group_name] = grouping_dict[group_name] + instance_name
        else:
            grouping_dict[group_name] = grouping_dict[group_name] + "," + instance_name
    return grouping_dict


def send_data(logger, if_config_vars, data):
    """ Sends parsed metric data to InsightFinder """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = dict()

    # for backend so this is the camel case in to_send_data_dict
    to_send_data_dict["licenseKey"] = if_config_vars['license_key']
    to_send_data_dict["userName"] = if_config_vars['user_name']

    to_send_data_dict["projectName"] = if_config_vars['project_name']
    to_send_data_dict["instanceName"] = socket.gethostname()
    to_send_data_dict["isMetricAgent"] = "true"
    to_send_data_dict["fileType"] = "grouping"
    to_send_data_dict["groupingData"] = json.dumps(data)

    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = if_config_vars['if_url'] + "/api/v1/customgrouping"
    send_data_to_receiver(logger, post_url, to_send_data_json)
    logger.info("--- Send data time: %s seconds ---" % str(time.time() - send_data_time))


def send_data_to_receiver(logger, post_url, to_send_data):
    attempts = 0
    while attempts < MAX_RETRY_NUM:
        if sys.getsizeof(to_send_data) > MAX_PACKET_SIZE:
            logger.error("Packet size too large %s.  Dropping packet." + str(sys.getsizeof(to_send_data)))
            break
        response_code = -1
        attempts += 1
        try:
            response = requests.post(post_url, data=json.loads(to_send_data), verify=False)
            response_code = response.status_code
        except:
            logger.error("Attempts: %d. Fail to send data, response code: %d wait %d sec to resend." % (
                attempts, response_code, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
            continue
        if response_code == 200:
            logger.info("Data send successfully.")
            break
        else:
            logger.error("Attempts: %d. Fail to send data, response code: %d wait %d sec to resend." % (
                attempts, response_code, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
    if attempts == MAX_RETRY_NUM:
        sys.exit(1)


def main():
    # get config
    cli_config_vars = get_cli_config_vars()

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)

    # set logger
    logger = logger_control('worker', cli_config_vars['log_level'])

    # get config file
    config_file = os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini'))
    logger.info("Process start with config: {}".format(config_file))

    if_config_vars = get_if_config_vars(logger, config_file)
    if not if_config_vars:
        sys.exit(1)

    agent_config_vars = get_agent_config_vars(logger, config_file, if_config_vars)
    if not agent_config_vars:
        time.sleep(1)
        sys.exit(1)

    print_summary_info(logger, if_config_vars, agent_config_vars)

    if not cli_config_vars['testing']:
        check_success = check_project_exist(logger, if_config_vars)
        if not check_success:
            return

    # read the previous processed file from the running index file
    last_object_key = None
    if os.path.exists(RUNNING_INDEX_FILE):
        try:
            with open(RUNNING_INDEX_FILE, 'r') as fp:
                last_object_key = (fp.readline() or '').strip() or None
                logger.info('Got last object key {}'.format(last_object_key))
        except Exception as e:
            logger.error('Failed to read index file: {}\n {}'.format(RUNNING_INDEX_FILE, e))
            sys.exit()

    region_name = agent_config_vars['aws_region']
    bucket_name = agent_config_vars['aws_s3_bucket_name']
    object_prefix = agent_config_vars['aws_s3_object_prefix']

    s3 = boto3.resource('s3',
                        aws_access_key_id=agent_config_vars['aws_access_key_id'],
                        aws_secret_access_key=agent_config_vars['aws_secret_access_key'],
                        region_name=region_name)
    bucket = s3.Bucket(bucket_name)
    logger.info('Connect to s3 bucket, region: {}, bucket: {}'.format(region_name, bucket_name))

    objects_keys = [x.key for x in bucket.objects.filter(Prefix=object_prefix)]
    logger.info('Found {} files in the bucket with prefix {}'.format(len(objects_keys), object_prefix))

    new_object_keys = objects_keys
    if last_object_key:
        try:
            idx = objects_keys.index(last_object_key)
            # no new objects
            if idx == len(objects_keys) - 1:
                new_object_keys = []
            else:
                new_object_keys = objects_keys[idx + 1:]
        except ValueError:
            # not found, start from first one
            pass
    logger.info('Found {} new files after {}'.format(len(new_object_keys), last_object_key))

    for obj_key in new_object_keys:
        process_get_data(logger, cli_config_vars, bucket, obj_key)

        # parse data
        parse_data = process_parse_data(logger, cli_config_vars, agent_config_vars)
        logger.info('Parsing data completed...')

        if cli_config_vars['testing']:
            logger.info('testing!!! do not sent data to IF. Data: {}'.format(parse_data))
        else:
            logger.debug('send data {} to IF.'.format(parse_data))
            send_data(logger, if_config_vars, parse_data)


if __name__ == "__main__":
    main()

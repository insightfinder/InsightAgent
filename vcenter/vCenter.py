#!/usr/bin/env python
# coding: utf-8

import glob
import http
import urllib
import multiprocessing
import os
import sys
import requests
import regex
import time
import pytz
from datetime import datetime, timedelta

import pandas as pd
import ssl
from pyVmomi import vim, vmodl
from pyVim import connect
from multiprocessing.pool import ThreadPool

import json
import logging
from configparser import ConfigParser
from optparse import OptionParser
from ifobfuscate import decode

import warnings
warnings.filterwarnings('ignore')

'''
This script gets metric data from VMware vSphere and ingests it into an IF metric project
'''

RETRY_WAIT_TIME_IN_SEC = 30
SESSION = requests.Session()
ATTEMPTS = 3
# Set it to 4 mins because VCenter cron is every 5 mins
MAX_TIME_OUT_THRESHOLD =  240

def set_logger_config():
    '''
    Configure logger object
    '''
    
    ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
    logger = logging.getLogger()
    logger.setLevel(cli_config_vars['log_level'])
    logging_format = logging.Formatter(
        '{ts} [pid {pid}] {lvl} {mod}.{func}():{line} {msg}'.format(
            ts='%(asctime)s',
            pid='%(process)d',
            lvl='%(levelname)-8s',
            mod='%(module)s',
            func='%(funcName)s',
            line='%(lineno)d',
            msg='%(message)s'),
        ISO8601[0])
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setFormatter(logging_format)
    logger.addHandler(logging_handler_out)
    return logger

def get_insight_agent_type_from_project_type(if_config_vars):
    if 'containerize' in if_config_vars and if_config_vars['containerize']:
        if 'METRIC' in if_config_vars['project_type']:
            if if_config_vars['is_replay']:
                return 'containerReplay'
            else:
                return 'containerStreaming'
        else:
            if if_config_vars['is_replay']:
                return 'ContainerHistorical'
            else:
                return 'ContainerCustom'
    elif if_config_vars['is_replay']:
        if 'METRIC' in if_config_vars['project_type']:
            return 'MetricFile'
        else:
            return 'LogFile'
    else:
        return 'Custom'

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

def get_config_vars(config_path):
    '''
    Get config variables from the config file
    '''
    
    if not os.path.exists(config_path):
        message = "No config file found. Exiting."
        logger.info(message)
        sys.exit(1)

    config = ConfigParser()
    config.read(config_path)

    if_vars = {}
    if_vars['host_url'] = config.get('insightFinder_vars', 'host_url')
    if_vars['http_proxy'] = config.get('insightFinder_vars', 'http_proxy')
    if_vars['https_proxy'] = config.get('insightFinder_vars', 'https_proxy')
    if_vars['license_key'] = config.get('insightFinder_vars', 'license_key')
    if_vars['project_name'] = config.get('insightFinder_vars', 'project_name')
    if_vars['system_name'] = config.get('insightFinder_vars', 'system_name')
    if_vars['user_name'] = config.get('insightFinder_vars', 'user_name')
    if_vars['project_type'] = config.get('insightFinder_vars', 'project_type').upper()
    if_vars['retries'] = config.getint('insightFinder_vars', 'retries')
    if_vars['sleep_seconds'] = config.getint('insightFinder_vars', 'sleep_seconds')
    if_vars['sampling_interval'] = config.getint('insightFinder_vars', 'sampling_interval')
    if_vars['is_replay'] = False

    if_proxies = dict()
    if_vars['if_proxies'] = if_proxies

    vCenter_vars = {}
    vCenter_vars['host'] = config.get('vCenter_vars', 'host')
    vCenter_vars['http_proxy'] = config.get('vCenter_vars', 'http_proxy')
    vCenter_vars['user_name'] = config.get('vCenter_vars', 'user_name')
    vCenter_vars['password'] = config.get('vCenter_vars', 'password')
    vCenter_vars['virtual_machines_list'] = config.get('vCenter_vars', 'virtual_machines_list')
    vCenter_vars['virtual_machines_regex'] = config.get('vCenter_vars', 'virtual_machines_regex')
    vCenter_vars['hosts_list'] = config.get('vCenter_vars', 'hosts_list')
    vCenter_vars['hosts_regex'] = config.get('vCenter_vars', 'hosts_regex')
    vCenter_vars['datastores_list'] = config.get('vCenter_vars', 'datastores_list')
    vCenter_vars['datastores_regex'] = config.get('vCenter_vars', 'datastores_regex')
    vCenter_vars['metrics_list'] = config.get('vCenter_vars', 'metrics_list')
    vCenter_vars['metrics_regex'] = config.get('vCenter_vars', 'metrics_regex')
    
    agent_vars = {}
    agent_vars['thread_pool'] = config.getint('agent_vars', 'thread_pool')
    agent_vars['chunk_size'] = config.getint('agent_vars', 'chunk_size_kb') * 1024

    return if_vars, vCenter_vars, agent_vars
    
def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))

def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    parser.add_option('-c', '--config', action='store', dest='config', default=abs_path_from_cur('conf.d'),
                      help='Path to the config file to use. Defaults to {}'.format(abs_path_from_cur('conf.d')))
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data).' +
                           ' Automatically turns on verbose logging')
    (options, args) = parser.parse_args()

    config_vars = {
        'config': options.config if os.path.isfile(options.config) else abs_path_from_cur('conf.d'),
        'testing': False,
        'log_level': logging.INFO
    }

    if options.testing:
        config_vars['testing'] = True

    if options.verbose:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING

    return config_vars

def collect_metric_data(vCenter_vars, agent_vars):
    '''
    Collect metric data from VMware vSphere using their pyVmomi Python SDK
    '''
    
    logger.info("Connecting to vCenter.")
    try:
        connection = connect_vmomi(vCenter_vars)
        content = connection.RetrieveContent()
    except Exception as e:
        logger.error('Could not connect to vCenter. Check the credentials/server state.')
        logger.exception(e)
        sys.exit(1)

    counter_info = {}
    for counter in content.perfManager.perfCounter:
        if counter.rollupType == 'none':
            continue
        counter_full = "{}.{}.{}.{}".format(counter.groupInfo.key, counter.nameInfo.key, counter.unitInfo.key, counter.rollupType)
        counter_info[counter_full] = counter.key

    if vCenter_vars['metrics_list']:
        metrics = vCenter_vars['metrics_list'].split(',')
        metrics = [metric.strip() for metric in metrics if metric.strip() in counter_info]
    elif vCenter_vars['metrics_regex']:
        re = regex.compile(vCenter_vars['metrics_regex'])
        metrics = list(filter(re.match, counter_info))
    else:
        metrics = []

    if len(metrics) == 0:
        logger.error('Metric list is empty.')
        sys.exit(1)
    
    hosts = get_entity_objects(content, vim.HostSystem, vCenter_vars['hosts_list'], vCenter_vars['hosts_regex'])
    virtual_machines = get_entity_objects(content, vim.VirtualMachine, vCenter_vars['virtual_machines_list'], vCenter_vars['virtual_machines_regex'])
    virtual_machines = whitelist_virtual_machines(virtual_machines, hosts)
    datastores = get_entity_objects(content, vim.Datastore, vCenter_vars['datastores_list'], vCenter_vars['datastores_regex'])
    entities = hosts + virtual_machines + datastores
    
    if len(entities) == 0:
        logger.error('Entity list is empty.')
        sys.exit(1)

    pool_map = ThreadPool(agent_vars['thread_pool'])
    params = [(content, counter_info, entity, metric) for entity in entities for metric in metrics]
    logger.debug("Size of paramters in bytes {}".format(sys.getsizeof(params)))
    logger.info("Collecting the performance metrics.")
    metric_data = pool_map.map(query_single_metric, params)
    
    metric_data = pd.concat(metric_data, axis=1, sort=True)
    if len(metric_data) == 0:
        logger.warning("No metric data found for the given parameters.")
        sys.exit(1)

    logger.info("Finished collecting metrics.")
    logger.debug("Size of data in bytes {}".format(sys.getsizeof(metric_data)))

    metric_data = metric_data.resample('T').mean().dropna(how='all')
    metric_data.index = ((metric_data.index.view(int) / 10**6)).astype(int)
    metric_data.index.name = 'timestamp'
    metric_data = metric_data.reset_index()
    metric_data = metric_data.astype(str).replace('nan','')
    logger.info("Received {} rows from vCenter API.".format(len(metric_data)))
    
    #metric_data.to_csv('sample data.csv')
    return metric_data

def connect_vmomi(vCenter_vars):
    '''
    Connect to the specified VMOMI ServiceInstance
    '''

    if ':' in vCenter_vars['host']:
        host, port = [k.strip() for k in vCenter_vars['host'].split(':')]
        port = int(port)
    else:
        host, port = vCenter_vars['host'], 443
    
    if ':' in vCenter_vars['http_proxy']:
        httpProxyHost, httpProxyPort = [k.strip() for k in vCenter_vars['http_proxy'].split(':')]
        httpProxyPort = int(httpProxyPort)
    else:
        httpProxyHost, httpProxyPort = vCenter_vars['http_proxy'], 80

    soapStub = connect.SmartStubAdapter(host=host,
                                        port=port,
                                        httpProxyHost=httpProxyHost,
                                        httpProxyPort=httpProxyPort,
                                        sslContext=ssl._create_unverified_context())
    
    connection = vim.ServiceInstance("ServiceInstance", soapStub)
    session_manager = connection.content.sessionManager
    if not session_manager.currentSession:
        connection.content.sessionManager.Login(vCenter_vars['user_name'], decode(vCenter_vars['password']))
    
    return connection

def get_entity_objects(content, entity_type, entity_list, entity_regex):
    '''
    Get a list of entity objects from entity names/regex
    '''

    container = content.viewManager.CreateContainerView(
            content.rootFolder, [entity_type], True)
    entities = container.view
    
    object_map = {entity.name: entity for entity in entities}
    
    if entity_list:
        entity_list = entity_list.split(',')
        entity_list = [entity.strip() for entity in entity_list]
    elif entity_regex:
        re = regex.compile(entity_regex)
        entity_list = list(filter(re.match, object_map))

    ls_objects = []
    for name in entity_list:
        if name in object_map:
            ls_objects.append(object_map[name])
        else:
            logger.warning("Could not find the '{}' type entity named '{}'.".format(entity_type, name))

    return ls_objects

def whitelist_virtual_machines(virtual_machines, hosts):
    '''
    Whitelist/select only the virtual machines running on the chosen hosts
    '''

    virtual_machines = [vm for vm in virtual_machines if vm.runtime.host in hosts]
    return virtual_machines

def query_single_metric(args):
    '''
    Query a single metric for a single entity
    '''
    
    content, counter_info, entity, metric = args
    metric_id = get_metric_id(counter_info, metric)
    query_interval = 15

    spec = vim.PerformanceManager.QuerySpec(
                entity=entity,
                metricId=[metric_id],
                startTime=execution_time - timedelta(minutes=query_interval),
                endTime=execution_time,
                intervalId=300)

    try:
        result = content.perfManager.QueryStats(querySpec=[spec])
    except Exception as e:
        logger.warning("Could not query the '{}' metric for '{}' entity.".format(metric, entity.name))
        logger.exception(e)
        return pd.DataFrame()
    
    if len(result) > 0 and len(result[0].value) > 0 and len(result[0].value[0].value) > 0:
        data = result[0].value[0].value
        idx = [sample.timestamp for sample in result[0].sampleInfo]
        instance_name = entity.name.replace('_', '-')
        if type(entity) == vim.VirtualMachine:
            instance_name += ('_' + entity.runtime.host.name.replace('_', '-'))
        df = pd.DataFrame(data, index=idx, columns=['{}[{}]'.format(metric, instance_name)])
        df = df[execution_time - timedelta(minutes=query_interval):]
        if 'percent' in metric:
            df = df / 100
    else:
        return pd.DataFrame()
    
    logger.debug("Retrieved {} metric for {} entity".format(metric, entity.name))
    return df

def get_metric_id(counter_info, metric):
    '''
    Get the PerformanceManager.MetricId object from its name
    '''
    
    metric_id = vim.PerformanceManager.MetricId(
                counterId=counter_info[metric],
                instance=''
                )
    return metric_id

def send_metric_data(metric_data, if_vars, agent_vars):
    '''
    Send the collected metric data to InsightFinder
    '''
    
    logger.info("Sending the performance metrics to InsightFinder.")
    data_chunk = []
    count = 0
    cur_data_size = 0
    for _, row in metric_data.iterrows():
        entry = dict(list(zip(row.index, row)))
        data_chunk.append(entry)
        count += 1
        cur_data_size += len(bytearray(json.dumps(entry), 'utf8'))
        if cur_data_size >= agent_vars['chunk_size']:
            logger.debug("Sending a data chunk.")
            send_data_chunk(data_chunk, if_vars)
            data_chunk = []
            cur_data_size = 0
    if len(data_chunk) != 0:
        logger.debug("Sending last data chunk.")
        send_data_chunk(data_chunk, if_vars)

    logger.info("Sent a total of {} metric rows to IF.".format(count))

def send_data_chunk(data_chunk, if_vars):
    '''
    Send a single data chunk to IF
    '''

    start_time = time.time()
    url = if_vars['host_url'] + '/customprojectrawdata'
    data = {
        'metricData': json.dumps(data_chunk),
        'licenseKey': if_vars['license_key'],
        'projectName': if_vars['project_name'],
        'userName': if_vars['user_name'],
        'agentType': 'CUSTOM'
    }

    proxies = {}
    if len(if_vars['http_proxy']) > 0:
        proxies['http'] = if_vars['http_proxy']
    if len(if_vars['https_proxy']) > 0:
        proxies['https'] = if_vars['https_proxy']

    attempts = 1
    response = requests.post(url, data=data, proxies=proxies, verify=False)
    while response.status_code != 200 and attempts < if_vars['retries']:
        logger.info("Failed to send data. Retrying in {} seconds.".format(
            if_vars['sleep_seconds']))
        time.sleep(if_vars['sleep_seconds'])
        response = requests.post(url, data=data, proxies=proxies, verify=False)
        attempts += 1

    if response.status_code == 200:
        logger.info("Successfully sent {} metric rows in {} seconds.".format(
            len(data_chunk), time.time() - start_time))
    else:
        logger.warning("Failed to send metric data in {} attempts.".format(
            if_vars['retries']))
        logger.info('Response Code: {}\nTEXT: {}'.format(
                response.status_code, response.text))
        sys.exit(1)

def send_request(logger, url, mode='GET', failure_message='Failure!', success_message='Success!',
                 **request_passthrough):
    """ sends a request to the given url """
    # determine if post or get (default)
    req = SESSION.get
    if mode.upper() == 'POST':
        req = SESSION.post

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

        # retry after sleep
        time.sleep(RETRY_WAIT_TIME_IN_SEC)

    logger.error('Failed! Gave up after {} attempts.'.format(req_num + 1))
    return -1

def check_project_exist(if_config_vars, project_name, system_name):
    is_project_exist = False
    if not system_name:
        system_name = if_config_vars['system_name']

    try:
        logger.info('Starting check project: ' + project_name)
        params = {
            'operation': 'check',
            'userName': if_config_vars['user_name'],
            'licenseKey': if_config_vars['license_key'],
            'projectName': project_name,
        }
        url = urllib.parse.urljoin(if_config_vars['host_url'], 'api/v1/check-and-add-custom-project')
        response = send_request(logger, url, 'POST', data=params, verify=False, proxies=if_config_vars['if_proxies'])
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

    create_project_sucess = False
    if not is_project_exist:
        try:
            logger.info('Starting add project: {}/{}'.format(system_name, project_name))
            params = {
                'operation': 'create',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': project_name,
                'systemName': system_name or project_name,
                'instanceType': 'PrivateCloud',
                'projectCloudType': 'PrivateCloud',
                'dataType': get_data_type_from_project_type(if_config_vars),
                'insightAgentType': get_insight_agent_type_from_project_type(if_config_vars),
                'samplingInterval': if_config_vars['sampling_interval'],
                'samplingIntervalInSeconds': int(if_config_vars['sampling_interval'] * 60),
            }
            url = urllib.parse.urljoin(if_config_vars['host_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'])
            if response == -1:
                logger.error('Add project error: ' + project_name)
            else:
                result = response.json()
                if result['success'] is False:
                    logger.error('Add project error: {}/{}'.format(system_name, project_name))
                else:
                    create_project_sucess = True
                    logger.info('Add project success: {}/{}'.format(system_name, project_name))

        except Exception as e:
            logger.error(e)
            logger.error('Add project error: {}/{}'.format(system_name, project_name))

    if create_project_sucess:
        # if create project is success, sleep 10s and check again
        time.sleep(10)
        try:
            logger.info('Starting check project: ' + project_name)
            params = {
                'operation': 'check',
                'userName': if_config_vars['user_name'],
                'licenseKey': if_config_vars['license_key'],
                'projectName': project_name,
            }
            url = urllib.parse.urljoin(if_config_vars['host_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'])
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

def worker_process(path):
    if_vars, vCenter_vars, agent_vars = get_config_vars(path)
    project_name = if_vars['project_name']
    if project_name:
        check_success = check_project_exist(if_vars, project_name, None)
        if not check_success:
            return
    try:
        metric_data = collect_metric_data(vCenter_vars, agent_vars)
        if not cli_config_vars['testing']:
            send_metric_data(metric_data, if_vars, agent_vars)
    except Exception as e:
        logger.error(e, exc_info=True)
        return


if __name__ == '__main__':
    execution_time = datetime.now(pytz.timezone('UTC'))

    cli_config_vars = get_cli_config_vars()
    files_path = os.path.join(cli_config_vars['config'], "*.ini")
    config_files = glob.glob(files_path)

    if len(config_files) == 0:
        logging.error("Config files not found")
        sys.exit(1)

    logger = set_logger_config()

    pool = multiprocessing.Pool(len(config_files))
    pool_result = pool.map_async(worker_process, config_files)
    pool.close()

    try:
        pool_result.get(timeout=MAX_TIME_OUT_THRESHOLD)
        pool.join()
    except Exception as e:
        logger.error(e, exc_info=True)
        pool.terminate()
    logger.info("Now the pool is closed and no longer available")

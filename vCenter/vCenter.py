#!/usr/bin/env python
# coding: utf-8

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
from ifobfuscate import decode

import warnings
warnings.filterwarnings('ignore')

'''
This script gets metric data from VMware vSphere and ingests it into an IF metric project
'''

def set_logger_config():
    '''
    Configure logger object
    '''
    
    ISO8601 = ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y%m%dT%H%M%SZ', 'epoch']
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
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
    if_vars['licenseKey'] = config.get('insightFinder_vars', 'licenseKey')
    if_vars['project_name'] = config.get('insightFinder_vars', 'project_name')
    if_vars['username'] = config.get('insightFinder_vars', 'username')
    if_vars['retries'] = config.getint('insightFinder_vars', 'retries')
    if_vars['sleep_seconds'] = config.getint('insightFinder_vars', 'sleep_seconds')

    vCenter_vars = {}
    vCenter_vars['host'] = config.get('vCenter_vars', 'host')
    vCenter_vars['http_proxy'] = config.get('vCenter_vars', 'http_proxy')
    vCenter_vars['username'] = config.get('vCenter_vars', 'username')
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

def collect_metric_data():
    '''
    Collect metric data from VMware vSphere using their pyVmomi Python SDK
    '''
    
    try:
        connection = connect_vmomi()
        content = connection.RetrieveContent()
    except:
        logger.error('Could not connect to vCenter. Check the credentials/server state.')
        sys.exit(1)

    counter_info = {}
    for counter in content.perfManager.perfCounter:
        counter_full = "{}.{}.{}".format(counter.groupInfo.key, counter.nameInfo.key, counter.rollupType)
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
    metric_data = pool_map.map(query_single_metric, params)
    
    metric_data = pd.concat(metric_data, axis=1, sort=True)
    if len(metric_data) == 0:
        logger.warning("No metric data found for the given parameters.")
        sys.exit(1)
    
    metric_data = metric_data.resample('T').mean().dropna(how='all')
    metric_data.index = ((metric_data.index.view(int) / 10**6)).astype(int)
    metric_data.index.name = 'timestamp'
    metric_data = metric_data.reset_index()
    metric_data = metric_data.astype(str).replace('nan','')
    logger.info("Received {} rows from vCenter API.".format(len(metric_data)))
    
    #metric_data.to_csv('sample data.csv')
    return metric_data

def connect_vmomi():
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
        connection.content.sessionManager.Login(vCenter_vars['username'], decode(vCenter_vars['password']))
    
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
    intervalId = 300 if type(entity) == vim.Datastore else 20
    query_interval = 15

    spec = vim.PerformanceManager.QuerySpec(
                entity=entity,
                metricId=[metric_id],
                startTime=execution_time - timedelta(minutes=query_interval),
                endTime=execution_time,
                intervalId=intervalId)

    try:
        result = content.perfManager.QueryStats(querySpec=[spec])
    except:
        logger.warning("Could not query the '{}' metric for '{}' entity.".format(metric, entity.name))
        return pd.DataFrame()
    
    if len(result) > 0 and len(result[0].value) > 0 and len(result[0].value[0].value) > 0:
        data = result[0].value[0].value
        idx = [sample.timestamp for sample in result[0].sampleInfo]
        instance_name = entity.name.replace('_', '-')
        if type(entity) == vim.VirtualMachine:
            container_name = entity.runtime.host.name.replace('_', '-')
            instance_name = container_name + '_' + instance_name
        df = pd.DataFrame(data, index=idx, columns=['{}[{}]'.format(metric, instance_name)])
        df = df[execution_time - timedelta(minutes=query_interval):]
    else:
        return pd.DataFrame()
    
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

def send_metric_data(metric_data):
    '''
    Send the collected metric data to InsightFinder
    '''
    
    data_chunk = []
    count = 0
    for _, row in metric_data.iterrows():
        entry = dict(list(zip(row.index, row)))
        data_chunk.append(entry)
        count += 1

        if len(bytearray(json.dumps(data_chunk), 'utf8')) >= agent_vars['chunk_size']:
            logger.debug("Sending a data chunk.")
            send_data_chunk(data_chunk)
            data_chunk = []
    if len(data_chunk) != 0:
        logger.debug("Sending last data chunk.")
        send_data_chunk(data_chunk)

    logger.info("Sent a total of {} metric rows to IF.".format(count))

def send_data_chunk(data_chunk):
    '''
    Send a single data chunk to IF
    '''

    start_time = time.time()
    url = if_vars['host_url'] + '/customprojectrawdata'
    data = {
        'metricData': json.dumps(data_chunk),
        'licenseKey': if_vars['licenseKey'],
        'projectName': if_vars['project_name'],
        'userName': if_vars['username'],
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

if __name__ == '__main__':
    execution_time = datetime.now(pytz.timezone('UTC'))
    logger = set_logger_config()
    
    config_path = 'config.ini'
    if_vars, vCenter_vars, agent_vars = get_config_vars(config_path)

    try:
        metric_data = collect_metric_data()
        send_metric_data(metric_data)
    except Exception as e:
        logger.error(e, exc_info=True)
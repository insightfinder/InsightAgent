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
from multiprocessing.pool import ThreadPool

import json
import logging
from configparser import ConfigParser
from optparse import OptionParser

import warnings
warnings.filterwarnings('ignore')

'''
This script gets performance metric data from Nagios API and ingests it into an IF metric project
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

    nagios_vars = {}
    nagios_vars['host_url'] = config.get('nagios_vars', 'host_url')
    nagios_vars['http_proxy'] = config.get('nagios_vars', 'http_proxy')
    nagios_vars['https_proxy'] = config.get('nagios_vars', 'https_proxy')
    nagios_vars['api_key'] = config.get('nagios_vars', 'api_key')
    nagios_vars['host_names_list'] = config.get('nagios_vars', 'host_names_list')
    nagios_vars['host_names_regex'] = config.get('nagios_vars', 'host_names_regex')
    nagios_vars['service_descriptors_list'] = config.get('nagios_vars', 'service_descriptors_list')
    nagios_vars['service_descriptors_regex'] = config.get('nagios_vars', 'service_descriptors_regex')
    nagios_vars['retries'] = config.getint('nagios_vars', 'retries')
    nagios_vars['sleep_seconds'] = config.getint('nagios_vars', 'sleep_seconds')
    
    agent_vars = {}
    agent_vars['query_interval'] = config.getint('agent_vars', 'query_interval')
    agent_vars['sampling_interval'] = config.getint('agent_vars', 'sampling_interval')
    agent_vars['thread_pool'] = config.getint('agent_vars', 'thread_pool')
    agent_vars['chunk_size'] = config.getint('agent_vars', 'chunk_size_kb') * 1024

    parser = OptionParser()
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                        help='Set to testing mode (do not send data).')
    (options, args) = parser.parse_args()

    return if_vars, nagios_vars, agent_vars, options

def collect_performance_data():
    '''
    Collect performance metric data from Nagios
    '''

    logger.info("Collecting host and service descriptor lists.")
    hosts = get_hosts()
    if len(hosts) == 0:
        logger.error('Host list is empty.')
        sys.exit(1)

    pool_map = ThreadPool(agent_vars['thread_pool'])
    services = pool_map.map(get_services, hosts)
    services = {service[0]: service[1] for service in services}

    pool_map = ThreadPool(agent_vars['thread_pool'])
    params = [(host, service) for host in hosts for service in services[host]]
    if len(params) == 0:
        logger.warn('No valid combinations of filters found. Exiting.')
        sys.exit(1)

    logger.info("Collecting the performance data.")
    metric_data = pool_map.map(query_nagiosAPI, params)
    
    metric_data = pd.concat(metric_data, axis=1, sort=True)
    if len(metric_data) == 0:
        logger.warning("No metric data found for the given parameters.")
        sys.exit(1)
    
    metric_data.index.name = 'timestamp'
    metric_data = metric_data.reset_index()
    metric_data = metric_data.astype(str).replace('nan','')
    logger.info("Received {} rows from nagios API.".format(len(metric_data)))
    
    #metric_data.to_csv('sample data.csv')
    return metric_data

def get_hosts():
    '''
    Retrieve host names for all hosts being monitored
    '''

    api = "/nagiosxi/api/v1/objects/hoststatus"
    url = nagios_vars['host_url'] + api
    params = {
        "apikey": nagios_vars['api_key']
    }

    proxies = {}
    if len(nagios_vars['http_proxy']) > 0:
        proxies['http'] = nagios_vars['http_proxy']
    if len(nagios_vars['https_proxy']) > 0:
        proxies['https'] = nagios_vars['https_proxy']

    attempts = 1
    response = requests.get(url, params=params, proxies=proxies, verify=False)
    while response.status_code != 200 and attempts < nagios_vars['retries']:
        logger.info("Failed to get host names. Retrying in {} seconds.".format(
            nagios_vars['sleep_seconds']))
        time.sleep(nagios_vars['sleep_seconds'])
        response = requests.get(url, params=params, proxies=proxies, verify=False)
        attempts += 1
    
    if response.status_code != 200:
        logger.warning("Failed to get host names in {} attempts.".format(
            nagios_vars['retries']))
        logger.info('Response Code: {}\nTEXT: {}'.format(
                response.status_code, response.text))
        sys.exit(1)

    result = response.json()
    if "error" in result:
        logger.warning("Could not retrieve hosts from the API. Error message: {}".format(result['error']))
        sys.exit(1)

    all_hosts = []
    for host in result['hoststatus']:
        all_hosts.append(host['host_name'])

    if nagios_vars['host_names_list']:
        hosts = nagios_vars['host_names_list'].split(',')
        hosts = [host.strip() for host in hosts if host.strip() in all_hosts]
    elif nagios_vars['host_names_regex']:
        re = regex.compile(nagios_vars['host_names_regex'])
        hosts = list(filter(re.match, all_hosts))
    else:
        hosts = []
    
    return hosts

def get_services(host):
    '''
    Retrieve service descriptions for all services being monitored for a host
    '''

    api = "/nagiosxi/api/v1/objects/servicestatus"
    url = nagios_vars['host_url'] + api
    params = {
        "apikey": nagios_vars['api_key'],
        "host_name": host
    }

    proxies = {}
    if len(nagios_vars['http_proxy']) > 0:
        proxies['http'] = nagios_vars['http_proxy']
    if len(nagios_vars['https_proxy']) > 0:
        proxies['https'] = nagios_vars['https_proxy']

    attempts = 1
    response = requests.get(url, params=params, proxies=proxies, verify=False)
    while response.status_code != 200 and attempts < nagios_vars['retries']:
        logger.info("Failed to get services for the host '{}'. Retrying in {} seconds.".format(
            host, nagios_vars['sleep_seconds']))
        time.sleep(nagios_vars['sleep_seconds'])
        response = requests.get(url, params=params, proxies=proxies, verify=False)
        attempts += 1
    
    if response.status_code != 200:
        logger.warning("Failed to get services for the host '{}' in {} attempts.".format(
            host, nagios_vars['retries']))
        logger.info('Response Code: {}\nTEXT: {}'.format(
                response.status_code, response.text))
        sys.exit(1)

    result = response.json()
    if "error" in result:
        logger.warning("Could not retrieve services for the host '{}'. Error message: {}".format(host, result['error']))
        return host, []

    all_services = []
    for service in result['servicestatus']:
        all_services.append(service['service_description'])

    if nagios_vars['service_descriptors_list']:
        services = nagios_vars['service_descriptors_list'].split(',')
        services = [service.strip() for service in services if service.strip() in all_services]
    elif nagios_vars['service_descriptors_regex']:
        re = regex.compile(nagios_vars['service_descriptors_regex'])
        services = list(filter(re.match, all_services))
    else:
        services = []
    
    return host, services

def query_nagiosAPI(args):
    '''
    Query Nagios API for a host name and service description
    '''
    
    #print(args)
    host, service = args
    api = "/nagiosxi/api/v1/objects/rrdexport"
    url = nagios_vars['host_url'] + api
    params = {
        "apikey": nagios_vars['api_key'],
        "host_name": host,
        "service_description": service,
        "start": (execution_time - timedelta(minutes=agent_vars['query_interval'])).timestamp(),
        "end": execution_time.timestamp(),
        "step": agent_vars['sampling_interval'] * 60,
        "maxrows": 2**31-1
    }

    proxies = {}
    if len(nagios_vars['http_proxy']) > 0:
        proxies['http'] = nagios_vars['http_proxy']
    if len(nagios_vars['https_proxy']) > 0:
        proxies['https'] = nagios_vars['https_proxy']

    attempts = 1
    response = requests.get(url, params=params, proxies=proxies, verify=False)
    while response.status_code != 200 and attempts < nagios_vars['retries']:
        logger.info("Failed to get data for host '{}' and service '{}'. Retrying in {} seconds.".format(
            host, service, nagios_vars['sleep_seconds']))
        time.sleep(nagios_vars['sleep_seconds'])
        response = requests.get(url, params=params, proxies=proxies, verify=False)
        attempts += 1
    
    if response.status_code != 200:
        logger.warning("Failed to get data for host '{}' and service '{}' in {} attempts.".format(
            host, service, nagios_vars['retries']))
        logger.info('Response Code: {}\nTEXT: {}'.format(
                response.status_code, response.text))
        sys.exit(1)

    result = response.json()
    if "error" in result:
        logger.warning("Could not get data for host '{}' and service '{}'. Error message: {}".format(host, service, result['error']))
        return pd.DataFrame()

    data = [row['v'] for row in result['data']['row']]
    index = [row['t'] * 1000 for row in result['data']['row']]
    columns = result['meta']['legend']['entry']

    if type(columns) == list:
        columns = [service.replace(' ', '') + '_' + col for col in columns]
    else:
        columns = [service.replace(' ', '')]
    columns= ['{}[{}]'.format(col, host) for col in columns]

    df = pd.DataFrame(data, index=index, columns=columns).astype(float).dropna()
    
    return df

def send_performance_data(metric_data):
    '''
    Send the collected metric data to InsightFinder
    '''
    
    logger.info("Sending the performance metrics to InsightFinder.")
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
    if_vars, nagios_vars, agent_vars, options = get_config_vars(config_path)

    try:
        metric_data = collect_performance_data()
        if not options.testing:
            send_performance_data(metric_data)
    except Exception as e:
        logger.error(e, exc_info=True)

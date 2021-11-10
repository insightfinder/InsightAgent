#!/usr/bin/env python
# coding: utf-8

import os
import sys
import requests
import regex
import time
from datetime import datetime, timedelta

import pandas as pd
from google.cloud import monitoring_v3
from google.cloud.monitoring_v3.query import Query
from multiprocessing.pool import ThreadPool

import json
import logging
from configparser import ConfigParser
from optparse import OptionParser

import warnings
warnings.filterwarnings('ignore')

'''
This script gets metric data from Google Cloud and ingests it into an IF metric project
'''

def set_logger_config():
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

    monitoring_vars = {}
    monitoring_vars['service_key_json'] = config.get('googleMonitoring_vars', 'service_key_json')
    monitoring_vars['http_proxy'] = config.get('googleMonitoring_vars', 'http_proxy')
    monitoring_vars['https_proxy'] = config.get('googleMonitoring_vars', 'https_proxy')
    monitoring_vars['project_id'] = config.get('googleMonitoring_vars', 'project_id')
    monitoring_vars['metrics_list'] = config.get('googleMonitoring_vars', 'metrics_list')
    monitoring_vars['metrics_regex'] = config.get('googleMonitoring_vars', 'metrics_regex')
    monitoring_vars['instance_field'] = config.get('googleMonitoring_vars', 'instance_field')
    monitoring_vars['container_field'] = config.get('googleMonitoring_vars', 'container_field')
    monitoring_vars['instance_field_list'] = config.get('googleMonitoring_vars', 'instance_field_list')
    monitoring_vars['instance_field_regex'] = config.get('googleMonitoring_vars', 'instance_field_regex')
    monitoring_vars['resource_type_list'] = config.get('googleMonitoring_vars', 'resource_type_list')
    monitoring_vars['resource_type_regex'] = config.get('googleMonitoring_vars', 'resource_type_regex')
    monitoring_vars['zone_list'] = config.get('googleMonitoring_vars', 'zone_list')
    monitoring_vars['zone_regex'] = config.get('googleMonitoring_vars', 'zone_regex')
    
    agent_vars = {}
    agent_vars['historical_time_range'] = config.get('agent_vars', 'historical_time_range')
    if agent_vars['historical_time_range']:
        agent_vars['historical_time_range'] = [datetime.strptime(metric.strip(), '%Y-%m-%d %H:%M:%S')
                                                        for metric in agent_vars['historical_time_range'].split(',')]
    agent_vars['query_interval'] = config.getint('agent_vars', 'query_interval')
    agent_vars['sampling_interval'] = config.getint('agent_vars', 'sampling_interval')
    agent_vars['thread_pool'] = config.getint('agent_vars', 'thread_pool')
    agent_vars['chunk_size'] = config.getint('agent_vars', 'chunk_size_kb') * 1024

    parser = OptionParser()
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                        help='Set to testing mode (do not send data).')
    (options, args) = parser.parse_args()

    return if_vars, monitoring_vars, agent_vars, options

def collect_metric_data():
    '''
    Collect metric data using Google's monitoring_v3 API
    '''

    logger.info("Connecting to Google Monitoring API.")
    try:
        set_proxy_env_variables()
        client = monitoring_v3.MetricServiceClient.from_service_account_json(monitoring_vars['service_key_json'])
        all_metrics = [metric.type for metric in client.list_metric_descriptors(name=f"projects/{monitoring_vars['project_id']}")]
    except:
        logger.error('Could not connect to Google Monitoring API. Check the credentials.')
        sys.exit(1)

    if monitoring_vars['metrics_list']:
        metrics = monitoring_vars['metrics_list'].split(',')
        metrics = [metric.strip() for metric in metrics if metric.strip() in all_metrics]
    elif monitoring_vars['metrics_regex']:
        re = regex.compile(monitoring_vars['metrics_regex'])
        metrics = list(filter(re.match, all_metrics))
    else:
        metrics = []

    if len(metrics) == 0:
        logger.error('Metric list is empty.')
        sys.exit(1)
    if not monitoring_vars['instance_field']:
        logger.error('Instance field is empty. Exiting.')
        sys.exit(1)
    
    pool_map = ThreadPool(agent_vars['thread_pool'])
    params = [(client, metric) for metric in metrics]
    labels = pool_map.map(get_labels, params)
    instance_field_dict = {label[0]: label[1] for label in labels}
    resource_type_dict = {label[0]: label[2] for label in labels}
    zone_dict = {label[0]: label[3] for label in labels}

    pool_map = ThreadPool(agent_vars['thread_pool'])
    params = [(client, metric, instance_field_val, resource_type, zone) for metric in metrics
                                                                for instance_field_val in instance_field_dict[metric]
                                                                for resource_type in resource_type_dict[metric]
                                                                for zone in zone_dict[metric]]
    if len(params) == 0:
        logger.warn('No valid combinations of filters found. Exiting.')
        sys.exit(1)

    logger.info("Collecting the monitoring metrics.")
    metric_data = pool_map.map(query_monitoringAPI, params)
    
    metric_data = pd.concat(metric_data, axis=1, sort=True)
    if len(metric_data) == 0:
        logger.warning("No metric data found for the given parameters.")
        sys.exit(1)

    metric_data = metric_data.resample('{}T'.format(agent_vars['sampling_interval'])).mean().dropna(how='all')    
    metric_data.index = ((metric_data.index.view(int) / 10**6)).astype(int)
    metric_data.index.name = 'timestamp'
    metric_data = metric_data.reset_index()
    metric_data = metric_data.astype(str).replace('nan','')
    logger.info("Received {} rows from Google Monitoring API.".format(len(metric_data)))
    
    #metric_data.to_csv('sample data.csv')
    return metric_data

def set_proxy_env_variables():
    '''
    Set environment variables for proxy settings to connect to Google's monitoring_v3 API
    '''

    if monitoring_vars['http_proxy'] and monitoring_vars['https_proxy']:
        os.environ["http_proxy"] = monitoring_vars['http_proxy']
        os.environ["https_proxy"] = monitoring_vars['https_proxy']
    elif monitoring_vars['http_proxy']:
        os.environ["http_proxy"] =  os.environ["https_proxy"] = monitoring_vars['http_proxy']
    elif monitoring_vars['https_proxy']:
        os.environ["http_proxy"] =  os.environ["https_proxy"] = monitoring_vars['https_proxy']

def reset_proxy_env_variables():
    '''
    Reset the environment variables for proxy settings
    '''

    if "http_proxy" in os.environ:
        del os.environ["http_proxy"]
    if "https_proxy" in os.environ:
        del os.environ["https_proxy"]

def get_labels(args):
    '''
    For a metric, get the list of whitelist values for the labels that are to be filtered upon
    '''

    client, metric = args
    
    if agent_vars['historical_time_range']:
        interval = monitoring_v3.TimeInterval(start_time=agent_vars['historical_time_range'][0], end_time=agent_vars['historical_time_range'][1])
    else:
        interval = monitoring_v3.TimeInterval(start_time=execution_time-timedelta(minutes=agent_vars['query_interval']), end_time=execution_time)
    results = client.list_time_series(
        request={
            "name": f"projects/{monitoring_vars['project_id']}",
            "filter": 'metric.type = "{}"'.format(metric),
            "interval": interval,
            "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.HEADERS,
        }
    )
    
    instance_field_vals = set()
    resource_types = set()
    zones = set()
    for result in results:
        instance_field = monitoring_vars['instance_field'].split(',')
        instance_field = [label.strip() for label in instance_field]
        for label in instance_field:
            if label in result.metric.labels:
                label_type = 'metric_label'
                label_name = label
                instance_field_vals.add(result.metric.labels[label])
                break
            if label in result.resource.labels:
                label_type = 'resource_label'
                label_name = label
                instance_field_vals.add(result.resource.labels[label])
                break

        if result.resource.type:
            resource_types.add(result.resource.type)
        if 'zone' in result.resource.labels:
            zones.add(result.resource.labels['zone'])

    instance_field_vals = filter_label(instance_field_vals, monitoring_vars['instance_field_list'], monitoring_vars['instance_field_regex'])
    instance_field_vals = [[label_type, {label_name: instance_name}] for instance_name in instance_field_vals]
    resource_types = filter_label(resource_types, monitoring_vars['resource_type_list'], monitoring_vars['resource_type_regex'])
    zones = filter_label(zones, monitoring_vars['zone_list'], monitoring_vars['zone_regex'])
    
    return metric, instance_field_vals, resource_types, zones

def filter_label(label_all, label_list, label_regex):
    '''
    Given the list of all available label values and (optionally) a positive-filter list/regex, return whitelisted values
    '''

    if not label_all:
        return []

    if label_list:
        label_list = label_list.split(',')
        label_list = [val.strip() for val in label_list]
        label_whitelist = list(label_all & set(label_list))
    elif label_regex:
        label_regex = regex.compile(label_regex)
        label_whitelist = list(filter(label_regex.match, label_all))
    else:
        label_whitelist = [None]
    return label_whitelist

def query_monitoringAPI(args):
    '''
    Single timeSeries query to the monitoring_v3 API
    '''
    
    #print(args[1:])
    client, metric, instance_field_val, resource_type, zone = args
    if agent_vars['historical_time_range']:
        query = Query(client, monitoring_vars['project_id'], metric_type=metric,
                    end_time=None, days=0, hours=0, minutes=0)
        query = query.select_interval(start_time=agent_vars['historical_time_range'][0], end_time=agent_vars['historical_time_range'][1])
    else:
        query = Query(client, monitoring_vars['project_id'], metric_type=metric,
                    end_time=execution_time, days=0, hours=0, minutes=agent_vars['query_interval'])
    
    label_type, instance_field_filter = instance_field_val
    if label_type == 'metric_label':
        query = query.select_metrics(**instance_field_filter)
        query = query.select_resources(resource_type=resource_type, zone=zone)
    elif label_type == 'resource_label':
        query = query.select_resources(resource_type=resource_type, zone=zone, **instance_field_filter)

    queryDF = query.as_dataframe()
    if len(queryDF) == 0:
        return pd.DataFrame()

    instance_field = monitoring_vars['instance_field'].split(',')
    instance_field = [label.strip() for label in instance_field]
    for label in instance_field:
        if label in queryDF.columns.names:
            col_names = list(queryDF.columns.get_level_values(label))
            col_names = [instance.replace('_', '-') for instance in col_names]
            break
    else:
        logger.warning("No labels from the provided Instance filed are available for the '{}' metric.".format(metric))
        return pd.DataFrame()

    if monitoring_vars['container_field']:
        container_field = monitoring_vars['container_field'].split(',')
        container_field = [label.strip() for label in container_field]
        for label in container_field:
            if label in queryDF.columns.names:
                container_col = list(queryDF.columns.get_level_values(label))
                container_col = [container.replace('_', '-') for container in container_col]
                break
        else:
            container_col = None
    else:
        container_col = None
    
    if container_col:
        col_names = [container + '_' + instance for instance, container in zip(col_names, container_col)]
    queryDF.columns = ['{}[{}]'.format(metric, col) for col in col_names]

    return queryDF

def send_metric_data(metric_data):
    '''
    Send the collected metric data to InsightFinder
    '''

    logger.info("Sending the performance metrics to InsightFinder.")
    reset_proxy_env_variables()

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
    execution_time = datetime.now()
    logger = set_logger_config()
    
    config_path = 'config.ini'
    if_vars, monitoring_vars, agent_vars, options = get_config_vars(config_path)

    try:
        metric_data = collect_metric_data()
        if not options.testing:
            send_metric_data(metric_data)
    except Exception as e:
        logger.error(e, exc_info=True)
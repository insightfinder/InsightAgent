#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Streaming host metric
"""

import argparse
import json
import logging
import logging.handlers
import time

import pandas as pd
import requests
import yaml


def send_data(data, config):
    """
    Send metric data to insightfinder
    :param data: a list conforming to the metricData field of insightfinder data ingestion api,
                ex. [{"timestamp":"1558631315000", "DiskUsed[build-server-7]":"0.253"}]
    :param config: a dict containing all fields except metricData for insightfinder data ingestion api
    :return: true/false to show if data sent
    """

    if not data:
        logging.warning('No data to send')
        return

    payload = {'metricData': json.dumps(data),
               'agentType': config['insightfinder']['agent_type'],
               'projectName': config['insightfinder']['project_name'],
               'userName': config['insightfinder']['user_name'],
               'licenseKey': config['insightfinder']['license_key']}

    url = config['insightfinder']['appserver'] + '/customprojectrawdata'
    logging.debug(f'Payload for {url}:\n{payload}')

    try:
        r = requests.post(url, data=payload, verify=False, timeout=3)
        if r.status_code == 200:
            logging.info(f'Succeeded to send data to {url} for project: {payload["projectName"]}')
        else:
            logging.error(f'Failed to send data to {url} for project: {payload["projectName"]}')
    except requests.exceptions.RequestException as e:
        logging.error(str(e))


def build_data(data, metricspec):
    """
    Build a list conforming to the metricData field of insightfinder data ingestion api
    :param data: a list of metric dict, ex.
                [{'TIME': '2021-01-07 13:03:30', 'IP_ADDRESS': '10.222.55.55', 'CPU_USER': '0.003', 'CPU_SYSTEM': '0'},
                {'TIME': '2021-01-07 13:03:30', 'IP_ADDRESS': '10.222.55.54', 'CPU_USER': '0.033', 'CPU_SYSTEM': '0'}]
    :param metricspec: a dict of metric data specification, refer to the comments in config.yml
    :return: a list of metric data for insightfiner data ingestion api,
            ex. [{"timestamp":"1558631315000", "DiskUsed[build-server-7]":"0.253"}]
    """

    if not data:
        logging.warning('No data to build.')
        return None

    logging.debug(f'Building data: {data}')
    logging.debug(f'with spec: {metricspec["fields"]}')

    df = pd.DataFrame(data)
    df = df.applymap(str)  # ensure all metric value is string

    col_timestamp = metricspec['fields']['timestamp']
    col_instance = metricspec['fields']['instance']
    col_metrics = metricspec['fields']['metrics']
    col_list = [col_timestamp, col_instance] + col_metrics
    logging.debug(f'Columns to process: {col_list}')

    df = df[col_list]
    df[col_timestamp] = pd.to_datetime(df[col_timestamp])

    '''
    At any time point, there are multiple instances which have its metrics.
    To create MultiIndex, set timestamp as level 0, instance as level 1.
    For example:
                                     CPU_USER CPU_SYSTEM CPU_WAIT CPU_IDLE
    timestamp           instance
    2021-01-07 12:59:30 10.222.55.54    0.012      0.002    0.006    0.979
                        10.222.55.55     0.02      0.001    0.003    0.973
    2021-01-07 13:01:30 10.222.55.54    0.004          0    0.023    0.972
                        10.222.55.55    0.028          0    0.093    0.877
    '''
    df.reset_index()
    df.set_index([col_timestamp, col_instance], inplace=True)
    df.sort_index(inplace=True)

    '''
    Start to join each instance's dataframe to get one dataframe as a whole like below:
                        CPU_USER[10.222.55.54] ... CPU_SYSTEM[10.222.55.55]
    timestamp
    2021-01-07 12:59:30                  0.001 ...                    0.012
    2021-01-07 13:01:30                  0.013 ...                    0.009
    '''
    grouped_instance = df.groupby(col_instance)
    logging.debug(f'Grouped instance: {grouped_instance.groups.keys()}')

    # Empty dataframe must have same index as joined dataframe
    first_instance = list(grouped_instance.groups.keys())[0]
    curr_idx = df.xs(first_instance, level=col_instance).index
    whole_df = pd.DataFrame(index=curr_idx)
    for name, group in grouped_instance:
        # Rename column to form "<metric name>[<instance name>]"
        instance_df = df.xs(name, level=col_instance).add_suffix('[' + name + ']')
        whole_df = whole_df.join(instance_df)

    # Build metricData
    metric_data = []
    for ts, metrics in whole_df.to_dict('index').items():
        epoch = int(ts.timestamp() * 1000)
        d = {'timestamp': str(epoch)}
        d.update(metrics)
        metric_data.append(d)

    return metric_data


def query_data(metricset, freq, instances):
    """
    Query metric data
    :param metricset: metricset to query, ex. cpu, filesystem.
    :param freq: the frequency to query metric, in minutes.
    :param instances: a list of instance name for which to query metric.
    :return: a json string of queried metric data
    """

    start_time = (pd.Timestamp.now() - pd.Timedelta(freq, 'minutes')).strftime('%Y%m%d%H%M%S')
    end_time = pd.Timestamp.now().strftime('%Y%m%d%H%M%S')
    payload = {'param': metricset, 'ips': ','.join(instances),
               'startTime': start_time, 'endTime': end_time}

    url = 'http://10.9.131.38/external/getdata'
    logging.debug(f'Payload for {url}:\n{payload} ')

    try:
        r = requests.get(url, params=payload, timeout=3)
        if r.ok:
            logging.debug(f'Get {metricset} data: {r.json()}')
            return r.json()
        else:
            logging.error(f'Failed to query {metricset} data')
    except requests.exceptions.RequestException as e:
        logging.error(str(e))

    return None


if __name__ == '__main__':
    # Command line arguments
    parser = argparse.ArgumentParser(description='Get cmcc host metric')
    parser.add_argument('-v', '--verbosity', action='count', default=0,
                        help='increase output verbosity')
    parser.add_argument('-l', '--logfile', help='logging file')
    args = parser.parse_args()

    # Logging config
    if args.verbosity >= 2:
        loglevel = logging.DEBUG
    elif args.verbosity >= 1:
        loglevel = logging.INFO
    else:
        loglevel = logging.WARNING
    fmt_str = '%(asctime)s - %(levelname)s - %(filename)s[line:%(lineno)d] - %(message)s'
    if args.logfile:
        logger = logging.getLogger()
        logger.setLevel(loglevel)
        rh = logging.handlers.RotatingFileHandler(args.logfile, maxBytes=5*1024**2, backupCount=1)
        formatter = logging.Formatter(fmt_str)
        rh.setFormatter(formatter)
        logger.addHandler(rh)
    else:
        logging.basicConfig(
            format=fmt_str,
            level=loglevel)

    # Load config.yml
    with open('config.yml') as c:
        config = yaml.load(c, yaml.FullLoader)
        logging.debug(f'Load config: {config}')
        instances = config['instances']
        metricset = config['metricset']
        query_interval = config['query_interval']
        logging.debug(f'To query {metricset} for {len(instances)} instances.')

    while True:
        logging.info('==> Start to process')
        start_time = time.perf_counter()
        for name,spec in metricset.items():
            r = query_data(name, query_interval, instances)
            metric_data = build_data(r, spec)
            send_data(metric_data, config)
        elapsed_time = time.perf_counter() - start_time
        logging.info(f'==> Finished in {elapsed_time} seconds, to sleep {query_interval} minutes.\n...')
        time.sleep(query_interval * 60)

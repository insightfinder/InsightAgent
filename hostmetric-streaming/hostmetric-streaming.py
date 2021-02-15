#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Streaming host metric
"""

import argparse
import json
import logging
import logging.handlers
import os
import time

import pandas as pd
import requests
import yaml
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


def send_request(url, payload):
    """
    Send http request.
    :param url: The url to access.
    :param payload: The payload to send.
    :return: None if request failed, Response content if request ok.
    """

    logging.debug(f'Request {url} with payload:\n{payload}')

    retries = Retry(
        total=10,
        allowed_methods=False,  # Set to a False value to retry on any verb.
        status_forcelist=[401, 500, 502, 503, 504],
        backoff_factor=3
    )

    with requests.Session() as s:
        s.mount(url, HTTPAdapter(max_retries=retries))
        try:
            resp = s.post(url, data=payload, verify=False, timeout=5)
            if resp.ok:
                return resp.text
        except requests.exceptions.RequestException as e:
            logging.error(str(e))
        return None


def send_data(data, if_config):
    """
    Send metric data to insightfinder.
    :param data: A list conforming to the metricData field of insightfinder data ingestion api,
                ex. [{"timestamp":"1558631315000", "DiskUsed[build-server-7]":"0.253"}]
    :param if_config: A dict containing all fields except metricData for insightfinder data ingestion api
    :return: True/False to show if data sent
    """

    if not data:
        logging.warning('No data to send')
        return

    payload = {'metricData': json.dumps(data),
               'agentType': if_config['agent_type'],
               'projectName': if_config['project_name'],
               'userName': if_config['user_name'],
               'licenseKey': if_config['license_key']}

    url = if_config['appserver'] + '/customprojectrawdata'

    content = send_request(url, payload)
    if content:
        logging.info(f'Succeeded to send data to {url} for project: {payload["projectName"]}')
        return True
    else:
        logging.error(f'Failed to send data to {url} for project: {payload["projectName"]}')
        return False


def joined_bylevel(df, level, surround, suffix=True):
    """
    Join dataframe by one level.
    :param df: Dataframe.
    :param level: The level to group by.
    :param surround: String of a pair of symbols to surround the item name of grouped level, which used to rename column.
    :param suffix: True to add suffix, False to add prefix to column label.
    :return: Joined dataframe.
    """

    grouped = df.groupby(level)

    # Prepare empty dataframe with same index as joined dataframe
    first = list(grouped.groups.keys())[0]
    idx_bylevel = df.xs(first, level=level).index
    joined_df = pd.DataFrame(index=idx_bylevel)
    for name, group in grouped:
        if suffix:
            renamed_df = df.xs(name, level=level).add_suffix(surround[0] + name + surround[1])
        else:
            renamed_df = df.xs(name, level=level).add_prefix(surround[0] + name + surround[1])
        joined_df = joined_df.join(renamed_df)

    return joined_df


def build_data(data, schema):
    """
    Build a list conforming to the metricData field of insightfinder data ingestion api
    :param data: A json string of metric data, ex.
                [{'TIME': '2021-01-07 13:03:30', 'IP_ADDRESS': '10.222.55.55', 'CPU_USER': '0.003', 'CPU_SYSTEM': '0'},
                {'TIME': '2021-01-07 13:03:30', 'IP_ADDRESS': '10.222.55.54', 'CPU_USER': '0.033', 'CPU_SYSTEM': '0'}]
    :param schema: A dict of data schema, refer to the comments in config.yml
    :return: A list of metric data for insightfiner data ingestion api,
            ex. [{"timestamp":"1558631315000", "DiskUsed[build-server-7]":"0.253"}]
    """

    if not data:
        logging.warning('No data to build.')
        return None

    logging.debug(f'Building data:\n{data}')
    logging.debug(f'with schema:\n{schema["fields"]}')

    df = pd.read_json(data, dtype='str')
    if df.empty:
        logging.warning('Empty dataframe.')
        return None

    col_timestamp = schema['fields']['timestamp']
    col_instance = schema['fields']['instance']
    col_metrics = schema['fields']['metrics']
    col_list = [col_timestamp, col_instance] + col_metrics
    col_device = None
    if 'device' in schema['fields']:
        col_device = schema['fields']['device']
        col_list.append(col_device)
        devices = schema['devices']

    # Get needed columns
    df = df[col_list]
    df[col_timestamp] = pd.to_datetime(df[col_timestamp])

    # Set MultiIndex
    idx = [col_timestamp, col_instance]
    if col_device:
        idx.append(col_device)
        df = df[df[col_device].isin(devices)]
    df.set_index(idx, inplace=True)
    df.sort_index(inplace=True)

    if col_device:
        joined_df = joined_bylevel(df, col_device, surround='()')
        final_df = joined_bylevel(joined_df, col_instance, surround='[]')
    else:
        final_df = joined_bylevel(df, col_instance, surround='[]')

    # Build metricData
    metric_data = []
    for ts, metrics in final_df.to_dict('index').items():
        epoch = int(ts.timestamp() * 1000)
        d = {'timestamp': str(epoch)}
        d.update(metrics)
        metric_data.append(d)

    return metric_data


def query_data(metricset, period, instances):
    """
    Query metric data
    :param metricset: The metricset to query, ex. cpu, filesystem.
    :param period: The past time period to query, in minutes.
    :param instances: A list of instance name for which to query metric.
    :return: A json string of queried metric data
    """

    start_time = (pd.Timestamp.now() - pd.Timedelta(period * 2, 'minutes')).strftime('%Y%m%d%H%M%S')
    end_time = pd.Timestamp.now().strftime('%Y%m%d%H%M%S')
    payload = {'param': metricset, 'ips': ','.join(instances),
               'startTime': start_time, 'endTime': end_time}

    url = 'http://10.9.131.38/external/getdata'

    content = send_request(url, payload)
    if content:
        logging.debug(f'Get {metricset} data:\n{content}')
    else:
        logging.error(f'Failed to query {metricset} data')

    return content


if __name__ == '__main__':
    # Command line arguments
    parser = argparse.ArgumentParser(description='Streaming host metric')
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
    fmt_str = '%(asctime)s - %(levelname)s - %(filename)s[line:%(lineno)d] ==> %(message)s'
    if args.logfile:
        logger = logging.getLogger()
        logger.setLevel(loglevel)
        rh = logging.handlers.RotatingFileHandler(args.logfile, maxBytes=5 * 1024 ** 2, backupCount=1)
        formatter = logging.Formatter(fmt_str)
        rh.setFormatter(formatter)
        logger.addHandler(rh)
    else:
        logging.basicConfig(format=fmt_str, level=loglevel)

    # Load config.yml
    config_path = f'{os.path.dirname(os.path.realpath(__file__))}/config.yml'
    with open(config_path) as c:
        config = yaml.load(c, yaml.FullLoader)
        logging.debug(f'Load config:\n{config}')
        instances = config['instances']
        metricset = config['metricset']
        query_interval = config['query_interval']
        logging.debug(f'To query {len(metricset)} metricsets for {len(instances)} instances.')

    while True:
        logging.info('Start to process')
        start_time = time.perf_counter()
        for name, schema in metricset.items():
            d = query_data(name, query_interval, instances)
            send_data(build_data(d, schema), config['insightfinder'])
        elapsed_time = time.perf_counter() - start_time
        logging.info(f'Finished in {elapsed_time} seconds, to sleep {query_interval} minutes.\n...')
        time.sleep(query_interval * 60)

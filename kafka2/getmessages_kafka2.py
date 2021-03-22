import configparser
import json
import logging
import os
import regex
import socket
import sys
import time
import pytz
import arrow
from optparse import OptionParser
from multiprocessing import Process
from datetime import datetime
import urllib.parse
import http.client
import requests
import statistics
import subprocess
import shlex
import csv
import threading
from heapq import heappush, heappop
from kafka import KafkaConsumer
from multiprocessing import Process, Queue
import queue
from dateutil import parser
import traceback
from pprint import pprint
import pandas as pd

'''
This script gathers data to send to Insightfinder
'''
logging.basicConfig(level=logging.WARNING,
                    format=('%(asctime)-15s '
                            '%(filename)s: '
                            '%(levelname)s: '
                            '%(funcName)s(): '
                            '%(lineno)d:\t'
                            '%(message)s')
                        )


# TODO: load target_fields from config
target_fields = ['svc_mean', 'tx_mean', 'req_count'] # 'value',
columns = ['timestamp','instance', 'http_status'] + target_fields
tx_q = Queue()
WAIT_PERIOD = 10 * 60


def load_dict_from_str(s):
    """ load a str like {k1=v1, k2=v2, ...} to a dict """
    l = []
    for i in s.replace("{", "").replace("}", "").split(","):
        l.append(tuple(i.strip().split("=")))
    return dict(l)


def read_csv(s):
    "read s with quote char"
    csv_reader = csv.reader([s], skipinitialspace=True)
    return next(csv_reader)


def get_kafka_consumer():
    consumer_args = agent_config_vars['kafka_kwargs']

    consumer = KafkaConsumer(**consumer_args)

    logger.debug("consumer kafka_kwargs {}".format(agent_config_vars['kafka_kwargs']))

    consumer.subscribe(agent_config_vars['topics'])
    logger.info('Successfully subscribed to topics' + str(agent_config_vars['topics']))
    # logger.debug(consumer.topics())
    return consumer


def consumer_process(q, logger, agent_config_vars):
    logger.info(f"consumer_process {os.getpid()} started")
    consumer = get_kafka_consumer()

    while True:
        try:
            try:
                kafka_poll_items = consumer.poll(timeout_ms=100).items()
            except Exception as ex:
                logger.warn('Exception when getting the messages in Kafka,' + \
                            're-establishing the connection: {ex}'.format(ex=str(ex), exc_info=True))
                try:
                    consumer.close()
                    consumer = get_kafka_consumer()
                except Exception as ex2:
                    pass

                continue

            for tp, messages in kafka_poll_items:
                for message in messages:
                    q.put(message)

        except Exception as ex:
            logger.error("Exception in processing messages from kafka: {ex}".format(ex=str(ex)), exc_info=True)
            # Let everything get reinitialized on the next call
            try:
                consumer.close()
            except Exception as ex2:
                pass

            break


def new_worker_process(q, tx_q, logger, agent_config_vars):
    """ process message from q """
    logger.debug(f"pid {os.getpid()} started")
    http_status_codes = set(["2xx", "3xx", "4xx", "5xx"])

    while True:
        item = {'key': None, 'metric_vals': {}}
        start_time = time.time()
        try:
            logger.debug(f"rx_q size {q.qsize()}")
            message = q.get(timeout=60)
            logger.info("got a message")
            msg_dict = json.loads(message.value.decode("ascii", errors='ignore'))
            tags_dict = msg_dict.get("tags", {})
            # ts_ = parser.isoparse(tags_dict['time_bucket'])
            http_status = tags_dict.get("http_status")
            service_alias = tags_dict.get('service_alias', '')

            if not service_alias or not http_status:
                logger.info("message dropped: no service alias or http_status")
                continue

            if agent_config_vars['service_alias_filter'] and \
                service_alias not in agent_config_vars['service_alias_filter']:
                logger.info("message dropped: filtered.")
                continue

            ts = msg_dict.get("timestamp", 0)
            client_alias = tags_dict.get('client_alias', '')
            instance = "{}_{}".format(client_alias, service_alias)
            fields_dict = msg_dict.get("fields", {})
            key = f'{instance}@{ts}'

            item['key'] = key
            item['timestamp'] = ts

            # save metric_vals
            item['metric_vals']['timestamp'] = ts * 1000
            item['metric_vals']['http_status'] = http_status
            item['metric_vals']['instance'] = instance

            for field in target_fields:
                v = fields_dict.get(field)
                item['metric_vals'][field] = None if v == 'null' else v

        except ValueError as e:
            logger.warning(e)

        except queue.Empty:
            logger.warning("queue timeout")
            pass

        except Exception:
            print("-" * 60)
            traceback.print_exc(file=sys.stdout)
            print("-" * 60)

        if item['key'] is not None:
            logger.debug(f"put item {item['key']} in the tx_q")
            tx_q.put(item)

        logger.debug(f"new_worker_process: processed in {time.time()-start_time:8.4f} secs")



def get_buffer_size(data):
    """ input : list of dicts, return size in bytes """
    return len(json.dumps(data))


def buffer_metric_data(metric_data_list, items):
    for item in items:
        metric_data_list.append((item['timestamp'], item['instance'], item['http_status'],
            item['svc_mean'], item['tx_mean'], item['req_count']))


def encode_fields(data):
    """ encode a list of data fields into IF format """
    instance, code, req_count, svc_mean, tx_mean, timestamp = data
    # TODO: find out where timestamp get str float type.
    result = { "timestamp": str(int(float(timestamp))),
               f"req_count_{code}[{instance}]": str(req_count),
               f"svc_mean_{code}[{instance}]": str(svc_mean),
               f"tx_mean_{code}[{instance}]": str(tx_mean)
            }
    return json.dumps(result)


def proc_metric_data_list(metric_data_list):
    """ aggregate by instance and http status code
        backfill with 0 for missed categories
        and proper encode each item
    """
    logging.info(f"len of metric_data_list: {len(metric_data_list)}")
    df = pd.DataFrame(data=metric_data_list, columns = columns)

    df2 =df.groupby(['instance', 'http_status']).agg({
        'req_count': ['sum'], 'svc_mean':['mean'], 'tx_mean':['mean'],
        'timestamp':['min']})

    http_status_codes = set(['2xx', '3xx', '4xx', '5xx'])
    prev_instance = None
    codes = set()
    l = []
    for group, val in df2.fillna(0).iterrows():
        req_count, svc_mean, tx_mean, timestamp = val
        instance, code = group

        if instance != prev_instance and prev_instance is not None:
            # fill 0 for prev_instance
            for code in http_status_codes - codes:
                t = (prev_instance, code, 0, 0, 0, timestamp)
                l.append(encode_fields(t))
            codes.clear()

        # process instance
        t = (instance, code, *[str(i) for i in val])
        l.append(encode_fields(t))
        prev_instance = instance
        codes.add(code)
    return l

def func_check_buffer(logger, if_config_vars, lock, buffer_d, args_d):
    metric_data_list = []
    interval = if_config_vars['sampling_interval']

    while True:
        time.sleep(interval)
        start_time = time.time()
        try:
            # check the buffer
            logger.debug(f"find {len(buffer_d)} items")

            # flush buffer if we haven't received any data for a long time
            time_elapsed = time.time() - args_d['latest_received_time']
            if time_elapsed > if_config_vars['run_interval']:
                logger.debug(f"time_elapsed:{time_elapsed} since latest_received_time={args_d['latest_received_time']}")
                if lock.acquire():
                    for key_item in buffer_d.values():
                        buffer_metric_data(metric_data_list, key_item.values())
                    buffer_d.clear()
                    lock.release()

            # send messages are too old comparing to latest message timestamp
            elif args_d['latest_msg_time'] > 0:
                expire_time = args_d['latest_msg_time'] - if_config_vars['run_interval']

                keys_to_drop = []
                if lock.acquire():
                    for ts in filter(lambda x: x < expire_time, buffer_d.keys()):
                        buffer_metric_data(metric_data_list, buffer_d[ts].values())
                        keys_to_drop.append(ts)
                    for ts in keys_to_drop:
                        buffer_d.pop(ts)
                    lock.release()

            if  len(metric_data_list) > 0:
                metric_data_list_processed = proc_metric_data_list(metric_data_list)

                for chunk in data_chunks(metric_data_list_processed, if_config_vars["chunk_size"]):
                    send_data(chunk)
                metric_data_list.clear()

        except Exception:
            print("-" * 60)
            traceback.print_exc(file=sys.stdout)
            print("-" * 60)


def new_sender_process(q, logger, if_config_vars):
    logger.info(f"sender_process {os.getpid()} started")

    # share with threads
    buffer_dict = {}
    args_dict = {'latest_msg_time': 0, 'latest_received_time': 0}

    # start an thread to check the buffer
    thread_lock = threading.Lock()
    thread1 = threading.Thread(target=func_check_buffer,
                               args=(logger, if_config_vars, thread_lock, buffer_dict, args_dict))
    thread1.start()

    # main thread
    while True:
        start_time = time.time()
        try:
            logger.debug(f"tx_q size: {q.qsize()}")
            item = q.get()
            logger.debug("get an item")

            timestamp = item['timestamp']
            # update latest messages time
            args_dict['latest_msg_time'] = max(args_dict['latest_msg_time'], timestamp)
            # update latest msg received time
            args_dict['latest_received_time'] = time.time()

            # drop this message if is too old, since that batch has been sent
            if timestamp < args_dict['latest_msg_time'] - if_config_vars['run_interval']:
                logger.info(f"dropped old msg with time={timestamp}")
                continue

            if timestamp not in buffer_dict:
                buffer_dict[timestamp] = {}

            key = item['key']
            if key not in buffer_dict[timestamp]:
                buffer_dict[timestamp][key] = {}

            # combine metrics data
            if thread_lock.acquire():
                buffer_dict[timestamp][key].update(item['metric_vals'])
                thread_lock.release()
            logger.debug(f"new item dict={buffer_dict[timestamp][key]}")
            logger.info("processed item")

        except Exception:
            print("-" * 60)
            traceback.print_exc(file=sys.stdout)
            print("-" * 60)

        logger.info(f"sender main thread: {time.time()-start_time:8.4f} secs")

    thread1.join()


def start_data_processing():
    logger.info("start_data_processing")

    rx_q=[]
    consumers = []

    for i in range(cli_config_vars['processes']):
        rx_q.append(Queue()) 

        # start consumer processes
        c = Process(target=consumer_process, args=(rx_q[i], logger, if_config_vars))
        consumers.append(c)

    for c in consumers:
        c.start()

    # start sender_process
    s = Process(target=new_sender_process, args=(tx_q, logger, if_config_vars))
    s.start()

    # start worker processes
    process_list = []
    for i in range(0, cli_config_vars['processes']):
        p = Process(target=new_worker_process,
                    args=(rx_q[i], tx_q, logger, agent_config_vars)
                    )
        process_list.append(p)

    for p in process_list:
        p.start()

    for p in process_list:
        p.join()

    # below should never be reached.
    for c in consumers:
        c.join()
    s.join()


def get_agent_config_vars():
    """ Read and parse config.ini """
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini'))):
        config_parser = configparser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini')))
        try:
            # proxy settings
            agent_http_proxy = config_parser.get('kafka', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('kafka', 'agent_https_proxy')

            # kafka settings
            kafka_config = {
                # hardcoded
                'api_version': (0, 10),
                'auto_offset_reset': '',
                'consumer_timeout_ms': 30 * if_config_vars['sampling_interval'] * 1000 if 'METRIC' in if_config_vars[
                    'project_type'] or 'LOG' in if_config_vars['project_type'] else None,

                # consumer settings
                'group_id': config_parser.get('kafka', 'group_id'),
                'client_id': config_parser.get('kafka', 'client_id'),

                # SSL
                'security_protocol': 'SSL' if config_parser.get('kafka', 'security_protocol') == 'SSL' else 'PLAINTEXT',
                'ssl_context': config_parser.get('kafka', 'ssl_context'),
                'ssl_cafile': config_parser.get('kafka', 'ssl_cafile'),
                'ssl_certfile': config_parser.get('kafka', 'ssl_certfile'),
                'ssl_keyfile': config_parser.get('kafka', 'ssl_keyfile'),
                'ssl_password': config_parser.get('kafka', 'ssl_password'),
                'ssl_crlfile': config_parser.get('kafka', 'ssl_crlfile'),
                'ssl_ciphers': config_parser.get('kafka', 'ssl_ciphers'),
                'ssl_check_hostname': ternary_tfd(config_parser.get('kafka', 'ssl_check_hostname')),

                # SASL
                'sasl_mechanism': config_parser.get('kafka', 'sasl_mechanism'),
                'sasl_plain_username': config_parser.get('kafka', 'sasl_plain_username'),
                'sasl_plain_password': config_parser.get('kafka', 'sasl_plain_password'),
                'sasl_kerberos_service_name': config_parser.get('kafka', 'sasl_kerberos_service_name'),
                'sasl_kerberos_domain_name': config_parser.get('kafka', 'sasl_kerberos_domain_name'),
                'sasl_oauth_token_provider': config_parser.get('kafka', 'sasl_oauth_token_provider')
            }

            # only keep settings with values
            kafka_kwargs = {k: v for (k, v) in list(kafka_config.items()) if v}

            # check SASL
            if 'sasl_mechanism' in kafka_kwargs:
                if kafka_kwargs['sasl_mechanism'] not in {'PLAIN', 'GSSAPI', 'OAUTHBEARER'}:
                    logger.warn('sasl_mechanism not one of PLAIN, GSSAPI, or OAUTHBEARER')
                    kafka_kwargs.pop('sasl_mechanism')
                elif kafka_kwargs['sasl_mechanism'] == 'PLAIN':
                    # set required vars for plain sasl if not present
                    if 'sasl_plain_username' not in kafka_kwargs:
                        kafka_kwargs['sasl_plain_username'] = ''
                    if 'sasl_plain_password' not in kafka_kwargs:
                        kafka_kwargs['sasl_plain_password'] = ''

            # handle boolean setting
            if config_parser.get('kafka', 'ssl_check_hostname').upper() == 'FALSE':
                kafka_kwargs['ssl_check_hostname'] = False

            # handle required arrays
            # bootstrap serverss
            if len(config_parser.get('kafka', 'bootstrap_servers')) != 0:
                kafka_kwargs['bootstrap_servers'] = config_parser.get('kafka', 'bootstrap_servers').strip().split(',')
            else:
                config_error('bootstrap_servers')

            # topics
            if len(config_parser.get('kafka', 'topics')) != 0:
                topics = config_parser.get('kafka', 'topics').split(',')
            else:
                config_error('topics')

            # filters
            filters_include = config_parser.get('kafka', 'filters_include')
            filters_exclude = config_parser.get('kafka', 'filters_exclude')
            service_alias_fliter = config_parser.get('kafka', 'service_alias_filter')

            # message parsing
            timestamp_format = config_parser.get('kafka', 'timestamp_format', raw=True)
            timestamp_field = config_parser.get('kafka', 'timestamp_field', raw=True) or 'timestamp'
            timezone = config_parser.get('kafka', 'timezone')
            instance_field = config_parser.get('kafka', 'instance_field', raw=True)
            device_field = config_parser.get('kafka', 'device_field', raw=True)
            data_fields = config_parser.get('kafka', 'data_fields', raw=True)

            # definitions
            data_format = config_parser.get('kafka', 'data_format').upper()
            csv_field_names = config_parser.get('kafka', 'csv_field_names')
            csv_field_delimiter = config_parser.get('kafka', 'csv_field_delimiter', raw=True) or ',|\t'
            json_top_level = config_parser.get('kafka', 'json_top_level')
            raw_regex = config_parser.get('kafka', 'raw_regex', raw=True)
            raw_start_regex = config_parser.get('kafka', 'raw_start_regex', raw=True)

            # metric buffer
            all_metrics = config_parser.get('kafka', 'all_metrics')
            metric_buffer_size_mb = config_parser.get('kafka', 'metric_buffer_size_mb') or '10'

        except configparser.NoOptionError:
            config_error()

        # any post-processing
        # check SASL
        if 'sasl_mechanism' in kafka_kwargs:
            if kafka_kwargs['sasl_mechanism'] not in {'PLAIN', 'GSSAPI', 'OAUTHBEARER'}:
                logger.warn('sasl_mechanism not one of PLAIN, GSSAPI, or OAUTHBEARER')
                kafka_kwargs.pop('sasl_mechanism')
            elif kafka_kwargs['sasl_mechanism'] == 'PLAIN':
                # set required vars for plain sasl if not present
                if 'sasl_plain_username' not in kafka_kwargs:
                    kafka_kwargs['sasl_plain_username'] = ''
                if 'sasl_plain_password' not in kafka_kwargs:
                    kafka_kwargs['sasl_plain_password'] = ''

        # proxies
        agent_proxies = dict()
        if len(agent_http_proxy) > 0:
            agent_proxies['http'] = agent_http_proxy
        if len(agent_https_proxy) > 0:
            agent_proxies['https'] = agent_https_proxy

        # filters
        if len(filters_include) != 0:
            filters_include = filters_include.split('|')
        if len(filters_exclude) != 0:
            filters_exclude = filters_exclude.split('|')
        if len(service_alias_fliter) != 0:
            service_alias_fliter = service_alias_fliter.split("|")

        # fields
        # project_field = project_field.split(',')
        instance_field = instance_field.split(',')
        device_field = device_field.split(',')
        timestamp_field = timestamp_field.split(',')
        if len(data_fields) != 0:
            data_fields = data_fields.split(',')
            # if project_field in data_fields:
            #    data_fields.pop(data_fields.index(project_field))
            if instance_field in data_fields:
                data_fields.pop(data_fields.index(instance_field))
            if device_field in data_fields:
                data_fields.pop(data_fields.index(device_field))
            if timestamp_field in data_fields:
                data_fields.pop(data_fields.index(timestamp_field))

        # timestamp format
        if len(timestamp_format) != 0:
            timestamp_format = [x for x in timestamp_format.split(',') if x.strip()]
        else:
            config_error('timestamp_format')

        if timezone:
            if timezone not in pytz.all_timezones:
                config_error('timezone')
            else:
                timezone = pytz.timezone(timezone)

        # data format
        if data_format == 'CSV':
            if len(csv_field_names) == 0:
                config_error('csv_field_names')
            csv_field_names = csv_field_names.split(',')
            try:
                csv_field_delimiter = regex.compile(csv_field_delimiter)
            except Exception as e:
                config_error('csv_field_delimiter')
        elif data_format == 'RAW':
            try:
                raw_regex = regex.compile(raw_regex)
            except Exception as e:
                config_error('raw_regex')
            # multiline
            if len(raw_start_regex) != 0:
                if raw_start_regex[0] != '^':
                    config_error('raw_start_regex')
                try:
                    raw_start_regex = regex.compile(raw_start_regex)
                except Exception as e:
                    config_error('raw_start_regex')
        elif data_format == 'JSON':
            pass
        else:
            config_error('data_format')

        # defaults
        if all_metrics:
            all_metrics = all_metrics.split(',')

        # add parsed variables to a global
        config_vars = {
            'kafka_kwargs': kafka_kwargs,
            'topics': topics,
            'filters_include': filters_include,
            'filters_exclude': filters_exclude,
            'data_format': data_format,
            'raw_regex': raw_regex,
            'raw_start_regex': raw_start_regex,
            'csv_field_names': csv_field_names,
            'csv_field_delimiter': csv_field_delimiter,
            'json_top_level': json_top_level,
            'timestamp_format': timestamp_format,
            'timezone': timezone,
            'timestamp_field': timestamp_field,
            'instance_field': instance_field,
            'device_field': device_field,
            'data_fields': data_fields,
            'proxies': agent_proxies,
            'all_metrics': all_metrics,
            'metric_buffer_size': int(metric_buffer_size_mb) * 1024 * 1024,  # as bytes
            'service_alias_filter': service_alias_fliter
        }

        return config_vars
    else:
        config_error_no_config()


#########################
### START_BOILERPLATE ###
#########################
def get_if_config_vars():
    """ get config.ini vars """
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini'))):
        config_parser = configparser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini')))
        try:
            user_name = config_parser.get('insightfinder', 'user_name')
            license_key = config_parser.get('insightfinder', 'license_key')
            token = config_parser.get('insightfinder', 'token')
            project_name = config_parser.get('insightfinder', 'project_name')
            project_type = config_parser.get('insightfinder', 'project_type').upper()
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            run_interval = config_parser.get('insightfinder', 'run_interval')
            chunk_size_kb = config_parser.get('insightfinder', 'chunk_size_kb')
            if_url = config_parser.get('insightfinder', 'if_url')
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            config_error()

        # check required variables
        if len(user_name) == 0:
            config_error('user_name')
        if len(license_key) == 0:
            config_error('license_key')
        if len(project_name) == 0:
            config_error('project_name')
        if len(project_type) == 0:
            config_error('project_type')

        if project_type not in {
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
            config_error('project_type')

        if len(sampling_interval) == 0:
            if 'METRIC' in project_type:
                config_error('sampling_interval')
            else:
                # set default for non-metric
                sampling_interval = 10

        if sampling_interval.endswith('s'):
            sampling_interval = int(sampling_interval[:-1])
        else:
            sampling_interval = int(sampling_interval) * 60

        if len(run_interval) == 0:
            config_error('run_interval')

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

        config_vars = {
            'user_name': user_name,
            'license_key': license_key,
            'token': token,
            'project_name': project_name,
            'project_type': project_type,
            'sampling_interval': int(sampling_interval),  # as seconds
            'run_interval': int(run_interval),  # as seconds
            'chunk_size': int(chunk_size_kb) * 1024,  # as bytes
            'if_url': if_url,
            'if_proxies': if_proxies
        }

        return config_vars
    else:
        config_error_no_config()


def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    parser.add_option('-p', '--processes', default=1, action='store', dest='processes',
                      help='Number of processes to run')
    parser.add_option('-l', '--level', action='store', dest='log_level',
                      help='logging level')

    (options, args) = parser.parse_args()

    config_vars = {
        'processes': 1,
        'testing': False,
        'log_level': logging.WARNING
    }

    if options.processes:
        config_vars['processes'] = int(options.processes)

    config_vars['log_level'] = eval(options.log_level or 'logging.WARNING')

    return config_vars


def config_error(setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(
        info))
    sys.exit(1)


def config_error_no_config():
    logger.error('No config file found. Exiting...')
    sys.exit(1)


def check_csv_fieldnames(csv_field_names, all_fields):
    # required
    for field, _map in all_fields['required_fields']:
        _map['index'] = get_field_index(
            csv_field_names,
            _map['name'],
            field,
            True)

    # optional
    for field, _map in all_fields['optional_fields']:
        if len(_map['name']) != 0:
            index = get_field_index(
                csv_field_names,
                _map['name'],
                field)
            _map['index'] = index if isinstance(index, int) else ''

    # filters
    for field, _map in all_fields['filters']:
        if len(_map['name']) != 0:
            filters_temp = []
            for _filter in _map['name']:
                filter_field = _filter.split(':')[0]
                filter_vals = _filter.split(':')[1]
                filter_index = get_field_index(
                    csv_field_names,
                    filter_field,
                    field)
                if isinstance(filter_index, int):
                    filter_temp = '{}:{}'.format(filter_index, filter_vals)
                    filters_temp.append(filter_temp)
            _map['filter'] = filters_temp

    # data
    if len(all_fields['data_fields']) != 0:
        data_fields_temp = []
        for data_field in all_fields['data_fields']:
            data_field_temp = get_field_index(
                csv_field_names,
                data_field,
                'data_field')
            if isinstance(data_field_temp, int):
                data_fields_temp.append(data_field_temp)
        all_fields['data_fields'] = data_fields_temp
    if len(all_fields['data_fields']) == 0:
        # use all non-timestamp fields
        all_fields['data_fields'] = list(range(len(csv_field_names)))

    return all_fields


def ternary_tfd(b, default=''):
    if TRUE.match(b):
        return True
    elif FALSE.match(b):
        return False
    else:
        return default


def is_in(find, find_in):
    if isinstance(find, (set, list, tuple)):
        for f in find:
            if f in find_in:
                return True
    else:
        if find in find_in:
            return True
    return False


def get_sentence_segment(sentence, start, end=None):
    segment = sentence.split(' ')[start:end]
    return ' '.join(segment)


def check_project(project_name):
    if 'token' in if_config_vars and len(if_config_vars['token']) != 0:
        logger.debug(project_name)
        try:
            # check for existing project
            check_url = urllib.parse.urljoin(if_config_vars['if_url'], '/api/v1/getprojectstatus')
            output_check_project = subprocess.check_output(
                'curl "' + check_url + '?userName=' + if_config_vars['user_name'] + '&token=' + if_config_vars[
                    'token'] + '&projectList=%5B%7B%22projectName%22%3A%22' + project_name + '%22%2C%22customerName%22%3A%22' +
                if_config_vars['user_name'] + '%22%2C%22projectType%22%3A%22CUSTOM%22%7D%5D&tzOffset=-14400000"',
                shell=True)
            # create project if no existing project
            if project_name not in output_check_project:
                logger.debug('creating project')
                create_url = urllib.parse.urljoin(if_config_vars['if_url'], '/api/v1/add-custom-project')
                output_create_project = subprocess.check_output(
                    'no_proxy= curl -d "userName=' + if_config_vars['user_name'] + '&token=' + if_config_vars[
                        'token'] + '&projectName=' + project_name + '&instanceType=PrivateCloud&projectCloudType=PrivateCloud&dataType=' + get_data_type_from_project_type() + '&samplingInterval=' + str(
                        if_config_vars['sampling_interval'] / 60) + '&samplingIntervalInSeconds=' + str(if_config_vars[
                                                                                                            'sampling_interval']) + '&zone=&email=&access-key=&secrete-key=&insightAgentType=' + get_insight_agent_type_from_project_type() + '" -H "Content-Type: application/x-www-form-urlencoded" -X POST ' + create_url + '?tzOffset=-18000000',
                    shell=True)
            # set project name to proposed name
            if_config_vars['project_name'] = project_name
            # try to add new project to system
            if 'system_name' in if_config_vars and len(if_config_vars['system_name']) != 0:
                system_url = urllib.parse.urljoin(if_config_vars['if_url'], '/api/v1/projects/update')
                output_update_project = subprocess.check_output(
                    'no_proxy= curl -d "userName=' + if_config_vars['user_name'] + '&token=' + if_config_vars[
                        'token'] + '&operation=updateprojsettings&projectName=' + project_name + '&systemName=' +
                    if_config_vars[
                        'system_name'] + '" -H "Content-Type: application/x-www-form-urlencoded" -X POST ' + system_url + '?tzOffset=-18000000',
                    shell=True)
        except subprocess.CalledProcessError as e:
            logger.error('Unable to create project for ' + project_name + '. Data will be sent to ' + if_config_vars[
                'project_name'])


def get_field_index(field_names, field, label, is_required=False):
    err_code = ''
    try:
        temp = int(field)
        if temp > len(field_names):
            err_msg = 'field {} is not a valid array index given field names {}'.format(field, field_names)
            field = err_code
        else:
            field = temp
    # not an integer
    except ValueError:
        try:
            field = field_names.index(field)
        # not in the field names
        except ValueError:
            err_msg = 'field {} is not a valid field in field names {}'.format(field, field_names)
            field = err_code
    finally:
        if field == err_code:
            logger.warn('Agent not configured correctly ({})\n{}'.format(label, err_msg))
            if is_required:
                sys.exit(1)
            return
        else:
            return field


def should_include_per_config(setting, value):
    """ determine if an agent config filter setting would exclude a given value """
    return len(agent_config_vars[setting]) != 0 and value not in agent_config_vars[setting]


def should_exclude_per_config(setting, value):
    """ determine if an agent config exclude setting would exclude a given value """
    return len(agent_config_vars[setting]) != 0 and value in agent_config_vars[setting]


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    return len(bytearray(json.dumps(json_data)))


def get_all_files(files, file_regex_c):
    return [i for j in
            [get_file_list_for_directory(k, file_regex_c) for k in files]
            for i in j if i]


def get_file_list_for_directory(root_path='/', file_name_regex_c=''):
    root_path = os.path.expanduser(root_path)
    if os.path.isdir(root_path):
        file_list = []
        for path, subdirs, files in os.walk(root_path):
            for name in files:
                if check_regex(file_name_regex_c, name):
                    file_list.append(os.path.join(path, name))
        return file_list
    elif os.path.isfile(root_path):
        if check_regex(file_name_regex_c, root_path):
            return [root_path]
    return []


def parse_raw_line(message, line):
    # if multiline
    if agent_config_vars['raw_start_regex']:
        # if new message, parse old and start new
        if agent_config_vars['raw_start_regex'].match(line):
            parse_raw_message(message)
            message = line
        else:  # add to current message
            logger.debug('continue building message')
            message += line
    else:
        parse_raw_message(line)
    return message


def parse_raw_message(message):
    matches = agent_config_vars['raw_regex'].match(message)
    if matches:
        message_json = matches.groupdict()
        message_json['_raw'] = message
        parse_json_message(message_json)


def check_regex(pattern_c, check):
    return not pattern_c or pattern_c.match(check)


def is_formatted(setting_value):
    """ returns True if the setting is a format string """
    return check_regex(FORMAT_STR, setting_value)


def is_math_expr(setting_value):
    return '=' in setting_value


def get_math_expr(setting_value):
    return setting_value.strip('=')


def is_named_data_field(setting_value):
    return ':' in setting_value


def merge_data(field, value, data={}):
    fields = field.split(JSON_LEVEL_DELIM)
    for i in range(len(fields) - 1):
        field = fields[i]
        if field not in data:
            data[field] = dict()
        data = data[field]
    data[fields[-1]] = value
    return data


def parse_formatted(message, setting_value, default='', allow_list=False, remove=False):
    """ fill a format string with values """
    fields = {field: get_json_field(message,
                                    field,
                                    default='',
                                    allow_list=allow_list,
                                    remove=remove)
              for field in FORMAT_STR.findall(setting_value)}
    if len(fields) == 0:
        return default
    return setting_value.format(**fields)


def get_data_values(timestamp, message):
    setting_values = agent_config_vars['data_fields'] or list(message.keys())
    # reverse list so it's in priority order, as shared fields names will get overwritten
    setting_values.reverse()
    data = {x: dict() for x in timestamp}
    for setting_value in setting_values:
        name, value = get_data_value(message, setting_value)
        if isinstance(value, (set, tuple, list)):
            for i in range(minlen(timestamp, value)):
                merge_data(name, value[i], data[timestamp[i]])
        else:
            merge_data(name, value, data[timestamp[0]])
    return data


def get_data_value(message, setting_value):
    if is_named_data_field(setting_value):
        setting_value = setting_value.split(':')
        # get name
        name = setting_value[0]
        if is_formatted(name):
            name = parse_formatted(message,
                                   name,
                                   default=name)
        # get value
        value = setting_value[1]
        # check if math
        evaluate = False
        if is_math_expr(value):
            evaluate = True
            value = get_math_expr(value)
        if is_formatted(value):
            value = parse_formatted(message,
                                    value,
                                    default=value,
                                    allow_list=True)
        if evaluate:
            value = eval(value)
    else:
        name = setting_value
        value = get_json_field(message,
                               setting_value,
                               allow_list=True)
    return (name, value)


def get_single_value(message, config_setting, default='', allow_list=False, remove=False):
    if config_setting not in agent_config_vars or len(agent_config_vars[config_setting]) == 0:
        return default
    setting_value = agent_config_vars[config_setting]
    if isinstance(setting_value, (set, list, tuple)):
        setting_value_single = setting_value[0]
    else:
        setting_value_single = setting_value
    if is_formatted(setting_value_single):
        return parse_formatted(message,
                               setting_value_single,
                               default=default,
                               allow_list=False,
                               remove=remove)
    else:
        return get_json_field_by_pri(message,
                                     [i for i in setting_value],
                                     default=default,
                                     allow_list=allow_list,
                                     remove=remove)


def get_json_field_by_pri(message, pri_list, default='', allow_list=False, remove=False):
    value = ''
    while value == '' and len(pri_list) != 0:
        field = pri_list.pop(0)
        if field:
            value = get_json_field(message,
                                   field,
                                   allow_list=allow_list,
                                   remove=remove)
    return value or default


def get_json_field(message, setting_value, default='', allow_list=False, remove=False):
    field_val = json_format_field_value(
        _get_json_field_helper(
            message,
            setting_value.split(JSON_LEVEL_DELIM),
            allow_list=allow_list,
            remove=remove))
    if len(field_val) == 0:
        field_val = default
    return field_val


class ListNotAllowedError():
    pass


def _get_json_field_helper(nested_value, next_fields, allow_list=False, remove=False):
    # check inputs; need a dict that is a subtree, an _array_ of fields to traverse down
    if len(next_fields) == 0:
        # nothing to look for
        return ''
    elif isinstance(nested_value, (list, set, tuple)):
        # for each elem in the list
        # already checked in the recursive call that this is OK
        return json_gather_list_values(nested_value, next_fields)
    elif not isinstance(nested_value, dict):
        # nothing to walk down
        return ''

    # get the next value
    next_field = next_fields.pop(0)
    next_value = json.loads(json.dumps(nested_value.get(next_field)))
    if len(next_fields) == 0 and remove:
        # last field to grab, so remove it
        nested_value.pop(next_field)

    # check the next value
    if next_value is None:
        # no next value defined
        return ''
    elif len(bytes(next_value)) == 0:
        # no next value set
        return ''

    # sometimes payloads come in formatted
    try:
        next_value = json.loads(next_value)
    except Exception as ex:
        next_value = json.loads(json.dumps(next_value))

    # handle simple lists
    while isinstance(next_value, (list, set, tuple)) and len(next_value) == 1:
        next_value = next_value.pop()

    # continue traversing?
    if next_fields is None:
        # some error, but return the value
        return next_value
    elif len(next_fields) == 0:
        # final value in the list to walk down
        return next_value
    elif isinstance(next_value, (list, set, tuple)):
        # we've reached an early terminal point, which may or may not be ok
        if allow_list:
            return json_gather_list_values(
                next_value,
                next_fields,
                remove=remove)
        else:
            raise ListNotAllowedError('encountered list or set in json when not allowed')
    elif isinstance(next_value, dict):
        # there's more tree to walk down
        return _get_json_field_helper(
            json.loads(json.dumps(next_value)),
            next_fields,
            allow_list=allow_list,
            remove=remove)
    else:
        # catch-all
        return ''


def json_gather_list_values(l, fields, remove=False):
    sub_field_value = []
    # treat each item in the list as a potential tree to walk down
    for sub_value in l:
        fields_copy = list(fields[i] for i in range(len(fields)))
        json_value = json_format_field_value(
            _get_json_field_helper(
                sub_value,
                fields_copy,
                allow_list=True,
                remove=remove))
        if len(json_value) != 0:
            sub_field_value.append(json_value)
    # return the full list of field values
    return sub_field_value


def json_format_field_value(value):
    # flatten 1-item set/list
    if isinstance(value, (list, set, tuple)):
        if len(value) == 1:
            return value.pop()
        return list(value)
    # keep dicts intact
    elif isinstance(value, dict):
        return value
    # stringify everything else
    return str(value)


def parse_json_message(messages):
    if len(agent_config_vars['json_top_level']) != 0:
        if agent_config_vars['json_top_level'] == '[]' and isinstance(messages, (list, set, tuple)):
            for message in messages:
                parse_json_message_single(message)
        else:
            top_level = _get_json_field_helper(
                messages,
                agent_config_vars['json_top_level'].split(JSON_LEVEL_DELIM),
                allow_list=True)
            if isinstance(top_level, (list, set, tuple)):
                for message in top_level:
                    parse_json_message_single(message)
            else:
                parse_json_message_single(top_level)
    elif isinstance(messages, (list, set, tuple)):
        for message_single in messages:
            parse_json_message_single(message_single)
    else:
        parse_json_message_single(messages)


def parse_json_message_single(message):
    # message = json.loads(json.dumps(message))
    # filter
    if len(agent_config_vars['filters_include']) != 0:
        # for each provided filter
        is_valid = False
        for _filter in agent_config_vars['filters_include']:
            filter_field = _filter.split(':')[0]
            filter_vals = _filter.split(':')[1].split(',')
            filter_check = get_json_field(
                message,
                filter_field.split(JSON_LEVEL_DELIM),
                allow_list=True)
            # check if a valid value
            for filter_val in filter_vals:
                if filter_val.upper() in filter_check.upper():
                    is_valid = True
                    break
            if is_valid:
                break
        if not is_valid:
            logger.debug('filtered message (inclusion): {} not in {}'.format(
                filter_check, filter_vals))
            return
        else:
            logger.debug('passed filter (inclusion)')

    if len(agent_config_vars['filters_exclude']) != 0:
        # for each provided filter
        for _filter in agent_config_vars['filters_exclude']:
            filter_field = _filter.split(':')[0]
            filter_vals = _filter.split(':')[1].split(',')
            filter_check = get_json_field(
                message,
                filter_field.split(JSON_LEVEL_DELIM),
                allow_list=True)
            # check if a valid value
            for filter_val in filter_vals:
                if filter_val.upper() in filter_check.upper():
                    logger.debug('filtered message (exclusion): {} in {}'.format(
                        filter_val, filter_check))
                    return
        logger.debug('passed filter (exclusion)')

    instance = get_single_value(message,
                                'instance_field',
                                default=HOSTNAME,
                                remove=True)
    device = get_single_value(message,
                              'device_field',
                              remove=True)
    # get timestamp
    try:
        timestamp = get_single_value(message,
                                     'timestamp_field',
                                     remove=True)
        timestamp = [timestamp]
    except ListNotAllowedError as lnae:
        timestamp = get_single_value(message,
                                     'timestamp_field',
                                     remove=True,
                                     allow_list=True)
    except Exception as e:
        logger.warn(e)
        return

    # get data
    data = get_data_values(timestamp, message)

    # hand off
    for timestamp, report_data in list(data.items()):
        ts = get_timestamp_from_date_string(timestamp)
        if not ts:
            continue
        if 'METRIC' in if_config_vars['project_type']:
            data_folded = fold_up(report_data, value_tree=True)  # put metric data in top level
            for data_field, data_value in list(data_folded.items()):
                if data_value is not None:
                    metric_handoff(
                        ts,
                        data_field,
                        data_value,
                        instance,
                        device)
        else:
            log_handoff(ts, report_data, instance, device)


def label_message(message, fields=[]):
    """ turns unlabeled, split data into labeled data """
    if agent_config_vars['data_format'] == 'CSV':
        fields = agent_config_vars['csv_field_names']
    json = dict()
    for i in range(minlen(fields, message)):
        json[fields[i]] = message[i]
    return json


def minlen(one, two):
    return min(len(one), len(two))


def parse_csv_message(message):
    # filter
    if len(agent_config_vars['filters_include']) != 0:
        # for each provided filter, check if there are any allowed valued
        is_valid = False
        for _filter in agent_config_vars['filters_include']:
            filter_field = _filter.split(':')[0]
            filter_vals = _filter.split(':')[1].split(',')
            filter_check = message[int(filter_field)]
            # check if a valid value
            for filter_val in filter_vals:
                if filter_val.upper() in filter_check.upper():
                    is_valid = True
                    break
            if is_valid:
                break
        if not is_valid:
            logger.debug('filtered message (inclusion): {} not in {}'.format(
                filter_check, filter_vals))
            return
        else:
            logger.debug('passed filter (inclusion)')

    if len(agent_config_vars['filters_exclude']) != 0:
        # for each provided filter, check if there are any disallowed values
        for _filter in agent_config_vars['filters_exclude']:
            filter_field = _filter.split(':')[0]
            filter_vals = _filter.split(':')[1].split(',')
            filter_check = message[int(filter_field)]
            # check if a valid value
            for filter_val in filter_vals:
                if filter_val.upper() in filter_check.upper():
                    logger.debug('filtered message (exclusion): {} in {}'.format(
                        filter_check, filter_val))
                    return
        logger.debug('passed filter (exclusion)')

    # project
    # if isinstance(agent_config_vars['project_field'], int):
    #    check_project(message[agent_config_vars['project_field']])

    # instance
    instance = HOSTNAME
    if isinstance(agent_config_vars['instance_field'], int):
        instance = message[agent_config_vars['instance_field']]

    # device
    device = ''
    if isinstance(agent_config_vars['device_field'], int):
        device = message[agent_config_vars['device_field']]

    # data & timestamp
    columns = [agent_config_vars['timestamp_field']] + agent_config_vars['data_fields']
    row = list(message[i] for i in columns)
    fields = list(agent_config_vars['csv_field_names'][j] for j in agent_config_vars['data_fields'])
    parse_csv_row(row, fields, instance, device)


def parse_csv_data(csv_data, instance, device=''):
    """
    parses CSV data, assuming the format is given as:
        header row:  timestamp,field_1,field_2,...,field_n
        n data rows: TIMESTAMP,value_1,value_2,...,value_n
    """

    # get field names from header row
    field_names = csv_data.pop(0).split(CSV_DELIM)[1:]

    # go through each row
    for row in csv_data:
        if len(row) > 0:
            parse_csv_row(row.split(CSV_DELIM), field_names, instance, device)


def parse_csv_row(row, field_names, instance, device=''):
    timestamp = get_timestamp_from_date_string(row.pop(0))
    if not timestamp:
        return
    if 'METRIC' in if_config_vars['project_type']:
        for i in range(len(row)):
            metric_handoff(timestamp, field_names[i], row[i], instance, device)
    else:
        json_message = dict()
        for i in range(len(row)):
            json_message[field_names[i]] = row[i]
        log_handoff(timestamp, json_message, instance, device)


def get_timestamp_from_date_string(date_string):
    """ parse a date string into unix epoch (ms) """
    datetime_obj = None
    epoch = None
    if 'timestamp_format' in agent_config_vars:
        for timestamp_format in agent_config_vars['timestamp_format']:
            try:
                if timestamp_format == 'epoch':
                    if 13 <= len(date_string) < 15:
                        timestamp = int(date_string) / 1000
                        datetime_obj = arrow.get(timestamp)
                    elif 9 <= len(date_string) < 13:
                        timestamp = int(date_string)
                        datetime_obj = arrow.get(timestamp)
                    else:
                        raise
                else:
                    if agent_config_vars['timezone']:
                        datetime_obj = arrow.get(date_string, timestamp_format,
                                                 tzinfo=agent_config_vars['timezone'].zone)
                    else:
                        datetime_obj = arrow.get(date_string, timestamp_format)
                break
            except Exception as e:
                logger.debug(e)
                logger.debug('timestamp {} does not match {}'.format(date_string, timestamp_format))
                continue
    else:
        try:
            if agent_config_vars['timezone']:
                datetime_obj = arrow.get(date_string, tzinfo=agent_config_vars['timezone'].zone)
            else:
                datetime_obj = arrow.get(date_string)
        except Exception as e:
            logger.debug(e)
            logger.error('timestamp {} can not parse'.format(date_string))

    # get epoch (misc)
    if datetime_obj:
        epoch = int(datetime_obj.float_timestamp * 1000)

    return epoch


def make_safe_instance_string(instance, device=''):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', instance)
    instance = COLONS.sub('-', instance)
    # if there's a device, concatenate it to the instance with an underscore
    if len(device) != 0:
        instance = '{}_{}'.format(make_safe_instance_string(device), instance)
    return instance


def make_safe_metric_key(metric):
    """ make safe string already handles this """
    metric = LEFT_BRACE.sub('(', metric)
    metric = RIGHT_BRACE.sub(')', metric)
    metric = PERIOD.sub('/', metric)
    return metric


def make_safe_string(string):
    """
    Take a single string and return the same string with spaces, slashes,
    underscores, and non-alphanumeric characters subbed out.
    """
    string = SPACES.sub('-', string)
    string = SLASHES.sub('.', string)
    string = UNDERSCORE.sub('.', string)
    string = NON_ALNUM.sub('', string)
    return string


def run_subproc_once(command, **passthrough):
    command = format_command(command)
    output = subprocess.check_output(command,
                                     universal_newlines=True,
                                     **passthrough).split('\n')
    for line in output:
        yield line


def run_subproc_background(command, **passthrough):
    command = format_command(command)
    try:
        proc = subprocess.Popen(command,
                                universal_newlines=True,
                                stdout=subprocess.PIPE,
                                **passthrough)
        while True:
            yield proc.stdout.readline()
    except Exception as e:
        logger.warn(e)
    finally:
        # make sure process exits
        proc.terminate()
        proc.wait()
        pass


def format_command(cmd):
    if not isinstance(cmd, (list, tuple)):  # no sets, as order matters
        cmd = shlex.split(cmd)
    return list(cmd)


def set_logger_config(level):
    """ set up logging according to the defined log level """
    # Get the root logger
    logger_obj = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger_obj.setLevel(level)
    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
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
    logging_handler_out.setFormatter(formatter)
    logger_obj.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logger_obj.addHandler(logging_handler_err)
    return logger_obj


def print_summary_info():
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

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)
    logger.debug(cli_data_block)


# def initialize_data_gathering(thread_number):
#     start_data_processing(thread_number)


def reset_metric_buffer():
    metric_buffer['buffer_key_list'] = []
    metric_buffer['buffer_ts_list'] = []
    metric_buffer['buffer_dict'] = {}

    metric_buffer['buffer_collected_list'] = []
    metric_buffer['buffer_collected_dict'] = {}


def reset_track():
    """ reset the track global for the next chunk """
    track['start_time'] = time.time()
    track['line_count'] = 0
    track['current_row'] = []


################################
# Functions to send data to IF #
################################
def data_chunks(metric_data, chunk_size):
    """ generate chunks of data from metric data """
    logger.debug(f"data_chunks chunk_size={chunk_size}")
    data_size = get_buffer_size(metric_data)
    chunks = data_size // chunk_size + 1
    num_msgs_per_chunk = max(1, len(metric_data) // chunks )
    for i in range(0, len(metric_data), num_msgs_per_chunk):
        yield(metric_data[i:i + num_msgs_per_chunk])

def send_data(metric_data):
    """ Send metric data dict to InsightFinder
    metric_data should be formatted as list of dicts
    """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = dict()
    # for backend so this is the camel case in to_send_data_dict
    to_send_data_dict["metricData"] = json.dumps(metric_data)
    to_send_data_dict["licenseKey"] = if_config_vars['license_key']
    to_send_data_dict["projectName"] = if_config_vars['project_name']
    to_send_data_dict["userName"] = if_config_vars['user_name']
    to_send_data_dict["agentType"] = "CUSTOM"

    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = if_config_vars['if_url'] + "/customprojectrawdata"
    send_data_to_receiver(post_url, to_send_data_json, len(metric_data))
    logger.info("-" * 40)
    logger.info(f"!!! packet of {len(metric_data)} items, size of {len(to_send_data_json)} bytes sent in {time.time() - send_data_time:8.4f} secs !!!")
    logger.info("-" * 40)


def send_data_to_receiver(post_url, to_send_data, num_of_message):
    MAX_RETRY_NUM = 3
    RETRY_WAIT_TIME_IN_SEC = 30
    logger.debug("send_data_to_receiver: url={}, data={}".format(post_url, to_send_data))
    attempts = 0
    while attempts < MAX_RETRY_NUM:
        response_code = -1
        attempts += 1
        try:
            response = requests.post(post_url, data=json.loads(to_send_data), verify=False)
            response_code = response.status_code
        except:
            print("Attempts: %d. Fail to send data, response code: %d wait %d sec to resend." % (
                attempts, response_code, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
            continue
        if response_code == 200:
            print("Data send successfully. Number of events: %d" % num_of_message)
            break
        else:
            print("Attempts: %d. Fail to send data, response code: %d wait %d sec to resend." % (
                attempts, response_code, RETRY_WAIT_TIME_IN_SEC))
            time.sleep(RETRY_WAIT_TIME_IN_SEC)
    if attempts == MAX_RETRY_NUM:
        sys.exit(1)


def get_data_type_from_project_type():
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


def get_insight_agent_type_from_project_type():
    if 'containerize' in agent_config_vars and agent_config_vars['containerize']:
        if is_replay():
            return 'containerReplay'
        else:
            return 'containerStreaming'
    elif is_replay():
        if 'METRIC' in if_config_vars['project_type']:
            return 'MetricFile'
        else:
            return 'LogFile'
    else:
        return 'Custom'


def get_agent_type_from_project_type():
    """ use project type to determine agent type """
    if 'METRIC' in if_config_vars['project_type']:
        if is_replay():
            return 'MetricFileReplay'
        else:
            return 'CUSTOM'
    elif is_replay():
        return 'LogFileReplay'
    else:
        return 'LogStreaming'
        # INCIDENT and DEPLOYMENT don't use this


def get_data_field_from_project_type():
    """ use project type to determine which field to place data in """
    # incident uses a different API endpoint
    if 'INCIDENT' in if_config_vars['project_type']:
        return 'incidentData'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'deploymentData'
    else:  # MERTIC, LOG, ALERT
        return 'metricData'


def get_api_from_project_type():
    """ use project type to determine which API to post to """
    # incident uses a different API endpoint
    if 'INCIDENT' in if_config_vars['project_type']:
        return 'incidentdatareceive'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'deploymentEventReceive'
    else:  # MERTIC, LOG, ALERT
        return 'customprojectrawdata'


def is_replay():
    return 'REPLAY' in if_config_vars['project_type']


def initialize_api_post_data():
    """ set up the unchanging portion of this """
    to_send_data_dict = dict()
    to_send_data_dict['userName'] = if_config_vars['user_name']
    to_send_data_dict['licenseKey'] = if_config_vars['license_key']
    to_send_data_dict['projectName'] = if_config_vars['project_name']
    to_send_data_dict['instanceName'] = HOSTNAME
    to_send_data_dict['agentType'] = get_agent_type_from_project_type()
    if 'METRIC' in if_config_vars['project_type'] and 'sampling_interval' in if_config_vars:
        to_send_data_dict['samplingInterval'] = str(if_config_vars['sampling_interval'])
    logger.debug(to_send_data_dict)
    return to_send_data_dict


if __name__ == "__main__":
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
    CSV_DELIM = ','
    ATTEMPTS = 3
    track = dict()
    metric_buffer = dict()

    # get config
    cli_config_vars = get_cli_config_vars()
    logger = set_logger_config(cli_config_vars['log_level'])
    if_config_vars = get_if_config_vars()
    agent_config_vars = get_agent_config_vars()
    print_summary_info()

    # start data processing
    start_data_processing()

#!/usr/bin/env python
import time
import sys
from optparse import OptionParser
import ConfigParser
import os
import requests
import json
import logging
import socket

METRICS_SET = "all_metrics_set"
FILTER_HOSTS = "filter_hosts"

'''
this script gathers system info from prometheus and use http api to send to server
'''


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-c", "--chunkSize",
                      action="store", dest="chunkSize", help="Metrics per chunk")
    parser.add_option("-l", "--logLevel",
                      action="store", dest="logLevel", help="Change log verbosity(WARNING: 0, INFO: 1, DEBUG: 2)")
    (options, args) = parser.parse_args()

    params = {}
    if options.serverUrl is None:
        params['serverUrl'] = 'https://app.insightfinder.com'
    else:
        params['serverUrl'] = options.serverUrl
    if options.chunkSize is None:
        params['chunkSize'] = 50
    else:
        params['chunkSize'] = int(options.chunkSize)
    params['logLevel'] = logging.INFO
    if options.logLevel == '0':
        params['logLevel'] = logging.WARNING
    elif options.logLevel == '1':
        params['logLevel'] = logging.INFO
    elif options.logLevel >= '2':
        params['logLevel'] = logging.DEBUG
    return params


def get_agent_config_vars():
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            user_name = config_parser.get('insightfinder', 'user_name')
            license_key = config_parser.get('insightfinder', 'license_key')
            project_name = config_parser.get('insightfinder', 'project_name')
            ssl_verification = config_parser.get('insightfinder', 'ssl_verify')
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        if len(user_name) == 0:
            logger.warning(
                "Agent not correctly configured(user_name). Check config file.")
            sys.exit(1)
        if len(license_key) == 0:
            logger.warning(
                "Agent not correctly configured(license_key). Check config file.")
            sys.exit(1)
        if len(project_name) == 0:
            logger.warning(
                "Agent not correctly configured(project_name). Check config file.")
            sys.exit(1)
        if len(ssl_verification) != 0 and (ssl_verification.lower() == 'false' or ssl_verification.lower() == 'f'):
            ssl_verification = False
        else:
            ssl_verification = True

        config_vars = {
            "userName": user_name,
            "licenseKey": license_key,
            "projectName": project_name,
            "sslSecurity": ssl_verification
        }

        return config_vars
    else:
        logger.error(
            "Agent not correctly configured. Check config file.")
        sys.exit(1)


def get_prometheus_config(_normalization_ids_map):
    """Read and parse Prometheus config from config.ini"""
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            all_metrics = config_parser.get('prometheus', 'all_metrics').split(",")
            normalization_ids = config_parser.get('prometheus', 'normalization_id').split(",")
            prometheus_url = config_parser.get('prometheus', 'prometheus_urls').split(",")
            filter_hosts = config_parser.get('prometheus', 'filter_hosts').split(",")
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        if len(normalization_ids[0]) != 0:
            for index in range(len(all_metrics)):
                metric = all_metrics[index]
                normalization_id = int(normalization_ids[index])
                if normalization_id > 1000:
                    logger.error("Please config the normalization_id between 0 to 1000.")
                    sys.exit(1)
                _normalization_ids_map[metric] = GROUPING_START + normalization_id
        if len(normalization_ids[0]) == 0:
            count = 1
            for index in range(len(all_metrics)):
                metric = all_metrics[index]
                _normalization_ids_map[metric] = GROUPING_START + count
                count += 1
        if len(filter_hosts[0]) == 0:
            filter_hosts = []

        prometheus_config = {
            METRICS_SET: all_metrics,
            PROMETHEUS_URLS: prometheus_url,
            FILTER_HOSTS: filter_hosts
        }
    else:
        logger.warning("No config file found. Using defaults.")
        prometheus_config = {
            PROMETHEUS_URLS: ["http://localhost:9200"]
        }

    return prometheus_config


def get_reporting_config_vars():
    reporting_config = {}
    with open(os.path.abspath(os.path.join(__file__, os.pardir, os.pardir, "reporting_config.json")), 'r') as f:
        config = json.load(f)
    reporting_interval_string = config['reporting_interval']
    if reporting_interval_string[-1:] == 's':
        reporting_interval = float(config['reporting_interval'][:-1])
        reporting_config['reporting_interval'] = float(reporting_interval / 60.0)
    else:
        reporting_config['reporting_interval'] = int(config['reporting_interval'])
        reporting_config['keep_file_days'] = int(config['keep_file_days'])
        reporting_config['prev_endtime'] = config['prev_endtime']
        reporting_config['deltaFields'] = config['delta_fields']

    reporting_config['keep_file_days'] = int(config['keep_file_days'])
    reporting_config['prev_endtime'] = config['prev_endtime']
    reporting_config['deltaFields'] = config['delta_fields']
    return reporting_config


def save_grouping(grouping):
    """
    Saves the grouping data to grouping.json
    :return: None
    """
    with open('grouping.json', 'w+') as f:
        f.write(json.dumps(grouping))


def load_grouping():
    if os.path.isfile('grouping.json'):
        logger.debug("Grouping file exists. Loading..")
        with open('grouping.json', 'r+') as f:
            try:
                grouping = json.loads(f.read())
            except ValueError:
                grouping = json.loads("{}")
                logger.debug("Error parsing grouping.json.")
    else:
        grouping = json.loads("{}")
    return grouping


def get_grouping_id(metric_key, normalization_ids_map):
    """
    Get grouping id for a metric key
    Parameters:
    - `metric_key` : metric key str to get group id.
    - `temp_id` : proposed group id integer
    """
    grouping_id = int(normalization_ids_map[metric_key])
    return grouping_id


def get_metric_list_from_file(config):
    """Get available metric list from File"""
    metric_list = set()
    with open(config['PROMETHEUS_METRICS_FILE'], 'r') as f:
        for line in f:
            if line:
                metric_list.add(line.replace('\n', ''))
        logger.debug("Get metric list from file: " + str(metric_list))
    return list(metric_list)


def get_metric_data(server_url, metric_list, end_time):
    """Get metric data from Prometheus API"""
    metric_datas = []
    try:
        for metric in metric_list:
            params = {
                "query": metric,
                "time": end_time,
            }
            if "http" not in server_url:
                url = "http://" + server_url + "/api/v1/query"
            else:
                url = server_url + "/api/v1/query"
                response = requests.get(url, params=params, verify=agent_config_vars['sslSecurity'])
                if response.status_code == 200:
                    res = response.json()
                    if res and res.get('status') == 'success':
                        datas = res.get('data', {}).get('result', [])
                        metric_datas.extend(datas)
        # change data to raw data api format:
        value_map = {
            'timestamp': str(end_time) + "000"
        }
        metric_data_all = []
        for log in metric_datas:
            host = log.get('metric').get('instance', '').split(':')[0]

            if host in prometheus_config[FILTER_HOSTS]:
                continue

            metric_name = log.get('metric').get('__name__')
            host_name = host
            header_field = metric_name + "[" + host_name + "]:" + str(
                get_grouping_id(metric_name, normalization_ids_map))
            value_list = log.get('value', [])
            if len(value_list) != 2:
                continue
            metric_value = value_list[1]
            value_map[header_field] = str(metric_value)
        metric_data_all.append(value_map)
    except requests.exceptions.ConnectionError:
        logger.error("Unable to connect to: " + url)
    except requests.exceptions.MissingSchema as e:
        logger.error("Missing Schema: " + str(e))
    except requests.exceptions.Timeout:
        logger.error("Timed out connecting to: " + url)
    except requests.exceptions.TooManyRedirects:
        logger.error("Too many redirects to: " + url)
    except ValueError:
        logger.error("Unable to parse result from: " + url)
    except requests.exceptions.RequestException as e:
        logger.error(str(e))
    return metric_data_all


def send_data(metric_data):
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = {"metric_data": json.dumps(metric_data),
                         "licenseKey": agent_config_vars['licenseKey'],
                         "projectName": agent_config_vars['projectName'],
                         "userName": agent_config_vars['userName'],
                         "instanceName": socket.gethostname().partition(".")[0],
                         "samplingInterval": str(int(reporting_config_vars['reporting_interval'] * 60)),
                         "agentType": "prometheus"}

    to_send_data_json = json.dumps(to_send_data_dict)
    logger.debug("TotalData: " +
                 str(len(bytearray(to_send_data_json))) + " Bytes")

    # send the data
    post_url = parameters['serverUrl'] + "/customprojectrawdata"
    response = requests.post(post_url, data=json.loads(to_send_data_json))
    if response.status_code == 200:
        logger.info(str(len(bytearray(to_send_data_json))) +
                    " bytes of data are reported.")
    else:
        logger.info("Failed to send data.")
    logger.debug("--- Send data time: %s seconds ---" %
                 (time.time() - send_data_time))


def chunks(list_to_split, size_of_each_chunk):
    """Yield successive size_of_each_chunk sized chunks from list_to_split."""
    for i in range(0, len(list_to_split), size_of_each_chunk):
        yield list_to_split[i:i + size_of_each_chunk]


def set_logger_config(level):
    """Set up logging according to the defined log level"""
    # Get the root logger
    logger_obj = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger_obj.setLevel(level)
    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
    # create a logging format
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(process)d - %(threadName)s - %(levelname)s - %(message)s')
    logging_handler_out.setFormatter(formatter)
    logger_obj.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logger_obj.addHandler(logging_handler_err)
    return logger_obj


if __name__ == "__main__":
    GROUPING_START = 15000
    PROMETHEUS_URLS = "prometheus_urls"
    normalization_ids_map = {}
    parameters = get_parameters()
    log_level = parameters['logLevel']
    logger = set_logger_config(log_level)
    agent_config_vars = get_agent_config_vars()
    reporting_config_vars = get_reporting_config_vars()

    # get agent configuration details
    prometheus_config = get_prometheus_config(normalization_ids_map)
    data_end_timestamp = int(time.time())

    try:
        logger.debug(
            "Collect metric data for timestamp: {}".format(data_end_timestamp))
        # get metric list from prometheus
        metric_list_all = list(prometheus_config["all_metrics_set"])
        if len(metric_list_all) == 0:
            logger.error("No metrics to get data for.")
            sys.exit()

        chunked_metric_list = chunks(metric_list_all, parameters['chunkSize'])
        for prometheus_server in prometheus_config["prometheus_urls"]:
            for sub_list in chunked_metric_list:
                # get metric data from prometheus every SAMPLING_INTERVAL
                metric_data_list = get_metric_data(
                    prometheus_server, sub_list, data_end_timestamp)
                if len(metric_data_list) == 0:
                    logger.error("No data for metrics received from Prometheus.")
                    sys.exit()
                # send metric data to insightfinder
                send_data(metric_data_list)

    except Exception as e:
        logger.error(
            "Error send metric data to insightfinder: {}".format(data_end_timestamp))
        logger.error(e)

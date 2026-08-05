import csv
import time
import json
import requests
import urllib3
import importlib
import sys
import copy
import arrow
import os
import pytz
import configparser

MAX_RETRY_NUM = 10
RETRY_WAIT_TIME_IN_SEC = 30
MAX_MESSAGE_LENGTH = 10000
MAX_DATA_SIZE = 4000000
MAX_PACKET_SIZE = 5000000

def get_agent_config_vars():
    config_vars = {}
    csv_vars = {}
    try:
        if os.path.exists(os.path.join(os.getcwd(), "config.ini")):
            parser = configparser.ConfigParser()
            parser.read(os.path.join(os.getcwd(), "config.ini"))
            file_name = parser.get('InsightFinder', 'file_name')
            license_key = parser.get('InsightFinder', 'insightFinder_license_key')
            project_name = parser.get('InsightFinder', 'insightFinder_project_name')
            user_name = parser.get('InsightFinder', 'insightFinder_user_name')
            server_url = parser.get('InsightFinder', 'insightFinder_server_url')
            http_proxy = parser.get('InsightFinder', 'http_proxy')
            https_proxy = parser.get('InsightFinder', 'https_proxy')

            if len(file_name) == 0:
                print("Agent not correctly configured(file name). Check config file.")
                sys.exit(1)
            if len(license_key) == 0:
                print("Agent not correctly configured(license key). Check config file.")
                sys.exit(1)
            if len(project_name) == 0:
                print("Agent not correctly configured(project name). Check config file.")
                sys.exit(1)
            if len(user_name) == 0:
                print("Agent not correctly configured(user name). Check config file.")
                sys.exit(1)
            if len(server_url) == 0:
                print("Agent not correctly configured(server url). Check config file.")
                sys.exit(1)

            # Proxies
            proxies = dict()
            if len(http_proxy) > 0:
                proxies['http'] = http_proxy
            if len(https_proxy) > 0:
                proxies['https'] = https_proxy
        
            config_vars['file_name'] = file_name
            config_vars['license_key'] = license_key
            config_vars['project_name'] = project_name
            config_vars['user_name'] = user_name
            config_vars['server_url'] = server_url
            config_vars['proxies'] = proxies            

            instance_field = parser.get('csv', 'instance_field')
            timestamp_field = parser.get('csv', 'timestamp_field')
            zone_field = parser.get('csv', 'zone_field')
            timestamp_format = parser.get('csv', 'timestamp_format')
            timestamp_timezone = parser.get('csv', 'timestamp_timezone') or 'UTC'
            omit_columns = parser.get('csv', 'omit_columns')
            data_format = (parser.get('csv', 'data_format', fallback='log') or 'log').strip().lower()

            if len(instance_field) == 0:
                print("Agent not correctly configured(file name). Check config file.")
                sys.exit(1)
            if len(timestamp_field) == 0:
                print("Agent not correctly configured(license key). Check config file.")
                sys.exit(1)
            if data_format not in ('log', 'metric'):
                config_error('data_format')

            try:
                omit_columns = omit_columns.split(',')
            except:
                config_error('omit_columns')

            if timestamp_timezone:
                if timestamp_timezone not in pytz.all_timezones:
                    config_error('timestamp_timezone')
                else:
                    timestamp_timezone = pytz.timezone(timestamp_timezone)

            csv_vars['instance_field'] = instance_field
            csv_vars['timestamp_field'] = timestamp_field
            csv_vars['zone_field'] = zone_field
            csv_vars['timestamp_format'] = timestamp_format
            csv_vars['timestamp_timezone'] = timestamp_timezone
            csv_vars['omit_columns'] = omit_columns
            csv_vars['data_format'] = data_format

    except IOError:
        print("config.ini file is missing")
    return config_vars,csv_vars

def config_error(setting=''):
    info = ' ({})'.format(setting) if setting else ''
    print('Agent not correctly configured{}. Check config file.'.format(info))
    sys.exit(1)

def parse_timestamp_ms(row, csv_vars):
    if len(csv_vars['timestamp_format']) == 0:
        timestamp = arrow.get(int(row[csv_vars['timestamp_field']]))
    else:
        timestamp = arrow.get(row[csv_vars['timestamp_field']], csv_vars['timestamp_format'], tzinfo=csv_vars['timestamp_timezone'])
    return timestamp.to(pytz.utc).timestamp() * 1000


def parse_json_field(field_value):
    """
    Attempts to parse a field value as JSON if it appears to be a JSON string.
    Returns the parsed JSON object if successful, otherwise returns the original string.
    """
    if isinstance(field_value, str):
        field_value = field_value.strip()
        if (field_value.startswith('{') and field_value.endswith('}')) or \
           (field_value.startswith('[') and field_value.endswith(']')):
            try:
                return json.loads(field_value)
            except json.JSONDecodeError:
                pass
    return field_value

def send_data(log_data):
    """ Sends parsed log data to InsightFinder """
    send_data_time = time.time()
    # prepare data for metric streaming agent
    to_send_data_dict = {"metricData": json.dumps(log_data),
                         "licenseKey": config_vars['license_key'],
                         "projectName": config_vars['project_name'],
                         "userName": config_vars['user_name'],
                         "agentType": "LogFileReplay"}
    to_send_data_json = json.dumps(to_send_data_dict)

    # send the data
    post_url = config_vars['server_url'] + "/api/v1/customprojectrawdata"
    send_data_to_receiver(post_url, to_send_data_json, len(log_data))
    print("--- Send data time: %s seconds ---" + str(time.time() - send_data_time))


def safe_string_to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def convert_to_metric_payload(chunk_metric_data):
    """ Mirrors convert_to_metric_data() in prometheus/getmessages_prometheus.py """
    instance_data_map = {}
    for entry in chunk_metric_data:
        instance_name = entry['instanceName']
        timestamp = entry['timestamp']
        metrics = entry['metrics']
        if not (metrics and timestamp and instance_name):
            continue
        if instance_name not in instance_data_map:
            instance_data_map[instance_name] = {'in': instance_name, 'cn': None, 'ct': None, 'dit': {}}
        instance_data_map[instance_name]['dit'][timestamp] = {'t': int(timestamp), 'm': metrics}

    return {
        "licenseKey": config_vars['license_key'],
        "userName": config_vars['user_name'],
        "data": {
            "projectName": config_vars['project_name'],
            "userName": config_vars['user_name'],
            "idm": instance_data_map,
        },
    }


def send_metric_data(chunk_metric_data):
    """ Sends parsed metric data to InsightFinder, same endpoint/shape as the prometheus agent's metric mode """
    send_data_time = time.time()
    payload = convert_to_metric_payload(chunk_metric_data)
    post_url = config_vars['server_url'] + "/api/v2/metric-data-receive"
    send_data_to_receiver(post_url, payload, len(chunk_metric_data), as_json=True)
    print("--- Send data time: %s seconds ---" + str(time.time() - send_data_time))


def send_data_to_receiver(post_url, to_send_data, num_of_message, as_json=False):
    attempts = 0
    while attempts < MAX_RETRY_NUM:
        packet_size = sys.getsizeof(to_send_data if isinstance(to_send_data, str) else json.dumps(to_send_data))
        if packet_size > MAX_PACKET_SIZE:
            print("Packet size too large %s.  Dropping packet." + str(packet_size))
            break
        response_code = -1
        attempts += 1
        try:
            if as_json:
                response = requests.post(post_url, json=to_send_data, proxies=config_vars['proxies'], verify=False)
            else:
                response = requests.post(post_url, data=json.loads(to_send_data), proxies=config_vars['proxies'], verify=False)
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

if __name__ == "__main__":
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    importlib.reload(sys)
    CHUNK_SIZE = 1000
    config_vars, csv_vars = get_agent_config_vars()
    omit = csv_vars['omit_columns']
    is_metric_mode = csv_vars['data_format'] == 'metric'
    send_func = send_metric_data if is_metric_mode else send_data
    non_metric_fields = {csv_vars['instance_field'], csv_vars['timestamp_field'], csv_vars['zone_field']}
    with open(config_vars['file_name'], encoding='utf-8') as csvfile:
        data = []
        count = 0
        size = 0
        reader = csv.DictReader(csvfile)
        for row in reader:
            timestamp_ms = parse_timestamp_ms(row, csv_vars)

            if is_metric_mode:
                metrics = []
                for header in row:
                    if header in omit or header in non_metric_fields:
                        continue
                    value = safe_string_to_float(row[header])
                    metrics.append({'m': header, 'v': value if value is not None else 0.0})
                new_entry = {
                    'instanceName': row[csv_vars['instance_field']],
                    'timestamp': timestamp_ms,
                    'metrics': metrics,
                }
            else:
                entry = {}
                entry['tag'] = row[csv_vars['instance_field']]

                # Extract zone name from csv field
                if csv_vars['zone_field'] and csv_vars['zone_field'] != "" and csv_vars['zone_field'] in row:
                    entry['zoneName'] = row[csv_vars['zone_field']]

                entry['eventId'] = timestamp_ms
                entry['data'] = {}
                for header in row:
                    if header not in omit:
                        # Parse potential JSON fields into Python objects
                        entry['data'][header] = parse_json_field(row[header])

                new_entry = copy.deepcopy(entry)

                # Check length of log message and truncate if too long
                if len(new_entry['data']) > MAX_MESSAGE_LENGTH:
                    new_entry['data'] = new_entry['data'][0:MAX_MESSAGE_LENGTH - 1]

            # Check size of entry and overall packet size
            entry_size = sys.getsizeof(json.dumps(new_entry))
            if size + entry_size >= MAX_DATA_SIZE:
                send_func(data)
                size = 0
                count = 0
                data = []

            # Add the entry to send
            data.append(new_entry)
            size += entry_size
            count += 1

            # Chunk number of entries
            if count >= CHUNK_SIZE:
                send_func(data)
                size = 0
                count = 0
                data = []
        if count != 0:
            send_func(data)


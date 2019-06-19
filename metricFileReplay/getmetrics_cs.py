#!/usr/bin/env python
import ConfigParser
import collections
import json
import logging
import os
import re
import socket
import sys
import time
import pytz
from optparse import OptionParser
from itertools import islice
from datetime import datetime
import dateutil
from dateutil.tz import tzlocal
import urlparse
import httplib
import requests

'''
This script gathers data to send to Insightfinder
'''


def start_data_processing():
    track['mode'] = 'METRICREPLAY'
    track['timestamp_format'] = 'epoch'

    # get a list of files as an array
    if len(agent_config_vars['directory']) != 0:
        files = get_file_list_for_directory(agent_config_vars['directory'])
    else:
        files = [agent_config_vars['file_path']]

    logger.debug('File list: ' + str(files))

    for file in files:
        logger.debug('Replaying file ' + str(file))
        read_data(file)
        if cli_config_vars['testing']:
            logger.debug('Skipping files:\n' + str(files[1:]))
            break


def read_data(filepath):
    with open(filepath) as metric_file:
        metric_json = json.load(metric_file)
        for metric_block in metric_json:
            metadata = parse_data_target(metric_block['target'])

            if should_filter_per_metadata(metadata):
                continue

            header = 'timestamp,' + metadata['type'] + '/' + metadata['unit'] + '/' + metadata['part']
            data = transpose_data(header, metric_block['datapoints'])
            parse_csv_metric_data(data, metadata['host'])


def transpose_data(header, data):
    csv = [header]
    for datapoint in data:
        csv.append(str(datapoint[1]) + ',' + str(datapoint[0]))
    return csv


def should_filter_per_metadata(metadata):
    for filter in agent_config_vars['filters']:
        if should_filter_per_config(filter, metadata[filter]):
            return True
    return False


def parse_data_target(target):
    target = target.split('.')
    return {
        'meta': target[0],
        'app': target[1],
        'region': target[2],
        'env': target[3],
        'os': target[4],
        'host': target[5],
        'type': target[6],
        'unit': target[7],
        'part': target[8]
    }


def get_agent_config_vars():
    """ Read and parse config.ini """
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini'))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini')))
        try:
            # fields to grab
            file_path = config_parser.get('agent', 'file_path')
            directory = config_parser.get('agent', 'directory')
            active_filters = config_parser.get('agent', 'active_filters')

            filters = dict()
            if len(active_filters) != 0:
                active_filters = active_filters.strip().split(',')
                for filter in active_filters:
                    objects = config_parser.get('agent', filter)
                    filters[filter] = objects.strip().split(',')

        except ConfigParser.NoOptionError:
            logger.error(
                'Agent not correctly configured. Check config file.')
            sys.exit(1)

        # defined required fields
        if len(file_path) == 0 and len(directory) == 0:
            logger.warning(
                'Agent not correctly configured (file_path/directory). Check config file.')
            exit()

        # add parsed variables to a global
        config_vars = {
            'file_path': file_path,
            'directory': directory,
            'filters': filters
        }

        return config_vars
    else:
        logger.warning('No config file found. Exiting...')
        exit()


########################
# Start of boilerplate #
########################
def get_if_config_vars():
    """ get config.ini vars """
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini'))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, 'config.ini')))
        try:
            user_name = config_parser.get('insightfinder', 'user_name')
            license_key = config_parser.get('insightfinder', 'license_key')
            project_name = config_parser.get('insightfinder', 'project_name')
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            chunk_size_kb = config_parser.get('insightfinder', 'chunk_size_kb')
            if_url = config_parser.get('insightfinder', 'url')
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
        except ConfigParser.NoOptionError:
            logger.error(
                'Agent not correctly configured. Check config file.')
            sys.exit(1)

        # check required variables
        if len(user_name) == 0:
            logger.warning(
                'Agent not correctly configured (user_name). Check config file.')
            sys.exit(1)
        if len(license_key) == 0:
            logger.warning(
                'Agent not correctly configured (license_key). Check config file.')
            sys.exit(1)
        if len(project_name) == 0:
            logger.warning(
                'Agent not correctly configured (project_name). Check config file.')
            sys.exit(1)
        # TODO: comment out if not a metric project
        #"""
        if len(sampling_interval) == 0:
            logger.warning(
                'Agent not correctly configured (sampling_interval). Check config file.')
            sys.exit(1)

        if sampling_interval.endswith('s'):
            sampling_interval = int(sampling_interval[:-1])
        else:
            sampling_interval = int(sampling_interval) * 60
        #"""

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
            'userName': user_name,
            'licenseKey': license_key,
            'projectName': project_name,
            'samplingInterval': int(sampling_interval),     # as seconds
            'chunkSize': int(chunk_size_kb) * 1024,         # as bytes
            'ifURL': if_url,
            'ifProxies': if_proxies
        }

        return config_vars
    else:
        logger.error(
            'Agent not correctly configured. Check config file.')
        sys.exit(1)


def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    parser.add_option('--tz', default='UTC',
                      action='store', dest='time_zone', help='Timezone of the data. See pytz.all_timezones')
    parser.add_option('-q', '--quiet',
                      action='store_true', dest='quiet', help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose',
                      action='store_true', dest='verbose', help='Enable verbose logging')
    parser.add_option('-t', '--testing',
                      action='store_true', dest='testing', help='Set to testing mode (do not send data).' +
                                                                ' Automatically turns on verbose logging')
    (options, args) = parser.parse_args()

    config_vars = dict()
    config_vars['testing'] = False
    if options.testing:
        config_vars['testing'] = True

    config_vars['logLevel'] = logging.INFO
    if options.verbose or options.testing:
        config_vars['logLevel'] = logging.DEBUG
    elif options.quiet:
        config_vars['logLevel'] = logging.WARNING

    if len(options.time_zone) != 0 and options.time_zone in pytz.all_timezones:
        config_vars['time_zone'] = pytz.timezone(options.time_zone)
    else:
        config_vars['time_zone'] = pytz.utc

    return config_vars


def should_filter_per_config(setting, value):
    """ determine if an agent config filter setting would exclude a given value """
    return len(agent_config_vars[setting]) != 0 and value not in agent_config_vars[setting]


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    return len(bytearray(json.dumps(json_data)))


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for index in xrange(0, len(l), n):
        yield l[index:index + n]


def chunk_map(data, SIZE=50):
    """Yield successive n-sized chunks from l."""
    it = iter(data)
    for i in xrange(0, len(data), SIZE):
        yield {k: data[k] for k in islice(it, SIZE)}


def get_file_list_for_directory(root_path):
    file_list = []
    for path, subdirs, files in os.walk(root_path):
        for name in files:
            file_list.append(os.path.join(path, name))
    return file_list


def get_timestamp_from_date_string(date_string):
    """ parse a date string into unix epoch (ms) """

    if 'timestamp_format' in track:
        if track['timestamp_format'] == 'epoch':
            timestamp_datetime = get_datetime_from_unix_epoch(date_string)
        else:
            timestamp_datetime = datetime.strptime(date_string, track['timestamp_format'])
    else:
        try:
            timestamp_datetime = dateutil.parse.parse(date_string)
        except e:
            timestamp_datetime = get_datetime_from_unix_epoch(date_string)
            track['timestamp_format'] = 'epoch'

    timestamp_localize = cli_config_vars['time_zone'].localize(timestamp_datetime)

    epoch = long((timestamp_localize - datetime(1970, 1, 1, tzinfo=pytz.utc)).total_seconds()) * 1000
    return epoch


def get_datetime_from_unix_epoch(date_string):
    try:
        # strip leading whitespace and zeros
        epoch = date_string.lstrip(' 0')
        # roughly check for a timestamp between ~1973 - ~2286
        if len(epoch) in range(13, 15):
            epoch = int(epoch) / 1000
        elif len(epoch) in range(9, 12):
            epoch = int(epoch)

        return datetime.fromtimestamp(epoch)
    except ValueError:
        # if the date cannot be converted into a number by built-in long()
        logger.warn('Date format not defined & data does not look like unix epoch: ' + date_string)
        sys.exit(1)


def make_safe_instance_string(instance, device=''):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', instance)
    # if there's a device, concatenate it to the instance with an underscore
    if len(device) != 0:
        instance += '_' + make_safe_instance_string(device)
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
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(process)d - %(threadName)s - %(levelname)s - %(message)s')
    logging_handler_out.setFormatter(formatter)
    logger_obj.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logger_obj.addHandler(logging_handler_err)
    return logger_obj


def print_summary_info():
    # info to be sent to IF
    post_data_block = '\nIF settings:'
    for i in if_config_vars.keys():
        post_data_block += '\n\t' + i + ': ' + str(if_config_vars[i])
    logger.debug(post_data_block)

    # variables from agent-specific config
    agent_data_block = '\nAgent settings:'
    for j in agent_config_vars.keys():
        agent_data_block += '\n\t' + j + ': ' + str(agent_config_vars[j])
    logger.debug(agent_data_block)

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for k in cli_config_vars.keys():
        cli_data_block += '\n\t' + k + ': ' + str(cli_config_vars[k])
    logger.debug(cli_data_block)


def initialize_data_gathering():
    reset_track()
    track['chunk_count'] = 0
    track['entry_count'] = 0

    start_data_processing()

    # last chunk
    if len(track['current_row']) > 0 or len(track['current_dict']) > 0:
        logger.debug('Sending last chunk')
        send_data_wrapper()

    logger.debug('Total chunks created: ' + str(track['chunk_count']))
    logger.debug('Total ' + track['mode'].lower() + ' entries: ' + str(track['entry_count']))


def reset_track():
    """ reset the track global for the next chunk """
    track['start_time'] = time.time()
    track['line_count'] = 0
    track['current_row'] = []
    track['current_dict'] = dict()


#########################################
# Functions to handle Log/Incident data #
#########################################
def log_handoff(timestamp, instance, data):
    entry = prepare_log_entry(timestamp, instance, data)
    track['current_row'].append(entry)
    track['line_count'] += 1
    track['entry_count'] += 1
    if get_json_size_bytes(track['current_row']) >= if_config_vars['chunkSize']:
        send_data_wrapper()
    elif track['entry_count'] % 100 == 0:
        logger.debug('Current data object size: ' + str(get_json_size_bytes(track['current_row'])) + ' bytes')


def prepare_log_entry(timestamp, instance, data):
    """ creates the log entry """
    entry = dict()
    entry['data'] = data
    if 'INCIDENT' in track['mode'].upper():
        entry['timestamp'] = timestamp
        entry['instanceName'] = instance
    else:
        entry['eventId'] = timestamp
        entry['tag'] = instance
    return entry


###################################
# Functions to handle Metric data #
###################################
def metric_handoff(timestamp, field_name, data, instance, device=''):
    append_metric_data_to_entry(timestamp, field_name, data, instance, device)
    track['entry_count'] += 1
    if get_json_size_bytes(track['current_dict']) >= if_config_vars['chunkSize']:
        send_data_wrapper()
    elif track['entry_count'] % 500 == 0:
        logger.debug('Current data object size: ' + str(get_json_size_bytes(track['current_dict'])) + ' bytes')


def append_metric_data_to_entry(timestamp, field_name, data, instance, device=''):
    """ creates the metric entry """
    key = make_safe_metric_key(field_name) + '[' + make_safe_instance_string(instance, device) + ']'
    ts_str = str(timestamp)
    if ts_str not in track['current_dict']:
        track['current_dict'][ts_str] = dict()
    current_obj = track['current_dict'][ts_str]

    # use the next non-null value to overwrite the prev value
    # for the same metric in the same timestamp
    if key in current_obj.keys():
        if data is not None and len(str(data)) > 0:
            current_obj[key] += '|' + str(data)
    else:
        current_obj[key] = str(data)
    track['current_dict'][ts_str] = current_obj


def transpose_metrics():
    """ flatten data up to the timestamp"""
    for timestamp in track['current_dict'].keys():
        track['line_count'] += 1
        new_row = dict()
        new_row['timestamp'] = timestamp
        for key in track['current_dict'][timestamp]:
            value = track['current_dict'][timestamp][key]
            if '|' in value:
                value = median(map(lambda v: int(v), value.split('|')))
            new_row[key] = str(value)
        track['current_row'].append(new_row)


def parse_csv_metric_data(csv_data, instance, device=''):
    """
    parses CSV data, assuming the format is given as:
        header row:  timestamp,field_1,field_2,...,field_n
        n data rows: TIMESTAMP,value_1,value_2,...,value_n
    """

    # get field names from header row
    field_names = csv_data.pop(0).split(',')[1:]

    # go through each row
    for row in csv_data:
        if len(row) == 0:
            continue
        row = row.split(',')
        timestamp = get_timestamp_from_date_string(row.pop(0))
        for i in range(len(row)):
            metric_handoff(timestamp, field_names[i], row[i], instance, device)


################################
# Functions to send data to IF #
################################
def send_data_wrapper():
    """ wrapper to send data """
    if 'METRIC' in track['mode'].upper():
        transpose_metrics()
        logger.debug(track['current_row'])
    logger.debug('--- Chunk creation time: %s seconds ---' % round(time.time() - track['start_time'], 2))
    send_data_to_if(track['current_row'])
    track['chunk_count'] += 1
    reset_track()


def send_data_to_if(chunk_metric_data):
    send_data_time = time.time()

    # prepare data for metric streaming agent
    data_to_post = initialize_api_post_data()
    data_to_post['metricData'] = json.dumps(chunk_metric_data)

    logger.debug('First:\n' + str(chunk_metric_data[0]))
    logger.debug('Last:\n' + str(chunk_metric_data[-1]))
    logger.debug('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
    logger.debug('Total Lines: ' + str(track['line_count']))

    # do not send if only testing
    if cli_config_vars['testing']:
        return

    # send the data
    post_url = urlparse.urljoin(if_config_vars['ifURL'], get_api_from_mode())
    send_request(post_url, 'POST', 'Could not send request to IF',
                 str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.',
                 data=data_to_post, proxies=if_config_vars['ifProxies'])
    logger.debug('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def send_request(url, mode='GET', failure_message='Failure!', success_message='Success!', **request_passthrough):
    """ sends a request to the given url """
    # determine if post or get (default)
    req = requests.get
    if mode.upper() == 'POST':
        req = requests.post

    for _ in xrange(ATTEMPTS):
        try:
            response = req(url, **request_passthrough)
            if response.status_code == httplib.OK:
                logger.info(success_message)
                return response
            else:
                logger.warn(failure_message)
                logger.debug('Response Code: ' + str(response.status_code) + '\n' +
                             'TEXT: ' + str(response.text))
        # handle various exceptions
        except requests.exceptions.Timeout:
            logger.exception(
                'Timed out. Reattempting...')
            continue
        except requests.exceptions.TooManyRedirects:
            logger.exception(
                'Too many redirects.')
            break
        except requests.exceptions.RequestException as e:
            logger.exception(
                'Exception ' + str(e))
            break

    logger.error(
        'Failed! Gave up after %d attempts.', ATTEMPTS)
    return -1


def get_agent_type_from_mode():
    """ use mode to determine agent type """
    if 'METRIC' in track['mode'].upper():
        if 'REPLAY' in track['mode'].upper():
            return 'MetricFileReplay'
        else:
            return 'CUSTOM'
    elif 'REPLAY' in track['mode'].upper():
        return 'LogFileReplay'
    else:
        return 'LogStreaming'


def get_api_from_mode():
    """ use mode to determine which API to post to """
    # incident uses a different API endpoint
    if 'INCIDENT' in track['mode'].upper():
        return 'incidentdatareceive'
    else:
        return 'customprojectrawdata'


def initialize_api_post_data():
    """ set up the unchanging portion of this """
    to_send_data_dict = dict()
    to_send_data_dict['userName'] = if_config_vars['userName']
    to_send_data_dict['licenseKey'] = if_config_vars['licenseKey']
    to_send_data_dict['projectName'] = if_config_vars['projectName']
    to_send_data_dict['instanceName'] = socket.gethostname().partition('.')[0]
    to_send_data_dict['agentType'] = get_agent_type_from_mode()
    if 'METRIC' in track['mode'].upper() and 'samplingInterval' in if_config_vars:
        to_send_data_dict['samplingInterval'] = str(if_config_vars['samplingInterval'])
    return to_send_data_dict


if __name__ == "__main__":
    # declare a few vars
    SPACES = re.compile(r"\s+")
    SLASHES = re.compile(r"\/+")
    UNDERSCORE = re.compile(r"\_+")
    LEFT_BRACE = re.compile(r"\[")
    RIGHT_BRACE = re.compile(r"\]")
    PERIOD = re.compile(r"\.")
    NON_ALNUM = re.compile(r"[^a-zA-Z0-9]")
    ATTEMPTS = 3
    track = dict()

    # get config
    cli_config_vars = get_cli_config_vars()
    logger = set_logger_config(cli_config_vars['logLevel'])
    if_config_vars = get_if_config_vars()
    agent_config_vars = get_agent_config_vars()
    print_summary_info()

    # start data processing
    initialize_data_gathering()

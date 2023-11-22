import configparser
import http.client
import json
import logging
import os
import shlex
import socket
import sys
import time
import traceback
import urllib.parse
from optparse import OptionParser
from sys import getsizeof

import arrow
import pytz
import regex
import requests
from pyzabbix import ZabbixAPI

LOG_GET_INTERVAL = 60

"""
This script gathers data to send to Insightfinder
"""


def start_data_processing(data_type):
    logger.info('Starting fetch {} items......'.format(data_type))

    # Create ZabbixAPI class instance
    zabbix_config = agent_config_vars['zabbix_kwargs']
    zabbix_url = zabbix_config['url']
    zabbix_user = zabbix_config['user']
    zabbix_password = zabbix_config['password']
    zapi = ZabbixAPI(server=zabbix_url)
    zapi.login(user=zabbix_user, password=zabbix_password)
    logger.info("Connected to Zabbix API Version %s" % zapi.api_version())

    # get host groups
    host_groups_map = {}
    host_groups_ids = []

    if len(agent_config_vars['host_groups']) == 0:
        logger.info("Query all host_groups")
        host_groups_req_params = {'output': 'extend'}
    else:
        host_groups_req_params = {'output': 'extend', 'filter': {"name": agent_config_vars['host_groups']}}

    host_groups_res = zapi.do_request('hostgroup.get', host_groups_req_params)
    for item in host_groups_res['result']:
        group_id = item['groupid']
        name = item['name']
        host_groups_ids.append(group_id)
        host_groups_map[group_id] = name
    logger.info("Zabbix host groups: %s" % json.dumps(host_groups_map))

    # get hosts
    hosts_map = {}
    hosts_group_map = {}
    hosts_ids = []
    hosts_res = zapi.do_request('host.get',
                                {'output': 'extend', 'groupids': host_groups_ids, 'selectHostGroups': 'extend',
                                 'filter': {"host": agent_config_vars['hosts']}, })
    for item in hosts_res['result']:
        host_id = item['hostid']
        name = item['name']
        hostgroups = item.get('hostgroups') or []
        host_group = hostgroups[len(hostgroups) - 1].get('name') or ''
        hosts_ids.append(host_id)

        hosts_map[host_id] = name
        hosts_group_map[host_id] = host_group

    logger.info("Zabbix hosts: %s, hostGroups: %s" % (hosts_map, hosts_group_map))
    if len(hosts_ids) == 0:
        logger.error('Hosts list is empty')
        sys.exit(1)

    # value_type: 0 - FLOAT 1 - CHAR 2 - LOG 3 - UNSIGNED(default)
    value_type_list = ['0', '3'] if data_type == 'Metric' else ['2']
    history_type = 0 if data_type == 'Metric' else 2

    items_map = {}
    items_ids = []

    # get data by hosts/applications
    items_res = zapi.do_request('item.get', {'output': 'extend', 'groupids': host_groups_ids, "hostids": hosts_ids,
                                             'filter': {'value_type': value_type_list}})

    for item in items_res['result']:
        item_id = item['itemid']
        items_ids.append(item_id)
        items_map[item_id] = item

    if len(items_ids) == 0:
        logger.error('Item list is empty')
        sys.exit(1)

    logger.info("Zabbix item ids: %s" % items_ids)

    # build map by item field
    all_field_map = {'hostid': hosts_map, 'hostgroup': hosts_group_map}

    # if it's streaming with log type, use history.get api
    if agent_config_vars['his_time_range']:
        logger.debug('Using time range for replay data: {}'.format(agent_config_vars['his_time_range']))
        for timestamp in range(agent_config_vars['his_time_range'][0], agent_config_vars['his_time_range'][1],
                               if_config_vars['sampling_interval']):
            history_res = zapi.do_request('history.get',
                                          {'output': 'extend', "history": history_type, "hostids": hosts_ids,
                                           "itemids": items_ids, 'time_from': timestamp,
                                           'time_till': timestamp + if_config_vars['sampling_interval'], })
            parse_messages_zabbix(data_type, history_res['result'], all_field_map, items_map, 'history')

            # clear data buffer when piece of time range end
            clear_data_buffer()
    else:
        logger.debug('Using current time for streaming data')
        if data_type != 'Metric':
            timestamp_end = int(arrow.now().floor('second').timestamp())
            timestamp_start = timestamp_end - if_config_vars["run_interval"]
            for timestamp in range(timestamp_start, timestamp_end, LOG_GET_INTERVAL):
                history_res = zapi.do_request('history.get',
                                              {'output': 'extend', "history": history_type, "hostids": hosts_ids,
                                               "itemids": items_ids, 'time_from': timestamp,
                                               'time_till': timestamp + if_config_vars['sampling_interval'], })
                parse_messages_zabbix(data_type, history_res['result'], all_field_map, items_map, 'history')
                # clear data buffer when piece of time range end
                clear_data_buffer()
        else:
            parse_messages_zabbix(data_type, items_res['result'], all_field_map, items_map, 'live')
            # clear data buffer when piece of time range end
            clear_data_buffer()

    logger.info('Closed......')


def parse_messages_zabbix(data_type, result, all_field_map, items_map, replay_type):
    count = 0
    logger.info('Reading {} messages'.format(len(result)))
    is_metric = True if data_type == 'Metric' else False

    for message in result:
        try:
            logger.debug('Message received')
            logger.debug(message)

            item_id = message['itemid']
            if not items_map.get(item_id):
                continue

            # set instance and device
            instance_field = agent_config_vars['instance_field'][0] if agent_config_vars['instance_field'] and len(
                agent_config_vars['instance_field']) > 0 else 'hostid'
            instance_id = items_map.get(item_id).get(instance_field)
            instance = all_field_map.get(instance_field).get(instance_id)

            # set component
            component_field = 'hostgroup'
            component = None
            if all_field_map.get(component_field):
                component = all_field_map.get(component_field).get(instance_id)

            # add device info if has
            device = None
            device_field = agent_config_vars['device_field']
            if device_field and len(device_field) > 0:
                device_field = agent_config_vars['device_field'][0]
                device_id = items_map.get(item_id).get(device_field)
                device = all_field_map.get(device_field).get(device_id)
            full_instance = make_safe_instance_string(instance, device)

            # set timestamp
            clock = message['lastclock'] if replay_type == 'live' else message['clock']
            timestamp = int(clock) * 1000
            if timestamp == 0:
                continue

            # set data field and value
            data_field = items_map[item_id]['name']
            data_field = make_safe_data_key(data_field)
            data_value = message['lastvalue'] if replay_type == 'live' else message['value']

            # set offset for timestamp
            timestamp += agent_config_vars['target_timestamp_timezone'] * 1000
            timestamp = str(timestamp)

            key = '{}-{}'.format(timestamp, full_instance)
            if key not in data_buffer['buffer_dict']:
                data_buffer['buffer_dict'][key] = {"timestamp": timestamp}

            if is_metric:
                data_key = '{}[{}]'.format(data_field, full_instance)
                data_buffer['buffer_dict'][key][data_key] = str(data_value)
            else:
                data_buffer['buffer_dict'][key]['tag'] = full_instance
                if component:
                    data_buffer['buffer_dict'][key]['componentName'] = component
                data_buffer['buffer_dict'][key]['data'] = str(data_value)

        except Exception as e:
            logger.warn('Error when parsing message')
            logger.warn(e)
            logger.debug(traceback.format_exc())
            continue

        track['entry_count'] += 1
        count += 1
        if count % 1000 == 0:
            logger.info('Parse {0} messages'.format(count))
    logger.info('Parse {0} messages'.format(count))


def get_agent_config_vars():
    """ Read and parse config.ini """
    config_ini = config_ini_path()
    if os.path.exists(config_ini):
        config_parser = configparser.ConfigParser()
        config_parser.read(config_ini)

        zabbix_kwargs = {}
        host_groups = None
        hosts = None
        applications = None
        his_time_range = None
        try:
            # zabbix settings
            zabbix_config = {}

            # only keep settings with values
            zabbix_kwargs = {k: v for (k, v) in list(zabbix_config.items()) if v}

            # handle boolean setting

            # handle required arrays
            if len(config_parser.get('zabbix', 'url')) != 0:
                zabbix_kwargs['url'] = config_parser.get('zabbix', 'url')
            else:
                config_error('url')
            if len(config_parser.get('zabbix', 'user')) != 0:
                zabbix_kwargs['user'] = config_parser.get('zabbix', 'user')
            else:
                config_error('user')
            if len(config_parser.get('zabbix', 'password')) != 0:
                zabbix_kwargs['password'] = config_parser.get('zabbix', 'password')
            else:
                config_error('password')

            # metrics
            host_groups = config_parser.get('zabbix', 'host_groups')
            hosts = config_parser.get('zabbix', 'hosts')
            applications = config_parser.get('zabbix', 'applications')

            # time range
            his_time_range = config_parser.get('zabbix', 'his_time_range')

            # proxies
            agent_http_proxy = config_parser.get('zabbix', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('zabbix', 'agent_https_proxy')

            # message parsing
            data_format = config_parser.get('zabbix', 'data_format').upper()
            # project_field = config_parser.get('agent', 'project_field', raw=True)
            instance_field = config_parser.get('zabbix', 'instance_field', raw=True)
            device_field = config_parser.get('zabbix', 'device_field', raw=True)
            timestamp_field = config_parser.get('zabbix', 'timestamp_field', raw=True) or 'timestamp'
            target_timestamp_timezone = config_parser.get('zabbix', 'target_timestamp_timezone', raw=True) or 'UTC'
            timestamp_format = config_parser.get('zabbix', 'timestamp_format', raw=True)
            timezone = config_parser.get('zabbix', 'timezone') or 'UTC'
            data_fields = config_parser.get('zabbix', 'data_fields', raw=True)

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error()

        # host_groups
        if len(host_groups) != 0:
            host_groups = [x for x in host_groups.split(',') if x.strip()]
        if len(hosts) != 0:
            hosts = [x for x in hosts.split(',') if x.strip()]
        if len(applications) != 0:
            applications = [x for x in applications.split(',') if x.strip()]

        if len(his_time_range) != 0:
            his_time_range = [x for x in his_time_range.split(',') if x.strip()]
            his_time_range = [int(arrow.get(x).float_timestamp) for x in his_time_range]

        if len(target_timestamp_timezone) != 0:
            target_timestamp_timezone = int(arrow.now(target_timestamp_timezone).utcoffset().total_seconds())
        else:
            config_error('target_timestamp_timezone')

        if timezone:
            if timezone not in pytz.all_timezones:
                config_error('timezone')
            else:
                timezone = pytz.timezone(timezone)

        # data format
        if data_format in {'JSON', 'JSONTAIL', 'AVRO', 'XML'}:
            pass
        else:
            config_error('data_format')

        # proxies
        agent_proxies = dict()
        if len(agent_http_proxy) > 0:
            agent_proxies['http'] = agent_http_proxy
        if len(agent_https_proxy) > 0:
            agent_proxies['https'] = agent_https_proxy

        # fields
        # project_fields = project_field.split(',')
        instance_fields = [x for x in instance_field.split(',') if x.strip()]
        device_fields = [x for x in device_field.split(',') if x.strip()]
        timestamp_fields = timestamp_field.split(',')
        if len(data_fields) != 0:
            data_fields = data_fields.split(',')
            # for project_field in project_fields:
            #   if project_field in data_fields:
            #       data_fields.pop(data_fields.index(project_field))
            for instance_field in instance_fields:
                if instance_field in data_fields:
                    data_fields.pop(data_fields.index(instance_field))
            for device_field in device_fields:
                if device_field in data_fields:
                    data_fields.pop(data_fields.index(device_field))
            for timestamp_field in timestamp_fields:
                if timestamp_field in data_fields:
                    data_fields.pop(data_fields.index(timestamp_field))

        # add parsed variables to a global
        config_vars = {'zabbix_kwargs': zabbix_kwargs, 'host_groups': host_groups, 'hosts': hosts,
                       'applications': applications, 'his_time_range': his_time_range,

                       'proxies': agent_proxies, 'data_format': data_format,  # 'project_field': project_fields,
                       'instance_field': instance_fields, 'device_field': device_fields, 'data_fields': data_fields,
                       'timestamp_field': timestamp_fields, 'target_timestamp_timezone': target_timestamp_timezone,
                       'timezone': timezone, 'timestamp_format': timestamp_format, }

        return config_vars
    else:
        config_error_no_config()


#########################
#   START_BOILERPLATE   #
#########################
def get_if_config_vars():
    """ get config.ini vars """
    config_ini = config_ini_path()
    if os.path.exists(config_ini):
        config_parser = configparser.ConfigParser()
        config_parser.read(config_ini)
        try:
            user_name = config_parser.get('insightfinder', 'user_name')
            license_key = config_parser.get('insightfinder', 'license_key')
            token = config_parser.get('insightfinder', 'token')
            project_name = config_parser.get('insightfinder', 'project_name')
            system_name = config_parser.get('insightfinder', 'system_name')
            project_type = config_parser.get('insightfinder', 'project_type').upper()
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            run_interval = config_parser.get('insightfinder', 'run_interval')
            chunk_size_kb = config_parser.get('insightfinder', 'chunk_size_kb')
            if_url = config_parser.get('insightfinder', 'if_url')
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error()

        # check required variables
        if len(user_name) == 0:
            return config_error('user_name')
        if len(license_key) == 0:
            return config_error('license_key')
        if len(project_name) == 0:
            return config_error('project_name')
        if len(project_type) == 0:
            return config_error('project_type')

        if project_type not in {'METRIC', 'METRICREPLAY', 'LOG', 'LOGREPLAY', 'INCIDENT', 'INCIDENTREPLAY', 'ALERT',
                                'ALERTREPLAY', 'DEPLOYMENT', 'DEPLOYMENTREPLAY'}:
            return config_error('project_type')

        is_replay = 'REPLAY' in project_type

        if len(sampling_interval) == 0:
            if 'METRIC' in project_type:
                return config_error('sampling_interval')
            else:
                # set default for non-metric
                sampling_interval = 10

        if sampling_interval.endswith('s'):
            sampling_interval = int(sampling_interval[:-1])
        else:
            sampling_interval = int(sampling_interval) * 60

        if len(run_interval) == 0:
            return config_error('run_interval')

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

        config_vars = {'user_name': user_name, 'license_key': license_key, 'token': token, 'project_name': project_name,
                       'system_name': system_name, 'project_type': project_type,
                       'sampling_interval': int(sampling_interval),  # as seconds
                       'run_interval': int(run_interval),  # as seconds
                       'chunk_size': int(chunk_size_kb) * 1024,  # as bytes
                       'if_url': if_url, 'if_proxies': if_proxies, 'is_replay': is_replay, }

        return config_vars
    else:
        config_error_no_config()


def config_ini_path():
    return abs_path_from_cur(cli_config_vars['config'])


def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))


def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    """
    ## not ready.
    parser.add_option('--threads', default=1, action='store', dest='threads',
                      help='Number of threads to run')
    """
    parser.add_option('-c', '--config', action='store', dest='config', default=abs_path_from_cur('config.ini'),
                      help='Path to the config file to use. Defaults to {}'.format(abs_path_from_cur('config.ini')))
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data).' + ' Automatically turns on verbose logging')
    (options, args) = parser.parse_args()

    """
    # not ready
    try:
        threads = int(options.threads)
    except ValueError:
        threads = 1
    """

    config_vars = {'config': options.config if os.path.isfile(options.config) else abs_path_from_cur('config.ini'),
                   'threads': 1, 'testing': False, 'log_level': logging.INFO}

    if options.testing:
        config_vars['testing'] = True

    if options.verbose:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING

    return config_vars


def config_error(setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(info))
    return False


def config_error_no_config():
    logger.error('No config file found. Exiting...')
    sys.exit(1)


def get_json_size_bytes(json_data):
    """ get size of json object in bytes """
    # return len(bytearray(json.dumps(json_data)))
    return getsizeof(json.dumps(json_data))


def make_safe_instance_string(instance, device=''):
    """ make a safe instance name string, concatenated with device if appropriate """
    # strip underscores
    instance = UNDERSCORE.sub('.', instance)
    instance = COLONS.sub('-', instance)
    # if there's a device, concatenate it to the instance with an underscore
    if device:
        instance = '{}_{}'.format(make_safe_instance_string(device), instance)
    return instance


def make_safe_data_key(metric):
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
        '{ts} [pid {pid}] {lvl} {mod}.{func}():{line} {msg}'.format(ts='%(asctime)s', pid='%(process)d',
                                                                    lvl='%(levelname)-8s', mod='%(module)s',
                                                                    func='%(funcName)s', line='%(lineno)d',
                                                                    msg='%(message)s'), ISO8601[0])
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


def initialize_data_gathering():
    data_type = get_data_type_from_project_type()

    reset_data_buffer()
    reset_track()
    track['chunk_count'] = 0
    track['entry_count'] = 0

    start_data_processing(data_type)

    # clear data buffer when data processing end
    clear_data_buffer()

    logger.info('Total chunks created: ' + str(track['chunk_count']))
    logger.info('Total {} entries: {}'.format(if_config_vars['project_type'].lower(), track['entry_count']))


def clear_data_buffer():
    # move all buffer data to current data, and send
    buffer_values = list(data_buffer['buffer_dict'].values())

    count = 0
    for row in buffer_values:
        track['current_row'].append(row)
        count += 1
        if count % 1000 == 0 or get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
            logger.debug('Sending buffer chunk')
            send_data_wrapper()

    # last chunk
    if len(track['current_row']) > 0:
        logger.debug('Sending last chunk')
        send_data_wrapper()

    reset_data_buffer()


def reset_data_buffer():
    data_buffer['buffer_key_list'] = []
    data_buffer['buffer_ts_list'] = []
    data_buffer['buffer_dict'] = {}

    data_buffer['buffer_collected_list'] = []
    data_buffer['buffer_collected_dict'] = {}


def reset_track():
    """ reset the track global for the next chunk """
    track['start_time'] = time.time()
    track['line_count'] = 0
    track['current_row'] = []


################################
# Functions to send data to IF #
################################
def send_data_wrapper():
    """ wrapper to send data """
    logger.debug('--- Chunk creation time: {} seconds ---'.format(round(time.time() - track['start_time'], 2)))
    send_data_to_if(track['current_row'])
    track['chunk_count'] += 1
    reset_track()


def send_data_to_if(chunk_metric_data):
    send_data_time = time.time()

    # prepare data for metric streaming agent
    data_to_post = initialize_api_post_data()
    if 'DEPLOYMENT' in if_config_vars['project_type'] or 'INCIDENT' in if_config_vars['project_type']:
        for chunk in chunk_metric_data:
            chunk['data'] = json.dumps(chunk['data'])
    data_to_post[get_data_field_from_project_type()] = json.dumps(chunk_metric_data)

    logger.debug('First:\n' + str(chunk_metric_data[0]))
    logger.debug('Last:\n' + str(chunk_metric_data[-1]))
    logger.info('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
    logger.info('Total Lines: ' + str(track['line_count']))

    # do not send if only testing
    if cli_config_vars['testing']:
        return

    # send the data
    post_url = urllib.parse.urljoin(if_config_vars['if_url'], get_api_from_project_type())
    send_request(post_url, 'POST', 'Could not send request to IF',
                 str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.', data=data_to_post,
                 verify=False, proxies=if_config_vars['if_proxies'])
    logger.info('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def send_request(url, mode='GET', failure_message='Failure!', success_message='Success!', **request_passthrough):
    """ sends a request to the given url """
    # determine if post or get (default)
    requests.packages.urllib3.disable_warnings()
    req = requests.get
    if mode.upper() == 'POST':
        req = requests.post

    global REQUESTS
    REQUESTS.update(request_passthrough)
    # logger.debug(REQUESTS)

    req_num = 0
    for req_num in range(ATTEMPTS):
        try:
            response = req(url, **request_passthrough)
            if response.status_code == http.client.OK:
                logger.info(success_message)
                return response
            else:
                logger.warn(failure_message)
                logger.info('Response Code: {}\nTEXT: {}'.format(response.status_code, response.text))
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

    logger.error('Failed! Gave up after {} attempts.'.format(req_num + 1))
    return -1


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
        if if_config_vars['is_replay']:
            return 'containerReplay'
        else:
            return 'containerStreaming'
    elif if_config_vars['is_replay']:
        if 'METRIC' in if_config_vars['project_type']:
            return 'MetricFile'
        else:
            return 'LogFile'
    else:
        return 'Custom'


def get_agent_type_from_project_type():
    """ use project type to determine agent type """
    if 'METRIC' in if_config_vars['project_type']:
        if if_config_vars['is_replay']:
            return 'MetricFileReplay'
        else:
            return 'CUSTOM'
    elif if_config_vars['is_replay']:
        return 'LogFileReplay'
    else:
        return 'LogStreaming'  # INCIDENT and DEPLOYMENT don't use this


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


def check_project_exist():
    is_project_exist = False

    system_name = if_config_vars['system_name']
    project_name = if_config_vars['project_name']

    try:
        logger.info('Starting check project: ' + project_name)
        params = {'operation': 'check', 'userName': if_config_vars['user_name'],
                  'licenseKey': if_config_vars['license_key'], 'projectName': project_name, }
        url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
        response = send_request(url, 'POST', data=params, verify=False, proxies=if_config_vars['if_proxies'])
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

    create_project_success = False
    if not is_project_exist:
        try:
            logger.info('Starting add project: {}/{}'.format(system_name, project_name))
            params = {'operation': 'create', 'userName': if_config_vars['user_name'],
                      'licenseKey': if_config_vars['license_key'], 'projectName': project_name,
                      'systemName': system_name or project_name, 'instanceType': 'Zabbix',
                      'projectCloudType': 'PrivateCloud', 'dataType': get_data_type_from_project_type(),
                      'insightAgentType': get_insight_agent_type_from_project_type(),
                      'samplingInterval': int(if_config_vars['sampling_interval'] / 60),
                      'samplingIntervalInSeconds': if_config_vars['sampling_interval'], }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(url, 'POST', data=params, verify=False, proxies=if_config_vars['if_proxies'])
            if response == -1:
                logger.error('Add project error: ' + project_name)
            else:
                result = response.json()
                if result['success'] is False:
                    logger.error('Add project error: {}/{}'.format(system_name, project_name))
                else:
                    create_project_success = True
                    logger.info('Add project success: {}/{}'.format(system_name, project_name))

        except Exception as e:
            logger.error(e)
            logger.error('Add project error: {}/{}'.format(system_name, project_name))

    if create_project_success:
        # if create project is success, sleep 10s and check again
        time.sleep(10)
        try:
            logger.info('Starting check project: ' + project_name)
            params = {'operation': 'check', 'userName': if_config_vars['user_name'],
                      'licenseKey': if_config_vars['license_key'], 'projectName': project_name, }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(url, 'POST', data=params, verify=False, proxies=if_config_vars['if_proxies'])
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
    CSV_DELIM = r",|\t"
    ATTEMPTS = 3
    REQUESTS = dict()
    track = dict()
    data_buffer = dict()

    # get config
    cli_config_vars = get_cli_config_vars()
    logger = set_logger_config(cli_config_vars['log_level'])
    logger.debug(cli_config_vars)
    if_config_vars = get_if_config_vars()
    agent_config_vars = get_agent_config_vars()
    print_summary_info()

    # Create project if we use project_name_prefix option
    check_success = False
    if not cli_config_vars['testing']:
        check_success = check_project_exist()

    if check_success:
        initialize_data_gathering()

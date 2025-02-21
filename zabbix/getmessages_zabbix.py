import configparser
import glob
import http.client
import json
import logging
import multiprocessing
import os
import re
import shlex
import socket
import sys
import time
import traceback
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from logging.handlers import QueueHandler
from optparse import OptionParser
from pathlib import Path
from sys import getsizeof

import arrow
import pytz
import regex
import requests
from pyzabbix import ZabbixAPI

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

"""
This script gathers data to send to Insightfinder
"""


def align_timestamp(timestamp, sampling_interval):
    if sampling_interval == 0 or not timestamp:
        return timestamp
    else:
        return int(timestamp / (sampling_interval * 1000)) * sampling_interval * 1000


def is_matching_allow_regex(text, allow_regex_map):
    if (not allow_regex_map) or len(allow_regex_map) == 0:
        return True

    for allow_regex in allow_regex_map:
        if allow_regex:
            if allow_regex.startswith('/') and allow_regex.endswith('/'):
                if regex.match(allow_regex[1:-1], text):
                    return True
            else:
                if text == allow_regex:
                    return True
    return False


def is_matching_disallow_regex(text, disallow_regex_map):
    if (not disallow_regex_map) or len(disallow_regex_map) == 0:
        return False

    for disallow_regex in disallow_regex_map:
        if disallow_regex:
            if disallow_regex.startswith('/') and disallow_regex.endswith('/'):
                if regex.match(disallow_regex[1:-1], text):
                    return True
            else:
                if text == disallow_regex:
                    return True
    return False


def is_matching_block_regex(item_id, name, block_regex_map):
    for block_regex in block_regex_map:
        if block_regex:
            text = block_regex.isdigit() and item_id or name
            if block_regex.startswith('/') and block_regex.endswith('/'):
                if regex.match(block_regex[1:-1], text):
                    return True
            else:
                if text == block_regex:
                    return True
    return False


def data_processing_worker(idx, total, logger, zapi, hostids, data_type, all_field_map, items_map, items_keys,
                           cli_config_vars, agent_config_vars, if_config_vars, sampling_now):
    logger.info('Starting data processing worker {}/{}...'.format(idx + 1, total))

    log_request_interval = agent_config_vars['log_request_interval']
    metric_allowlist_map = agent_config_vars['metric_allowlist_map'] or {}
    metric_disallowlist_map = agent_config_vars['metric_disallowlist_map'] or {}
    his_time_range = agent_config_vars['his_time_range']
    sampling_interval = if_config_vars['sampling_interval']

    # value_type: 0 - FLOAT 1 - CHAR 2 - LOG 3 - UNSIGNED(default)
    value_type_list = ['0', '3'] if data_type == 'Metric' else ['2']
    history_type = 0 if data_type == 'Metric' else 2

    if his_time_range:
        timestamp_end = his_time_range[1]
        timestamp_start = his_time_range[0]
    else:
        timestamp_end = int(arrow.utcnow().floor('second').timestamp())
        if data_type == 'Metric':
            live_window = sampling_interval * 10
            timestamp_start = timestamp_end - live_window
        else:
            timestamp_start = timestamp_end - if_config_vars["run_interval"]

    items_ids_map = {}
    items_ids = []

    data_buffer = {}
    reset_data_buffer(data_buffer)

    track = {'chunk_count': 0, 'entry_count': 0}
    reset_track(track)

    if data_type == 'Log' or data_type == 'Metric':
        items_res = zapi.do_request('item.get', {'output': ['key_', 'itemid', 'name'], "hostids": hostids,
                                                 'selectHosts': ['hostId'], 'filter': {'value_type': value_type_list}})
        items_ids_map = {}
        items_keys_map = {}
        for item in items_res['result']:
            item_id = item['itemid']
            item_key = item['key_']
            item_name = item['name']
            if data_type == 'Metric':
                if is_matching_allow_regex(item_name, metric_allowlist_map):
                    if not is_matching_disallow_regex(item_name, metric_disallowlist_map):
                        items_ids_map[item_id] = item
                        items_keys_map[item_key] = item
            else:
                items_ids_map[item_id] = item
                items_keys_map[item_key] = item
        items_ids = list(items_ids_map.keys())
        items_keys = list(items_keys_map.keys())
        logger.info("Zabbix item count: %s" % len(items_ids))

    if data_type == 'Metric':
        if his_time_range:
            his_interval = sampling_interval * 10
            logger.debug('Using time range for replay data: {}'.format(his_time_range))
            for timestamp in range(timestamp_start, timestamp_end, his_interval):
                time_now = arrow.utcnow()
                query = {'output': 'extend', "history": history_type, "hostids": hostids, "itemids": items_ids,
                         'time_from': timestamp, 'time_till': timestamp + his_interval}
                logger.debug('Begin history.get query {} from {} hosts'.format(query, len(hostids)))

                history_res = zapi.do_request('history.get', query)
                logger.info(
                    'Query {} items from {} hosts with {} metrics in {} seconds'.format(len(history_res['result']),
                                                                                        len(hostids), len(items_keys), (
                                                                                                arrow.utcnow() - time_now).total_seconds()))
                parse_messages_zabbix(logger, data_type, history_res['result'], all_field_map, items_ids_map, 'history',
                                      agent_config_vars, track, data_buffer, sampling_interval, sampling_now)

                clear_data_buffer(logger, cli_config_vars, if_config_vars, track, data_buffer)
        else:
            time_now = arrow.utcnow()
            metric_output = ['key_', 'itemid', 'lastclock', 'clock', 'lastvalue', 'value', 'name']

            params = {'output': metric_output, "hostids": hostids, "selectHosts": ['hostId'],
                      'filter': {'value_type': value_type_list, 'key_': items_keys}}
            logger.info('Begin item.get query from {} hosts'.format(len(hostids)))
            items_res = zapi.do_request('item.get', params)
            logger.info('Query {} items from {} hosts with {} metrics in {} seconds'.format(len(items_res['result']),
                                                                                            len(hostids),
                                                                                            len(items_keys), (
                                                                                                    arrow.utcnow() - time_now).total_seconds()))
            parse_messages_zabbix(logger, data_type, items_res['result'], all_field_map, items_map, 'live',
                                  agent_config_vars, track, data_buffer, sampling_interval, sampling_now)
            clear_data_buffer(logger, cli_config_vars, if_config_vars, track, data_buffer)
    elif data_type == 'Alert':
        for timestamp in range(timestamp_start, timestamp_end, log_request_interval):
            time_now = arrow.utcnow()
            time_end = (
                           timestamp + log_request_interval if timestamp + log_request_interval < timestamp_end else timestamp_end) - 1
            query = {'output': 'extend', 'hostids': hostids, 'selectHosts': 'extend', 'time_from': timestamp,
                     'time_till': time_end, }
            logger.info('Begin event.get query from {} hosts: {}'.format(len(hostids), query))

            history_res = zapi.do_request('event.get', query)

            parse_messages_zabbix(logger, data_type, history_res['result'], all_field_map, items_map, 'history',
                                  agent_config_vars, track, data_buffer, log_request_interval, sampling_now)

            query = {'output': 'extend', 'hostids': hostids, 'selectHosts': 'extend', 'time_from': timestamp,
                     'time_till': time_end, }
            logger.info('Begin problem.get query from {} hosts: {}'.format(len(hostids), query))

            history_res = zapi.do_request('problem.get', query)

            logger.info('Query {} items from {} hosts in {} seconds'.format(len(history_res['result']), len(hostids), (
                    arrow.utcnow() - time_now).total_seconds()))
            parse_messages_zabbix(logger, data_type, history_res['result'], all_field_map, items_map, 'history',
                                  agent_config_vars, track, data_buffer, log_request_interval, sampling_now)
            # clear data buffer when piece of time range end
            clear_data_buffer(logger, cli_config_vars, if_config_vars, track, data_buffer)
    else:
        for timestamp in range(timestamp_start, timestamp_end, log_request_interval):
            time_now = arrow.utcnow()
            time_end = (
                           timestamp + log_request_interval if timestamp + log_request_interval < timestamp_end else timestamp_end) - 1

            query = {'output': 'extend', "history": history_type, "hostids": hostids, "itemids": items_ids,
                     'time_from': timestamp, 'time_till': time_end}
            logger.info('Begin history.get query from {} hosts. {}'.format(len(hostids), query))

            history_res = zapi.do_request('history.get', query)

            logger.info('Query {} items from {} hosts in {} seconds'.format(len(history_res['result']), len(hostids), (
                    arrow.utcnow() - time_now).total_seconds()))
            parse_messages_zabbix(logger, data_type, history_res['result'], all_field_map, items_ids_map, 'history',
                                  agent_config_vars, track, data_buffer, log_request_interval, sampling_now)
            clear_data_buffer(logger, cli_config_vars, if_config_vars, track, data_buffer)
    return idx + 1


def start_data_processing(logger, config_name, cli_config_vars, agent_config_vars, if_config_vars, sampling_now):
    data_type = get_data_type_from_project_type(logger, if_config_vars)
    logger.info('Starting fetch {} items......'.format(data_type))

    # Create ZabbixAPI class instance
    zabbix_config = agent_config_vars['zabbix_kwargs']
    zabbix_url = zabbix_config['url']
    zabbix_user = zabbix_config['user']
    zabbix_password = zabbix_config['password']
    max_workers = agent_config_vars['max_workers']
    request_timeout = agent_config_vars['request_timeout']
    zapi = ZabbixAPI(server=zabbix_url, timeout=request_timeout)
    zapi.login(user=zabbix_user, password=zabbix_password)
    logger.info("Connected to Zabbix API Version %s" % zapi.api_version())

    template_ids = agent_config_vars['template_ids'] or []
    host_blocklist_map = agent_config_vars['host_blocklist_map'] or {}
    metric_allowlist_map = agent_config_vars['metric_allowlist_map'] or {}
    metric_disallowlist_map = agent_config_vars['metric_disallowlist_map'] or {}
    device_field = agent_config_vars['device_field']

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
    max_host_per_request = agent_config_vars['max_host_per_request']

    # get hosts
    hosts_map = {}
    hosts_group_map = {}
    host_template_map = {}
    hosts_ids = []
    hosts_res = zapi.do_request('host.get', {'output': ['name', 'hostid'], 'groupids': host_groups_ids,
                                             'selectHostGroups': ['groupid', 'name'],
                                             'selectParentTemplates': ['templateid', 'name'],
                                             'filter': {"host": agent_config_vars['hosts']}, })
    for item in hosts_res['result']:
        host_id = item['hostid']
        host_name = item['name']
        if not is_matching_block_regex(host_id, host_name, host_blocklist_map):
            hostgroups = item.get('hostgroups') or []
            # use the last hostgroup as the component name
            host_group = hostgroups[len(hostgroups) - 1].get('name') or ''

            parent_templates = item.get('parentTemplates') or []
            for template in parent_templates:
                if template.get('templateid') not in host_template_map:
                    host_template_map[template.get('templateid')] = template.get('name')

            hosts_ids.append(host_id)
            hosts_map[host_id] = host_name
            hosts_group_map[host_id] = host_group

    host_template_ids = list(host_template_map.keys())

    logger.info("Zabbix hosts count: %s" % len(hosts_ids))
    if len(hosts_ids) == 0:
        logger.error('Hosts list is empty, quit')
        return

    # get data by hosts/applications
    hosts_ids_list = [hosts_ids]
    if len(hosts_ids) > max_host_per_request:
        hosts_ids_list = [hosts_ids[i:i + max_host_per_request] for i in range(0, len(hosts_ids), max_host_per_request)]

    items_map = {}
    items_keys = []
    if data_type == 'Metric':
        # get the items based on the keys
        item_output = ['name', 'itemid', 'key_']
        if device_field:
            item_output.append(device_field)

        # get the item keys based on the template
        metric_template_ids = template_ids if len(template_ids) > 0 else host_template_ids
        templates_res = zapi.do_request('template.get', {'output': ['name'], 'templateids': metric_template_ids,
                                                         'selectItems': item_output})
        for template in templates_res['result']:
            items = template.get('items') or []
            for item in items:
                item_key = item['key_']
                item_name = item['name']
                if is_matching_allow_regex(item_name, metric_allowlist_map):
                    if not is_matching_disallow_regex(item_name, metric_disallowlist_map):
                        items_map[item_key] = item

        items_keys = list(items_map.keys())

        if len(items_keys) == 0:
            logger.error('Item list is empty')
            return

        # logger.info("Zabbix item count: %s" % len(items_keys))

    all_field_map = {'hostid': hosts_map, 'hostgroup': hosts_group_map}

    total = len(hosts_ids_list)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(data_processing_worker, idx, total, logger, zapi, hostids, data_type, all_field_map,
                                   items_map, items_keys, cli_config_vars, agent_config_vars, if_config_vars,
                                   sampling_now) for idx, hostids in enumerate(hosts_ids_list)]
        for future in as_completed(futures):
            logger.info('Data processing worker {}/{} finished'.format(future.result(), total))
    logger.info('Data processing done')


def parse_messages_zabbix(logger, data_type, result, all_field_map, items_map, replay_type, agent_config_vars, track,
                          data_buffer, sampling_interval, sampling_now):
    count = 0
    logger.info('Reading {} messages'.format(len(result)))
    is_metric = True if data_type == 'Metric' else False
    is_alert = True if data_type == 'Alert' else False

    instance_field = agent_config_vars['instance_field'][0] if agent_config_vars['instance_field'] and len(
        agent_config_vars['instance_field']) > 0 else 'hostid'
    device_field = agent_config_vars['device_field']
    target_timestamp_timezone = agent_config_vars['target_timestamp_timezone']
    component_from_host_group = agent_config_vars['component_from_host_group']
    zone_from_host_group = agent_config_vars['zone_from_host_group']
    component_from_instance_name_re_sub = agent_config_vars['component_from_instance_name_re_sub']
    alert_data_fields = agent_config_vars['alert_data_fields']

    for message in result:
        try:
            logger.debug('Message received:' + str(message))

            item_key = message.get('key_')
            item_id = message.get('itemid')
            item_name = message.get('name')

            # set instance and device
            if not message.get('hosts'):
                item = items_map.get(item_id)
                if not item:
                    continue
                hosts = item.get('hosts')
                if hosts and len(hosts) > 0:
                    instance_id = hosts[0].get(instance_field)
                else:
                    continue
            else:
                hosts = message.get('hosts')
                if hosts and len(hosts) > 0:
                    instance_id = hosts[0].get(instance_field)
                else:
                    continue

            instance = all_field_map.get(instance_field).get(instance_id)

            # set zone
            zone = None
            if zone_from_host_group:
                zone_field = 'hostgroup'
                if all_field_map.get(zone_field):
                    zone = all_field_map.get(zone_field).get(instance_id)


            # set component
            component = None
            if component_from_host_group:
                component_field = 'hostgroup'
                if all_field_map.get(component_field):
                    component = all_field_map.get(component_field).get(instance_id)
            elif component_from_instance_name_re_sub:
                re_sub_rules = component_from_instance_name_re_sub.split(",")
                if len(re_sub_rules) % 2 != 0:
                    logger.error("Unable to parse component_from_instance_name_re_sub")

                re_rule_part1 = ""
                re_rule_part2 = ""
                component = instance

                for rule_index in range(len(re_sub_rules)):
                    if rule_index %2 == 0:
                        re_rule_part1 = re_sub_rules[rule_index]
                    else:
                        re_rule_part2 = re_sub_rules[rule_index]
                        component = re.sub(re_rule_part1, re_rule_part2, component)

            # add device info if it has
            device = None
            if (item_key or item_id) and device_field and len(device_field) > 0:
                device_field = device_field[0]
                if items_map.get(item_key) or items_map.get(item_id):
                    item = items_map.get(item_key) or items_map.get(item_id)
                    device_id = item.get(device_field)
                    device = all_field_map.get(device_field).get(device_id)
            full_instance = make_safe_instance_string(instance, device)

            # set timestamp
            if is_metric and replay_type == 'live':
                timestamp = sampling_now
            else:
                clock = message['lastclock'] if replay_type == 'live' else message['clock']
                timestamp = int(clock) * 1000
                timestamp += target_timestamp_timezone * 1000
                if is_metric:
                    timestamp = align_timestamp(timestamp, sampling_interval)

            if timestamp == 0:
                continue

            # set data field and value
            data_field = None
            if is_metric:
                if item_name:
                    data_field = item_name
                else:
                    item = items_map.get(item_key) or items_map.get(item_id)
                    if item:
                        data_field = item['name']
                if not data_field:
                    logger.warn('cannot find item name from {}'.format(message))
                    continue

                data_field = make_safe_data_key(data_field)

            data_value = None
            if is_alert:

                # Skip Alerts / Problems `resolved` or `ok` event
                if 'value' in message and message['value'] == '0':
                    continue

                if alert_data_fields and len(alert_data_fields) == 1:
                    data_value = message.get([alert_data_fields[0]])
                elif alert_data_fields and len(alert_data_fields) > 1:
                    data_value = {field: message.get(field) for field in alert_data_fields}
                else:
                    data_value = message
            elif replay_type == 'live':
                data_value = str(message['lastvalue'])
            else:
                data_value = str(message['value'])

            # Special Case: Convert 'ICMP response time' to use ms instead of second
            if data_value and data_field == 'ICMP response time':
                data_value = str(float(data_value) * 1000)

            timestamp = str(timestamp)

            key = '{}-{}'.format(timestamp, full_instance)
            if key not in data_buffer['buffer_dict']:
                data_buffer['buffer_dict'][key] = {"timestamp": timestamp, "data": {}}

            if is_metric:
                data_buffer['buffer_dict'][key]['instanceName'] = full_instance
                if component:
                    data_buffer['buffer_dict'][key]['componentName'] = component
                    data_buffer['buffer_dict'][key]['zone'] = zone

                # data_key = '{}[{}]'.format(data_field, full_instance)
                data_buffer['buffer_dict'][key]['data'][data_field] = data_value
            else:
                data_buffer['buffer_dict'][key]['tag'] = full_instance
                if component:
                    data_buffer['buffer_dict'][key]['componentName'] = component
                    data_buffer['buffer_dict'][key]['zone'] = zone
                data_buffer['buffer_dict'][key]['data'] = data_value

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


def get_agent_config_vars(logger, config_ini):
    """ Read and parse config.ini """
    """ get config.ini vars """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False

    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser(interpolation=None)
        config_parser.read_file(fp)

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
                config_error(logger, 'url')
            if len(config_parser.get('zabbix', 'user')) != 0:
                zabbix_kwargs['user'] = config_parser.get('zabbix', 'user')
            else:
                config_error(logger, 'user')
            if len(config_parser.get('zabbix', 'password')) != 0:
                zabbix_kwargs['password'] = config_parser.get('zabbix', 'password')
            else:
                config_error(logger, 'password')

            # metrics
            host_groups = config_parser.get('zabbix', 'host_groups')
            hosts = config_parser.get('zabbix', 'hosts')
            host_blocklist = config_parser.get('zabbix', 'host_blocklist')
            template_ids = config_parser.get('zabbix', 'template_ids')
            metric_allowlist = config_parser.get('zabbix', 'metric_allowlist')
            metric_disallowlist = config_parser.get('zabbix', 'metric_disallowlist', fallback=None)
            applications = config_parser.get('zabbix', 'applications')

            max_workers = config_parser.get('zabbix', 'max_workers')
            request_timeout = config_parser.get('zabbix', 'request_timeout')
            max_host_per_request = config_parser.get('zabbix', 'max_host_per_request')

            # log
            log_request_interval = config_parser.get('zabbix', 'log_request_interval')

            # time range
            his_time_range = config_parser.get('zabbix', 'his_time_range')

            # proxies
            agent_http_proxy = config_parser.get('zabbix', 'agent_http_proxy')
            agent_https_proxy = config_parser.get('zabbix', 'agent_https_proxy')

            # message parsing
            data_format = config_parser.get('zabbix', 'data_format').upper()
            # project_field = config_parser.get('agent', 'project_field', raw=True)
            instance_field = config_parser.get('zabbix', 'instance_field', raw=True)
            component_from_host_group = config_parser.get('zabbix', 'component_from_host_group') or False
            zone_from_host_group = config_parser.get('zabbix', 'zone_from_host_group') or False
            component_from_instance_name_re_sub = config_parser.get('zabbix', 'component_from_instance_name_re_sub', fallback=None)
            device_field = config_parser.get('zabbix', 'device_field', raw=True)
            timestamp_field = config_parser.get('zabbix', 'timestamp_field', raw=True) or 'timestamp'
            target_timestamp_timezone = config_parser.get('zabbix', 'target_timestamp_timezone', raw=True) or 'UTC'
            timestamp_format = config_parser.get('zabbix', 'timestamp_format', raw=True)
            timezone = config_parser.get('zabbix', 'timezone') or 'UTC'
            data_fields = config_parser.get('zabbix', 'data_fields', raw=True)
            alert_data_fields = config_parser.get('zabbix', 'alert_data_fields', raw=True)

        except configparser.NoOptionError as cp_noe:
            logger.error(cp_noe)
            return config_error(logger, )

        # host_groups
        if len(host_groups) != 0:
            host_groups = [x for x in host_groups.split(',') if x.strip()]
        if len(hosts) != 0:
            hosts = [x for x in hosts.split(',') if x.strip()]
        host_blocklist_map = {}
        if len(host_blocklist) != 0:
            for host_block in host_blocklist.split(','):
                host_block = host_block.strip()
                if len(host_block) != 0:
                    host_blocklist_map[host_block] = host_block

        if len(template_ids) != 0:
            template_ids = [x for x in template_ids.split(',') if x.strip()]

        metric_allowlist_map = {}
        if len(metric_allowlist) != 0:
            for metric_allow in metric_allowlist.split(','):
                metric_allow = metric_allow.strip()
                if len(metric_allow) != 0:
                    metric_allowlist_map[metric_allow] = metric_allow

        metric_disallowlist_map = {}
        if metric_disallowlist and len(metric_disallowlist) != 0:
            for metric_disallow in metric_disallowlist.split(','):
                metric_disallow = metric_disallow.strip()
                if len(metric_disallow) != 0:
                    metric_disallowlist_map[metric_disallow] = metric_disallow

        if len(applications) != 0:
            applications = [x for x in applications.split(',') if x.strip()]

        if len(max_workers) != 0:
            max_workers = int(max_workers)
        else:
            max_workers = multiprocessing.cpu_count()
        if max_workers > 10:
            max_workers = 10

        if len(request_timeout) != 0:
            request_timeout = int(request_timeout)
        else:
            request_timeout = 60

        if len(max_host_per_request) != 0:
            max_host_per_request = int(max_host_per_request)
        else:
            max_host_per_request = 100

        if len(log_request_interval) != 0:
            log_request_interval = int(log_request_interval)
        else:
            log_request_interval = 60

        if len(his_time_range) != 0:
            his_time_range = [x for x in his_time_range.split(',') if x.strip()]
            his_time_range = [int(arrow.get(x).float_timestamp) for x in his_time_range]

        if len(target_timestamp_timezone) != 0:
            target_timestamp_timezone = int(arrow.now(target_timestamp_timezone).utcoffset().total_seconds())
        else:
            config_error(logger, 'target_timestamp_timezone')

        if timezone:
            if timezone not in pytz.all_timezones:
                config_error(logger, 'timezone')
            else:
                timezone = pytz.timezone(timezone)

        # data format
        if data_format in {'JSON', 'JSONTAIL', 'AVRO', 'XML'}:
            pass
        else:
            config_error(logger, 'data_format')

        # proxies
        agent_proxies = dict()
        if len(agent_http_proxy) > 0:
            agent_proxies['http'] = agent_http_proxy
        if len(agent_https_proxy) > 0:
            agent_proxies['https'] = agent_https_proxy

        # fields
        # project_fields = project_field.split(',')
        instance_fields = [x for x in instance_field.split(',') if x.strip()]
        if component_from_host_group:
            component_from_host_group = True if component_from_host_group.lower() == 'true' else False

        if zone_from_host_group:
            zone_from_host_group = True if zone_from_host_group.lower() == 'true' else False

        device_fields = [x for x in device_field.split(',') if x.strip()]
        timestamp_fields = timestamp_field.split(',')
        if len(data_fields) != 0:
            data_fields = data_fields.split(',')
            for instance_field in instance_fields:
                if instance_field in data_fields:
                    data_fields.pop(data_fields.index(instance_field))
            for device_field in device_fields:
                if device_field in data_fields:
                    data_fields.pop(data_fields.index(device_field))
            for timestamp_field in timestamp_fields:
                if timestamp_field in data_fields:
                    data_fields.pop(data_fields.index(timestamp_field))

        if len(alert_data_fields) != 0:
            alert_data_fields = [x for x in alert_data_fields.split(',') if x.strip()]

        # add parsed variables to a global
        config_vars = {'zabbix_kwargs': zabbix_kwargs, 'host_groups': host_groups, 'hosts': hosts,
                       'host_blocklist': host_blocklist, 'host_blocklist_map': host_blocklist_map,
                       'template_ids': template_ids, 'metric_allowlist': metric_allowlist,
                       'metric_allowlist_map': metric_allowlist_map,
                       'metric_disallowlist_map': metric_disallowlist_map,
                       'max_workers': max_workers,
                       'request_timeout': request_timeout, 'max_host_per_request': max_host_per_request,
                       'log_request_interval': log_request_interval, 'applications': applications,
                       'his_time_range': his_time_range, 'proxies': agent_proxies, 'data_format': data_format,
                       # 'project_field': project_fields,
                       'instance_field': instance_fields, 'component_from_host_group': component_from_host_group,
                       'zone_from_host_group': zone_from_host_group,
                       'device_field': device_fields, 'data_fields': data_fields,
                       'alert_data_fields': alert_data_fields, 'timestamp_field': timestamp_fields,
                       'target_timestamp_timezone': target_timestamp_timezone, 'timezone': timezone,
                       'timestamp_format': timestamp_format, 'component_from_instance_name_re_sub': component_from_instance_name_re_sub}

        return config_vars


#########################
#   START_BOILERPLATE   #
#########################
def get_if_config_vars(logger, config_ini):
    """ get config.ini vars """
    if not os.path.exists(config_ini):
        logger.error('No config file found. Exiting...')
        return False

    with open(config_ini) as fp:
        config_parser = configparser.ConfigParser()
        config_parser.read_file(fp)
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
            return config_error(logger, )

        # check required variables
        if len(user_name) == 0:
            return config_error(logger, 'user_name')
        if len(license_key) == 0:
            return config_error(logger, 'license_key')
        if len(project_name) == 0:
            return config_error(logger, 'project_name')
        if len(project_type) == 0:
            return config_error(logger, 'project_type')

        if project_type not in {'METRIC', 'METRICREPLAY', 'LOG', 'LOGREPLAY', 'INCIDENT', 'INCIDENTREPLAY', 'ALERT',
                                'ALERTREPLAY', 'DEPLOYMENT', 'DEPLOYMENTREPLAY'}:
            return config_error(logger, 'project_type')

        is_replay = 'REPLAY' in project_type

        if len(sampling_interval) == 0:
            if 'METRIC' in project_type:
                return config_error(logger, 'sampling_interval')
            else:
                # set default for non-metric
                sampling_interval = 10

        if sampling_interval.endswith('s'):
            sampling_interval = int(sampling_interval[:-1])
        else:
            sampling_interval = int(sampling_interval) * 60

        if len(run_interval) == 0:
            return config_error(logger, 'run_interval')

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


def abs_path_from_cur(filename=''):
    return os.path.abspath(os.path.join(__file__, os.pardir, filename))


def get_cli_config_vars():
    """ get CLI options. use of these options should be rare """
    usage = 'Usage: %prog [options]'
    parser = OptionParser(usage=usage)
    """
    """
    parser.add_option('-c', '--config', action='store', dest='config', default=abs_path_from_cur('conf.d'),
                      help='Path to the config files to use. Defaults to {}'.format(abs_path_from_cur('conf.d')))
    parser.add_option('-q', '--quiet', action='store_true', dest='quiet', default=False,
                      help='Only display warning and error log messages')
    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', default=False,
                      help='Enable verbose logging')
    parser.add_option('-t', '--testing', action='store_true', dest='testing', default=False,
                      help='Set to testing mode (do not send data).' + ' Automatically turns on verbose logging')
    parser.add_option('--timeout', action='store', dest='timeout', help='Minutes of timeout for all processes')
    (options, args) = parser.parse_args()

    config_vars = {'config': options.config if os.path.isdir(options.config) else abs_path_from_cur('conf.d'),
                   'testing': False, 'log_level': logging.INFO, }

    if options.testing:
        config_vars['testing'] = True

    if options.verbose:
        config_vars['log_level'] = logging.DEBUG
    elif options.quiet:
        config_vars['log_level'] = logging.WARNING

    config_vars['timeout'] = int(options.timeout) * 60 if options.timeout else 0

    return config_vars


def config_error(logger, setting=''):
    info = ' ({})'.format(setting) if setting else ''
    logger.error('Agent not correctly configured{}. Check config file.'.format(info))
    return False


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
    metric = UNDERSCORE.sub('-', metric)
    metric = COLONS.sub('-', metric)
    metric = COMMA.sub('-', metric)
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


def print_summary_info(logger, if_config_vars, agent_config_vars):
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


def clear_data_buffer(logger, cli_config_vars, if_config_vars, track, data_buffer):
    # move all buffer data to current data, and send
    buffer_values = list(data_buffer['buffer_dict'].values())

    count = 0
    for row in buffer_values:
        track['current_row'].append(row)
        count += 1
        if count % 1000 == 0 or get_json_size_bytes(track['current_row']) >= if_config_vars['chunk_size']:
            logger.debug('Sending buffer chunk')
            send_data_wrapper(logger, cli_config_vars, if_config_vars, track, data_buffer)

    # last chunk
    if len(track['current_row']) > 0:
        logger.debug('Sending last chunk')
        send_data_wrapper(logger, cli_config_vars, if_config_vars, track, data_buffer)

    reset_data_buffer(data_buffer)


def reset_data_buffer(data_buffer):
    data_buffer['buffer_key_list'] = []
    data_buffer['buffer_ts_list'] = []
    data_buffer['buffer_dict'] = {}

    data_buffer['buffer_collected_list'] = []
    data_buffer['buffer_collected_dict'] = {}


def reset_track(track):
    """ reset the track global for the next chunk """
    track['start_time'] = time.time()
    track['line_count'] = 0
    track['current_row'] = []


################################
# Functions to send data to IF #
################################
def send_data_wrapper(logger, cli_config_vars, if_config_vars, track, data_buffer):
    """ wrapper to send data """
    logger.debug('--- Chunk creation time: {} seconds ---'.format(round(time.time() - track['start_time'], 2)))
    send_data_to_if(logger, track['current_row'], cli_config_vars, if_config_vars)
    track['chunk_count'] += 1
    reset_track(track)


def safe_string_to_float(s):
    try:
        return float(s)
    except ValueError:
        return None


def convert_to_metric_data(logger, chunk_metric_data, cli_config_vars, if_config_vars):
    to_send_data_dict = dict()
    to_send_data_dict['licenseKey'] = if_config_vars['license_key']
    to_send_data_dict['userName'] = if_config_vars['user_name']

    data_dict = dict()
    data_dict['projectName'] = if_config_vars['project_name']
    data_dict['userName'] = if_config_vars['user_name']
    if 'system_name' in if_config_vars:
        data_dict['systemName'] = if_config_vars['system_name']
    data_dict['iat'] = 'zabbix'
    if 'sampling_interval' in if_config_vars:
        data_dict['si'] = str(if_config_vars['sampling_interval'])

    instance_data_map = dict()
    for chunk in chunk_metric_data:
        instance_name = chunk['instanceName']
        component_name = chunk.get('componentName')
        zone = chunk.get('zone')
        timestamp = chunk['timestamp']
        data = chunk['data']
        if data and timestamp and instance_name:
            ts = int(timestamp)
            if instance_name not in instance_data_map:
                instance_data_map[instance_name] = {'in': instance_name, 'cn': component_name, 'z': zone, 'dit': {}, }

            if timestamp not in instance_data_map[instance_name]['dit']:
                instance_data_map[instance_name]['dit'][timestamp] = {'t': ts, 'm': []}

            data_set = instance_data_map[instance_name]['dit'][timestamp]['m']
            for metric_name, metric_value in data.items():
                float_value = safe_string_to_float(metric_value)
                if float_value is not None:
                    data_set.append({'m': metric_name, 'v': float_value})
                else:
                    data_set.append({'m': metric_name, 'v': 0.0})

    data_dict['idm'] = instance_data_map
    to_send_data_dict['data'] = data_dict

    return to_send_data_dict


def send_data_to_if(logger, chunk_metric_data, cli_config_vars, if_config_vars):
    send_data_time = time.time()

    # prepare data for metric streaming agent
    data_to_post = None
    json_to_post = None
    if 'METRIC' in if_config_vars['project_type']:
        json_to_post = convert_to_metric_data(logger, chunk_metric_data, cli_config_vars, if_config_vars)
        logger.debug(json_to_post)
        post_url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v2/metric-data-receive')
    else:
        data_to_post = initialize_api_post_data(logger, if_config_vars)
        if 'DEPLOYMENT' in if_config_vars['project_type'] or 'INCIDENT' in if_config_vars['project_type']:
            for chunk in chunk_metric_data:
                chunk['data'] = json.dumps(chunk['data'])
        data_to_post[get_data_field_from_project_type(if_config_vars)] = json.dumps(chunk_metric_data)
        post_url = urllib.parse.urljoin(if_config_vars['if_url'], get_api_from_project_type(if_config_vars))

    # do not send if only testing
    if cli_config_vars['testing']:
        return

    # send the data
    if data_to_post:
        logger.debug('First:\n' + str(chunk_metric_data[0]))
        logger.debug('Last:\n' + str(chunk_metric_data[-1]))
        logger.info('Total Data (bytes): ' + str(get_json_size_bytes(data_to_post)))
        logger.info('Total Lines: ' + str(len(chunk_metric_data)))

        send_request(logger, post_url, 'POST', 'Could not send request to IF',
                     str(get_json_size_bytes(data_to_post)) + ' bytes of data are reported.', data=data_to_post,
                     verify=False, proxies=if_config_vars['if_proxies'])
    elif json_to_post:
        logger.info('Total Data (bytes): ' + str(get_json_size_bytes(json_to_post)))
        send_request(logger, post_url, 'POST', 'Could not send request to IF',
                     str(get_json_size_bytes(json_to_post)) + ' bytes of data are reported.', json=json_to_post,
                     verify=False, proxies=if_config_vars['if_proxies'])

    logger.info('--- Send data time: %s seconds ---' % round(time.time() - send_data_time, 2))


def send_request(logger, url, mode='GET', failure_message='Failure!', success_message='Success!',
                 **request_passthrough):
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


def get_data_type_from_project_type(logger, if_config_vars):
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


def get_insight_agent_type_from_project_type(agent_config_vars, if_config_vars):
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


def get_agent_type_from_project_type(if_config_vars):
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


def get_data_field_from_project_type(if_config_vars):
    """ use project type to determine which field to place data in """
    # incident uses a different API endpoint
    if 'INCIDENT' in if_config_vars['project_type']:
        return 'incidentData'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'deploymentData'
    else:  # MERTIC, LOG, ALERT
        return 'metricData'


def get_api_from_project_type(if_config_vars):
    """ use project type to determine which API to post to """
    # incident uses a different API endpoint
    if 'INCIDENT' in if_config_vars['project_type']:
        return 'incidentdatareceive'
    elif 'DEPLOYMENT' in if_config_vars['project_type']:
        return 'deploymentEventReceive'
    else:  # LOG, ALERT
        return 'customprojectrawdata'


def initialize_api_post_data(logger, if_config_vars):
    """ set up the unchanging portion of this """
    to_send_data_dict = dict()
    to_send_data_dict['userName'] = if_config_vars['user_name']
    to_send_data_dict['licenseKey'] = if_config_vars['license_key']
    to_send_data_dict['projectName'] = if_config_vars['project_name']
    to_send_data_dict['instanceName'] = HOSTNAME
    to_send_data_dict['agentType'] = get_agent_type_from_project_type(if_config_vars)
    if 'METRIC' in if_config_vars['project_type'] and 'sampling_interval' in if_config_vars:
        to_send_data_dict['samplingInterval'] = str(if_config_vars['sampling_interval'])
    logger.debug(to_send_data_dict)
    return to_send_data_dict


def check_project_exist(logger, agent_config_vars, if_config_vars, project_name, system_name):
    is_project_exist = False
    if not system_name:
        system_name = if_config_vars['system_name']

    try:
        logger.info('Starting check project: ' + project_name)
        params = {'operation': 'check', 'userName': if_config_vars['user_name'],
                  'licenseKey': if_config_vars['license_key'], 'projectName': project_name, }
        url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
        response = send_request(logger, url, 'POST', data=params, verify=False, proxies=if_config_vars['if_proxies'])
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
                      'projectCloudType': 'Zabbix',
                      'dataType': get_data_type_from_project_type(logger, if_config_vars),
                      'insightAgentType': get_insight_agent_type_from_project_type(agent_config_vars, if_config_vars),
                      'samplingInterval': int(if_config_vars['sampling_interval'] / 60),
                      'samplingIntervalInSeconds': if_config_vars['sampling_interval'], }
            url = urllib.parse.urljoin(if_config_vars['if_url'], 'api/v1/check-and-add-custom-project')
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'])
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
            response = send_request(logger, url, 'POST', data=params, verify=False,
                                    proxies=if_config_vars['if_proxies'])
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


def listener_configurer():
    """ set up logging according to the defined log level """
    # create a logging format
    formatter = logging.Formatter(
        '{ts} {name} [pid {pid}] {lvl} {func}:{line} {msg}'.format(ts='%(asctime)s', name='%(name)s', pid='%(process)d',
                                                                   lvl='%(levelname)-8s', func='%(funcName)s',
                                                                   line='%(lineno)d', msg='%(message)s'), ISO8601[0])

    # Get the root logger
    root = logging.getLogger()

    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
    logging_handler_out.setFormatter(formatter)
    root.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logging_handler_err.setFormatter(formatter)
    root.addHandler(logging_handler_err)


def listener_process(q, c_config):
    listener_configurer()
    while True:
        while not q.empty():
            record = q.get()

            if not record or record.name == 'KILL':
                return

            logger = logging.getLogger(record.name)
            logger.handle(record)
        time.sleep(1)


def queue_configurer(q):
    h = QueueHandler(q)  # Just the one handler needed
    root = logging.getLogger()
    root.addHandler(h)
    # Default log level to info
    root.setLevel(logging.INFO)


def worker_process(args):
    (config_file, c_config, utc_now_time, q) = args

    config_name = Path(config_file).stem
    level = c_config['log_level']

    # start sub process
    logger = logging.getLogger('worker.' + config_name)
    logger.setLevel(level)

    logger.info("Setup logger in PID {}".format(os.getpid()))
    logger.info("Process start with config: {}".format(config_file))

    if_config_vars = get_if_config_vars(logger, config_file)
    if not if_config_vars:
        return

    agent_config_vars = get_agent_config_vars(logger, config_file)
    if not agent_config_vars:
        return

    print_summary_info(logger, if_config_vars, agent_config_vars)
    if not c_config['testing']:
        # check project first if project_name is set
        project_name = if_config_vars['project_name']
        if project_name:
            check_success = check_project_exist(logger, agent_config_vars, if_config_vars, project_name, None)
            if not check_success:
                return

    target_timestamp_timezone = agent_config_vars['target_timestamp_timezone']
    sampling_interval = if_config_vars['sampling_interval']

    sampling_now = align_timestamp((utc_now_time + target_timestamp_timezone) * 1000, sampling_interval)
    start_data_processing(logger, config_name, c_config, agent_config_vars, if_config_vars, sampling_now)


def main():
    # capture warnings to logging system
    logging.captureWarnings(True)

    # get config
    cli_config_vars = get_cli_config_vars()

    # get all config file
    files_path = os.path.join(cli_config_vars['config'], "*.ini")
    config_files = glob.glob(files_path)

    if len(config_files) == 0:
        logging.error("Config files not found")
        sys.exit(1)

    # logger
    m = multiprocessing.Manager()
    queue = m.Queue()
    listener = multiprocessing.Process(target=listener_process, args=(queue, cli_config_vars))
    listener.start()

    # set up main logger following example from work_process
    queue_configurer(queue)
    main_logger = logging.getLogger('main')

    # variables from cli config
    cli_data_block = '\nCLI settings:'
    for kk, kv in sorted(cli_config_vars.items()):
        cli_data_block += '\n\t{}: {}'.format(kk, kv)
    main_logger.info(cli_data_block)

    # get args
    utc_now_time = int(arrow.utcnow().float_timestamp)
    arg_list = [(f, cli_config_vars, utc_now_time, queue) for f in config_files]

    # start sub process by pool
    pool = multiprocessing.Pool(len(arg_list))
    pool_result = pool.map_async(worker_process, arg_list)
    pool.close()

    timeout = cli_config_vars['timeout']
    need_timeout = timeout > 0
    if need_timeout:
        pool_result.wait(timeout=timeout)

    try:
        pool_result.get(timeout=1 if need_timeout else None)
        pool.join()
    except TimeoutError:
        main_logger.error("We lacked patience and got a multiprocessing.TimeoutError")
        pool.terminate()

    # end
    main_logger.info("Now the pool is closed and no longer available")

    # send kill signal
    time.sleep(1)
    kill_logger = logging.getLogger('KILL')
    kill_logger.info('KILL')
    listener.join()


if __name__ == "__main__":
    main()

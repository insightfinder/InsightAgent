#!/usr/bin/env python
#
# This script gets metric data of containers from Sysdig Monitor
# This script shows an advanced Sysdig Monitor data request that leverages
# filtering and segmentation.
#
# Requires a API Token. Obtained from user settings on Sysdig Monitor
# The request returns the last 10 minutes of CPU utilization for the 5
# busiest containers inside the given host, with 1 minute data granularity
#

import ast
import ConfigParser
import collections
import logging
import re
import socket
import time
from optparse import OptionParser
from itertools import islice
import requests
import os
import sys
import json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), '..'))
from sdcclient import SdcClient

#
# parse user supplied arguments from command-line
#


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-w", "--serverUrl",
                      action="store", dest="serverUrl", help="Server Url")
    parser.add_option("-c", "--chunkLines",
                      action="store", dest="chunkLines", help="Timestamps per chunk for historical data.")
    parser.add_option("-l", "--logLevel",
                      action="store", dest="logLevel", help="Change log verbosity(WARNING: 0, INFO: 1, DEBUG: 2)")
    (options, args) = parser.parse_args()

    params = dict()
    if options.serverUrl is None:
        params['serverUrl'] = 'http://stg.insightfinder.com'
    else:
        params['serverUrl'] = options.serverUrl
    if options.chunkLines is None:
        params['chunkLines'] = 50
    else:
        params['chunkLines'] = int(options.chunkLines)
    params['logLevel'] = logging.INFO
    if options.logLevel == '0':
        params['logLevel'] = logging.WARNING
    elif options.logLevel == '1':
        params['logLevel'] = logging.INFO
    elif options.logLevel >= '2':
        params['logLevel'] = logging.DEBUG

    return params

#
# Read and parse InsightFinder config from config.ini
#


def get_agent_config_vars():
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            user_name = config_parser.get('insightfinder', 'user_name')
            license_key = config_parser.get('insightfinder', 'license_key')
            project_name = config_parser.get('insightfinder', 'project_name')
            sampling_interval = config_parser.get('insightfinder', 'sampling_interval')
            if_http_proxy = config_parser.get('insightfinder', 'if_http_proxy')
            if_https_proxy = config_parser.get('insightfinder', 'if_https_proxy')
            host_chunk_size = int(config_parser.get('insightfinder', 'host_chunk_size'))
            metric_chunk_size = int(config_parser.get('insightfinder', 'metric_chunk_size'))
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

        config_vars = {
            "userName": user_name,
            "licenseKey": license_key,
            "projectName": project_name,
            "samplingInterval": sampling_interval,
            "hostChunkSize": host_chunk_size,
            "metricChunkSize": metric_chunk_size,
            "httpProxy": if_http_proxy,
            "httpsProxy": if_https_proxy
        }

        return config_vars
    else:
        print("Agent not correctly configured")
        logger.error(
            "Agent not correctly configured. Check config file.")
        sys.exit(1)

#
# Read and parse Sysdig config from config.ini
#


def get_sysdig_config():
    """Read and parse Sysdig config from config.ini"""
    if os.path.exists(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini"))):
        config_parser = ConfigParser.SafeConfigParser()
        config_parser.read(os.path.abspath(os.path.join(__file__, os.pardir, "config.ini")))
        try:
            sysdig_api_key = config_parser.get('sysdig', 'api_key')
            hostname = config_parser.get('sysdig', 'hostname')
            all_metrics = config_parser.get('sysdig', 'all_metrics').split(',')
            print(type(all_metrics))
            print(all_metrics)
        except ConfigParser.NoOptionError:
            logger.error(
                "Agent not correctly configured. Check config file.")
            sys.exit(1)

        if len(sysdig_api_key) == 0:
            logger.warning(
                "Agent not correctly configured(API KEY). Check config file.")
            exit()
        if len(hostname) == 0:
            logger.warning(
                "Agent not correctly configured. Check config file.")
            exit()

        sysdig_config = {
            "SYSDIG_API_KEY": sysdig_api_key,
            "HOSTNAME": hostname,
            "ALL_METRICS": all_metrics
        }
    else:
        logger.warning("No config file found. Exiting...")
        exit()

    return sysdig_config


def format_data(res):
    formated_data = []
    print(type(res))

    for data_dict in res['data']:

        instance = data_dict['d'][0] + '_' + data_dict['d'][1]
        formated_data.append({'cpu.used.percent' + '[' + instance + ']':str(data_dict['d'][2]), 'memory.used.percent' + '[' + instance + ']':str(data_dict['d'][3]), 'timestamp':str(data_dict['t']*1000)})

    print(formated_data)
    return formated_data



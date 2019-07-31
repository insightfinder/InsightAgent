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




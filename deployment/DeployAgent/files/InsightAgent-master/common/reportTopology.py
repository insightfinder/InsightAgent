# -*- coding: utf-8 -*-
import os
import time
from optparse import OptionParser
import json
import socket
import requests

usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",
    action="store", dest="homepath", help="Directory to run from")
parser.add_option("-t", "--time",
    action="store", dest="reporting_time", help="Reporting Interval")

(options, args) = parser.parse_args()


if options.homepath is None:
    homepath = os.getcwd()
else:
    homepath = options.homepath

if options.reporting_time is None:
    reporting_time = 1
else:
    reporting_time = options.reporting_time

datadir = 'data/'

LICENSEKEY = os.environ["INSIGHTFINDER_LICENSE_KEY"]
PROJECTNAME = os.environ["INSIGHTFINDER_PROJECT_NAME"]
USERNAME = os.environ["INSIGHTFINDER_USER_NAME"]
serverUrl = 'https://agent-data.insightfinder.com'

hostname = socket.gethostname().partition(".")[0]

#topology json path
json_file_path = os.path.join(homepath, datadir + "topology.json")

if os.path.exists(json_file_path):  # check if file exists
    created = os.path.getmtime(json_file_path)
    now = time.time()

    #check if the file is created/modified within the reporting interval
    if now - created <= reporting_time * 60:

        #load the topology json
        with open(json_file_path) as json_data:
            topology_json = json.load(json_data)

        #start create the output json
        result = {}
        result["metricData"] = json.dumps(topology_json)
        result["licenseKey"] = LICENSEKEY
        result["projectName"] = PROJECTNAME
        result["userName"] = USERNAME
        result["instanceName"] = hostname
        result["agentType"] = "topologyData"
        #end create output json

        #post data to server
        json_data = json.dumps(result)
        url = serverUrl + "/customprojectrawdata"
        time.sleep(5)
        response = requests.post(url, data=json.loads(json_data))
        print response

    else:
        os.remove(json_file_path)

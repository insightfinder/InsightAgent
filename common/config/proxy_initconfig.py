#!/usr/bin/python

import os
import json
from optparse import OptionParser

homepath = os.getenv("INSIGHTAGENTDIR")
usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-r", "--reporting_interval",
    action="store", dest="reporting_interval", help="Reporting interval in minute")
parser.add_option("-u", "--username",
    action="store", dest="userName", help="User name")
parser.add_option("-p", "--projectname",
    action="store", dest="projectName", help="Project name")
(options, args) = parser.parse_args()

if options.reporting_interval is None:
    reporting_interval = "5"
else:
    reporting_interval = options.reporting_interval
if homepath is None:
	homepath = os.getcwd()
if options.userName is None:
    USERNAME = os.environ["INSIGHTFINDER_USER_NAME"]
else:
    USERNAME = options.userName
if options.projectName is None:
    PROJECTNAME = os.environ["INSIGHTFINDER_PROJECT_NAME"]
else:
    PROJECTNAME = options.projectName

deltaFields = ["CPU", "DiskRead", "DiskWrite", "NetworkIn", "NetworkOut"]

#update endtime in config file
def update_configs(reporting_interval,prev_endtime,keep_file_days):
    with open(os.path.join(homepath,"proxy_reporting_config.json"),"r") as f:
        config = json.load(f)

    temp = {
        'reporting_interval' : reporting_interval,
        'prev_endtime' : prev_endtime,
        'keep_file_days' : keep_file_days,
        'delta_fields' : deltaFields
    }
    config[USERNAME + "_" +PROJECTNAME] = temp

    with open(os.path.join(homepath,"proxy_reporting_config.json"),"w") as f:
        json.dump(config, f)

update_configs(reporting_interval,"0","5")

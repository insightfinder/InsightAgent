#!/usr/bin/python

import os
import json
from optparse import OptionParser

homepath = os.getenv("INSIGHTAGENTDIR")
usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-r", "--reporting_interval",
    action="store", dest="reporting_interval", help="Reporting interval in minute")
(options, args) = parser.parse_args()

if options.reporting_interval is None:
    reporting_interval = "5"
else:
    reporting_interval = options.reporting_interval
if homepath is None:
	homepath = os.getcwd()

deltaFields = ["CPU#%", "DiskRead#MB", "DiskWrite#MB", "NetworkIn#MB", "NetworkOut#MB"]

#update endtime in config file
def update_configs(reporting_interval,prev_endtime,keep_file_days):
    config = {
        'reporting_interval' : reporting_interval,
        'prev_endtime' : prev_endtime,
        'keep_file_days' : keep_file_days,
        'delta_fields' : deltaFields
    }
    with open(os.path.join(homepath,"reporting_config.json"),"w") as f:
        json.dump(config, f)

update_configs(reporting_interval,"0","5")

#!/usr/bin/python

import os
import json
from optparse import OptionParser

homepath = os.getenv("INSIGHTAGENTDIR")
usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-u", "--username",
    action="store", dest="userName", help="User name")
parser.add_option("-p", "--projectname",
    action="store", dest="projectName", help="Project name")
(options, args) = parser.parse_args()

if options.userName is None:
    USERNAME = os.environ["INSIGHTFINDER_USER_NAME"]
else:
    USERNAME = options.userName
if options.projectName is None:
    PROJECTNAME = os.environ["INSIGHTFINDER_PROJECT_NAME"]
else:
    PROJECTNAME = options.projectName

def del_config():
    with open(os.path.join(homepath,"proxy_reporting_config.json"),"r") as f:
        config = json.load(f)

    del config[USERNAME + "_" +PROJECTNAME]

    with open(os.path.join(homepath,"proxy_reporting_config.json"),"w") as f:
        json.dump(config, f)

del_config()

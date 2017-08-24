from datadog import initialize, api
import time
import csv
import os
from optparse import OptionParser
import socket
#import ConfigParser


COMMA_DELIMITER = ","
NEWLINE_DELIMITER = "\n"


def getindex(col_name):
    if col_name == "cpu.idle":
        return 10001
    elif col_name == "cpu.system":
        return 10002
    elif col_name == "cpu.iowait":
        return 10003
    elif col_name == "cpu.user":
        return 10004
    elif col_name == "cpu.stolen":
        return 10005
    elif col_name == "cpu.guest":
        return 10006
    elif col_name == "mem.free":
        return 10007
    elif col_name == "mem.used":
        return 10008
    elif col_name == "io.await":
        return 10009
    elif col_name == "swap.free":
        return 10010
    elif col_name == "swap.used":
        return 10011
    elif col_name == "net.bytes_rcvd":
        return 10012
    elif col_name == "net.bytes_sent":
        return 10013
    elif col_name == "disk.in_use":
        return 10014
    elif col_name == "load.1":
        return 10015
    elif col_name == "load.5":
        return 10016
    elif col_name == "load.15":
        return 10017



usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",action="store", dest="homepath", help="Directory to run from")
parser.add_option("-u", "--username",
    action="store", dest="userName", help="User name")
parser.add_option("-p", "--projectname",
    action="store", dest="projectName", help="Project name")
parser.add_option("-k", "--apikey",
    action="store", dest="apiKey", help="API key")
parser.add_option("-a", "--appkey",
    action="store", dest="appKey", help="APP key")

(options, args) = parser.parse_args()

if options.homepath is None:
	homepath = os.getcwd()
else:
	homepath = options.homepath

if options.userName is None:
    USERNAME = os.environ["INSIGHTFINDER_USER_NAME"]
else:
    USERNAME = options.userName
if options.projectName is None:
    PROJECTNAME = os.environ["INSIGHTFINDER_PROJECT_NAME"]
else:
    PROJECTNAME = options.projectName
if options.apiKey is None:
    API_KEY = ""
else:
    API_KEY = options.apiKey
if options.appKey is None:
    APP_KEY = ""
else:
    APP_KEY = options.appKey


#instances=[]
#instances = [e.strip() for e in config.get('HOSTNAME', 'HOSTLIST').split(',')]

#initialization
options = {
    'api_key': API_KEY,
    'app_key': APP_KEY
}

initialize(**options)






datadir = os.path.join('data',os.path.join(USERNAME,PROJECTNAME))
date = time.strftime("%Y%m%d")
filename = os.path.join(homepath,os.path.join(datadir,date+".csv"))


#getting current time
now = int(time.time())

#use this offset to find the start time = now - offset (in secs)
offset = 60
#list of metrics to fetch
metrics_names = ['cpu.idle','cpu.system','cpu.iowait','cpu.user','cpu.stolen','cpu.guest','mem.free','mem.used','io.await','swap.free','swap.used','net.bytes_rcvd','net.bytes_sent','disk.in_use','load.1','load.5','load.15']
metrics = []
instances = []

dummy_query = 'system.cpu.idle{*}by{host}'
temp = api.Metric.query(start=now - offset, end=now, query=dummy_query)
for i in range(0,len(temp['series'])):
    instances.append(temp['series'][i]['scope'][5:])


print instances

header = 'timestamp'
query = ''
for i in instances:
    for m in metrics_names:
        #building query for api calls
        query += 'system.' + m +'{*}by{'+ i +'},'
        #building header
        header += COMMA_DELIMITER + m + "["+ i +"]:" + str(getindex(m))

query = query[:-1]
header += NEWLINE_DELIMITER

return_from_api = api.Metric.query(start=now - offset, end=now, query=query)

line = ''
line += str(now*1000)
status = return_from_api.get('status','error')


if status == 'ok' and return_from_api['series']:
    for i in range(0,len(return_from_api['series'])):

        points = return_from_api['series'][i]['pointlist']
        val = ''
        for item in points:
            if item[1] is None:
                continue
            else:
                val = item[1]
                break
        line += COMMA_DELIMITER + str(val)
    csvFile = open(filename, "a+")
    if( not (os.path.isfile(filename)) or (os.stat(filename).st_size == 0)):
        csvFile.write(header)
    line += NEWLINE_DELIMITER
    print line
    csvFile.write(line)
    csvFile.close()

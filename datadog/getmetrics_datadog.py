from datadog import initialize, api
import time
import csv
import os
from optparse import OptionParser
import socket

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



#initialization
options = {
    'api_key': os.getenv('DATADOG_API_KEY', ''),
    'app_key': os.getenv('DATADOG_APP_KEY', '')
}

initialize(**options)

usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",action="store", dest="homepath", help="Directory to run from")
(options, args) = parser.parse_args()

if options.homepath is None:
	homepath = os.getcwd()
else:
	homepath = options.homepath

datadir = 'data/'
date = time.strftime("%Y%m%d")
filename = os.path.join(homepath,datadir+date+".csv")


#getting current time
now = int(time.time())

#use this offset to find the start time = now - offset (in secs)
offset = 60
#list of metrics to fetch
metrics_names = ['cpu.idle','cpu.system','cpu.iowait','cpu.user','cpu.stolen','cpu.guest','mem.free','mem.used','io.await','swap.free','swap.used','net.bytes_rcvd','net.bytes_sent','disk.in_use','load.1','load.5','load.15']
metrics = []

header = 'timestamp'
query = ''
for m in metrics_names:
    #building query for api calls
    query += 'system.' + m +'{*}by{'+ socket.gethostname()+'},'
    #building header
    header += COMMA_DELIMITER + m + "["+socket.gethostname()+"]:" + str(getindex(m))

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
    csvFile.write(line)
    csvFile.close()

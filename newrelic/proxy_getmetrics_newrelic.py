import subprocess
import json
import os
import time
from optparse import OptionParser
import ConfigParser
import datetime

COMMA_DELIMITER = ","
NEWLINE_DELIMITER = "\n"

def getindex(col_name):
    if col_name == "cpu":
        return 11001
    elif col_name == "cpu_stolen":
        return 11002
    elif col_name == "disk_io":
        return 11003
    elif col_name == "memory":
        return 11004
    elif col_name == "memory_used":
        return 11005
    elif col_name == "memory_total":
        return 11006
    elif col_name == "fullest_disk":
        return 11007
    elif col_name == "fullest_disk_free":
        return 11008
    elif col_name == "memory_swap":
        return 11009
    elif col_name == "cpu_load":
        return 11010
    elif col_name == "bytes_sent":
        return 11011
    elif col_name == "bytes_rcvd":
        return 11012
    elif col_name == "response_time":
        return 11013
    elif col_name == "throughput":
        return 11014
    elif col_name == "error_rate":
        return 11015
    elif col_name == "apdex_target":
        return 11016
    elif col_name == "apdex_score":
        return 11017

usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",
    action="store", dest="homepath", help="Directory to run from")
parser.add_option("-u", "--username",
    action="store", dest="userName", help="User name")
parser.add_option("-p", "--projectname",
    action="store", dest="projectName", help="Project name")
parser.add_option("-k", "--apikey",
    action="store", dest="apiKey", help="API key")
parser.add_option("-s", "--samplinginterval",
    action="store", dest="samplingInterval", help="Sampling Interval")
(options, args) = parser.parse_args()

tstamp = int(time.time())


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
if options.samplingInterval is None:
    min_diff = '5'
else:
    min_diff = options.samplingInterval


now = datetime.datetime.utcnow()
before = now - datetime.timedelta(minutes=int(min_diff)) # sampling interval
now = now.isoformat().split('.')[0] + '+00:00'
before = before.isoformat().split('.')[0] + '+00:00'

if options.homepath is None:
	homepath = os.getcwd()
else:
	homepath = options.homepath

#config = ConfigParser.ConfigParser()

#instance_file = os.path.join(homepath,"newrelic/newrelic.cfg");
#config.read(instance_file)

#instances=[]
#instances = [e.strip() for e in config.get('HOSTNAME', 'HOSTLIST').split(',')]

#app_instances=[]
#app_instances = [e.strip() for e in config.get('APPNAME', 'APPLIST').split(',')]


datadir = os.path.join('data',os.path.join(USERNAME,PROJECTNAME))
date = time.strftime("%Y%m%d")
filename = os.path.join(homepath,os.path.join(datadir,date+".csv"))



req = 'curl -X GET "https://api.newrelic.com/v2/servers.json"  -H "X-Api-Key:' + API_KEY + '" -i'
proc = subprocess.Popen([req] , stdout=subprocess.PIPE,stderr=subprocess.PIPE , shell=True)
(out,err) = proc.communicate()
outlist = out.split("\n")
status = outlist[6]

metric = {}

colvalues = ['cpu' , 'cpu_stolen' , 'disk_io' , 'memory' , 'memory_used' , 'memory_total' , 'fullest_disk' , 'fullest_disk_free']

add_colvalues = {'System/Swap/Used/bytes' : 'memory_swap' ,  'System/Load' : 'cpu_load' , 'System/Network/All/Received/bytes/sec' : 'bytes_rcvd' , 'System/Network/All/Transmitted/bytes/sec' : 'bytes_sent'}


query_d = ''
for key in add_colvalues:
    query_d += 'names[]=' + key + '&'
query_d += 'values[]=average_value&summarize=true'
query_d += '&from=' + before
query_d += '&to=' + now


if "OK" in status:
    output = json.loads(outlist[14])
    for i in range(0,len(output['servers'])):
        name = output['servers'][i]['name']
        sid = output['servers'][i]['id']
        reporting = output['servers'][i]['reporting']
        if reporting:
            tempdict = {}
            tempdict['id'] = sid
            for val in colvalues:
                tempdict[val] = output['servers'][i]['summary'][val]

            inner_req = 'curl -X GET "https://api.newrelic.com/v2/servers/' + str(sid) + '/metrics/data.json" -H "X-Api-Key:' + API_KEY + '" -i -d "' + query_d + '"'
            inner_proc = subprocess.Popen([inner_req] , stdout=subprocess.PIPE,stderr=subprocess.PIPE , shell=True)
            (inner_out,inner_err) = inner_proc.communicate()
            inner_outlist = inner_out.split("\n")
            inner_status = inner_outlist[6]

            if "OK" in inner_status:
                inner_output = json.loads(inner_outlist[14])
                inner_output = inner_output['metric_data']['metrics']
                for i in range(0,len(inner_output)):
                    tempdict[add_colvalues[inner_output[i]['name']]] = inner_output[i]['timeslices'][0]['values']['average_value']
            metric[name]= tempdict
    header = 'timestamp'
    line = str(tstamp*1000)

    print metric

    for key in metric:
        if "OK" in status:
            for val in colvalues:
                header += COMMA_DELIMITER + val + '[' + key + ']:'+ str(getindex(val))
                line += COMMA_DELIMITER + str(metric[key][val])
                
        if "OK" in inner_status:
            for tempval in add_colvalues:
                val = add_colvalues[tempval]
                header += COMMA_DELIMITER + val + '[' + key + ']:'+ str(getindex(val))
                line += COMMA_DELIMITER + str(metric[key][val])

app_req = 'curl -X GET "https://api.newrelic.com/v2/applications.json"  -H "X-Api-Key:' + API_KEY + '" -i'
app_proc = subprocess.Popen([app_req] , stdout=subprocess.PIPE,stderr=subprocess.PIPE , shell=True)
(app_out,app_err) = app_proc.communicate()
app_outlist = app_out.split("\n")
app_status = app_outlist[6]

app_colvalues = ['response_time' , 'throughput' , 'error_rate' , 'apdex_target' , 'apdex_score']

app_metric = {}

if "OK" in status:
    app_output = json.loads(app_outlist[14])
    #print len(app_output['applications'])
    for i in range(0,len(app_output['applications'])):
        name = app_output['applications'][i]['name']
        sid = app_output['applications'][i]['id']
        reporting = app_output['applications'][i]['reporting']
        if reporting:
            #print output['applications'][i]
            tempdict = {}
            tempdict['id'] = sid
            for val in app_colvalues:
                tempdict[val] = app_output['applications'][i]['application_summary'][val]

            app_metric[name]= tempdict

    for key in app_metric:
        for val in app_colvalues:
            header += COMMA_DELIMITER + val + '[' + key + ']:'+ str(getindex(val))
            line += COMMA_DELIMITER + str(app_metric[key][val])

print line
print header


if "OK" in app_status or "OK" in status:
    header += NEWLINE_DELIMITER
    line += NEWLINE_DELIMITER
    csvFile = open(filename, "a+")
    if( not (os.path.isfile(filename)) or (os.stat(filename).st_size == 0)):
        csvFile.write(header)
    csvFile.write(line)
    csvFile.close()

import csv
import time
from optparse import OptionParser
import os
import json
import math
import socket
import collections
import sys
import subprocess
import requests
import datetime
import itertools

serverUrl = 'https://agent-data.insightfinder.com'
usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",
    action="store", dest="homepath", help="Directory to run from")
parser.add_option("-w", "--serverUrl",
    action="store", dest="serverUrl", help="Server Url")
(options, args) = parser.parse_args()

if options.homepath is None:
    homepath = os.getcwd()
else:
    homepath = options.homepath

#For calling reportCustomMetrics from '../common' directory.
sys.path.insert(0, os.path.join(homepath,'common'))
import reportCustomMetrics


if options.serverUrl != None:
    serverUrl = options.serverUrl

datadir = "data/"

command = ['bash', '-c', 'source ' + str(homepath) + '/.agent.bashrc && env']
proc = subprocess.Popen(command, stdout = subprocess.PIPE)
for line in proc.stdout:
  (key, _, value) = line.partition("=")
  os.environ[key] = value.strip()
proc.communicate()

LICENSEKEY = os.environ["INSIGHTFINDER_LICENSE_KEY"]
PROJECTNAME = os.environ["INSIGHTFINDER_PROJECT_NAME"]
USERNAME = os.environ["INSIGHTFINDER_USER_NAME"]

with open(os.path.join(homepath,"reporting_config.json"), 'r') as f:
    config = json.load(f)

reporting_interval_string = config['reporting_interval']
is_second_reporting = False
if reporting_interval_string[-1:]=='s':
    is_second_reporting = True
    reporting_interval = float(config['reporting_interval'][:-1])
    reporting_interval = float(reporting_interval/60)
else:
    reporting_interval = int(config['reporting_interval'])
keep_file_days = int(config['keep_file_days'])
prev_endtime = config['prev_endtime']
deltaFields = config['delta_fields']

new_prev_endtime_epoch = 0
hostname = socket.getfqdn()
hostnameShort = socket.gethostname().partition(".")[0]
csvpath = "/var/lib/collectd/csv/"+ hostnameShort
if not os.path.exists(csvpath):
    csvpath = "/var/lib/collectd/csv/"+ hostname
if not os.path.exists(csvpath):
    directoryList = os.listdir("/var/lib/collectd/csv")
    if len(directoryList)>0:
        csvpath = "/var/lib/collectd/csv/"+ directoryList[0]

date = time.strftime("%Y-%m-%d")

#deletes old csv files from a directory
def remove_old_files(directory, filetype):
    now = datetime.datetime.now()
    now_time = now.time()
    # time between which each day the deletion is done
    if now_time >= datetime.time(06,30) and now_time <= datetime.time(20,35):
        # data directory path
        data_file_path = directory
        # data_file_path = os.path.join(homepath,datadir)
        now = time.time()
        for f in os.listdir(data_file_path):
            data_file = os.path.join(data_file_path, f)
            #check files older than 3 days
            if os.stat(data_file).st_mtime < now - 2 * 86400:
                #only delete csv files
                if filetype is None:
                    if os.path.isfile(data_file):
                        os.remove(data_file)
                else:
                    if str(filetype) in str(os.path.splitext(data_file)[1]):
                        if os.path.isfile(data_file):
                            os.remove(data_file)

def getindex(col_name):
    if col_name == "CPU":
        return 7001
    elif col_name == "DiskRead" or col_name == "DiskWrite":
        return 7002
    elif col_name == "DiskUsed":
        return 7003
    elif col_name == "NetworkIn" or col_name == "NetworkOut":
        return 7004
    elif col_name == "MemUsed":
        return 7005
    elif "DiskUsed" in col_name:
        return 7006
    elif "LoadAvg" in col_name:
        return 7007
    elif "Process" in col_name:
        return 7008

def update_results(lists):
    with open(os.path.join(homepath,datadir+"previous_results.json"),'w') as f:
        json.dump(lists,f)

def get_previous_results():
    with open(os.path.join(homepath,datadir+"previous_results.json"),'r') as f:
        return json.load(f)

if prev_endtime != "0":
    start_time = prev_endtime
    # pad a second after prev_endtime
    start_time_epoch = 1000+long(1000*time.mktime(time.strptime(start_time, "%Y%m%d%H%M%S")));
    end_time_epoch = start_time_epoch + 1000*60*reporting_interval
    start_time_epoch = start_time_epoch/1000
else: # prev_endtime == 0
    end_time_epoch = int(time.time())*1000
    start_time_epoch = end_time_epoch - 1000*60*reporting_interval
    start_time_epoch = start_time_epoch/1000

#update prev_endtime in config file
def update_timestamp(prev_endtime):
    with open(os.path.join(homepath,"reporting_config.json"), 'r') as f:
        config = json.load(f)
    config['prev_endtime'] = prev_endtime
    with open(os.path.join(homepath,"reporting_config.json"),"w") as f:
        json.dump(config, f)

#send data to insightfinder
def sendData():
    global metricData
    if len(metricData) == 0:
        return
    #update projectKey, userName in dict
    alldata["metricData"] = json.dumps(metricData)
    alldata["licenseKey"] = LICENSEKEY
    alldata["projectName"] = PROJECTNAME
    alldata["userName"] = USERNAME
    alldata["instanceName"] = hostname

    #print the json
    json_data = json.dumps(alldata)
    #print json_data
    print str(len(bytearray(json_data))) + " Bytes data are reported"
    url = serverUrl + "/customprojectrawdata"
    response = requests.post(url, data=json.loads(json_data))

fieldnames = []
log = []
allLog = []
alldata = {}
contentsNum = 0
rawData = collections.OrderedDict()
filenames = {'cpu/percent-active-': ['CPU'], 'memory/memory-used-': ['MemUsed'], 'load/load-': ['LoadAvg1', 'LoadAvg5', 'LoadAvg15'],\
             'processes/ps_state-blocked-': ['BlockedProcess'], 'processes/ps_state-paging-': ['PagingProcess'], 'processes/ps_state-running-': ['RunningProcess'], \
             'processes/ps_state-sleeping-': ['SleepingProcess'], 'processes/ps_state-stopped-': ['StoppedProcess'], 'processes/ps_state-zombies-': ['ZombieProcess']}
allDirectories = os.listdir(csvpath)
# remove old csv files in datadir
remove_old_files(os.path.join(homepath,datadir), 'csv')
for eachdir in allDirectories:
    # remove old collectd log files
    remove_old_files(os.path.join(csvpath, eachdir), None)
    if "disk" in eachdir:
        filenames[eachdir+"/disk_octets-"] = [eachdir+'_DiskWrite', eachdir+'_DiskRead']
    if "interface" in eachdir:
        filenames[eachdir+"/if_octets-"] = [eachdir+'_NetworkIn', eachdir+'_NetworkOut']
allLatestTimestamps = []

fileNamesToAdd = []
aggregateCPU = False
#Calculate average CPU
for fEntry in os.walk(os.path.join(csvpath)):
    if "cpu-" in fEntry[0]:
	aggregateCPU = True
        filenames['aggregation-cpu-average/cpu-system-'] = ['CPU']

for eachfile in filenames:
    if "cpu/percent-active" in eachfile and aggregateCPU == True:
        continue;
    if "aggregation-cpu-average/cpu-system" in eachfile and aggregateCPU == True:
	    csvfile1 = open(os.path.join(csvpath,eachfile+date))
	    csvfile2 = open(os.path.join(csvpath,'aggregation-cpu-average/cpu-user-'+date))
	    csvfile3 = open(os.path.join(csvpath,'aggregation-cpu-average/cpu-idle-'+date))
	    reader1 = csv.reader(csvfile1)
	    reader2 = csv.reader(csvfile2)
	    reader3 = csv.reader(csvfile3)
	    for row, row1, row2 in itertools.izip(reader1, reader2, reader3):
		if reader1.line_num > 1:
		    if long(int(float(row[0]))) < long(start_time_epoch) :
			continue
		    timestampStr = str(int(float(row[0])))
		    new_prev_endtime_epoch = long(timestampStr) * 1000.0
		    if timestampStr in rawData:
			valueList = rawData[timestampStr]
			total = float(row[1]) + float(row1[1]) + float(row2[1])
			idle = float(row2[1])
			result = 1 - round(float(idle/total),4)
			print "result " + str(round((1 - float(idle/total)),4)) + " T=" + str(total) + " i=" + str(idle) 
			valueList[filenames[eachfile][0]] = str(round((1 - float(idle/total))*100,4))
			rawData[timestampStr] = valueList
		    else:
			valueList = {}
			total = float(row[1]) + float(row1[1]) + float(row2[1])
			idle = float(row2[1])
			result = 1 - round(float(idle/total),4)
			print "result " + str(round((1 - float(idle/total)),4)) + " T=" + str(total) + " i=" + str(idle) 
			valueList[filenames[eachfile][0]] = str(round((1 - float(idle/total))*100,4))
			rawData[timestampStr] = valueList
	    allLatestTimestamps.append(new_prev_endtime_epoch)
	    aggregateCPU = False
    else:
	    try:
        	csvfile = open(os.path.join(csvpath,eachfile+date))
        	reader = csv.reader(csvfile)
    	    except IOError:
        	continue
	    for row in reader:
		if reader.line_num > 1:
		    if long(int(float(row[0]))) < long(start_time_epoch) :
			continue
		    timestampStr = str(int(float(row[0])))
		    new_prev_endtime_epoch = long(timestampStr) * 1000.0
		    if timestampStr in rawData:
			valueList = rawData[timestampStr]
			valueList[filenames[eachfile][0]] = row[1]
			if ("disk" in eachfile) or ("interface" in eachfile):
			    valueList[filenames[eachfile][1]] = row[2]
			elif "load" in eachfile:
			    valueList[filenames[eachfile][1]] = row[2]
			    valueList[filenames[eachfile][2]] = row[3]
			rawData[timestampStr] = valueList
		    else:
			valueList = {}
			valueList[filenames[eachfile][0]]= row[1]
			if ("disk" in eachfile) or ("interface" in eachfile):
			    valueList[filenames[eachfile][1]] = row[2]
			elif "load" in eachfile:
			    valueList[filenames[eachfile][1]] = row[2]
			    valueList[filenames[eachfile][2]] = row[3]
			rawData[timestampStr] = valueList
	    allLatestTimestamps.append(new_prev_endtime_epoch)
new_prev_endtime_epoch = max(allLatestTimestamps)


metricData = []
metricList = ["CPU", "MemUsed", "DiskWrite", "DiskRead", "NetworkIn", "NetworkOut", "LoadAvg1", "LoadAvg5", "LoadAvg15", \
              "BlockedProcess", "PagingProcess", "RunningProcess", "SleepingProcess", "StoppedProcess", "ZombieProcess"]
deltaFields = ["DiskRead", "DiskWrite", "NetworkIn", "NetworkOut"]
previousResult = {}
thisData = {}
if os.path.isfile(os.path.join(homepath,datadir+"previous_results.json")) == False:
    previousResult = {}
else:
    previousResult = get_previous_results()

if bool(rawData) == False:
    print "No data is reported"
    sys.exit()

for eachtimestamp in rawData:
    data = rawData[eachtimestamp]
    thisData = {}
    thisData['timestamp'] = str(int(eachtimestamp)*1000)
    diskread = diskwrite = networkin = networkout = 0
    newResult = {}
    for eachmetric in metricList:
        if eachmetric == "DiskWrite" or eachmetric == "DiskRead" or eachmetric == "NetworkIn" or eachmetric == "NetworkOut":
            for eachdata in data:
                if "DiskWrite" in eachdata:
                    diskwrite += float(data[eachdata])
                if "DiskRead" in eachdata:
                    diskread += float(data[eachdata])
                if "NetworkIn" in eachdata:
                    networkin = float(data[eachdata])
                if "NetworkOut" in eachdata:
                    networkout = float(data[eachdata])
        if (eachmetric not in data) and eachmetric != "DiskRead" and eachmetric != "DiskWrite" and eachmetric != "NetworkIn" and eachmetric != "NetworkOut":
            finalMetricName = str(eachmetric) + "[" + str(hostnameShort) + "]:" + str(getindex(eachmetric))
            thisData[finalMetricName] = "NaN"
            continue
        else:
            finalMetricName = str(eachmetric) + "[" + str(hostnameShort) + "]:" + str(getindex(eachmetric))
            if eachmetric == "DiskWrite":
                thisData[finalMetricName] = str(float(float(diskwrite)/(1024*1024)))
            elif eachmetric == "DiskRead":
                thisData[finalMetricName] = str(float(float(diskread)/(1024*1024)))
            elif eachmetric == "NetworkIn":
                thisData[finalMetricName] = str(float(float(networkin)/(1024*1024)))
            elif eachmetric == "NetworkOut":
                thisData[finalMetricName] = str(float(float(networkout)/(1024*1024)))
            elif eachmetric == "MemUsed":
                thisData[finalMetricName] = str(float(float(data[eachmetric])/(1024*1024)))
            else:
                thisData[finalMetricName] = str(data[eachmetric])
            newResult[finalMetricName] = thisData[finalMetricName]
            if eachmetric in deltaFields:
                if finalMetricName in previousResult:
                    thisData[finalMetricName] = str(abs(float(thisData[finalMetricName]) - float(previousResult[finalMetricName])))
                else:
                    thisData[finalMetricName] = "NaN"
    previousResult = newResult
    metricData.append(thisData)

update_results(previousResult)


#update endtime in config
if new_prev_endtime_epoch == 0:
    print "No data is reported"
else:
    new_prev_endtimeinsec = math.ceil(long(new_prev_endtime_epoch)/1000.0)
    new_prev_endtime = time.strftime("%Y%m%d%H%M%S", time.localtime(long(new_prev_endtimeinsec)))
    update_timestamp(new_prev_endtime)
    sendData()

#Update custom Metrics
reported = reportCustomMetrics.getcustommetrics(serverUrl, PROJECTNAME, USERNAME, LICENSEKEY, homepath)
if reported:
    print "Custom metrics sent"
else:
    print "Failed to send custom metrics"

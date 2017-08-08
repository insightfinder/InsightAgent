#!/usr/bin/python
##TODO: This file needs to be refactored when time permits
import csv
import json
import os
import time
import subprocess
import datetime
import socket
from optparse import OptionParser
import math
import reportCustomMetrics

'''
this script reads reporting interval and prev endtime config2
and opens daily log file and reports header + rows within
window of reporting interval after prev endtime
if prev endtime is 0, report most recent reporting interval
till now from today's log file (may or may not be present)
assumping gmt epoch timestamp and local date daily file
'''
serverUrl = 'https://agent-data.insightfinder.com'
#serverUrl = 'http://localhost:8080'
usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-f", "--fileInput",
    action="store", dest="inputFile", help="Input data file (overriding daily data file)")
parser.add_option("-m", "--mode",
    action="store", dest="mode", help="Running mode: live or metricFileReplay or logFileReplay")
parser.add_option("-d", "--directory",
    action="store", dest="homepath", help="Directory to run from")
parser.add_option("-t", "--agentType",
    action="store", dest="agentType", help="Agent type")
parser.add_option("-w", "--serverUrl",
    action="store", dest="serverUrl", help="Server Url")
parser.add_option("-s", "--splitID",
    action="store", dest="splitID", help="The split ID to use when grouping results on the server")
parser.add_option("-g", "--splitBy",
    action="store", dest="splitBy", help="The 'split by' to use when grouping results on the server. Examples: splitByEnv, splitByGroup")
(options, args) = parser.parse_args()

if options.homepath is None:
    homepath = os.getcwd()
else:
    homepath = options.homepath
if options.mode is None:
    mode = "live"
else:
    mode = options.mode
if options.agentType is None:
    agentType = ""
else:
    agentType = options.agentType
if options.serverUrl != None:
    serverUrl = options.serverUrl
##Optional split id and split by for metric file replay
if options.splitID is None:
    splitID = None 
else:
    splitID = options.splitID
if options.splitBy is None:
    splitBy = None
else:
    splitBy = options.splitBy

datadir = 'data/'

if agentType == "hypervisor":
    import urllib
    command = ['sh', '-c', 'source ' + str(homepath) + '/.agent.bashrc && env']
else:
    import requests
    command = ['bash', '-c', 'source ' + str(homepath) + '/.agent.bashrc && env']

proc = subprocess.Popen(command, stdout = subprocess.PIPE)
for line in proc.stdout:
  (key, _, value) = line.partition("=")
  os.environ[key] = value.strip()
proc.communicate()

LICENSEKEY = os.environ["INSIGHTFINDER_LICENSE_KEY"]
PROJECTNAME = os.environ["INSIGHTFINDER_PROJECT_NAME"]
USERNAME = os.environ["INSIGHTFINDER_USER_NAME"]


reportedDataSize = 0
totalSize = 0
firstData = False
chunkSize = 0
totalChunks = 0
currentChunk = 1
def getindex(col_name):
    if col_name == "CPU":
        return 1
    elif col_name == "DiskRead" or col_name == "DiskWrite":
        return 2
    elif col_name == "DiskUsed":
        return 3
    elif col_name == "NetworkIn" or col_name == "NetworkOut":
        return 4
    elif col_name == "MemUsed":
        return 5

#update prev_endtime in config file
def update_timestamp(prev_endtime):
    with open(os.path.join(homepath,"reporting_config.json"), 'r') as f:
        config = json.load(f)
    config['prev_endtime'] = prev_endtime
    with open(os.path.join(homepath,"reporting_config.json"),"w") as f:
        json.dump(config, f)

def getTotalSize(iFile):
    filejson = open(os.path.join(homepath, iFile))
    allJsonData = []
    jsonData = json.load(filejson)
    for row in jsonData:
        allJsonData.append(row)
    filejson.close()
    return len(bytearray(json.dumps(allJsonData)))

def ec2InstanceType():
    url = "http://169.254.169.254/latest/meta-data/instance-type"
    try:
        response = requests.post(url)
    except requests.ConnectionError, e:
        print "Error finding instance-type"
        return
    if response.status_code != 200:
        print "Error finding instance-type"
        return
    instanceType = response.text
    return instanceType
#send data to insightfinder
reportedChunks = 0
def sendData():
    global reportedDataSize
    global firstData
    global chunkSize
    global totalChunks
    global currentChunk
    global totalSize
    global minTimestampEpoch
    global maxTimestampEpoch
    global splitID
    global splitBy
    global reportedChunks
    if len(metricData) == 0:
        return
    #update projectKey, userName in dict
    alldata["metricData"] = json.dumps(metricData)
    alldata["licenseKey"] = LICENSEKEY
    alldata["projectName"] = PROJECTNAME
    alldata["userName"] = USERNAME
    alldata["instanceName"] = hostname
    if agentType == "ec2monitoring":
        alldata["instanceType"] = ec2InstanceType()

    #print the json
    json_data = json.dumps(alldata)
    if "FileReplay" in mode:
        reportedDataSize += len(bytearray(json.dumps(metricData)))
        if firstData == False:
            chunkSize = reportedDataSize
            firstData = True
            totalChunks = int(math.ceil(float(totalSize)/float(chunkSize)))
	    #This is a hack fix and should be fixed. Pushing the fix off until we refactor this file.
	#    if mode == "metricFileReplay":
	 #     totalChunks = totalChunks-1
    	alldata["minTimestamp"] = minTimestampEpoch
    	alldata["maxTimestamp"] = maxTimestampEpoch
        reportedDataPer = (float(reportedDataSize)/float(totalSize))*100
        reportedChunks += 1
        print str(reportedChunks) + " out of " + str(totalChunkCount)+" are reported"
        alldata["chunkSerialNumber"] = str(currentChunk)
        alldata["chunkTotalNumber"] = str(totalChunkCount)
	if(not splitID == None and not splitBy == None):
	  alldata["splitID"] = splitID
	  alldata["splitBy"] = splitBy
        currentChunk += 1
        if mode == "logFileReplay":
            alldata["agentType"] = "LogFileReplay"
        if mode == "metricFileReplay":
            alldata["agentType"] = "MetricFileReplay"
    else:
        print str(len(bytearray(json_data))) + " bytes data are reported"
    #print the json
    json_data = json.dumps(alldata)
    #print json_data
    url = serverUrl + "/customprojectrawdata"
    if agentType == "hypervisor":
        response = urllib.urlopen(url, data=urllib.urlencode(alldata))
    else:
        response = requests.post(url, data=json.loads(json_data))

def updateAgentDataRange(minTS,maxTS):
    #update projectKey, userName in dict
    helperdata["licenseKey"] = LICENSEKEY
    helperdata["projectName"] = PROJECTNAME
    helperdata["userName"] = USERNAME
    helperdata["operation"] = "updateAgentDataRange"
    helperdata["minTimestamp"] = minTS
    helperdata["maxTimestamp"] = maxTS

    #print the json
    json_data = json.dumps(helperdata)
    #print json_data
    url = serverUrl + "/agentdatahelper"
    response = requests.post(url, data=json.loads(json_data))


#main
with open(os.path.join(homepath,"reporting_config.json"), 'r') as f:
    config = json.load(f)
reporting_interval = int(config['reporting_interval'])
keep_file_days = int(config['keep_file_days'])
prev_endtime = config['prev_endtime']
deltaFields = config['delta_fields']

#locate time range and date range
new_prev_endtime = prev_endtime
new_prev_endtime_epoch = 0
dates = []
if "FileReplay" in mode and prev_endtime != "0" and len(prev_endtime) >= 8:
    start_time = prev_endtime
    # pad a second after prev_endtime
    start_time_epoch = 1000+long(1000*time.mktime(time.strptime(start_time, "%Y%m%d%H%M%S")));
    end_time_epoch = start_time_epoch + 1000*60*reporting_interval
elif prev_endtime != "0":
    start_time = prev_endtime
    # pad a second after prev_endtime
    start_time_epoch = 1000+long(1000*time.mktime(time.strptime(start_time, "%Y%m%d%H%M%S")));
    end_time_epoch = start_time_epoch + 1000*60*reporting_interval
else: # prev_endtime == 0
    end_time_epoch = int(time.time())*1000
    start_time_epoch = end_time_epoch - 1000*60*reporting_interval

alldata = {}
helperdata = {}
metricData = []
fieldnames = []
idxdate = 0
hostname = socket.gethostname().partition(".")[0]
minTimestampEpoch = 0
maxTimestampEpoch = 0
totalChunkCount = 0
chunkMaxSize = 7000000
chunkingPadding = 30000
if options.inputFile is None:
    for i in range(0,2+int(float(reporting_interval)/24/60)):
        dates.append(time.strftime("%Y%m%d", time.localtime(start_time_epoch/1000 + 60*60*24*i)))
    for date in dates:
        if agentType == "kafka":
            fileadd = "_kafka"
        elif agentType == "elasticsearch-storage":
            fileadd = "_es"
        else:
            fileadd = ""

        if os.path.isfile(os.path.join(homepath, datadir + date + fileadd + ".csv")):
            dailyFile = open(os.path.join(homepath, datadir + date + fileadd + ".csv"))
            dailyFileReader = csv.reader(dailyFile)
            for row in dailyFileReader:
                if idxdate == 0 and dailyFileReader.line_num == 1:
                    #Get all the metric names
                    fieldnames = row
                    for i in range(0,len(fieldnames)):
                        if fieldnames[i] == "timestamp":
                            timestamp_index = i
                elif dailyFileReader.line_num > 1:
                    if long(row[timestamp_index]) < long(start_time_epoch) :
                        continue
                    #Read each line from csv and generate a json
                    thisData = {}
                    for i in range(0,len(row)):
                        if fieldnames[i] == "timestamp":
                            new_prev_endtime_epoch = row[timestamp_index]
                            thisData[fieldnames[i]] = row[i]
                        else:
                            colname = fieldnames[i]
                            if colname.find("]") == -1:
                                colname = colname+"["+hostname+"]"
                            if colname.find(":") == -1:
                                groupid = getindex(fieldnames[i])
                                colname = colname+":"+str(groupid)
                            thisData[colname] = row[i]
                    metricData.append(thisData)
            dailyFile.close()
            idxdate += 1
    #update endtime in config
    if new_prev_endtime_epoch == 0:
        print "No data is reported"
    else:
        new_prev_endtimeinsec = math.ceil(long(new_prev_endtime_epoch)/1000.0)
        new_prev_endtime = time.strftime("%Y%m%d%H%M%S", time.localtime(long(new_prev_endtimeinsec)))
        update_timestamp(new_prev_endtime)
        sendData()
else:
    if os.path.isfile(os.path.join(homepath,options.inputFile)):
        numlines = len(open(os.path.join(homepath,options.inputFile)).readlines())
        file = open(os.path.join(homepath,options.inputFile))
        metricdataSizeKnown = False
        metricdataSize = 0
        if mode == "logFileReplay":
            jsonData = json.load(file)
            numlines = len(jsonData)
            maxSize = 0
            for row in jsonData:
               #calculate largest log
               if len(bytearray(json.dumps(row))) > maxSize:
                   maxSize = len(bytearray(json.dumps(row)))
            maxAmount = chunkMaxSize/(maxSize + chunkingPadding)
            totalChunkCount = int(math.ceil(float(numlines) / float(maxAmount))) 
            for row in jsonData:
                new_prev_endtime_epoch = row[row.keys()[0]]
                if minTimestampEpoch == 0 or minTimestampEpoch > long(new_prev_endtime_epoch):
                    minTimestampEpoch = long(new_prev_endtime_epoch)
                if maxTimestampEpoch == 0 or maxTimestampEpoch < long(new_prev_endtime_epoch):
                    maxTimestampEpoch = long(new_prev_endtime_epoch)
                metricData.append(row)
                if metricdataSizeKnown == False:
                    metricdataSize = len(bytearray(json.dumps(metricData)))
                    metricdataSizeKnown = True
                    totalSize = getTotalSize(options.inputFile)
                if ((len(metricData)) < maxAmount):  # Not using exact 750KB as some data will be padded later
                    continue
                else:
                    sendData()
                    metricData = []
            sendData()
        else:
            fileReader = csv.reader(file)
            metricDatas = []
            for row in fileReader:
                if fileReader.line_num == 1:
                    #Get all the metric names
                    fieldnames = row
                    for i in range(0,len(fieldnames)):
                        if fieldnames[i] == "timestamp":
                            timestamp_index = i
                elif fileReader.line_num > 1:
                    #Read each line from csv and generate a json
                    thisData = {}
                    for i in range(0,len(row)):
                        if fieldnames[i] == "timestamp":
                            new_prev_endtime_epoch = row[timestamp_index]
                            thisData[fieldnames[i]] = row[i]
                            # update min/max timestamp epoch
                            if minTimestampEpoch == 0 or minTimestampEpoch > long(new_prev_endtime_epoch):
                                minTimestampEpoch = long(new_prev_endtime_epoch)
                            if maxTimestampEpoch == 0 or maxTimestampEpoch < long(new_prev_endtime_epoch):
                                maxTimestampEpoch = long(new_prev_endtime_epoch)
                        else:
                            colname = fieldnames[i]
                            if colname.find("]") == -1:
                                colname = colname+"[-]"
                            if colname.find(":") == -1:
                                groupid = i
                                colname = colname+":"+str(groupid)
                            thisData[colname] = row[i]
                    metricDatas.append(thisData)
            if metricdataSizeKnown == False:
                    metricdataSize = len(bytearray(json.dumps(metricDatas)))
                    metricdataSizeKnown = True
                    totalSize = metricdataSize * (numlines - 1) # -1 for header
            maxSize = 0
            numlines = len(metricDatas)
            for entry in metricDatas:
                if len(bytearray(json.dumps(row))) > maxSize:
                    maxSize = len(bytearray(json.dumps(row)))
            maxAmount = chunkMaxSize/(maxSize + chunkingPadding)
            totalChunkCount = int(math.ceil(float(numlines) / float(maxAmount)))
            
            for entry in metricDatas:
                metricData.append(entry)
                if len(metricData) < maxAmount:
                    continue;
                else:
                    sendData()
                    metricData = []
            sendData()
        file.close()
        updateAgentDataRange(minTimestampEpoch,maxTimestampEpoch)

#old file cleaning
for dirpath, dirnames, filenames in os.walk(os.path.join(homepath,datadir)):
    for file in filenames:
        if ".csv" not in file:
            continue
        curpath = os.path.join(dirpath, file)
        file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(curpath))
        if datetime.datetime.now() - file_modified > datetime.timedelta(days=keep_file_days):
            os.rename(curpath,os.path.join("/tmp",file))

#Update custom Metrics
reported = reportCustomMetrics.getcustommetrics(serverUrl, PROJECTNAME, USERNAME, LICENSEKEY, homepath)
if reported:
    print "Custom metrics sent"
else:
    print "Failed to send custom metrics"


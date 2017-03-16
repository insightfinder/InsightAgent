#!/usr/bin/python

import csv
import json
import os
import glob
import time
import subprocess
import datetime
import socket
from optparse import OptionParser
import math

'''
this script reads reporting interval and prev endtime config2
and opens daily log file and reports header + rows within
window of reporting interval after prev endtime
if prev endtime is 0, report most recent reporting interval
till now from today's log file (may or may not be present)
assuming gmt epoch timestamp and local date daily file
'''

usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",
    action="store", dest="homepath", help="Directory to run from")
parser.add_option("-f", "--fileInput",
    action="store", dest="inputFile", help="Input data file (overriding daily data file)")
parser.add_option("-m", "--mode",
    action="store", dest="mode", help="Running mode: live or metricFileReplay or logFileReplay or logStreaming")
parser.add_option("-t", "--agentType",
    action="store", dest="agentType", help="Agent type")
(options, args) = parser.parse_args()

if options.homepath is None:
    homepath = os.getcwd()
else:
    homepath = options.homepath

datapath = '/tmp'
if options.inputFile is None:
    options.inputFile = max(glob.iglob(os.path.join(datapath,'insightfinder-log*')), key=os.path.getmtime)
    inputFile = options.inputFile
else:
    inputFile = options.inputFile

if options.mode is None:
    mode = "live"
else:
    mode = options.mode

if options.agentType is None:
    agentType = ""
else:
    agentType = options.agentType


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
serverUrl = 'https://insightfinderstaging.appspot.com'

reportedDataSize = 0
totalSize = 0
firstData = False
chunkSize = 0
totalChunks = 0
currentChunk = 1
metaData = {}
prev_endtime = "0"
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

def deleteContent(pfile):
    with open(os.path.join(homepath, options.inputFile), 'w') as fd:
        fd.close()

#update prev_endtime in config file
def update_timestamp(prev_endtime):
    with open(os.path.join(homepath,"reporting_config.json"), 'r') as f:
        config = json.load(f)
    config['prev_endtime'] = prev_endtime
    with open(os.path.join(homepath,"reporting_config.json"),"w") as f:
        json.dump(config, f)

def getLogMetaData(projectName, userName):
    global totalChunks
    global currentChunk
    global totalSize
    global reportedDataSize
    global metaData
    global prev_endtime
    with open(os.path.join(homepath, "log_meta_data.json"), 'r') as f:
        metaData = json.load(f)
    if projectName + userName in metaData:
        projectData = metaData[projectName + userName]
        totalSize = projectData["totalSize"]
        totalChunks = projectData["totalChunks"]
        currentChunk = projectData["currentChunk"]
        reportedDataSize = projectData["reportedDataSize"]
        prev_endtime = projectData["prev_endtime"]

def storeLogMetaData(projectName, userName):
    global totalChunks
    global currentChunk
    global totalSize
    global metaData
    global prev_endtime
    metaData[projectName + userName] = {
        "totalSize" : totalSize,
        "currentChunk" : currentChunk,
        "totalChunks" : totalChunks,
        "reportedDataSize" : reportedDataSize,
        "prev_endtime" : prev_endtime
    }
    with open(os.path.join(homepath, "log_meta_data.json"), 'w') as f:
        json.dump(metaData, f)

def is_json(myjson):
  try:
    json_object = json.loads(myjson)
  except ValueError, e:
    return False
  return True

def getTotalSize(iFile):
    filejson = open(os.path.join(homepath, iFile))
    allJsonData = []
    if '.json' in iFile:
        jsonData = json.load(filejson)
    else:
        jsonData = []
        for line in filejson:
            line = line[line.find("{"):]
            jsonData.append(json.loads(line))
    for row in jsonData:
        allJsonData.append(row)

    filejson.close()
    return len(bytearray(json.dumps(allJsonData)))

#send data to insightfinder
def sendData():
    global reportedDataSize
    global firstData
    global chunkSize
    global totalChunks
    global currentChunk
    global totalSize
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
    reportedDataSize += len(bytearray(json.dumps(metricData)))
    if firstData == False:
        chunkSize = reportedDataSize
        firstData = True
        totalChunks += int(float(totalSize)/float(chunkSize))
    print reportedDataSize, totalSize, totalChunks
    reportedDataPer = (float(reportedDataSize)/float(totalSize))*100
    print str(min(100.0,math.ceil(reportedDataPer))) + "% of data are reported"
    alldata["chunkSerialNumber"] = str(currentChunk)
    alldata["chunkTotalNumber"] = str(totalChunks)
    if mode == "logStreaming":
        alldata["minTimestamp"] = str(minTimestampEpoch)
        alldata["maxTimestamp"] = str(maxTimestampEpoch)
    alldata["agentType"] = "LogFileReplay"

    currentChunk += 1
    #print the json
    json_data = json.dumps(alldata)
    #print json_data
    url = serverUrl + "/customprojectrawdata"
    print alldata["chunkTotalNumber"] +" ^^^^ "+alldata["chunkSerialNumber"]
    response = requests.post(url, data=json.loads(json_data))

def updateAgentDataRange(minTS,maxTS):
    #update projectKey, userName in dict
    alldata["licenseKey"] = LICENSEKEY
    alldata["projectName"] = PROJECTNAME
    alldata["userName"] = USERNAME
    alldata["operation"] = "updateAgentDataRange"
    alldata["minTimestamp"] = minTS
    alldata["maxTimestamp"] = maxTS

    #print the json
    json_data = json.dumps(alldata)
    #print json_data
    url = serverUrl + "/agentdatahelper"
    response = requests.post(url, data=json.loads(json_data))

#main
with open(os.path.join(homepath,"reporting_config.json"), 'r') as f:
    config = json.load(f)
reporting_interval = int(config['reporting_interval'])
keep_file_days = int(config['keep_file_days'])
deltaFields = config['delta_fields']

if os.path.isfile(os.path.join(homepath, "log_meta_data.json")) == True:
    getLogMetaData(PROJECTNAME, USERNAME)
#locate time range and date range
new_prev_endtime = prev_endtime
new_prev_endtime_epoch = 0
dates = []
if ("FileReplay" in mode or "logStreaming" in mode) and prev_endtime != "0" and len(prev_endtime) >= 8:
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
    start_time_epoch = 0#end_time_epoch - 1000*60*reporting_interval

alldata = {}
metricData = []
fieldnames = []
idxdate = 0
hostname = socket.gethostname().partition(".")[0]
minTimestampEpoch = 0
maxTimestampEpoch = 0

def getTotalSizeJson(jsonData) :
    temp = []
    for row in jsonData:
        if 'timestamp' in row:
            if mode == "logStreaming":
                row['timestamp'] = long(row['timestamp'])*1000
            if long(row['timestamp']) < long(start_time_epoch):
                continue
            temp.append(row)
    return len(bytearray(json.dumps(temp))), temp



if os.path.isfile(os.path.join('/tmp',options.inputFile)):
    numlines = len(open(os.path.join('/tmp',options.inputFile)).readlines())
    file = open(os.path.join('/tmp',options.inputFile))
    metricdataSizeKnown = False
    metricdataSize = 0
    count  = 0;
    firstChunkSize = 0;
    if '.json' in options.inputFile:
        jsonData = json.load(file)
    else:
       jsonData = []
       for line in file:
           line = line[line.find("{"):]
           jsonData.append(json.loads(line))
    numlines = len(jsonData)
    size,jsonData = getTotalSizeJson(jsonData)
    totalSize += size;
    for row in jsonData:
        metricData.append(row)
        new_prev_endtime_epoch = row[row.keys()[0]]
        if minTimestampEpoch == 0 or minTimestampEpoch > long(new_prev_endtime_epoch):
            minTimestampEpoch = long(new_prev_endtime_epoch)
        if maxTimestampEpoch == 0 or maxTimestampEpoch < long(new_prev_endtime_epoch):
            maxTimestampEpoch = long(new_prev_endtime_epoch)

        if metricdataSizeKnown == False:
            metricdataSize = len(bytearray(json.dumps(metricData)))
            metricdataSizeKnown = True
        if ((len(bytearray(json.dumps(metricData))) + metricdataSize) < 700000):  # Not using exact 750KB as some data will be padded later
            continue
        else:
            firstChunkSize = len(bytearray(json.dumps(metricData)));
            sendData()
            metricData = []
    #Send the last chunk
    remainingDataSize = len(bytearray(json.dumps(metricData)))
    if remainingDataSize > 0:
        if (remainingDataSize < firstChunkSize):
            totalChunks += 1
        sendData()
    #save json file

    file.close()
    #deleteContent(options.inputFile)
    if new_prev_endtime_epoch == 0:
        print "No data is reported"
    else:
        new_prev_endtimeinsec = math.ceil(long(new_prev_endtime_epoch)/1000.0)
        new_prev_endtime = time.strftime("%Y%m%d%H%M%S", time.localtime(long(new_prev_endtimeinsec)))
        prev_endtime = new_prev_endtime
        storeLogMetaData(PROJECTNAME, USERNAME)
        updateAgentDataRange(minTimestampEpoch,maxTimestampEpoch)
else:
    print "Invalid Input File"

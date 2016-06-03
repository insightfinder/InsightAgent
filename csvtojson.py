#!/usr/bin/python

import csv
import json
import os
import time
import subprocess
import requests
import datetime
import socket
from optparse import OptionParser

'''
this script reads reporting interval and prev endtime config2
and opens daily log file and reports header + rows within 
window of reporting interval after prev endtime
if prev endtime is 0, report most recent reporting interval 
till now from today's log file (may or may not be present)
assumping gmt epoch timestamp and local date daily file
'''

usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-f", "--fileInput",
    action="store", dest="inputFile", help="Input data file (overriding daily data file)")
parser.add_option("-m", "--mode",
    action="store", dest="mode", help="Running mode: live or replay")
parser.add_option("-d", "--directory",
    action="store", dest="homepath", help="Directory to run from")
(options, args) = parser.parse_args()

if options.homepath is None:
    homepath = os.getcwd()
else:
    homepath = options.homepath
if options.mode is None:
    mode = "live"
else:
    mode = options.mode
datadir = 'data/'

command = ['bash', '-c', 'source ' + str(homepath) + '/.agent.bashrc && env']
proc = subprocess.Popen(command, stdout = subprocess.PIPE)
for line in proc.stdout:
  (key, _, value) = line.partition("=")
  os.environ[key] = value.strip()
proc.communicate()

PROJECTKEY = os.environ["INSIGHTFINDER_PROJECT_KEY"]
USERNAME = os.environ["INSIGHTFINDER_USER_NAME"]

def getindex(col_name):
    if col_name == "CPU#%":
        return 1
    elif col_name == "DiskRead#MB" or col_name == "DiskWrite#MB":
        return 2
    elif col_name == "DiskUsed#MB":
        return 3
    elif col_name == "NetworkIn#MB" or col_name == "NetworkOut#MB":
        return 4
    elif col_name == "MemUsed#MB":
        return 5

#update prev_endtime in config file
def update_timestamp(prev_endtime):
    with open(os.path.join(homepath,"reporting_config.json"), 'r') as f:
        config = json.load(f)
    config['prev_endtime'] = prev_endtime
    with open(os.path.join(homepath,"reporting_config.json"),"w") as f:
        json.dump(config, f)

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
if mode == "replay" and prev_endtime != "0" and len(prev_endtime) >= 8:
    start_time = prev_endtime
    # pad a second after prev_endtime
    start_time_epoch = 1000+long(1000*time.mktime(time.strptime(start_time, "%Y%m%d%H%M%S")));
    end_time_epoch = start_time_epoch + 1000*60*reporting_interval
else: # prev_endtime == 0
    end_time_epoch = int(time.time())*1000
    start_time_epoch = end_time_epoch - 1000*60*reporting_interval

alldata = {}
metricData = []
fieldnames = []
idxdate = 0
hostname = socket.gethostname().partition(".")[0]

if options.inputFile is None:
    for i in range(0,2+int(float(reporting_interval)/24/60)):
        dates.append(time.strftime("%Y%m%d", time.localtime(start_time_epoch/1000 + 60*60*24*i)))
    for date in dates:
        if os.path.isfile(os.path.join(homepath,datadir+date+".csv")):
            dailyFile = open(os.path.join(homepath,datadir+date+".csv"))
            dailyFileReader = csv.reader(dailyFile)
            for row in dailyFileReader:
                if idxdate == 0 and dailyFileReader.line_num == 1:
                    #Get all the metric names
                    fieldnames = row
                    for i in range(0,len(fieldnames)):
                        if fieldnames[i] == "timestamp":
                            timestamp_index = i
                elif dailyFileReader.line_num > 1:
                    if long(row[timestamp_index]) < long(start_time_epoch) or long(row[timestamp_index]) > long(end_time_epoch) :
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
else:
    if os.path.isfile(os.path.join(homepath,datadir+options.inputFile)):
        file = open(os.path.join(homepath,datadir+options.inputFile))
        fileReader = csv.reader(file)
        for row in fileReader:
            if fileReader.line_num == 1:
                #Get all the metric names
                fieldnames = row
                for i in range(0,len(fieldnames)):
                    if fieldnames[i] == "timestamp":
                        timestamp_index = i
            elif fileReader.line_num > 1:
                if long(row[timestamp_index]) < long(start_time_epoch) or long(row[timestamp_index]) > long(end_time_epoch) :
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
                            colname = colname+"[-]"
                        if colname.find(":") == -1:
                            groupid = i
                            colname = colname+":"+str(groupid)
                        thisData[colname] = row[i]
                metricData.append(thisData)
        file.close()

#update endtime in config
if new_prev_endtime_epoch == 0:
    print "No data is reported"
else:
    new_prev_endtime = time.strftime("%Y%m%d%H%M%S", time.localtime(long(new_prev_endtime_epoch)/1000))
    update_timestamp(new_prev_endtime)

    #update projectKey, userName in dict
    alldata["metricData"] = json.dumps(metricData)
    alldata["projectKey"] = PROJECTKEY
    alldata["userName"] = USERNAME
    alldata["instanceName"] = hostname

    #print the json
    json_data = json.dumps(alldata)
    print json_data
    print str(len(bytearray(json_data))) + " bytes data are reported"
    url = 'https://insightfindergae.appspot.com/customprojectrawdata'
    #url = 'http://localhost:8888/customprojectrawdata'
    response = requests.post(url, data=json.loads(json_data))

#old file cleaning
for dirpath, dirnames, filenames in os.walk(os.path.join(homepath,datadir)):
    for file in filenames:
        curpath = os.path.join(dirpath, file)
        file_modified = datetime.datetime.fromtimestamp(os.path.getmtime(curpath))
        if datetime.datetime.now() - file_modified > datetime.timedelta(days=keep_file_days):
            os.rename(curpath,os.path.join("/tmp",file))

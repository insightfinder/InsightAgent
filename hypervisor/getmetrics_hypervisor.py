#!/usr/bin/python

import csv
import subprocess
import time
import os
from optparse import OptionParser
import socket
import sys

'''
this script gathers system info from /proc/ and add to daily csv file
'''

usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",
    action="store", dest="homepath", help="Directory to run from")
(options, args) = parser.parse_args()


if options.homepath is None:
    homepath = os.getcwd()
else:
    homepath = options.homepath
datadir = 'data/'


def listtocsv(lists):
    log = ''
    for i in range(0,len(lists)):
        log = log + str(lists[i])
        if(i+1 != len(lists)):
            log = log + ','
    resource_usage_file.write("%s\n"%(log))

globalGroupIndex=8013
def getindex(col_name):
    global globalGroupIndex
    if col_name == "cpuUsed":
        return 8001
    if col_name == "cpuSystem":
        return 8002
    if col_name == "cpuOverlap":
        return 8003
    if col_name == "cpuRun":
        return 8004
    if col_name == "cpuReady":
        return 8005
    if col_name == "cpuWait":
        return 8006
    elif col_name == "DiskReadRate" or col_name == "DiskWriteRate":
        return 8008
    elif "Commands" in col_name:
        return 8007
    elif col_name == "MemUsed":
        return 8009
    elif col_name == "NetworkIn/vSwitch0Total":
        return 8010
    elif col_name == "NetworkOut/vSwitch0Total":
        return 8011
    elif col_name == "NetworkIn/vSwitch1Total":
        return 8012
    elif col_name == "NetworkOut/vSwitch1Total":
        return 8013
    else:
        globalGroupIndex+=1
        return globalGroupIndex

fields = []
hostname = socket.gethostname().partition(".")[0]
try:
    command = "esxtop -b -n 1 > " + os.path.join(homepath,datadir) + "esxtopOutput.txt"
    print command
    date = time.strftime("%Y%m%d")
    resource_usage_file = open(os.path.join(homepath,datadir+date+".csv"),'a+')
    csvContent = resource_usage_file.readlines()
    numlines = len(csvContent)
    metricValues = []
    proc = subprocess.Popen(command, cwd=homepath, stdout=subprocess.PIPE, shell=True)
    (out,err) = proc.communicate()
    logFile = open((os.path.join(homepath,datadir,"esxtopOutput.txt")),'r')
    content=logFile.readlines()
    metrics = content[0].split(",")
    values = content[1].split(",")
    metricList = ["timestamp", "cpuUsed", "cpuSystem", "cpuOverlap", "cpuRun", "cpuReady", "cpuWait", "DiskCommands", "DiskReadCommands", \
                   "DiskWriteCommands","DiskReadRate", "DiskWriteRate", "MemUsed", "NetworkIn/vSwitch0Total", "NetworkOut/vSwitch0Total", "NetworkIn/vSwitch1Total", \
                  "NetworkOut/vSwitch1Total"]
    metricDict = {"timestamp" : [], "cpuUsed" : ["% Used", "Group Cpu"], "cpuSystem" : ["% System", "Group Cpu"], "cpuOverlap" : ["% Overlap", "Group Cpu"], \
                  "cpuRun" : ["% Run", "Group Cpu"], "cpuReady" : ["% Ready", "Group Cpu"], "cpuWait" : ["% Wait", "Group Cpu"], "DiskReadRate" : ["MBytes Read/sec"], \
                  "DiskWriteRate" : ["MBytes Written/sec"], "MemUsed" : [], "DiskCommands" : ["Commands/sec"], "DiskReadCommands" : ["Reads/sec"], \
                  "DiskWriteCommands" : ["Writes/sec"], "NetworkIn/vSwitch0Total" : ["MBits Received/sec", "vSwitch0"], "NetworkOut/vSwitch0Total" : ["MBits Transmitted/sec", "vSwitch0"], \
                  "NetworkIn/vSwitch1Total" : ["MBits Received/sec", "vSwitch1"], "NetworkOut/vSwitch1Total" : ["MBits Transmitted/sec", "vSwitch1"]}
    totalMemory = freeMemory = diskRead = diskWrite = networkTx = networkRx = cpu = cpuused = 0
    timestamp = int(time.time()*1000)
    for i in range(0,len(metrics)):
        if "MBits Transmitted/sec" in metrics[i] or "MBits Received/sec" in metrics[i]:
            if "USB" in metrics[i]:
                continue
            #print metrics[i]
            temp = metrics[i]
            s = temp.index('(')
            t = temp.index(')')
            temp1=temp[s+1:t]
            tok=temp1.split(':')
            fd = tok[0]+"/"+tok[len(tok)-1]
            if "MBits Transmitted/sec" in metrics[i]:
                fd = "NetworkOut/"+fd
                metricDict.update({fd:["MBits Transmitted/sec"]})
            elif "MBits Received/sec" in metrics[i]:
                fd = "NetworkIn/"+fd
                metricDict.update({fd:["MBits Received/sec"]})
            metricList.append(fd)
    for i in range(len(metricList)):
        metricValues.append(0)
    metricValues[metricList.index("timestamp")] = timestamp
    for i in range(0,len(metrics)):
        for metric in metricDict:
            if metric == "MemUsed":
                if "Memory\Machine MBytes" in metrics[i]:
                    values[i] = values[i].replace('"', '').strip()
                    totalMemory = totalMemory + float(values[i])
                elif "Memory\Free MBytes" in metrics[i]:
                    values[i] = values[i].replace('"', '').strip()
                    freeMemory = freeMemory + int(values[i])
                metricValues[metricList.index(metric)] = abs(totalMemory - freeMemory)
            elif metric == "timestamp":
                continue
            else:
                searchKeys = metricDict[metric]
                allKeyspresent = True
                for searchKey in metricDict[metric]:
                    if searchKey not in metrics[i]:
                        allKeyspresent = False
                        break
                if allKeyspresent == True:
                    if "Network" in metric and metric.count("/") == 2:
                        temp = metrics[i]
                        s = temp.index('(')
                        t = temp.index(')')
                        temp1=temp[s+1:t]
                        tok=temp1.split(':')
                        fd = tok[0]+"/"+tok[len(tok)-1]
                        if "NetworkIn" in metric:
                            fd = "NetworkIn/"+fd
                        else:
                            fd = "NetworkOut/"+fd
                        if fd != metric:
                            continue
                    values[i] = values[i].replace('"', '').strip()
                    metricValues[metricList.index(metric)] += float(values[i])
    for metric in metricList:
        if metric != "timestamp":
            groupid = getindex(metric)
            tempField = metric + "[" + hostname + "]"
            tempField = tempField + ":" + str(groupid)
            fields.append(tempField)
        else:
            fields.append(metric)
    print fields
    if numlines < 1:
        listtocsv(fields)
    else:
        headercsv = csvContent[0]
        header = headercsv.split("\n")[0].split(",")
        print header
        if cmp(header,fields) != 0:
            oldFile = os.path.join(homepath,datadir+date+".csv")
            newFile = os.path.join(homepath,datadir+date+"."+time.strftime("%Y%m%d%H%M%S")+".csv")
            os.rename(oldFile,newFile)
            resource_usage_file = open(os.path.join(homepath,datadir+date+".csv"), 'a+')
            listtocsv(fields)
    listtocsv(metricValues)
    resource_usage_file.flush()
    resource_usage_file.close()

except KeyboardInterrupt:
    print "Interrupt from keyboard"

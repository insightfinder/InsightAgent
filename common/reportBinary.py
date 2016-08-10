#!/usr/bin/python

import csv
import json
import os
import sys
import time
import subprocess
import datetime
import socket
from optparse import OptionParser
import math
import base64

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
    action="store", dest="mode", help="Running mode: binaryFileReplay")
parser.add_option("-d", "--directory",
    action="store", dest="homepath", help="Directory to run from")
parser.add_option("-t", "--agentType",
    action="store", dest="agentType", help="Agent type")
parser.add_option("-T", "--fileType",
    action="store", dest="fileType", help="File type: 1 for faultImpactAnalysis, 2 for functionLocalization")
parser.add_option("-S", "--sessionID",
    action="store", dest="sessionID", help="Session ID")
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
if options.fileType is None:
    print "Please specify fileType. 1 for faultImpactAnalysis, 2 for functionLocalization."
    parser.print_help()
    sys.exit()
else:
    if options.fileType == "1":
        fileType = "faultImpactAnalysis"
    if options.fileType == "2":
        fileType = "functionLocalization"
if options.sessionID is None:
    print "Please specify sessionID."
    parser.print_help()
    sys.exit()
else:
    sessionID = options.sessionID

datadir = 'syscall/data/'

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
serverUrl = 'https://insightfindergae.appspot.com'

reportedDataSize = 0
totalSize = 0
firstData = False
chunkSize = 0
totalChunks = 0
currentChunk = 1
fileName = ""
BLOCKSIZE = 700000
metricdataSize = 0

#send data to insightfinder
def sendData():
    global reportedDataSize
    global firstData
    global chunkSize
    global totalChunks
    global currentChunk
    global totalSize
    global fileType
    global sessionID
    if len(metricData) == 0:
        return
    #update projectKey, userName in dict
    #alldata["metricData"] = json.dumps(metricData)
    #print metricData
    #encodedData = base64.b64encode(metricData)
    #file2 = "/home/ting/workspace/InsightAgent/syscall/data/out.python.log"
    #with open(file2, 'wb') as fw:
    #    fw.write(base64.b64decode(encodedData))
    #print encodedData
    #print LICENSEKEY, PROJECTNAME, USERNAME, hostname, fileType, metricdataSize
    alldata["metricData"] = base64.b64encode(metricData)
    alldata["licenseKey"] = LICENSEKEY
    alldata["projectName"] = PROJECTNAME
    alldata["userName"] = USERNAME
    alldata["instanceName"] = hostname
    alldata["fileType"] = fileType
    alldata["fileSize"] = metricdataSize
    alldata["sessionID"] = sessionID

    if mode == "binaryFileReplay":
        reportedDataSize += BLOCKSIZE
        if firstData == False:
            chunkSize = reportedDataSize
            firstData = True
            totalChunks = int(math.ceil(float(totalSize)/float(chunkSize)))
            #print "totalChunks = ", str(totalSize), "/", str(chunkSize)
        reportedDataPer = (float(reportedDataSize)/float(totalSize))*100
        print str(metricdataSize), str(sys.getsizeof(metricData)), str(min(100.0, math.floor(reportedDataPer))) + "% of data are reported"
        alldata["chunkSerialNumber"] = str(currentChunk)
        alldata["chunkTotalNumber"] = str(totalChunks)
        currentChunk += 1
        alldata["agentType"] = "binaryFileReplay" 
    json_data = json.dumps(alldata)
    url = serverUrl + "/customprojectrawdata"
    if agentType == "hypervisor":
        response = urllib.urlopen(url, data=urllib.urlencode(alldata))
    else:
        response = requests.post(url, data=json.loads(json_data))


alldata = {}
metricData = []
fieldnames = []
idxdate = 0
hostname = socket.gethostname().partition(".")[0]
minTimestampEpoch = 0
maxTimestampEpoch = 0

if options.inputFile is not None:
    if os.path.isfile(os.path.join(homepath,options.inputFile)):
        #numlines = len(open(os.path.join(homepath,options.inputFile)).readlines())
        #file2 = open("/home/ting/workspace/InsightAgent/syscall/data/out.python.log")
        fileName = options.inputFile.split("/")[-1]
        file = os.path.join(homepath,options.inputFile)
        metricdataSizeKnown = False
        metricdataSize = os.path.getsize(file)
        if mode == "binaryFileReplay":
            totalSize = os.path.getsize(file)
            with open(file, 'rb') as fp:
                for block in iter(lambda: fp.read(BLOCKSIZE), ''):
                    metricData = block
                    sendData()


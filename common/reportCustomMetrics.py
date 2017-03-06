#!/usr/bin/python

import csv
import time
import json
import socket
import collections
import sys
import requests
import os
import pprint
from optparse import OptionParser

'''
This script reads custom metrics from the ../custom directory and reports them to a project 
in Insight Finder app for analysis.
'''

#homepath = '/home/ec2-user/InsightAgent-master/'
hostnameShort = socket.gethostname().partition(".")[0]
indexMap = {
	"startTime": 99901,
	"endTime": 99902,
	"duration": 99903,
	"bytes": 99801,
	"clientTxTime": 99802,
	"queueTime": 99803,
	"connectTime": 99804,
	"responseTime": 99805,
	"totalTime": 99806
}



#Get metric-wise index.
def getindex(header):
	if header not in indexMap:
		return 1
	else:
		return indexMap[header]
    

#Modify metric header as per IF format
def getnewheader(header):
    if header == 'timestamp':
        return "timestamp"
    else:
        return str(header) + "[" + str(hostnameShort) + "]:" + str(getindex(header))

#Create the data to be posted and send the POST request
def dopost(json_output, LICENSEKEY, PROJECTNAME, USERNAME, SERVERURL):
    req_data = {}
    if len(json_output) == 0:
        return
    req_data["metricData"] = json.dumps(json_output)
    req_data["licenseKey"] = LICENSEKEY
    req_data["projectName"] = PROJECTNAME
    req_data["userName"] = USERNAME
    req_data["instanceName"] = hostnameShort

    req_payload = json.dumps(req_data)
    url = SERVERURL + "/customprojectrawdata"
    response = requests.post(url, data = json.loads(req_payload))
    print response.status_code
    print response.text
    #print response.json()


def getcustommetrics(SERVERURL, PROJECTNAME, USERNAME, LICENSEKEY, HOMEPATH):
    #Get the path for the customMetric files.
    dirpath = os.path.join(HOMEPATH, "custom")
    #Get all the files in that directory
    files = [f for f in os.listdir(dirpath) if os.path.isfile(os.path.join(dirpath, f))]
    
    #Create the output directory, if it doesn't exist already.
    if not os.path.isdir(os.path.join(dirpath, 'outputFiles')):
        os.makedirs(os.path.join(dirpath, 'outputFiles'))

    writePath = os.path.join(dirpath, 'outputFiles')
    
    #Filter CSV files out and move all of them to the output directory.
    for f in files:
        splt_name = f.split('.')
        if len(splt_name) > 1 and splt_name[1].lower() == 'csv':
            os.rename(os.path.join(dirpath,f),os.path.join(writePath, f))
    
    #Iterating through each file, collecting and processing metrics and sending them to insight finder.
    for files_to_scan in os.listdir(writePath):
        with open(os.path.join(writePath,files_to_scan), 'r') as f:
            json_output = []
            header_map = {}
            unparsableFile = False
            dictReader = csv.DictReader(f)
            header = dictReader.fieldnames
            if not header:
                unparsableFile = True
                continue
            
            #Check if header exists by checking if its a string value.
            try:
                float(header[0])
                print "unparsable file"
                unparsableFile = True
                continue
            except ValueError:
                pass
            #Create a map between the formatted header_fields and the raw header_fields    
            for h in header:
                header_map[h] = getnewheader(h)
            
            #Create a json object for each row and push it to an array
            for row in dictReader:
                row_obj = {}
                for key,val in row.iteritems():
                    row_obj[header_map[key]] = val
                json_output.append(row_obj)
            
            #Send a post request to the Insight Finder server with the created payload.
            dopost(json_output, LICENSEKEY, PROJECTNAME, USERNAME, SERVERURL)    
        #pprint.pprint(json_output)
    return True
                    
            
    
    



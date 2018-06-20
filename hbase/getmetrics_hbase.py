#!/usr/bin/python

import linecache
import json
import csv
from subprocess import Popen, PIPE, STDOUT
import time
import os
from optparse import OptionParser
import multiprocessing
import socket
import fileinput
from itertools import izip
import commands
import random
import re

# This script gathers hbase operation execution time and add to csv file

def getIndex(columnName):
    if columnName == "get":
        return 21017
    elif columnName == "put":
        return 21020   

def listToCSV(lists):
    log = ''
    for i in range(0,len(lists)):
        log = log + str(lists[i])
        if(i+1 != len(lists)):
		log = log + ','
    hbase_execution_time.write("%s\n"%(log))

def initialize():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                  action="store", dest="homepath", help="Directory to run from")
    (options, args) = parser.parse_args()

    if options.homepath is None:
        homepath = os.getcwd()
    else:
        homepath = options.homepath
        
    return homepath

def executeHbaseCommandsFromConf():   
    confCommand ='/usr/local/HBase/bin/hbase shell ' +  homepath + configFileName \
        + '| grep -E "\srow\(s\)|in\s|\sseconds" | awk \'{print $4}\''

    hbaseCommandQuerying = Popen(confCommand, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
    output_check = re.compile(r"[0-9].[0-9]{4}")

    for line in iter(hbaseCommandQuerying.stdout.readline,''):
        if output_check.search(line.rstrip()):
            executionOutputList.append(line.rstrip())


if __name__ == '__main__':

    hbaseType = ["get", "put"]
    dict = {}
    executionOutputList = []
    executionTime = {}
    fields = [] # save csv header
    dataList = [] # save csv data

    homepath = initialize()
    datadir = 'data/'
    hostname = socket.gethostname().partition(".")[0]

    try:

        # execute hbase commnads from the configuration file
        configFileName = "/hbaseExecute.conf" 
        configFile = open(homepath+configFileName,'r+')

        for x in hbaseType:
           executionTime[x] = []
       
        executeHbaseCommandsFromConf()
        linenumber = 0

        for eachline in configFile:
            for x in hbaseType:
                if x in eachline.split():
                    executionTime[x].append(float(executionOutputList[linenumber]))
            linenumber += 1
    	
        # save the average time of each type to dict
        for cmdType in hbaseType:
            if len(executionTime[cmdType]) == 0:
    		  dict[cmdType] = 0
            else:
    		  dict[cmdType] = round(sum(executionTime[cmdType])/len(executionTime[cmdType]),4)

        # build header of csv file
        fields.append("timestamp")

        for cmdType in hbaseType:
    	   groupid = getIndex(cmdType)
    	   field = cmdType + "[" + hostname + "]:" + str(groupid)
    	   fields.append(field)	

        # append data of csv file
        currentEpoch = int(round(time.time() * 1000))
        dataList.append(currentEpoch)

        for cmdType in hbaseType:
    	   dataList.append(dict[cmdType])

        date = time.strftime("%Y%m%d")
        hbase_execution_time = open(os.path.join(homepath,datadir + date + ".csv"), 'a+')   
        csvContent = hbase_execution_time.readlines()
        numlines = len(csvContent)

        if (numlines < 1):
    	   listToCSV(fields)
        else:
    	   headercsv = csvContent[0]
    	   header = headercsv.split("\n")[0].split(",")

        listToCSV(dataList)

        hbase_execution_time.flush()
        hbase_execution_time.close()

    except KeyboardInterrupt:
        print "Interrupt from keyboard" 

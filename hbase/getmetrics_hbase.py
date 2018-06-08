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

# This script gathers hbase operation execution time and add to csv file

def getindex(col_name): # need to generate the group id from a range
#    return random.randint(3000,10000)
#    if col_name == "alter":
#        return 21001
#    if col_name == "create":
#        return 21002
#    if col_name == "describe":
#        return 21003
#    if col_name == "disable":
#        return 21004
#    if col_name == "disable_all":
#        return 21005
#    if col_name == "is_disabled":
#        return 21006
#    if col_name == "drop":
#        return 21007
#    if col_name == "drop_all":
#        return 21008
#    if col_name == "enable":
#        return 21009
#    if col_name == "enable_all":
#        return 21010
#    if col_name == "is_enabled":
#        return 21011
#    if col_name == "exists":
#        return 21012
#    if col_name == "list":
#        return 21013
#    if col_name == "count":
#        return 21014
#    if col_name == "delete":
#        return 21015
#    if col_name == "delete_all":
#        return 21016
    if col_name == "get":
        return 21017
#    if col_name == "get_Counter":
#        return 21018
#    if col_name == "incr":
#        return 21019
    if col_name == "put":
        return 21020
#    if col_name == "scan":
#        return 21021
#    if col_name == "truncate":
#        return 21022

def listtocsv(lists):
    log = ''
    for i in range(0,len(lists)):
        log = log + str(lists[i])
        if(i+1 != len(lists)):
		log = log + ','
    hbase_execution_time.write("%s\n"%(log))


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
hostname = socket.gethostname().partition(".")[0]


#hbaseType = ["alter", "create", "describe", "disable", "disable_all", "is_disabled", "drop", "drop_all", "enable", 
#                    "enable_all", "is_enabled", "exists", "list", "count", "delete", "delete_all", "get", "get_counter", "incr", "put", "scan", "truncate"]

hbaseType = ["get", "put"]

dict = {}
executionTime = {}
fields = [] # save csv header
dataList = [] # save csv data

try:
    configFileName = "/hbaseExecute.conf" # save hbase commnad in conf file
    configFile = open(homepath+configFileName,'r+')

    for x in hbaseType:
	   executionTime[x] = []

    for eachline in configFile:
        print eachline
        for x in hbaseType:
            if x in eachline.split(): # disable, is_disabled
                cmd = 'echo ' + '"' + eachline.rstrip('\n') + '"' + ' | /usr/local/HBase/bin/hbase shell | grep -E "\srow(s)\sin\s|\sseconds" | awk \'{print $4}\''
                hbaseQuerying = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
                output = hbaseQuerying.stdout.read().splitlines()[-1]
                print "output:", output.strip('\n')
                # save each execution time to list of each type
                executionTime[x].append(float(output.strip('\n')))			

    print executionTime	

    # save the average time of each type to dict
    for cmdType in hbaseType:
        if len(executionTime[cmdType]) == 0:
		  dict[cmdType] = 0
    	else:
		  dict[cmdType] = round(sum(executionTime[cmdType])/len(executionTime[cmdType]),4)

    print ""
    print dict

    # build header of csv file
    fields.append("timestamp")

    for cmdType in hbaseType:
	   groupid = getindex(cmdType)
	   field = cmdType + "[" + hostname + "]:" + str(groupid)
	   fields.append(field)	

    print ""
    print fields

    # append data of csv file
    currentEpoch = int(round(time.time() * 1000))
    dataList.append(currentEpoch)

    for cmdType in hbaseType:
	   dataList.append(dict[cmdType])

    print ""
    print dataList

    date = time.strftime("%Y%m%d")

    hbase_execution_time = open(os.path.join(homepath,datadir + date + ".csv"), 'a+')   
    csvContent = hbase_execution_time.readlines()
    numlines = len(csvContent)

    print "numlines:", numlines

    if (numlines < 1):
	   listtocsv(fields)
    else:
	   headercsv = csvContent[0]
	   header = headercsv.split("\n")[0].split(",")

    listtocsv(dataList)

    hbase_execution_time.flush()
    hbase_execution_time.close()

except KeyboardInterrupt:
    print "Interrupt from keyboard" 

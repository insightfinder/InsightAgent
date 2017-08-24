#!/usr/bin/python
import linecache
import json
import csv
import subprocess
import time
import os
import socket
import sys
from optparse import OptionParser

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
newInstanceAvailable = False
hostname = socket.gethostname().partition(".")[0]

def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]

def listtocsv(lists):
    log = ''
    for i in range(0,len(lists)):
        log = log + str(lists[i])
        if(i+1 != len(lists)):
            log = log + ','
    resource_usage_file.write("%s\n"%(log))

def getindex(col_name):
    if "CPU" in col_name:
        return 2001
    elif "DiskRead" in col_name or "DiskWrite" in col_name:
        return 2002
    elif "DiskUsed" in col_name:
        return 2003
    elif "NetworkIn" in col_name or "NetworkOut" in col_name:
        return 2004
    elif "Mem" in col_name:
        return 2005
    elif "DiskUsed" in col_name:
        return 2006
    elif "LoadAvg" in col_name:
        return 2007
    elif "InOctets" in col_name or "OutOctets" in col_name:
        return 2008
    elif "InDiscards" in col_name or "OutDiscards" in col_name:
        return 2009
    elif "InErrors" in col_name or "OutErrors" in col_name:
        return 2010
    elif "SwapUsed" in col_name or "SwapTotal" in col_name:
        return 2011


def update_results(lists):
    with open(os.path.join(homepath,datadir+"previous_results.json"),'w') as f:
        json.dump(lists,f)

def init_previous_results():
    global dockerInstances
    first_result = {}
    timestampRead = False
    for containers in dockerInstances:
        dockerID = containers
        if len(dockerID) > 12:
            dockerID = dockerID[:12]
        for eachfile in filenames:
            tempfile = eachfile.split(".")
            correctFile = tempfile[0]+"_"+containers+"."+tempfile[1]
            if(eachfile == "timestamp.txt" and timestampRead == False):
                correctFile = eachfile
                timestampRead = True
            elif(eachfile == "timestamp.txt"):
                continue
            try:
                txt_file = open(os.path.join(homepath,datadir,correctFile))
            except IOError:
                continue
            lines = txt_file.read().split("\n")
            for eachline in lines:
                tokens = eachline.split("=")
                if(len(tokens) == 1):
                    continue
                if(eachfile == "cpumetrics.txt"):
                    tokens[0] = tokens[0] + "[" + dockerID + "_" + hostname + "]"
                elif(correctFile != "timestamp.txt"):
                    tokens[0] = tokens[0] + "[" + dockerID + "_" + hostname + "]"
                    tokens[1] = float(float(tokens[1])/(1024*1024))
                if(tokens[0] != "timestamp"):
                    groupid = getindex(tokens[0])
                    tokens[0] = tokens[0] + ":" + str(groupid)
                first_result[tokens[0]] = float(tokens[1])
    update_results(first_result)
    time.sleep(1)
    if(os.path.isdir("/cgroup") == True):
        proc = subprocess.Popen([os.path.join(homepath,"cgroup/getmetrics_cgroup.sh")], cwd=homepath, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    elif(os.path.isdir("/sys/fs/cgroup/blkio/docker") == True):
        proc = subprocess.Popen([os.path.join(homepath,"cgroup/getmetrics_sys_fs_cgroup.sh")], cwd=homepath, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    elif(os.path.isdir("/sys/fs/cgroup/blkio/system.slice") == True):
        proc = subprocess.Popen([os.path.join(homepath,"cgroup/getmetrics_sys_fs_slice_cgroup.sh")], cwd=homepath, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    else:
        print"No cgroups found.Stopping."
        sys.exit()
    (out,err) = proc.communicate()
    if "No such file or directory" in err:
        print "Error in fetching metrics for some containers"

def get_previous_results():
    with open(os.path.join(homepath,datadir+"previous_results.json"),'r') as f:
        return json.load(f)

def check_delta(field):
    deltaFields = ["CPU", "DiskRead", "DiskWrite", "NetworkIn", "NetworkOut"]
    for eachfield in deltaFields:
        if(eachfield in field):
            return True
    return False

def calculate_delta(fieldname,value):
    previous_result = get_previous_results()
    delta = float(value) - previous_result[fieldname]
    delta = abs(delta)
    # If there is an error in fetching data, return 0. Else delta value will be wrong and high.
    if (abs(delta) == abs(previous_result[fieldname])):
        delta = 0
    if("CPU" in fieldname):
        delta = delta/100
    return round(delta,4)

dockerInstances = []
def update_docker():
    global dockers
    global newInstanceAvailable
    global dockerInstances


    proc = subprocess.Popen(["docker ps --no-trunc | awk '{if(NR>1) print $NF}'"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    dockers = out.split("\n")
    if os.path.isfile(os.path.join(homepath,datadir+"totalInstances.json")) == False:
        towritePreviousInstances = {}
        for containers in dockers:
            if containers != "":
                dockerInstances.append(containers)
        towritePreviousInstances["overallDockerInstances"] = dockerInstances
        with open(os.path.join(homepath,datadir+"totalInstances.json"),'w') as f:
            json.dump(towritePreviousInstances,f)
    else:
        with open(os.path.join(homepath,datadir+"totalInstances.json"),'r') as f:
            dockerInstances = json.load(f)["overallDockerInstances"]
    newInstances = []
    for eachDocker in dockers:
        if eachDocker == "":
            continue
        newInstances.append(eachDocker)
    if cmp(newInstances,dockerInstances) != 0:
        try:
            writeInsatanceFile("currentInstances", newInstances)
            writeInsatanceFile("previousInstances", dockerInstances)
        except Exception as e:
            print e
        towritePreviousInstances = {}
        towritePreviousInstances["overallDockerInstances"] = newInstances
        with open(os.path.join(homepath,datadir+"totalInstances.json"),'w') as f:
            json.dump(towritePreviousInstances,f)
        newInstanceAvailable = True
        dockerInstances = newInstances

def writeInsatanceFile(filename, instanceList):
    global hostname
    jsonData = {}
    print "In Function writeInsatanceFile()"
    print instanceList
    print os.path.join(homepath, datadir + filename + ".json")
    newInstanceList = []
    for index in range(len(instanceList)):
        dockerID = instanceList[index]
        if len(instanceList[index]) > 12:
            dockerID = instanceList[index][:12]
        newInstanceList.append(dockerID + "_" + hostname)
    jsonData["instanceList"] = newInstanceList
    with open(os.path.join(homepath, datadir + filename + ".json"), 'w') as f:
        json.dump(jsonData, f)

fields = []
filenames = ["timestamp.txt","cpumetrics.txt","diskmetricsread.txt","diskmetricswrite.txt","networkmetrics.txt","memmetrics.txt", "networkinterfacemetrics.txt", "diskusedmetrics.txt"]
try:
    date = time.strftime("%Y%m%d")
    update_docker()
    if newInstanceAvailable == True and os.path.isfile(os.path.join(homepath,datadir+date+".csv")) == True:
        oldFile = os.path.join(homepath,datadir+date+".csv")
        newFile = os.path.join(homepath,datadir+date+"."+time.strftime("%Y%m%d%H%M%S")+".csv")
        os.rename(oldFile,newFile)
        os.remove(os.path.join(homepath,datadir+"previous_results.json"))
    resource_usage_file = open(os.path.join(homepath,datadir+date+".csv"),'a+')
    numlines = len(resource_usage_file.readlines())
    values = []
    dict = {}
    timestampread = False
    ipAddress = get_ip_address()
    if(os.path.isdir("/cgroup") == True):
        proc = subprocess.Popen([os.path.join(homepath,"cgroup/getmetrics_cgroup.sh")], cwd=homepath, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    elif(os.path.isdir("/sys/fs/cgroup/blkio/docker") == True):
        proc = subprocess.Popen([os.path.join(homepath,"cgroup/getmetrics_sys_fs_cgroup.sh")], cwd=homepath, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    elif(os.path.isdir("/sys/fs/cgroup/blkio/system.slice") == True):
        proc = subprocess.Popen([os.path.join(homepath,"cgroup/getmetrics_sys_fs_slice_cgroup.sh")], cwd=homepath, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    else:
        print"No cgroups found.Stopping."
        sys.exit()
    (out,err) = proc.communicate()
    if "No such file or directory" in err:
        print "Error in fetching metrics for some containers"
    if(os.path.isfile(homepath+"/"+datadir+"timestamp.txt") == False):
        sys.exit()
    if(os.path.isfile(homepath+"/"+datadir+"previous_results.json") == False) or newInstanceAvailable == True:
        init_previous_results()
    for containers in dockerInstances:
        tokens = []
        dockerID = containers
        if len(dockerID) > 12:
            dockerID = dockerID[:12]
        for eachfile in filenames:
            tempfile = eachfile.split(".")
            correctFile = tempfile[0]+"_"+containers+"."+tempfile[1]
            if(eachfile == "timestamp.txt" and timestampread == False):
                correctFile = eachfile
                timestampread = True
            elif(eachfile == "timestamp.txt"):
                continue
            try:
                txt_file = open(os.path.join(homepath,datadir,correctFile))
            except IOError:
                continue
            lines = txt_file.read().split("\n")
            for eachline in lines:
                tokens = eachline.split("=")
                if(len(tokens) == 1):
                    continue
                if(eachfile == "cpumetrics.txt"):
                    tokens[0] = tokens[0] + "[" + dockerID + "_" + hostname + "]"
                elif(correctFile != "timestamp.txt"):
                    tokens[0] = tokens[0] + "[" + dockerID + "_" + hostname + "]"
                    tokens[1] = float(float(tokens[1])/(1024*1024))
                if(tokens[0] != "timestamp"):
                    groupid = getindex(tokens[0])
                    tokens[0] = tokens[0] + ":" + str(groupid)
                fields.append(tokens[0])
                if(check_delta(tokens[0]) == True):
                    deltaValue = calculate_delta(tokens[0], tokens[1])
                    valuetoappend = "%.4f" %deltaValue
                    values.append(valuetoappend)
                else:
                    if(tokens[0] == "timestamp"):
                        values.append(tokens[1])
                    else:
                        valuetoappend = "%.4f" %float(tokens[1])
                        values.append(valuetoappend)
                dict[tokens[0]] = float(tokens[1])
    if(numlines < 1):
        listtocsv(fields)
    listtocsv(values)
    resource_usage_file.flush()
    resource_usage_file.close()
    update_results(dict)

except KeyboardInterrupt:
    print "Interrupt from keyboard"

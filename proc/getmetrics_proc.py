#!/usr/bin/python

import linecache
import json
import csv
import subprocess
import time
import os
from optparse import OptionParser
import multiprocessing

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
    elif "DiskUsed" in col_name:
        return 6
    elif "LoadAvg" in col_name:
        return 7

def update_results(lists):
    with open(os.path.join(homepath,datadir+"previous_results.json"),'w') as f:
        json.dump(lists,f)

def init_previous_results():
    first_result = {}
    for eachfile in filenames:
        if(eachfile == "cpumetrics.txt"):
            get_cpuusage(eachfile, tokens, first_result)
        else:
            txt_file = open(os.path.join(homepath,datadir,eachfile))
            lines = txt_file.read().split("\n")
            for eachline in lines:
                tokens = eachline.split("=")
                if(len(tokens) == 1):
                    continue
                if(eachfile == "diskmetrics.txt"):
                    tokens[1] = float(float(tokens[1])*512/(1024*1024))
                elif(eachfile == "diskusedmetrics.txt" or eachfile == "memmetrics.txt"):
                    tokens[1] = float(float(tokens[1])/1024)
                elif(eachfile == "networkmetrics.txt"):
                    tokens[1] = float(float(tokens[1])/(1024*1024))
                first_result[tokens[0]] = float(tokens[1])
    update_results(first_result)
    time.sleep(1)
    proc = subprocess.Popen([os.path.join(homepath,"proc","getmetrics.sh")], cwd=homepath, stdout=subprocess.PIPE, shell=True)
    (out,err) = proc.communicate()

def get_previous_results():
    with open(os.path.join(homepath,datadir+"previous_results.json"),'r') as f:
        return json.load(f)

def check_delta(field):
    with open(os.path.join(homepath,"reporting_config.json"),'r') as f:
        config_lists = json.load(f)
    deltaFields = config_lists['delta_fields']
    for eachfield in deltaFields:
        if(eachfield == field):
            return True
    return False

def calculate_delta(fieldname,value):
    previous_result = get_previous_results()
    delta = float(value) - previous_result[fieldname]
    delta = abs(delta)
    return round(delta,4)

def calculate_cpudelta(current_result):
    previous_result = get_previous_results()
    prev_cpu_usage = previous_result["cpu_usage"]
    totalresult = 0
    for eachcpu in prev_cpu_usage:
        prev_total = 0
        curr_total = 0
        for eachmetric in prev_cpu_usage[eachcpu]:
            prev_total += prev_cpu_usage[eachcpu][eachmetric]
        for eachmetric in current_result[eachcpu]:
            curr_total += current_result[eachcpu][eachmetric]
        prev_idle = prev_cpu_usage[eachcpu]["idle"] + prev_cpu_usage[eachcpu]["iowait"]
        curr_idle = current_result[eachcpu]["idle"] + current_result[eachcpu]["iowait"]
        if((curr_total - prev_total) == 0):
            result = 0
        else:
            result = (1-round((curr_idle - prev_idle)/(curr_total - prev_total),4))*100
        result = abs(result)
        totalresult += float(result)
    return totalresult

def get_cpuusage(filename,field_values,which_dict):
    cpuusage_file = open(os.path.join(homepath,datadir,filename))
    lines = cpuusage_file.read().split("\n")
    cpu_dict={}
    cpu_count = multiprocessing.cpu_count()
    for i in range(0,cpu_count):
        cpucore = "cpu"+str(i)
        cpu_dict[cpucore] = {}
    for eachline in lines:
        tokens_split = eachline.split("=")
        if(len(tokens_split) == 1):
            continue
        cpucoresplit = tokens_split[0].split("$")
        cpu_dict[cpucoresplit[0]][cpucoresplit[1]] = float(tokens_split[1])
    totalresult = 0
    for i in range(0,cpu_count):
        cpucore = "cpu"+str(i)
        which_dict["cpu_usage"] = cpu_dict
        Total = cpu_dict[cpucore]["user"] + cpu_dict[cpucore]["nice"] + cpu_dict[cpucore]["system"] + cpu_dict[cpucore]["idle"] + cpu_dict[cpucore]["iowait"] + cpu_dict[cpucore]["irq"] + cpu_dict[cpucore]["softirq"]
        idle = cpu_dict[cpucore]["idle"] + cpu_dict[cpucore]["iowait"]
        field_values[0] = "CPU"
        result = 1 - round(float(idle/Total),4)
        totalresult += float(result)
    field_values.append(totalresult*100)

filenames = ["timestamp.txt", "cpumetrics.txt","diskmetrics.txt","diskusedmetrics.txt","networkmetrics.txt","memmetrics.txt","loadavg.txt"]
fields = []
try:
    date = time.strftime("%Y%m%d")
    resource_usage_file = open(os.path.join(homepath,datadir+date+".csv"),'a+')
    csvContent = resource_usage_file.readlines()
    numlines = len(csvContent)
    values = []
    dict = {}
    proc = subprocess.Popen([os.path.join(homepath,"proc","getmetrics.sh")], cwd=homepath, stdout=subprocess.PIPE, shell=True)
    (out,err) = proc.communicate()

    if(os.path.isfile(homepath+"/"+datadir+"previous_results.json") == False):
        init_previous_results()

    tokens = []
    for eachfile in filenames:
        if(eachfile == "cpumetrics.txt"):
            get_cpuusage(eachfile, tokens,dict)
            groupid = getindex(tokens[0])
            field = tokens[0]+":"+str(groupid)
            print field
            fields.append(field)
            if(check_delta(tokens[0]) == True):
                deltaValue = calculate_cpudelta(dict["cpu_usage"])
                values.append(deltaValue)
            else:
               values.append(tokens[1])
               dict[tokens[0]] = float(tokens[1])
        else:
            txt_file = open(os.path.join(homepath,datadir,eachfile))
            lines = txt_file.read().split("\n")
            for eachline in lines:
                tokens = eachline.split("=")
                if(len(tokens) == 1):
                    continue
                if(tokens[0] != "timestamp"):
                    groupid = getindex(tokens[0])
                    field = tokens[0]+":"+str(groupid)
                    print field
                else:
                    field = tokens[0]
                fields.append(field)
                if(eachfile == "diskmetrics.txt"):
                    tokens[1] = float(float(tokens[1])*512/(1024*1024))
                elif(eachfile == "diskusedmetrics.txt" or eachfile == "memmetrics.txt"):
                    tokens[1] = float(float(tokens[1])/1024)
                elif(eachfile == "networkmetrics.txt"):
                    tokens[1] = float(float(tokens[1])/(1024*1024))
                if(check_delta(tokens[0]) == True):
                    deltaValue = calculate_delta(tokens[0],tokens[1])
                    values.append(deltaValue)
                    dict[tokens[0]] = float(tokens[1]) # Actual values need to be stored in dict and not delta values
                else:
                    if(tokens[0] == "timestamp"):
                        values.append(tokens[1])
                    else:
                        values.append(round(float(tokens[1]),4))
                    dict[tokens[0]] = float(tokens[1])

    if(numlines < 1):
        listtocsv(fields)
        FieldsWritten = True
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
    listtocsv(values)
    resource_usage_file.flush()
    resource_usage_file.close()
    update_results(dict)
except KeyboardInterrupt:
    print "Interrupt from keyboard"


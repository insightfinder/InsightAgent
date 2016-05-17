#!/usr/bin/python

import linecache
import json
import csv
import subprocess
import time
import os
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

def listtocsv(lists):
    log = ''
    for i in range(0,len(lists)):
        log = log + str(lists[i])
        if(i+1 != len(lists)):
            log = log + ','
    resource_usage_file.write("%s\n"%(log))


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
                first_result[tokens[0]] = float(tokens[1])
    update_results(first_result)
    time.sleep(1)
    proc = subprocess.Popen([os.path.join(homepath,"getmetrics.sh")], cwd=homepath, stdout=subprocess.PIPE, shell=True)
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
    return round(delta,4)

def calculate_cpudelta(current_result):
    previous_result = get_previous_results()
    prev_cpu_usage = previous_result["cpu_usage"]
    prev_total = 0
    curr_total = 0
    for eachmetric in prev_cpu_usage:
        prev_total += prev_cpu_usage[eachmetric]
    for eachmetric in current_result:
        curr_total += current_result[eachmetric]
    prev_idle = prev_cpu_usage["idle"] + prev_cpu_usage["iowait"]
    curr_idle = current_result["idle"] + current_result["iowait"]
    if((curr_total - prev_total) == 0):
        result = 0
    else:
        result = (1-round((curr_idle - prev_idle)/(curr_total - prev_total),4))*100
    return result

def get_cpuusage(filename,field_values,which_dict):
    cpuusage_file = open(os.path.join(homepath,datadir,filename))
    lines = cpuusage_file.read().split("\n")
    cpu_dict={}
    for eachline in lines:
        tokens_split = eachline.split("=")
        if(len(tokens_split) == 1):
            continue
        cpu_dict[tokens_split[0]] = float(tokens_split[1])
    which_dict["cpu_usage"] = cpu_dict
    Total = cpu_dict["user"] + cpu_dict["nice"] + cpu_dict["system"] + cpu_dict["idle"] + cpu_dict["iowait"] + cpu_dict["irq"] + cpu_dict["softirq"]
    idle = cpu_dict["idle"] + cpu_dict["iowait"]
    field_values[0] = "CPU_utilization#%"
    result = 1 - round(float(idle/Total),4)
    field_values.append(result*100)

filenames = ["timestamp.txt", "cpumetrics.txt","diskmetrics.txt","diskusedmetrics.txt","networkmetrics.txt","memmetrics.txt"]
fields = []
try:
    date = time.strftime("%Y%m%d")
    resource_usage_file = open(os.path.join(homepath,datadir+date+".csv"),'a+')
    numlines = len(resource_usage_file.readlines())
    values = []
    dict = {}
    proc = subprocess.Popen([os.path.join(homepath,"getmetrics.sh")], cwd=homepath, stdout=subprocess.PIPE, shell=True)
    (out,err) = proc.communicate()

    if(os.path.isfile("previous_results.json") == False):
        init_previous_results()

    tokens = []
    for eachfile in filenames:
        if(eachfile == "cpumetrics.txt"):
            get_cpuusage(eachfile, tokens,dict)
            fields.append(tokens[0])
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
                fields.append(tokens[0])
                if(check_delta(tokens[0]) == True):
                    deltaValue = calculate_delta(tokens[0],tokens[1])
                    values.append(deltaValue)
                    dict[tokens[0]] = float(tokens[1]) # Actual values need to be stored in dict and not delta values
                else:
                   values.append(tokens[1])
                   dict[tokens[0]] = round(float(tokens[1]),4)


    if(numlines < 1):
        listtocsv(fields)
        FieldsWritten = True
    listtocsv(values)
    resource_usage_file.flush()
    resource_usage_file.close()
    update_results(dict)
except KeyboardInterrupt:
    print "Interrupt from keyboard"


#!/usr/bin/python

import time
import datetime
import requests
import sys
import os
import subprocess
import signal
import socket
from optparse import OptionParser
import json

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

hostname=socket.gethostname()
cAdvisoraddress = "http://"+hostname+":8080/api/v1.3/docker/"

command = ['bash', '-c', 'source ' + str(homepath) + '/.agent.bashrc && env']
proc = subprocess.Popen(command, stdout = subprocess.PIPE)
for line in proc.stdout:
    (key, _, value) = line.partition("=")
    os.environ[key] = value.strip()
proc.communicate()
samplingInterval = os.environ["SAMPLING_INTERVAL"]
samplingInterval = int(samplingInterval) * 60 / 2

counter_time_map = {}
counter = 0
##the default value it 60-1, when cAdvisor started, the code need to calculate the index because of the sliding window
index = 59
dockers = []
num_apache = 0
num_sql = 0
newInstanceAvailable = False

#The json structure to get data from cadvisor varies between latest and old versions
cAdvisorStruct = {"old": ["/docker/",""], "new": ["/system.slice/docker-", ".scope"]}

def getindex(colName):
    if colName == "CPU":
        return 3001
    elif colName == "DiskRead" or colName == "DiskWrite":
        return 3002
    elif colName == "NetworkIn" or colName == "NetworkOut":
        return 3003
    elif colName == "MemUsed":
        return 3004

def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]

dockerInstances = []
def update_docker():
    global dockers
    global num_apache
    global num_sql
    global newInstanceAvailable
    global dockerInstances


    proc = subprocess.Popen(["docker ps --no-trunc | awk '{if(NR!=1) print $1}'"], stdout=subprocess.PIPE, shell=True)
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
        towritePreviousInstances = {}
        towritePreviousInstances["overallDockerInstances"] = newInstances
        with open(os.path.join(homepath,datadir+"totalInstances.json"),'w') as f:
            json.dump(towritePreviousInstances,f)
        newInstanceAvailable = True

def getmetric():
    global counter_time_map
    global counter
    global index
    global dockers
    global num_apache
    global num_sql
    global cAdvisoraddress
    global dockerInstances
    global samplingInterval

    try:
        startTime = int(round(time.time() * 1000))
        date = time.strftime("%Y%m%d")
        ipAddress = get_ip_address()
        while True:
            try:
                r = requests.get(cAdvisoraddress)
            except:
                currTime = int(round(time.time() * 1000))
                if currTime > startTime+10000:
                    print "unable to get requests from ",cAdvisoraddress
                    sys.exit()
                continue
            if newInstanceAvailable == True and os.path.isfile(os.path.join(homepath,datadir+date+".csv")) == True:
                oldFile = os.path.join(homepath,datadir+date+".csv")
                newFile = os.path.join(homepath,datadir+date+"."+time.strftime("%Y%m%d%H%M%S")+".csv")
                os.rename(oldFile,newFile)
            if(cAdvisorStruct["old"][0]+dockers[0]+cAdvisorStruct["old"][1]) in r.json():
                jsonStruct = cAdvisorStruct["old"]
            elif(cAdvisorStruct["new"][0]+dockers[0]+cAdvisorStruct["new"][1]) in r.json():
                jsonStruct = cAdvisorStruct["new"]
            else:
                print "Unsupported Cadvisor version"
                sys.exit()
            index = len(r.json()[jsonStruct[0]+dockers[0]+jsonStruct[1]]["stats"])-1
            time_stamp = startTime
            if (time_stamp in counter_time_map.values()):
                continue
            counter_time_map[counter] = time_stamp
            counter = (counter+1)%60
            log = str(startTime)
            cpu_all = 0
            resource_usage_file = open(os.path.join(homepath,datadir+date+".csv"), 'a+')
            numlines = len(resource_usage_file.readlines())
            for i in range(len(dockers)-1):
                #get cpu
                index = len(r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"])-1
                if index-int(samplingInterval) < 0:
                    samplingInterval = 1
                cpu_used = r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index]["cpu"]["usage"]["total"]
                prev_cpu = r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index-int(samplingInterval)]["cpu"]["usage"]["total"]
                cur_cpu = float(float(cpu_used - prev_cpu)/1000000000)
                cur_cpu = abs(cur_cpu)
                #get mem
                curr_mem = r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index]['memory']['usage']
                mem = float(float(curr_mem)/(1024*1024)) #MB
                mem = abs(mem)
                #get disk
                curr_block_num = len(r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index]["diskio"]["io_service_bytes"])
                curr_io_read = 0
                curr_io_write = 0
                prev_io_read = 0
                prev_io_write = 0
                for j in range(curr_block_num):
                    curr_io_read += r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index]["diskio"]["io_service_bytes"][j]["stats"]["Read"]
                    curr_io_write += r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index]["diskio"]["io_service_bytes"][j]["stats"]["Write"]
                prev_block_num = len(r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index-int(samplingInterval)]["diskio"]["io_service_bytes"])
                prev_io_read = 0
                prev_io_write = 0
                for j in range(prev_block_num):
                    prev_io_read += r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index-int(samplingInterval)]["diskio"]["io_service_bytes"][j]["stats"]["Read"]
                    prev_io_write += r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index-int(samplingInterval)]["diskio"]["io_service_bytes"][j]["stats"]["Write"]
                io_read = float(float(curr_io_read - prev_io_read)/(1024*1024)) #MB
                io_write = float(float(curr_io_write - prev_io_write)/(1024*1024)) #MB
                #get network
                prev_network_t = r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index-int(samplingInterval)]["network"]["tx_bytes"]
                prev_network_r = r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index-int(samplingInterval)]["network"]["rx_bytes"]
                curr_network_t = r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index]["network"]["tx_bytes"]
                curr_network_r = r.json()[jsonStruct[0]+dockers[i]+jsonStruct[1]]["stats"][index]["network"]["rx_bytes"]
                network_t = float(float(curr_network_t - prev_network_t)/(1024*1024)) #MB
                network_r = float(float(curr_network_r - prev_network_r)/(1024*1024)) #MB
                log = log + "," + str(cur_cpu) + "," + str(io_read) + "," + str(io_write)+ "," + str(network_r)+ "," + str(network_t)+ "," + str(mem)
                #log = log + "," + str(cur_cpu)
                if(numlines < 1):
                    serverType = ["Web", "DB"]
                    fields = ["timestamp","CPU","DiskRead","DiskWrite","NetworkIn","NetworkOut","MemUsed"]
                    #fields = ["timestamp","CPU"]
                    if i == 0:
                        fieldnames = fields[0]
                    host = hostname.partition(".")[0]
                    for k in range(1,len(fields)):
                        if(fields[k] == "timestamp"):
                            continue
                        if(fieldnames != ""):
                            fieldnames = fieldnames + ","
                        groupid = getindex(fields[k])
                        dockerID = dockers[i]
                        if len(dockerID) > 12:
                            dockerID = dockerID[:12]
                        metric = fields[k] + "[" + dockerID + "_" + host + "]"
                        fieldnames = fieldnames + metric +":"+str(groupid)
            if(numlines < 1):
                resource_usage_file.write("%s\n"%(fieldnames))
            print log #is it possible that print too many things?
            writelog = log
            resource_usage_file.write("%s\n" % (writelog))
            resource_usage_file.flush()
            resource_usage_file.close()
            break;
    except KeyboardInterrupt:
        print "Keyboard Interrupt"


def main():
    try:
        update_docker()
        getmetric()
    except (KeyboardInterrupt, SystemExit):
        print "Keyboard Interrupt"
        sys.exit()

if __name__ == "__main__":
    main()

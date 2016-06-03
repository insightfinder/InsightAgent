#Version8: based of monitorMetrics7.py
#This script makes a GET request to the cAdvisor running on hgcc07

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

counter_time_map = {}
counter = 0
##the default value it 60-1, when cAdvisor started, the code need to calculate the index because of the sliding window
index = 59
dockers = []
num_apache = 0
num_sql = 0
newInstanceAvailable = False

def getindex(colName):
    if colName == "CPU#%":
        return 1
    elif colName == "MemUsed#MB":
        return 2

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

    proc = subprocess.Popen(["docker ps --no-trunc | grep -cP 'rubis_apache' | awk '{print $ 1;}'"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    num_apache = int(out.split("\n")[0])

    proc = subprocess.Popen(["docker ps --no-trunc | grep -cP 'rubis_db' | awk '{print $ 1;}'"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    num_sql = int(out.split("\n")[0])

    proc = subprocess.Popen(["docker ps --no-trunc | grep -E 'rubis_apache|rubis_db' | awk '{print $ 1;}'"], stdout=subprocess.PIPE, shell=True)
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
    for eachDocker in dockers:
        if eachDocker == "":
            continue
        if eachDocker not in dockerInstances:
            towritePreviousInstances = {}
            dockerInstances.append(eachDocker)
            towritePreviousInstances["overallDockerInstances"] = dockerInstances
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
            if num_apache == 0 and num_sql == 0:
                break
            if newInstanceAvailable == True:
                oldFile = os.path.join(homepath,datadir+date+".csv")
                newFile = os.path.join(homepath,datadir+date+"."+time.strftime("%Y%m%d%H%M%S")+".csv")
                os.rename(oldFile,newFile)
            index = len(r.json()["/docker/"+dockers[0]]["stats"])-1
            time_stamp = r.json()["/docker/"+dockers[0]]["stats"][index]["timestamp"][:19]
            if (time_stamp in counter_time_map.values()):
                continue
            counter_time_map[counter] = time_stamp
            counter = (counter+1)%60
            log = str((int(time.mktime(time.strptime(time_stamp, "%Y-%m-%dT%H:%M:%S")))-4*3600)*1000)
            cpu_all = 0
            resource_usage_file = open(os.path.join(homepath,datadir+date+".csv"), 'a+')
            numlines = len(resource_usage_file.readlines())
            if num_apache == 0 and len(dockers)-1 != len(dockerInstances):
                log = log + ",NaN,NaN"
            for i in range(len(dockers)-1):
                #get cpu
                cpu_used = r.json()["/docker/"+dockers[i]]["stats"][index]["cpu"]["usage"]["total"]
                prev_cpu = r.json()["/docker/"+dockers[i]]["stats"][index-1]["cpu"]["usage"]["total"]
                cur_cpu = float((cpu_used - prev_cpu)/10000000)
                cur_cpu = abs(cur_cpu)
                #get mem
                curr_mem = r.json()["/docker/"+dockers[i]]["stats"][index]['memory']['usage']
                mem = float(curr_mem/(1024*1024)) #MB
                mem = abs(mem)
                #get disk
                curr_block_num = len(r.json()["/docker/"+dockers[i]]["stats"][index]["diskio"]["io_service_bytes"])
                curr_io_read = 0
                curr_io_write = 0
                prev_io_read = 0
                prev_io_write = 0
                for j in range(curr_block_num):
                    curr_io_read += r.json()["/docker/"+dockers[i]]["stats"][index]["diskio"]["io_service_bytes"][j]["stats"]["Read"]
                    curr_io_write += r.json()["/docker/"+dockers[i]]["stats"][index]["diskio"]["io_service_bytes"][j]["stats"]["Write"]
                prev_block_num = len(r.json()["/docker/"+dockers[i]]["stats"][index-1]["diskio"]["io_service_bytes"])
                prev_io_read = 0
                prev_io_write = 0
                for j in range(prev_block_num):
                    prev_io_read += r.json()["/docker/"+dockers[i]]["stats"][index-1]["diskio"]["io_service_bytes"][j]["stats"]["Read"]
                    prev_io_write += r.json()["/docker/"+dockers[i]]["stats"][index-1]["diskio"]["io_service_bytes"][j]["stats"]["Write"]
                io_read = float((curr_io_read - prev_io_read)/(1024*1024)) #MB
                io_write = float((curr_io_write - prev_io_write)/(1024*1024)) #MB
                #get network
                prev_network_t = r.json()["/docker/"+dockers[i]]["stats"][index-1]["network"]["tx_bytes"]
                prev_network_r = r.json()["/docker/"+dockers[i]]["stats"][index-1]["network"]["rx_bytes"]
                curr_network_t = r.json()["/docker/"+dockers[i]]["stats"][index]["network"]["tx_bytes"]
                curr_network_r = r.json()["/docker/"+dockers[i]]["stats"][index]["network"]["rx_bytes"]
                network_t = float((curr_network_t - prev_network_t)/(1024*1024)) #MB
                network_r = float((curr_network_r - prev_network_r)/(1024*1024)) #MB
                #log = log + "," + str(cur_cpu) + "," + str(io_read) + "," + str(io_write)+ "," + str(network_r)+ "," + str(network_t)+ "," + str(mem)
                log = log + "," + str(cur_cpu) + "," + str(mem)
                if(numlines < 1):
                    serverType = ["Web", "DB"]
                    #fields = ["timestamp","CPU#%","DiskRead#MB","DiskWrite#MB","NetworkIn#MB","NetworkOut#MB","MemUsed#MB"]
                    fields = ["timestamp","CPU#%","MemUsed#MB"]
                    if i == 0:
                        fieldnames = fields[0]
                    host = hostname.partition(".")[0]
                    for k in range(1,len(fields)):
                        if(fields[k] == "timestamp"):
                            continue
                        if(fieldnames != ""):
                            fieldnames = fieldnames + ","
                        if num_apache == 0:
                            server = serverType[1]
                        else:
                            server = serverType[i]
                        groupid = getindex(fields[k])
                        metric = fields[k] + "[" + server + "_" + str(ipAddress) + "]"
                        fieldnames = fieldnames + metric +":"+str(groupid)
            if num_sql == 0 and len(dockers)-1 != len(dockerInstances):
                #log = log + ",NaN,NaN,NaN,NaN,NaN,NaN"
                log = log + ",NaN,NaN"
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

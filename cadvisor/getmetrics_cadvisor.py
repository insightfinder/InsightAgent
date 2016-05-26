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

def getindex(colName):
    if colName == "WEB_CPU_utilization#%" or colName == "DB_CPU_utilization#%":
	return 1
    elif colName == "WEB_DiskRead#MB" or colName == "DB_DiskRead#MB" or colName == "WEB_DiskWrite#MB" or colName == "DB_DiskWrite#MB":
	return 2
    elif colName == "WEB_NetworkIn#MB" or colName == "DB_NetworkIn#MB" or colName == "WEB_NetworkOut#MB" or colName == "DB_NetworkOut#MB":
	return 3
    elif colName == "WEB_MemUsed#MB" or colName == "DB_MemUsed#MB":
	return 4

def update_docker():
    global dockers
    global num_apache
    global num_sql

    proc = subprocess.Popen(["sudo docker ps --no-trunc | grep -cP 'rubis_apache' | awk '{print $ 1;}'"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    num_apache = int(out.split("\n")[0])

    proc = subprocess.Popen(["sudo docker ps --no-trunc | grep -cP 'rubis_db' | awk '{print $ 1;}'"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    num_sql = int(out.split("\n")[0])

    proc = subprocess.Popen(["sudo docker ps --no-trunc | grep -E 'rubis_apache|rubis_db' | awk '{print $ 1;}'"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    dockers = out.split("\n")

def getmetric():
    global counter_time_map
    global counter
    global index
    global dockers
    global num_apache
    global num_sql
    global cAdvisoraddress

    try:
        while True:
            try:
                r = requests.get(cAdvisoraddress)
            except:
                continue
            index = len(r.json()["/docker/"+dockers[0]]["stats"])-1
            time_stamp = r.json()["/docker/"+dockers[0]]["stats"][index]["timestamp"][:19]
            if (time_stamp in counter_time_map.values()):
                continue
            counter_time_map[counter] = time_stamp
            counter = (counter+1)%60
            log = str((int(time.mktime(time.strptime(time_stamp, "%Y-%m-%dT%H:%M:%S")))-4*3600)*1000)
            cpu_all = 0
            if num_apache == 0:
                log = log + ","
            for i in range(len(dockers)-1):
                #get cpu
                cpu_used = r.json()["/docker/"+dockers[i]]["stats"][index]["cpu"]["usage"]["total"]
                prev_cpu = r.json()["/docker/"+dockers[i]]["stats"][index-1]["cpu"]["usage"]["total"]
                cur_cpu = float((cpu_used - prev_cpu)/10000000)
		#get mem
                curr_mem = r.json()["/docker/"+dockers[i]]["stats"][index]['memory']['usage']
                mem = float(curr_mem/(1024*1024)) #MB
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
                log = log + "," + str(cur_cpu) + "," + str(io_read) + "," + str(io_write)+ "," + str(network_r)+ "," + str(network_t)+ "," + str(mem)

            print log #is it possible that print too many things?
            writelog = log
            date = time.strftime("%Y%m%d")
            resource_usage_file = open(os.path.join(homepath,datadir+date+".csv"), 'a+')
            numlines = len(resource_usage_file.readlines())
            if(numlines < 1):
		fields = ["timestamp","WEB_CPU_utilization#%","WEB_DiskRead#MB","WEB_DiskWrite#MB","WEB_NetworkIn#MB","WEB_NetworkOut#MB","WEB_MemUsed#MB","timestamp","DB_CPU_utilization#%","DB_DiskRead#MB","DB_DiskWrite#MB","DB_NetworkIn#MB","DB_NetworkOut#MB","DB_MemUsed#MB"]
		fieldnames = fields[0]
		host = hostname.partition(".")[0]
		for i in range(1,len(fields)):
		    if(fields[i] == "timestamp"):
			continue
		    if(fieldnames != ""):
			fieldnames = fieldnames + ","
		    groupid = getindex(fields[i])
		    fieldnames = fieldnames+fields[i] + "[" +host+"]"+":"+str(groupid)
		resource_usage_file.write("%s\n"%(fieldnames))
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

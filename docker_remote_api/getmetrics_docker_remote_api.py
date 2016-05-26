#!/bin/python
import subprocess
import os
from optparse import OptionParser
import linecache
import json
import time
import datetime
import socket

usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",
    action="store", dest="homepath", help="Directory to run from")
(options, args) = parser.parse_args()
date = time.strftime("%Y%m%d")
hostname=socket.gethostname().partition(".")[0]

if options.homepath is None:
    homepath = os.getcwd()
else:
    homepath = options.homepath
datadir = 'data/'

def listtocsv(lists):
    finallog = ''
    for i in range(0,len(lists)):
        finallog = finallog + str(lists[i])
        if(i+1 != len(lists)):
            finallog = finallog + ','
    csvFile.write("%s\n"%(finallog))

def getindex(colName):
    if colName == "CPU_utilization#%":
        return 1
    elif colName == "DiskRead#MB" or colName == "DiskWrite#MB":
        return 2
    elif colName == "NetworkIn#MB" or colName == "NetworkOut#MB":
        return 3
    elif colName == "MemUsed#MB":
        return 4

metricResults = {}
def toJson (header, values):
    global metricResults
    headerFields = header.split(",")
    valueFields = values.split(",")
    for i in range(0,len(headerFields)):
        metricResults[headerFields[i]] = valueFields[i]

def updateResults():
    global metricResults
    with open(os.path.join(homepath,datadir+"previous_results.json"),'w') as f:
	json.dump(metricResults,f)

def initPreviousResults():
    global numlines
    global date
    global hostname

    log = ''
    for i in range(len(dockers)-1):
	try:
	    filename = "stat%s.txt"%dockers[i]
	    statsFile = open(os.path.join(homepath,datadir+filename),'r')
	except IOError as e:
	    print "I/O error({0}): {1}: {2}".format(e.errno, e.strerror, e.filename)
	    continue
	data = statsFile.readlines()
	for eachline in data:
	    if isJson(eachline) == True:
		metricData = json.loads(eachline)
		break
	if(numlines < 1):
	    fields = ["timestamp","CPU_utilization#%","DiskRead#MB","DiskWrite#MB","NetworkIn#MB","NetworkOut#MB","MemUsed#MB"]
	    if i == 0:
		fieldnames = fields[0]
	    host = dockers[i]
	    for j in range(1,len(fields)):
		if(fieldnames != ""):
		    fieldnames = fieldnames + ","
		groupid = getindex(fields[j])
		nextfield = fields[j] + "[" +hostname+"_"+host+"]"+":"+str(groupid)
		fieldnames = fieldnames + nextfield
	else:
	    fieldnames = linecache.getline(os.path.join(homepath,datadir+date+".csv"),1)
	timestamp = metricData['read'][:19]
	timestamp =  int(time.mktime(datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").timetuple())*1000)
	networkRx = round(float(float(metricData['network']['rx_bytes'])/(1024*1024)),4) #MB
	networkTx = round(float(float(metricData['network']['tx_bytes'])/(1024*1024)),4) #MB
	cpu = round(float(metricData['cpu_stats']['cpu_usage']['total_usage'])/10000000,4) #Convert nanoseconds to jiffies
	memUsed = round(float(float(metricData['memory_stats']['usage'])/(1024*1024)),4) #MB
	diskRead = round(float(float(metricData['blkio_stats']['io_service_bytes_recursive'][0]['value'])/(1024*1024)),4) #MB
	diskWrite = round(float(float(metricData['blkio_stats']['io_service_bytes_recursive'][1]['value'])/(1024*1024)),4) #MB
	if i == 0:
	    log = log + str(timestamp)
	log = log + "," + str(cpu) + "," + str(diskRead) + "," + str(diskWrite) + "," + str(networkRx) + "," + str(networkTx) + "," + str(memUsed)
    toJson(fieldnames,log)
    updateResults()
    time.sleep(1)
    proc = subprocess.Popen([os.path.join(homepath,datadir+"getmetrics_docker.sh")], cwd=homepath, stdout=subprocess.PIPE, shell=True)
    (out,err) = proc.communicate()

def getPreviousResults():
    with open(os.path.join(homepath,datadir+"previous_results.json"),'r') as f:
	return json.load(f)

def isJson(jsonString):
    try:
	jsonObject = json.loads(jsonString)
	if jsonObject['read'] != "":
	    return True
    except ValueError, e:
	return False
    except TypeError, e:
	return False
    return True

def checkDelta(fd):
    deltaFields = ["CPU_utilization", "DiskRead", "DiskWrite", "NetworkIn", "NetworkOut"]
    for eachfield in deltaFields:
	if(eachfield == fd):
	    return True
    return False

def calculateDelta():
    global fieldnames
    fieldsList = fieldnames.split(",")
    previousResult = getPreviousResults()
    currentResult = metricResults
    finallogList = []
    for key in fieldsList:
	if(checkDelta(key.split('#')[0]) == True):
	    deltaValue = float(currentResult[key]) - float(previousResult[key])
	    finallogList.append(deltaValue)
        else:
	    finallogList.append(currentResult[key])
    return finallogList

def update_docker():
    global dockers

    proc = subprocess.Popen(["docker ps | awk '{if(NR!=1) print $1}'"], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    dockers = out.split("\n")
    cronfile = open(os.path.join(homepath,datadir+"getmetrics_docker.sh"),'w')
    cronfile.write("#!/bin/sh\nDATADIR='data/'\ncd $DATADIR\n")
    containerCount = 0
    for container in dockers:
	if container == "":
	    continue
        containerCount+=1
	command = "echo -e \"GET /containers/"+container+"/stats?stream=0 HTTP/1.1\\r\\n\" | nc -U /var/run/docker.sock > stat"+container+".txt & PID"+str(containerCount)+"=$!"
	cronfile.write(command+"\n")
    for i in range(1,containerCount+1):
	cronfile.write("wait $PID"+str(i)+"\n")
    cronfile.close()
    os.chmod(os.path.join(homepath,datadir+"getmetrics_docker.sh"),0755)

def getmetrics():
    global dockers
    global numlines
    global date
    global fieldnames
    global csvFile
    global hostname
    try:
	while True:
	    csvFile = open(os.path.join(homepath,datadir+date+".csv"), 'a+')
	    numlines = len(csvFile.readlines())
            if(os.path.isfile(homepath+"/"+datadir+"previous_results.json") == False):
                initPreviousResults()
	    log = ''
	    for i in range(len(dockers)-1):
		try:
		    filename = "stat%s.txt"%dockers[i]
		    statsFile = open(os.path.join(homepath,datadir+filename),'r')
		except IOError as e:
		    print "I/O error({0}): {1}: {2}".format(e.errno, e.strerror, e.filename)
		    continue
                data = statsFile.readlines()
		for eachline in data:
		    if isJson(eachline) == True:
			metricData = json.loads(eachline)
			break
                if(numlines < 1):
                    fields = ["timestamp","CPU_utilization#%","DiskRead#MB","DiskWrite#MB","NetworkIn#MB","NetworkOut#MB","MemUsed#MB"]
                    if i == 0:
                        fieldnames = fields[0]
                    host = dockers[i]
                    for j in range(1,len(fields)):
                        if(fieldnames != ""):
                            fieldnames = fieldnames + ","
                        groupid = getindex(fields[j])
                        nextfield = fields[j] + "[" +hostname+"_"+host+"]"+":"+str(groupid)
                        fieldnames = fieldnames + nextfield
		else:
		    fieldnames = linecache.getline(os.path.join(homepath,datadir+date+".csv"),1).rstrip("\n")
		timestamp = metricData['read'][:19]
		timestamp =  int(time.mktime(datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").timetuple())*1000)
		networkRx = round(float(float(metricData['network']['rx_bytes'])/(1024*1024)),4) #MB
		networkTx = round(float(float(metricData['network']['tx_bytes'])/(1024*1024)),4) #MB
		cpu = round(float(metricData['cpu_stats']['cpu_usage']['total_usage'])/10000000,4) #Convert nanoseconds to jiffies
		memUsed = round(float(float(metricData['memory_stats']['usage'])/(1024*1024)),4) #MB
		diskRead = round(float(float(metricData['blkio_stats']['io_service_bytes_recursive'][0]['value'])/(1024*1024)),4) #MB
		diskWrite = round(float(float(metricData['blkio_stats']['io_service_bytes_recursive'][1]['value'])/(1024*1024)),4) #MB
		if i == 0:
		    log = log + str(timestamp)
		log = log + "," + str(cpu) + "," + str(diskRead) + "," + str(diskWrite) + "," + str(networkRx) + "," + str(networkTx) + "," + str(memUsed)
	    print log
	    toJson(fieldnames,log)
	    deltaList = calculateDelta()
	    updateResults()
	    if numlines < 1:
		csvFile.write("%s\n"%(fieldnames))
	    listtocsv(deltaList)
	    csvFile.flush()
	    csvFile.close()
            break
    except KeyboardInterrupt:
	print "Keyboard Interrupt"

try:
    update_docker()
    proc = subprocess.Popen([os.path.join(homepath,datadir+"getmetrics_docker.sh")], cwd=homepath, stdout=subprocess.PIPE, shell=True)
    (out,err) = proc.communicate()
    getmetrics()
except KeyboardInterrupt:
    print "Interrupt from keyboard"


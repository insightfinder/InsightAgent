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

newInstanceAvailable = False

def listtocsv(lists):
    finallog = ''
    for i in range(0,len(lists)):
        finallog = finallog + str(lists[i])
        if(i+1 != len(lists)):
            finallog = finallog + ','
    if finallog != "":
        csvFile.write("%s\n"%(finallog))

def getindex(colName):
    if colName == "CPU#%":
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
    if header == "" or values == "":
        return
    headerFields = header.split(",")
    valueFields = values.split(",")
    for i in range(0,len(headerFields)):
        metricResults[headerFields[i]] = valueFields[i]

def updateResults():
    global metricResults
    if not metricResults:
        return
    with open(os.path.join(homepath,datadir+"previous_results.json"),'w') as f:
        json.dump(metricResults,f)

def initPreviousResults():
    global numlines
    global date
    global hostname
    global dockers
    timestampRecorded = False

    log = ''
    fieldnames = ''
    towritePreviousInstances = {}
    for i in range(len(dockers)):
        validDocker = False
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
                validDocker = True
                break
        if validDocker == False:
            continue
        timestamp = metricData['read'][:19]
        timestamp =  int(time.mktime(datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").timetuple())*1000)
        if (time.time()*1000 - timestamp) > 300000:
            continue
        configFileName = [fname for fname in os.listdir("/var/lib/docker/containers/"+dockers[i]+"/") if fname.startswith("config")]
        if os.path.isfile("/var/lib/docker/containers/"+dockers[i]+"/"+configFileName[0]) == False:
            continue
        containerConfig = open("/var/lib/docker/containers/"+dockers[i]+"/"+configFileName[0],"r")
        dataline = containerConfig.readline()
        containerName = json.loads(dataline)["Name"]
        if "insightfinder" in containerName:
            continue
        fields = ["timestamp","CPU#%","DiskRead#MB","DiskWrite#MB","NetworkIn#MB","NetworkOut#MB","MemUsed#MB"]
        if timestampRecorded == False:
            fieldnames = fields[0]
        host = dockers[i]
        if len(host) > 12:
            host = host[:12]
        for j in range(1,len(fields)):
            if(fieldnames != ""):
                fieldnames = fieldnames + ","
            groupid = getindex(fields[j])
            nextfield = fields[j] + "[" +host+"_"+hostname+"]"+":"+str(groupid)
            fieldnames = fieldnames + nextfield
        try:
            if 'network' in metricData or 'networks' in metricData:
                networkRx = round(float(float(metricData['network']['rx_bytes'])/(1024*1024)),4) #MB
                networkTx = round(float(float(metricData['network']['tx_bytes'])/(1024*1024)),4) #MB
            else:
                networkRx = 0.0
                networkTx = 0.0
        except KeyError,e:
            networkMetrics = metricData['networks']
            networkRx = 0.0
            networkTx = 0.0
            for key in networkMetrics:
                networkRx += float(networkMetrics[key]['rx_bytes'])
                networkTx += float(networkMetrics[key]['tx_bytes'])
            networkRx = round(float(networkRx/(1024*1024)),4) #MB
            networkTx = round(float(networkTx/(1024*1024)),4) #MB
        cpu = round(float(metricData['cpu_stats']['cpu_usage']['total_usage'])/10000000,4) #Convert nanoseconds to jiffies
        memUsed = round(float(float(metricData['memory_stats']['usage'])/(1024*1024)),4) #MB
        diskRead = round(float(float(metricData['blkio_stats']['io_service_bytes_recursive'][0]['value'])/(1024*1024)),4) #MB
        diskWrite = round(float(float(metricData['blkio_stats']['io_service_bytes_recursive'][1]['value'])/(1024*1024)),4) #MB
        if timestampRecorded == False:
            if log != "":
                log = str(timestamp) + "," + log
            else:
                log = str(timestamp)
            timestampRecorded = True
        log = log + "," + str(cpu) + "," + str(diskRead) + "," + str(diskWrite) + "," + str(networkRx) + "," + str(networkTx) + "," + str(memUsed)
        dockerInstances.append(dockers[i])
        towritePreviousInstances["overallDockerInstances"] = dockerInstances
        with open(os.path.join(homepath,datadir+"totalInstances.json"),'w') as f:
            json.dump(towritePreviousInstances,f)
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
    return False

def checkDelta(fd):
    deltaFields = ["CPU", "DiskRead", "DiskWrite", "NetworkIn", "NetworkOut"]
    for eachfield in deltaFields:
        if(eachfield == fd):
            return True
    return False

precpu={}
def calculateDelta():
    global fieldnames
    global metricResults
    finallogList = []
    if fieldnames == "":
        return finallogList
    fieldsList = fieldnames.split(",")
    previousResult = getPreviousResults()
    currentResult = metricResults
    for key in fieldsList:
        if((key.split('#')[0]) == "CPU"):
            if  key not in precpu:
                deltaValue = "NaN"
                finallogList.append(deltaValue)
                continue
            previousCPU = precpu[key]
            if str(currentResult[key]) == "NaN" or str(previousCPU) == "NaN":
                deltaValue = "NaN"
            else:
                deltaValue =  round((float(currentResult[key]) - float(previousCPU)),4)
                if deltaValue < 0:
                    deltaValue = 0
            finallogList.append(deltaValue)
        elif(checkDelta(key.split('#')[0]) == True):
            if (key not in currentResult) or (key not in previousResult):
                deltaValue = "NaN"
            elif str(currentResult[key]) == "NaN" or str(previousResult[key]) == "NaN":
                deltaValue = "NaN"
            else:
                deltaValue = float(currentResult[key]) - float(previousResult[key])
                if deltaValue < 0:
                    deltaValue = 0
            finallogList.append(deltaValue)
        else:
            if key not in currentResult:
                currentValue = "NaN"
                finallogList.append(currentValue)
            else:
                finallogList.append(currentResult[key])
    return finallogList

def removeStatFiles():
    global dockers
    for i in range(len(dockers)):
        statfile = "stat%s.txt"%dockers[i]
        if os.path.isfile(os.path.join(homepath,datadir+statfile)) == True:
            os.remove(os.path.join(homepath,datadir+statfile))

dockerInstances = []
dockers = []
def update_docker():
    global newInstanceAvailable
    global dockers
    dockers = os.listdir("/var/lib/docker/containers")
    cronfile = open(os.path.join(homepath,datadir+"getmetrics_docker.sh"),'w')
    cronfile.write("#!/bin/sh\nDATADIR='data/'\ncd $DATADIR\n")
    containerCount = 0
    for container in dockers:
        if container == "":
            continue
        containerCount+=1
        command = "echo \"GET /containers/"+container+"/stats?stream=0 HTTP/1.1\\r\\n\" | nc -U -i 5 /var/run/docker.sock > stat"+container+".txt & PID"+str(containerCount)+"=$!"
        cronfile.write(command+"\n")
    for i in range(1,containerCount+1):
        cronfile.write("wait $PID"+str(i)+"\n")
    cronfile.close()
    os.chmod(os.path.join(homepath,datadir+"getmetrics_docker.sh"),0755)

metricData = {}
def getmetrics():
    global dockerInstances
    global numlines
    global date
    global fieldnames
    global csvFile
    global hostname
    global newInstanceAvailable
    timestampAvailable = False
    global metricData
    global dockers
    instances = []
    try:
        while True:
            fields = ["timestamp","CPU#%","DiskRead#MB","DiskWrite#MB","NetworkIn#MB","NetworkOut#MB","MemUsed#MB"]
            if newInstanceAvailable == True:
                oldFile = os.path.join(homepath,datadir+date+".csv")
                newFile = os.path.join(homepath,datadir+date+"."+time.strftime("%Y%m%d%H%M%S")+".csv")
                os.rename(oldFile,newFile)
            csvFile = open(os.path.join(homepath,datadir+date+".csv"), 'a+')
            numlines = len(csvFile.readlines())
            if(os.path.isfile(homepath+"/"+datadir+"previous_results.json") == False):
                initPreviousResults()
            log = ''
            fieldnames = ''
            for i in range(len(dockers)):
                try:
                    with open(os.path.join(homepath,datadir+"totalInstances.json"),'r') as f:
                        dockerInstances = json.load(f)["overallDockerInstances"]
                    filename = "stat%s.txt"%dockers[i]
                    host = dockers[i]
                    if len(host) > 12:
                        host = host[:12]
                    if os.path.isfile(os.path.join(homepath,datadir+filename)) == False:
                        if dockers[i] in dockerInstances:
                            for fieldIndex in range(1,len(fields)):
                                if(fieldnames != ""):
                                    fieldnames = fieldnames + ","
                                groupid = getindex(fields[fieldIndex])
                                nextfield = fields[fieldIndex] + "[" +host+"_"+hostname+"]"+":"+str(groupid)
                                fieldnames = fieldnames + nextfield
                                if(log != ""):
                                    log = log + ","
                                log = log + "NaN"
                            instances.append(dockers[i])
                            continue
                    else:
                        statsFile = open(os.path.join(homepath,datadir+filename),'r')
                except IOError as e:
                    print "I/O error({0}): {1}: {2}".format(e.errno, e.strerror, e.filename)
                    continue
                data = statsFile.readlines()
                jsonAvailable = False
                for eachline in data:
                    if isJson(eachline) == True:
                        metricData = json.loads(eachline)
                        jsonAvailable = True
                        break
                #File available but stat file doesn't have json object
                if jsonAvailable == False:
                    if dockers[i] in dockerInstances:
                        for fieldIndex in range(1,len(fields)):
                            if(fieldnames != ""):
                                fieldnames = fieldnames + ","
                            groupid = getindex(fields[fieldIndex])
                            nextfield = fields[fieldIndex] + "[" +host+"_"+hostname+"]"+":"+str(groupid)
                            fieldnames = fieldnames + nextfield
                            if(log != ""):
                                log = log + ","
                            log = log + "NaN"
                        instances.append(dockers[i])
                    continue
                timestamp = metricData['read'][:19]
                timestamp =  int(time.mktime(datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S").timetuple())*1000)
                if (time.time()*1000 - timestamp) > 300000:
                    continue
                configFileName = [fname for fname in os.listdir("/var/lib/docker/containers/"+dockers[i]+"/") if fname.startswith("config")]
                if os.path.isfile("/var/lib/docker/containers/"+dockers[i]+"/"+configFileName[0]) == False:
                    continue
                containerConfig = open("/var/lib/docker/containers/"+dockers[i]+"/"+configFileName[0],"r")
                dataline = containerConfig.readline()
                containerName = json.loads(dataline)["Name"]
                if "insightfinder" in containerName:
                    continue
                for j in range(1,len(fields)):
                    if(fieldnames != ""):
                        fieldnames = fieldnames + ","
                    groupid = getindex(fields[j])
                    nextfield = fields[j] + "[" +host+"_"+hostname+"]"+":"+str(groupid)
                    fieldnames = fieldnames + nextfield
                try:
                    if "network" in metricData or "networks" in metricData:
                        networkRx = round(float(float(metricData['network']['rx_bytes'])/(1024*1024)),4) #MB
                        networkTx = round(float(float(metricData['network']['tx_bytes'])/(1024*1024)),4) #MB
                    else:
                        networkRx = 0.0
                        networkTx = 0.0
                except KeyError,e:
                    networkMetrics = metricData['networks']
                    networkRx = 0.0
                    networkTx = 0.0
                    for key in networkMetrics:
                        networkRx += float(networkMetrics[key]['rx_bytes'])
                        networkTx += float(networkMetrics[key]['tx_bytes'])
                    networkRx = round(float(networkRx/(1024*1024)),4) #MB
                    networkTx = round(float(networkTx/(1024*1024)),4) #MB
                cpu = round(float(metricData['cpu_stats']['cpu_usage']['total_usage'])/10000000,4) #Convert nanoseconds to jiffies
                precpu["CPU#%["+host+"_"+hostname+"]"+":"+str(1)] = round(float(metricData['precpu_stats']['cpu_usage']['total_usage'])/10000000,4)
                memUsed = round(float(float(metricData['memory_stats']['usage'])/(1024*1024)),4) #MB
                diskRead = round(float(float(metricData['blkio_stats']['io_service_bytes_recursive'][0]['value'])/(1024*1024)),4) #MB
                diskWrite = round(float(float(metricData['blkio_stats']['io_service_bytes_recursive'][1]['value'])/(1024*1024)),4) #MB
                instances.append(dockers[i])
                if timestampAvailable == False:
                    if fieldnames != "":
                        fieldnames = fields[0] + "," + fieldnames
                    else:
                        fieldnames = fields[0]
                    if log == "":
                        log = str(timestamp)
                    else:
                        log = str(timestamp) + "," + log
                    timestampAvailable = True
                log = log + "," + str(cpu) + "," + str(diskRead) + "," + str(diskWrite) + "," + str(networkRx) + "," + str(networkTx) + "," + str(memUsed)
            if timestampAvailable == False and fieldnames != "":
                fieldnames = fields[0] + "," + fieldnames
                log = "NaN" + "," + log
            toJson(fieldnames,log)
            deltaList = calculateDelta()
            updateResults()
            if cmp(instances,dockerInstances) != 0:
                newInstanceAvailable = True
                oldFile = os.path.join(homepath,datadir+date+".csv")
                newFile = os.path.join(homepath,datadir+date+"."+time.strftime("%Y%m%d%H%M%S")+".csv")
                os.rename(oldFile,newFile)
                csvFile = open(os.path.join(homepath,datadir+date+".csv"), 'a+')
                numlines = len(csvFile.readlines())
                towritePreviousInstances = {}
                towritePreviousInstances["overallDockerInstances"] = instances
                with open(os.path.join(homepath,datadir+"totalInstances.json"),'w') as f:
                    json.dump(towritePreviousInstances,f)
            if numlines < 1 or newInstanceAvailable == True:
                if fieldnames != "":
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
    removeStatFiles()
except KeyboardInterrupt:
    print "Interrupt from keyboard"

#!/usr/time bin/env python
# encoding: utf-8

import os,sys
import time
import getopt
import commands
import subprocess
import math
import string
import time
import argparse
import datetime

allSystemCalls = {}
allCounts = {}
allNormalCounts = {}
allAnomalyCounts = {}
syscallList = []
normalUnitCount = 0
anomalyUnitCount = 0
calc_start = 0
calc_end = 0

def get_args():
    parser = argparse.ArgumentParser(description='Script retrieves arguments for insightfinder pre-processing system call traces.')
    parser.add_argument('-d', '--HOME_DIR', type=str, help='The HOME directory of Insight syscall trace', required=True)
    parser.add_argument('-p', '--PROCESS_NAME', type=str, help='The process name for which will be pre-procesing.', required=True)
    parser.add_argument('-f', '--SYSCALL_LOG', type=str, help='The file which stores the system call traces', required=True)
    args = parser.parse_args()
    syscallLog = args.SYSCALL_LOG
    procNames = args.PROCESS_NAME
    homepath = args.HOME_DIR
    return homepath, procNames, syscallLog


class SystemCall:
    def __init__(self,timeStamp,name,tid):
        self.timeStamp = timeStamp
        self.name = name
        self.tid = tid
        self.executionTime = -1
        self.exitValue = -1


def outputLog(systemCallList,outFileName,procName):
    outFile = open(outFileName,'w')
    global calc_end
    global calc_start
    outFile.write("#pid,tid,start_time,end_time,cpu_id,event,functionName\n")
    total = 0
    nItems = 0
    pTime = -1
    average = {}
    averageList = {}
    counts = {}
    preContext = -1
    preTID = -1
    preContextTID = -1
    for item in systemCallList:
        #print item.timeStamp, item.name, item.tid
        if not "CONTEXT" in item.name:
            if pTime != -1:
                diff = float(item.timeStamp) - pTime
                if not item.tid in average:
                    average[item.tid] = diff
                    counts[item.tid] = 1
                    averageList[item.tid] = []
                else:
                    average[item.tid] = average[item.tid]+diff
                    counts[item.tid] = counts[item.tid] + 1
                averageList[item.tid].append(diff)
        else:
            preContext = pTime
            preContextTID = preTID
        pTime = float(item.timeStamp)
        preTID = item.tid
    #print average
    intervals = {}
    iTotal = float(0)
    iCount = 0
    for key,value in average.iteritems():
        avg = float((1.0* average[key])/counts[key])
        avgList = averageList[key]
        temp = 0
        for item in avgList:
            temp = temp+item
        outV = float(float(temp)/len(avgList))
        std = calcSTD(avg,avgList)
        #print str(outV) + " " + str(std)
        interval = avg + (2.0 * std)
        iTotal = iTotal + float(interval)
        iCount = iCount + 1
        intervals[key] = interval
        pMethod = getPercentile(avgList,0.999)
        print "Mean+2 Method: "+str(interval)+ " PMethod:"+str(pMethod)
        #intervals[key] = pMethod
    calc_end = time.clock()
    elapsed = calc_end - calc_start
    print "Interval calculation time: "+str(elapsed)
    pTID = -1
    threadLists = {}
    #Split by TID
    for item in systemCallList:
        if not item.tid in threadLists:
            threadLists[item.tid] = []
        threadLists[item.tid].append(item)
    #for k,v in threadLists.iteritems():
    #   for items in v:
    #       print items.tid + " " +items.name
    #Split by context
    listsWithContext = {}
    for tid,cList in threadLists.iteritems():
        listsWithContext[tid] = []
        listToAdd = []
        for sysCall in cList:
            if not "CONTEXT" in sysCall.name:
                listToAdd.append(sysCall)
            else:
                listsWithContext[tid].append(listToAdd)
                listToAdd = []
        listsWithContext[tid].append(listToAdd)
    #Split by time gap
    for tid,lists in listsWithContext.iteritems():
        for syscallList in lists:
            pTime = -1
            currentList = []
            for item in syscallList:                        
                if pTime != -1:
                    diff = float(item.timeStamp) - pTime
                    #print str(iToUse) + " " +str(diff) + " CTID: "+str(item.tid) + "pTID: " +str(pTID )
                    #Output cList create new list
                    if diff >= intervals[item.tid]:
                        print "Large gap, splitting Diff: "+str(diff) + " Threshold: "+str(intervals[item.tid])
                        outputList(currentList,outFile,procName)
                        currentList = []
                    currentList.append(item)
                pTime = float(item.timeStamp)
            #Output anything left
            outputList(currentList,outFile,procName)
    outFile.close()


def getPercentile(listToCheck,pValue):
    index = int(len(listToCheck)*pValue)
    listToCheck.sort()
    cIndex = 0
    for item in listToCheck:
        cIndex = cIndex+1
        if cIndex == index:
            return item
        
def outputList(currentList,outFile,procName):
    if len(currentList) == 0:
        return
    tUnit = currentList[0]
    outString = str(tUnit.tid) +","+str(tUnit.tid)+","+str(tUnit.timeStamp)+","+str(tUnit.timeStamp)+",0,"+"!"+","+str(tUnit.timeStamp)+" None"
    outFile.write(outString+"\n")
    for item in currentList:
        outString = str(item.tid)+","+str(item.tid)+","+str(item.timeStamp)+","+str(item.timeStamp)+",0,EID_SVC_BGN,"+item.name+","+procName
        outFile.write(outString+"\n")
        outString = str(item.tid) +","+str(item.tid)+","+str(item.exitValue)+","+str(item.exitValue)+",0,EID_SVC_END_LX,exit_syscall,"+procName
        outFile.write(outString+"\n")
    outString = str(tUnit.tid) +","+str(tUnit.tid)+","+str(tUnit.timeStamp)+","+str(tUnit.timeStamp)+",0,"+"@"+","+str(tUnit.timeStamp)+" None"
    outFile.write(outString+"\n")

def calcSTD(avg,cList):
    cTotal = 0
    for i in cList:
        cDiff = i - avg
        cDiff = cDiff*cDiff
        cTotal+=cDiff   
    cTotal = float((1.0*cTotal)/len(cList))
    retVal = math.sqrt(cTotal)
    return retVal

def getSystemCall(line):
    if line == -1:
        return SystemCall(-1,"CONTEXT_SWITCH",-1)
    timeString = line.split("]")[0].split("[")[1]
    contextsRaw = line.split("{")[2].split("}")[0].split(",")
    TID = ""
    for item in contextsRaw:
        if "tid =" in item:
            TID = item.split("tid = ")[1].strip(" ")
    timestamp=str(int((datetime.datetime.strptime(timeString[:-3], "%Y-%m-%d %H:%M:%S.%f") - datetime.datetime(1970, 1, 1, 0, 0, 0)).total_seconds()*1000))+"."+timeString[-6:]
    #timeStringSplit = timeString.split(" ")[1].split(":")
    #hour = float(timeStringSplit[0]) * 3600
    #minutes = float(timeStringSplit[1] ) * 60
    #tsValue = hour+minutes+float(timeStringSplit[2])
    systemCallTemp = line.split("{")[0].split(" ")
    systemCall = systemCallTemp[len(systemCallTemp)-2].strip(":")
    #return SystemCall(tsValue,systemCall,TID)
    return SystemCall(timestamp,systemCall,TID)

def getSyscallList(fileName,procNames):
    inputFile = open(fileName)
    pMap = {}
    if "," in procNames:
        pTemp = procNames.split(",")
        for pName in pTemp:
            pMap[pName] = 1
    else:
        pMap[procNames] = 1
    previousSyscall = ""
    syscallList = []
    offset = -1
    numProcessed = 0
    scListMap = {}
    heartBeat = 100000
    #heartBeat = 1000000
    numContextSwitches = 0
    pTID=  -1
    for line in inputFile:
        sc = getSystemCall(line)
        ##print sc
        use = 0
        for k,v in pMap.iteritems():
            if k in line:
                use = 1
        #if not sc.procName in pMap:
        if use == 0:
            pTID = sc.tid
            del sc
            continue
        offset = offset + 1
        if not sc.tid in scListMap:
            scListMap[sc.tid] = []
        if sc.tid != pTID:
            cs = getSystemCall(-1)
            numContextSwitches = numContextSwitches+1
            cs.tid = sc.tid
            scListMap[sc.tid].append(cs) 
        scListMap[sc.tid].append(sc)
        #print sc.timeStamp, sc.name, sc.tid
        numProcessed = numProcessed + 1
        if numProcessed % heartBeat == 0:
            print "Processed "+str(heartBeat)+" entries."
        pTID = sc.tid
    #print scListMap
    print "Done creating list"
    for threadID, syscalls in scListMap.iteritems():
        for sc in syscalls:
            if sc.name == "CONTEXT_SWITCH":
                syscallList.append(sc)
                continue
            if ("exit_syscall" in sc.name or "syscall_exit" in sc.name) and not previousSyscall == "":
                if not sc.tid == previousSyscall.tid:
                    #print("Warning: Change without syscall completion at log position "+str(offset))
                    previousSyscall = ""
                    continue
                executionTime = float(sc.timeStamp) - float(previousSyscall.timeStamp)
                previousSyscall.executionTime = executionTime
                previousSyscall.exitValue = sc.timeStamp
                syscallList.append(previousSyscall)
            else:
                previousSyscall = sc
    #print syscallList
    return syscallList

#Entry point, parses the arguments and calls the functions to segment the input system call log.
def main():
    global calc_start
    homepath, procNames, syscallLog = get_args()
    print procNames
    syscallLog = homepath+"/data/"+syscallLog
    print "Segmenting log "+syscallLog
    outFileName = syscallLog+"_segmented_withContext.log"
    start_t = time.clock()
    calc_start = start_t
    systemCallList = getSyscallList(syscallLog,procNames)
    outputLog(systemCallList,outFileName,procNames)
    end_t = time.clock()
    elapsed = end_t - start_t
    print "Total time: "+str(elapsed)


if __name__ == "__main__":
    main()

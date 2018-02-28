#!/usr/bin/python
import csv
import json
from optparse import OptionParser
import os
import subprocess
import time

'''
this script gathers JVM metrics from jolokia and add to daily csv file
'''


def getIndexForColName(col_name):
    col_name = col_name.lower()
    if "nonheapmemoryusage" in col_name:
        return 9001
    elif "heapmemoryusage" in col_name:
        return 9002
    elif "processcpu" in col_name:
        return 9003
    elif "systemcpu" in col_name:
        return 9004
    elif "maxfile" in col_name:
        return 9005
    elif "openfile" in col_name:
        return 9006
    elif "thread" in col_name:
        return 9007
    elif "psscavengegarbage" in col_name:
        return 9008
    elif "psmarksweepgarbage" in col_name:
        return 9009
    elif "peakusage" in col_name:
        if "pspermgen" in col_name:
            return 9010
        elif "psoldgen" in col_name:
            return 9011
        elif "pssurvivor" in col_name:
            return 9012
        elif "pseden" in col_name:
            return 9013
    elif "collectionusage" in col_name:
        if "pspermgen" in col_name:
            return 9014
        elif "psoldgen" in col_name:
            return 9015
        elif "pssurvivor" in col_name:
            return 9016
        elif "pseden" in col_name:
            return 9017
    elif "usage" in col_name:
        if "pspermgen" in col_name:
            return 9018
        elif "psoldgen" in col_name:
            return 9019
        elif "pssurvivor" in col_name:
            return 9020
        elif "pseden" in col_name:
            return 9021
    else:
        return 9999


# returns the homePath of the script(default or from parameters)
def getParameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    (options, args) = parser.parse_args()

    if options.homepath is None:
        homePath = os.getcwd()
    else:
        homePath = options.homepath

    return homePath


def getInstanceDetails(filename):
    instances = []
    with open(filename, 'rb') as csvFile:
        instancereader = csv.reader(csvFile, delimiter=',')
        for row in instancereader:
            instance = []
            instance.append(row[0])
            instance.append(row[1])
            instances.append(instance)
    return instances


def updateHeaderList(headerList, instances):
    headerList.append('timestamp')
    for instance in instances:
        for metric in metrics['Memory']:
            for path in metrics['Memory'][metric]:
                headerList.append(metric + "-" + path + "[" + instance[0] + "]:" + str(getIndexForColName(metric)))

        for cpuMetric in metrics['OperatingSystem']:
            headerList.append(cpuMetric + "[" + instance[0] + "]:" + str(getIndexForColName(cpuMetric)))

        for threadMetric in metrics['Threading']:
            headerList.append(threadMetric + "[" + instance[0] + "]:" + str(getIndexForColName(threadMetric)))

        for gcMetric in metrics['PSScavengeGarbageCollector']:
            metricName = 'PSScavengeGarbageCollector_' + gcMetric
            headerList.append(
                metricName + "[" + instance[0] + "]:" + str(getIndexForColName(metricName)))

        for gcMetric in metrics['PSMarkSweepGarbageCollector']:
            metricName = 'PSMarkSweepGarbageCollector_' + gcMetric
            headerList.append(metricName + "[" + instance[0] + "]:" + str(
                getIndexForColName(metricName)))

        for memoryPoolMetric in metrics['PSPermGenMemoryPool']:
            for path in metrics['PSPermGenMemoryPool'][memoryPoolMetric]:
                metricName = 'PSPermGenMemoryPool_' + memoryPoolMetric + "-" + path
                headerList.append(
                    metricName + "[" + instance[0] + "]:" + str(
                        getIndexForColName(metricName)))

        for memoryPoolMetric in metrics['PSOldGenMemoryPool']:
            for path in metrics['PSOldGenMemoryPool'][memoryPoolMetric]:
                metricName = 'PSOldGenMemoryPool_' + memoryPoolMetric + "-" + path
                headerList.append(
                    metricName + "[" + instance[0] + "]:" + str(
                        getIndexForColName(metricName)))

        for memoryPoolMetric in metrics['PSSurvivorSpaceMemoryPool']:
            for path in metrics['PSSurvivorSpaceMemoryPool'][memoryPoolMetric]:
                metricName = 'PSSurvivorSpaceMemoryPool_' + memoryPoolMetric + "-" + path
                headerList.append(
                    metricName + "[" + instance[0] + "]:" + str(
                        getIndexForColName(metricName)))

        for memoryPoolMetric in metrics['PSEdenSpaceMemoryPool']:
            for path in metrics['PSEdenSpaceMemoryPool'][memoryPoolMetric]:
                metricName = 'PSEdenSpaceMemoryPool_' + memoryPoolMetric + "-" + path
                headerList.append(
                    metricName + "[" + instance[0] + "]:" + str(
                        getIndexForColName(metricName)))


def getJSONForInstanceMbean(mbeanString, instance):
    requestJsonMemOSThread = {}
    requestJsonMemOSThread["type"] = "read"
    requestJsonMemOSThread["mbean"] = mbeanString
    requestJsonMemOSThread["config"] = {'ignoreErrors': 'true'}
    proc = subprocess.Popen(['curl -H "Content-Type: application/json" -X POST -d \'' + json.dumps(
        requestJsonMemOSThread) + '\' ' + instance], stdout=subprocess.PIPE, shell=True)
    (out, err) = proc.communicate()
    output = json.loads(out)
    return output


def updateDataList(currentDataList, instances):
    JsonMemOSThread = getJSONForInstanceMbean("java.lang:type=*", instances[0][1])
    currentDataList.append(str(JsonMemOSThread['timestamp'] * 1000))

    requestGarbageCollector = {}
    requestGarbageCollector["type"] = "read"
    requestGarbageCollector["mbean"] = "java.lang:name=PS*,type=GarbageCollector"

    for instance in instances:
        JsonMemOSThread = getJSONForInstanceMbean("java.lang:type=*", instance[1])
        gcMetricJSON = getJSONForInstanceMbean("java.lang:name=PS*,type=GarbageCollector", instance[1])
        permGenMemJSON = getJSONForInstanceMbean("java.lang:name=PS Perm Gen,type=MemoryPool", instance[1])
        oldGenMemJSON = getJSONForInstanceMbean("java.lang:name=PS Old Gen,type=MemoryPool", instance[1])
        survivorSpaceJSON = getJSONForInstanceMbean("java.lang:name=PS Survivor Space,type=MemoryPool", instance[1])
        edenSpaceJSON = getJSONForInstanceMbean("java.lang:name=PS Eden Space,type=MemoryPool", instance[1])

        for memoryPoolMetric in metrics['Memory']:
            for path in metrics['Memory'][memoryPoolMetric]:
                currentDataList.append(str(JsonMemOSThread['value']['java.lang:type=Memory'][memoryPoolMetric][path]))

        for cpuMetric in metrics['OperatingSystem']:
            if "Count" in cpuMetric:
                currentDataList.append(str(JsonMemOSThread['value']['java.lang:type=OperatingSystem'][cpuMetric]))
            else:
                currentDataList.append(str(JsonMemOSThread['value']['java.lang:type=OperatingSystem'][cpuMetric] * 100))

        for threadMetric in metrics['Threading']:
            currentDataList.append(str(JsonMemOSThread['value']['java.lang:type=Threading'][threadMetric]))

        for gcMetric in metrics['PSScavengeGarbageCollector']:
            if 'java.lang:name=PS Scavenge,type=GarbageCollector' not in gcMetricJSON['value']:
                currentDataList.append(str(0))
            else:
                currentDataList.append(
                str(gcMetricJSON['value']['java.lang:name=PS Scavenge,type=GarbageCollector'][gcMetric]))

        for gcMetric in metrics['PSMarkSweepGarbageCollector']:
            if 'java.lang:name=PS MarkSweep,type=GarbageCollector' not in gcMetricJSON['value']:
                currentDataList.append(str(0))
            else:
                currentDataList.append(
                str(gcMetricJSON['value']['java.lang:name=PS MarkSweep,type=GarbageCollector'][gcMetric]))

        for memoryPoolMetric in metrics['PSPermGenMemoryPool']:
            for path in metrics['PSPermGenMemoryPool'][memoryPoolMetric]:
                if memoryPoolMetric not in permGenMemJSON['value']:
                    currentDataList.append(str(0))
                else:
                    currentDataList.append(str(permGenMemJSON['value'][memoryPoolMetric][path]))

        for memoryPoolMetric in metrics['PSOldGenMemoryPool']:
            for path in metrics['PSOldGenMemoryPool'][memoryPoolMetric]:
                if memoryPoolMetric not in oldGenMemJSON['value']:
                    currentDataList.append(str(0))
                else:
                    currentDataList.append(str(oldGenMemJSON['value'][memoryPoolMetric][path]))

        for memoryPoolMetric in metrics['PSSurvivorSpaceMemoryPool']:
            for path in metrics['PSSurvivorSpaceMemoryPool'][memoryPoolMetric]:
                if memoryPoolMetric not in survivorSpaceJSON['value']:
                    currentDataList.append(str(0))
                else:
                    currentDataList.append(str(survivorSpaceJSON['value'][memoryPoolMetric][path]))

        for memoryPoolMetric in metrics['PSEdenSpaceMemoryPool']:
            for path in metrics['PSEdenSpaceMemoryPool'][memoryPoolMetric]:
                if memoryPoolMetric not in edenSpaceJSON['value']:
                    currentDataList.append(str(0))
                else:
                    currentDataList.append(str(edenSpaceJSON['value'][memoryPoolMetric][path]))


def checkNewInstances(instances):
    newInstances = []
    currentDate = time.strftime("%Y%m%d")
    instancesMetaDataFilePath = os.path.join(homePath, dataDirectory + "totalVMs.json")
    for instance in instances:
        newInstances.append(instance[1])
    if os.path.isfile(instancesMetaDataFilePath) == False:
        towritePreviousInstances = {}
        towritePreviousInstances["allInstances"] = newInstances
        with open(instancesMetaDataFilePath, 'w') as instancesMetaDataFile:
            json.dump(towritePreviousInstances, instancesMetaDataFile)
    else:
        with open(instancesMetaDataFilePath, 'r') as instancesMetaDataFile:
            oldInstances = json.load(instancesMetaDataFile)["allInstances"]
        if cmp(newInstances, oldInstances) != 0:
            towritePreviousInstances = {}
            towritePreviousInstances["allInstances"] = newInstances
            with open(instancesMetaDataFilePath, 'w') as instancesMetaDataFile:
                json.dump(towritePreviousInstances, instancesMetaDataFile)
            if os.path.isfile(os.path.join(homePath, dataDirectory + currentDate + ".csv")) == True:
                oldFile = os.path.join(homePath, dataDirectory + currentDate + ".csv")
                newFile = os.path.join(homePath,
                                       dataDirectory + currentDate + "." + time.strftime("%Y%m%d%H%M%S") + ".csv")
                os.rename(oldFile, newFile)


def writeDataToFile(headerList, currentDataList):
    # write data to csv file
    with open(os.path.join(homePath, dataDirectory, time.strftime("%Y%m%d") + ".csv"), 'a+') as csvDataFile:
        dataFileLines = len(csvDataFile.readlines())
        if (dataFileLines < 1):
            csvDataFile.write(listToCSVRow(headerList))
            csvDataFile.write("\n")
        csvDataFile.write(listToCSVRow(currentDataList))
        csvDataFile.write("\n")
        csvDataFile.close()


def listToCSVRow(lists):
    dataRow = ''
    for i in range(0, len(lists)):
        if len(str(lists[i])) == 0:
            dataRow += '0'
        else:
            dataRow = dataRow + str(lists[i])
        if (i + 1 != len(lists)):
            dataRow = dataRow + ','
    return dataRow


if __name__ == '__main__':

    metrics = {'Memory': {'NonHeapMemoryUsage': ['max', 'committed', 'init', 'used'],
                          'HeapMemoryUsage': ['max', 'committed', 'init', 'used']},
               'OperatingSystem': ['ProcessCpuLoad', 'SystemCpuLoad', 'MaxFileDescriptorCount',
                                   'OpenFileDescriptorCount'],
               'Threading': ['ThreadCount', 'TotalStartedThreadCount'],
               'PSScavengeGarbageCollector': ['CollectionCount', 'CollectionTime'],
               'PSMarkSweepGarbageCollector': ['CollectionCount', 'CollectionTime'],
               'PSPermGenMemoryPool': {'Usage': ['max', 'committed', 'init', 'used'],
                                       'CollectionUsage': ['max', 'committed', 'init', 'used'],
                                       'PeakUsage': ['max', 'committed', 'init', 'used']},
               'PSOldGenMemoryPool': {'Usage': ['max', 'committed', 'init', 'used'],
                                      'CollectionUsage': ['max', 'committed', 'init', 'used'],
                                      'PeakUsage': ['max', 'committed', 'init', 'used']},
               'PSSurvivorSpaceMemoryPool': {'Usage': ['max', 'committed', 'init', 'used'],
                                             'CollectionUsage': ['max', 'committed', 'init', 'used'],
                                             'PeakUsage': ['max', 'committed', 'init', 'used']},
               'PSEdenSpaceMemoryPool': {'Usage': ['max', 'committed', 'init', 'used']},
               'CollectionUsage': ['max', 'committed', 'init', 'used'],
               'PeakUsage': ['max', 'committed', 'init', 'used']}
    homePath = getParameters()
    dataDirectory = 'data/'
    currentDate = time.strftime("%Y%m%d")
    dataFileName = os.path.join(homePath, dataDirectory + currentDate + ".csv")
    currentDataList = []
    headerList = []

    instances = getInstanceDetails(os.path.join(homePath, "jolokia", "instancelist.csv"))
    updateHeaderList(headerList, instances)
    updateDataList(currentDataList, instances)

    # check if new VMs are present since last run
    checkNewInstances(instances)

    writeDataToFile(headerList, currentDataList)
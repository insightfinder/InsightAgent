#!/usr/bin/python

from __future__ import print_function
import json
import sys
import libvirt
import libxml2
import time
import os
from xml.etree import ElementTree
from optparse import OptionParser
import socket

'''
this script gathers system info from kvm using libvirt about the host and guest(s) machines and add to daily csv file
'''


def getIndexForColName(col_name):
    if "cpu" in str(col_name).lower():
        return 2001
    elif "disk" in str(col_name).lower() and ("read" in str(col_name).lower() or "write" in str(col_name).lower()):
        return 2002
    elif "disk" in str(col_name).lower() and "used" in str(col_name).lower():
        return 2003
    elif "network" in str(col_name).lower() and (
                    "in" in str(col_name).lower() or "out" in str(col_name).lower()):
        return 2004
    elif "mem" in str(col_name).lower():
        return 2005
    elif "load" in str(col_name).lower():
        return 2007
    elif "octets" in str(col_name).lower() and (
                    "in" in str(col_name).lower() or "out" in str(col_name).lower()):
        return 2008
    elif "discards" in str(col_name).lower() and (
                    "in" in str(col_name).lower() or "out" in str(col_name).lower()):
        return 2009
    elif "errors" in str(col_name).lower() and (
                    "in" in str(col_name).lower() or "out" in str(col_name).lower()):
        return 2010
    elif "swap" in str(col_name).lower() and (
                    "used" in str(col_name).lower() or "total" in str(col_name).lower()):
        return 2011


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


def updateDataForHost(currentDataList):
    # Open connection with the Hypervisor
    libvertConn = libvirt.open('qemu:///system')
    if libvertConn == None:
        print('Failed to open connection to '
              '', file=sys.stderr)
        exit(1)
    currentTimeStamp = str(int(time.time() * 1000))
    CPUDataMap = libvertConn.getCPUMap()
    mem = libvertConn.getFreeMemory()
    stats = libvertConn.getCPUStats(-1)
    currentDataList.append(currentTimeStamp)
    currentDataList.append(str(round(mem / 1048576., 2)))
    currentDataList.append(str(CPUDataMap[0]))
    currentDataList.append(str(stats['kernel'] / 10 ** 9))
    currentDataList.append(str(stats['idle'] / 10 ** 9))
    currentDataList.append(str(stats['user'] / 10 ** 9))
    currentDataList.append(str(stats['iowait'] / 10 ** 9))
    libvertConn.close()


def updateHeaderForHost(headerList):
    hostname = socket.gethostname().partition(".")[0]
    hostMetrics = ["FreeMemory", "CPUCount", "CPUUsage_Kernel", "CPUUsage_Idle", "CPUUsage_User", "CPUUsage_IOWait"]
    headerList.append("timestamp")
    for hostMetric in hostMetrics:
        headerList.append(hostMetric + "[" + hostname + "]:" + str(getIndexForColName(hostMetric)))


def updateHeaderForVMDomain(vmDomain, headerList):
    vmMetrics = ["Disk_Read_Requests", "Disk_Read_Size", "Disk_Write_Requests", "Disk_Write_Size", "Cpu_Time",
                 "System_Time", "User_Time", "MemUsed_Actual", "MemUsed_Majorfault", "MemUsed_Swapin", "MemUsed_Rss",
                 "Network_Read_Size", "Network_Read_Packets", "Network_Write_Size", "Network_Write_Packets"]
    for vmMetric in vmMetrics:
        headerList.append(vmMetric + "[" + str(vmDomain.name()) + "]:" + str(getIndexForColName(vmMetrics)))


def updateHeaderForVMDomains(vmDomains, headerList):
    for vmDomain in vmDomains:
        updateHeaderForVMDomain(vmDomain, headerList)


def getVMDomains():
    # Open connection with the Hypervisor
    libvertConn = libvirt.open('qemu:///system')
    if libvertConn == None:
        print('Failed to open connection to '
              '', file=sys.stderr)
        exit(1)
    # Get the information about the various guest VMs
    vmIdentities = libvertConn.listDomainsID()
    vmDomains = []
    if len(vmIdentities) == 1:
        vmDomains.append(libvertConn.lookupByID(vmIdentities[0]))
        if len(vmDomains) == 0:
            print('Failed to find the domain ', file=sys.stderr)
            exit(1)
    else:
        # Handle for multiple domains
        for id in vmIdentities:
            vmDomains.append(libvertConn.lookupByID(id))
    return vmDomains


def updateDataForVMDomains(vmDomains, currentDataList):
    for vmDomain in vmDomains:
        # get disk metrics
        for device in getDevicesForVMDomain(vmDomain):
            read_req, read_bytes, write_req, write_bytes, err = \
                vmDomain.blockStats(device)
            currentDataList.append(str(read_req))
            currentDataList.append(str(round(read_bytes / 1048576., 2)))
            currentDataList.append(str(write_req))
            currentDataList.append(str(round(write_bytes / 1048576., 2)))

        # get CPU metrics
        CPUstats = vmDomain.getCPUStats(True)
        currentDataList.append(str(CPUstats[0]['cpu_time'] / 10 ** 9))
        currentDataList.append(str(CPUstats[0]['system_time'] / 10 ** 9))
        currentDataList.append(str(CPUstats[0]['user_time'] / 10 ** 9))

        # get memory metrics
        memStats = vmDomain.memoryStats()
        if memStats.has_key('actual'):
            currentDataList.append(str(round(memStats['actual'] / 1048576., 2)))
        else:
            currentDataList.append("0")
        if memStats.has_key('major_fault'):
            currentDataList.append(str(round(memStats['major_fault'] / 1048576., 2)))
        else:
            currentDataList.append("0")
        if memStats.has_key('swap_in'):
            currentDataList.append(str(round(memStats['swap_in'] / 1048576., 2)))
        else:
            currentDataList.append("0")
        if memStats.has_key('rss'):
            currentDataList.append(str(round(memStats['rss'] / 1048576., 2)))
        else:
            currentDataList.append("0")

        # get interface metrics
        tree = ElementTree.fromstring(vmDomain.XMLDesc())
        iface = tree.find('devices/interface/target').get('dev')
        stats = vmDomain.interfaceStats(iface)
        currentDataList.append(str(round(stats[0] / 1048576., 2)))
        currentDataList.append(str(stats[1]))
        currentDataList.append(str(round(stats[4] / 1048576., 2)))
        currentDataList.append(str(stats[5]))


def getDevicesForVMDomain(dom):
    devices = []
    doc = libxml2.parseDoc(dom.XMLDesc(0))
    ctxt = doc.xpathNewContext()

    # Iterate through all disk target elements of the domain.
    for dev in ctxt.xpathEval("/domain/devices/disk/target"):
        if not str(dev.get_properties()).split('"')[1] in devices:
            devices.append(str(dev.get_properties()).split('"')[1])
        return devices


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


def checkNewVMs(vmDomains):
    newVMNames = []
    vmMetaDataFilePath = os.path.join(homePath, dataDirectory + "totalVMs.json")
    for vmDomain in vmDomains:
        newVMNames.append(vmDomain.name())
    if os.path.isfile(vmMetaDataFilePath) == False:
        towritePreviousVM = {}
        towritePreviousVM["allVM"] = newVMNames
        with open(vmMetaDataFilePath, 'w') as vmMetaDataFile:
            json.dump(towritePreviousVM, vmMetaDataFile)
    else:
        with open(vmMetaDataFilePath, 'r') as vmMetaDataFile:
            oldVMDomains = json.load(vmMetaDataFile)["allVM"]
        if cmp(newVMNames, oldVMDomains) != 0:
            towritePreviousVM = {}
            towritePreviousVM["allVM"] = newVMNames
            with open(vmMetaDataFilePath, 'w') as vmMetaDataFile:
                json.dump(towritePreviousVM, vmMetaDataFile)
            if os.path.isfile(os.path.join(homePath, dataDirectory + date + ".csv")) == True:
                oldFile = os.path.join(homePath, dataDirectory + date + ".csv")
                newFile = os.path.join(homePath, dataDirectory + date + "." + time.strftime("%Y%m%d%H%M%S") + ".csv")
                os.rename(oldFile, newFile)


def writeDataToFile(headerList, currentDataList):
    # write data to csv file
    with open(os.path.join(homePath, dataDirectory, date + ".csv"), 'a+') as csvDataFile:
        dataFileLines = len(csvDataFile.readlines())
        if (dataFileLines < 1):
            csvDataFile.write(listToCSVRow(headerList))
            csvDataFile.write("\n")
        csvDataFile.write(listToCSVRow(currentDataList))
        csvDataFile.write("\n")
        csvDataFile.close()


if __name__ == '__main__':
    homePath = getParameters()
    dataDirectory = 'data/'
    currentDataList = []
    headerList = []

    # get metrics for host machine
    updateHeaderForHost(headerList)
    updateDataForHost(currentDataList)

    # get metrics for VMs
    vmDomains = getVMDomains()
    updateHeaderForVMDomains(vmDomains, headerList)
    updateDataForVMDomains(vmDomains, currentDataList)
    date = time.strftime("%Y%m%d")

    # check if new VMs are present since last run
    checkNewVMs(vmDomains)

    writeDataToFile(headerList, currentDataList)

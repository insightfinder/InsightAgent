#!/usr/bin/python

from __future__ import print_function
import sys
import libvirt
import libxml2
import time
import os
from xml.dom import minidom
from xml.etree import ElementTree
import csv
from optparse import OptionParser
import socket


'''
this script gathers system info from kvm using libvirt about the host and guest(s) machines and add to daily csv file
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
hostname = socket.gethostname().partition(".")[0]

currentTimeStamp = str(int(time.time()*1000))
header = ""
currRow = currentTimeStamp+","
firstFetch = False

date = time.strftime("%Y%m%d")


def createInitialHeader():
    global header
    header += "timestamp,FreeMemory[Host]<MB>,CPUCount[Host],CPUUsage_Kernel[Host]<s>,CPUUsage_Idle[Host]<s>,CPUUsage_User[Host]<s>,CPUUsage_IOWait[Host]<s>"

def appendGuestHeader(name):
    global header
    header += (",Disk_Read_Requests["+name+"]")
    header += (",Disk_Read_Size["+name+"]<MB>")
    header += (",Disk_Write_Requests["+name+"]")
    header += (",Disk_Write_Size["+name+"]<MB>")
    header += (",Cpu_Time["+name+"]<s>")
    header += (",System_Time["+name+"]<s>")
    header += (",User_Time["+name+"]<s>")
    header += (",MemUsed_Actual["+name+"]<MB>")
    header += (",MemUsed_Majorfault["+name+"]<MB>")
    header += (",MemUsed_Swapin["+name+"]<MB>")
    header += (",MemUsed_Rss["+name+"]<MB>")
    header += (",Network_Read_Size["+name+"]<MB>")
    header += (",Network_Read_Packets["+name+"]")
    header += (",Network_Write_Size["+name+"]<MB>")
    header += (",Network_Write_Packets["+name+"]")

def get_host_info(conn):
    global currRow
    map = conn.getCPUMap()
    mem = conn.getFreeMemory()
    stats = conn.getCPUStats(-1)
    currRow += (str(round(mem/1048576.,2))+",")
    currRow += (str(map[0])+",")
    currRow += (str(stats['kernel']/10**9)+",")
    currRow += (str(stats['idle']/10**9)+",")
    currRow += (str(stats['user']/10**9)+",")
    currRow += (str(stats['iowait']/10**9)+",")

    # print("Host Name is " + conn.getHostname())
    # print("Free memory on the node (host) is " + str(mem/1048576.) + " MBs.")
    # print("Free memory on the node (host) is " + str(round(mem/1048576.,2)) + " MBs.")
    # print("CPUs: " + str(map[0]))
    # print("Available: " + str(map[1]))
    # print("CPU Usage Stats:")
    # for key, val in stats.iteritems():
    #     print(str(key)+" "+str(val/10**9))
    # print("============================================================\n")

def get_domain_info(doms):
    global currRow
    for d in doms:
        #print(d.name())
        appendGuestHeader(d.name())
        #print("\nDisk Read Metrics:")
        for dev in get_target_devices(d):
            read_req, read_bytes, write_req, write_bytes, err = \
            d.blockStats(dev)
            # print('Read requests issued:  '+str(read_req))
            # print('Bytes read:            '+str(read_bytes))
            # print('Write requests issued: '+str(write_req))
            # print('Bytes written:         '+str(write_bytes))
            # print('Number of errors:      '+str(err))
            currRow += (str(read_req)+",")
            currRow += (str(round(read_bytes/1048576.,2))+",")
            currRow += (str(write_req)+",")
            currRow += (str(round(write_bytes/1048576.,2))+",")

        #print("\nCPU metrics:")
        CPUstats = d.getCPUStats(True)
        # for key, val in CPUstats[0].iteritems():
        #     print(key+" "+str(val))
        currRow += (str(CPUstats[0]['cpu_time']/10**9)+",")
        currRow += (str(CPUstats[0]['system_time']/10**9)+",")
        currRow += (str(CPUstats[0]['user_time']/10**9)+",")

        #print("\nMemory metrics")
        memStats  = d.memoryStats()
        #print('memory used:')
        # for name in memStats:
        #     print(str(memStats[name])+' ('+name+')')
        if memStats.has_key('actual'):
            currRow += (str(round(memStats['actual']/1048576.,2))+",")
        else:
            currRow += ("0,")
        if memStats.has_key('major_fault'):
            currRow += (str(round(memStats['major_fault']/1048576.,2))+",")
        else:
            currRow += ("0,")
        if memStats.has_key('swap_in'):
            currRow += (str(round(memStats['swap_in']/1048576.,2))+",")
        else:
            currRow += ("0,")
        if memStats.has_key('rss'):
            currRow += (str(round(memStats['rss']/1048576.,2))+",")
        else:
            currRow += ("0,")


        #print('\nNetwork stats:')
        tree = ElementTree.fromstring(d.XMLDesc())
        iface = tree.find('devices/interface/target').get('dev')
        stats = d.interfaceStats(iface)
        # print('read bytes:    '+str(stats[0]))
        # print('read packets:  '+str(stats[1]))
        # print('read errors:   '+str(stats[2]))
        # print('read drops:    '+str(stats[3]))
        # print('write bytes:   '+str(stats[4]))
        # print('write packets: '+str(stats[5]))
        # print('write errors:  '+str(stats[6]))
        # print('write drops:   '+str(stats[7]))
        currRow += (str(round(stats[0]/1048576.,2))+",")
        currRow += (str(stats[1])+",")
        currRow += (str(round(stats[4]/1048576.,2))+",")
        currRow += (str(stats[5])+",")
        #print("============================================================\n")

def writeToCsv(headerMissing):
    global header
    global currRow
    with open(os.path.join(homepath,datadir+date+".csv"),'a') as csvFile:
        if headerMissing==True:
            csvFile.write(header)
            csvFile.write("\n")
        currRow = currRow[:-1]
        csvFile.write(currRow)
        csvFile.write("\n")
        csvFile.close()


def get_target_devices(dom):
    devices=[]
    doc=libxml2.parseDoc(dom.XMLDesc(0))
    ctxt = doc.xpathNewContext()

	#Iterate through all disk target elements of the domain.
    for dev in ctxt.xpathEval("/domain/devices/disk/target"):
        if not str(dev.get_properties()).split('"')[1] in devices:
			devices.append(str(dev.get_properties()).split('"')[1])
	return devices

#Open connection with the Hypervisor
conn = libvirt.open('qemu:///system')
if conn == None:
    print('Failed to open connection to qemu:///system', file=sys.stderr)
    exit(1)

createInitialHeader();

#Get the information about host
get_host_info(conn)

#Get the information about the various guest VMs
ids = conn.listDomainsID()
doms = []
if len(ids) == 1:
    doms.append(conn.lookupByID(ids[0]))
    if len(doms) == 0:
        print('Failed to find the domain ', file=sys.stderr)
        exit(1)
else:
    #Handle for multiple domains
    for id in ids:
        doms.append(conn.lookupByID(id))
get_domain_info(doms)


if (os.path.isfile(os.path.join(homepath,datadir+date+".csv"))):
    firstFetch=False
else:
    firstFetch=True

if firstFetch == True:
    writeToCsv(True)
else:
    writeToCsv(False)

conn.close()
exit(0)

#!/bin/python
import subprocess
import json
import os
import time
from optparse import OptionParser
import csv



COMMA_DELIMITER = ","
NEWLINE_DELIMITER = "\n"
metrics = {'Memory':{'NonHeapMemoryUsage':['max','committed', 'init', 'used'],'HeapMemoryUsage':['max','committed', 'init', 'used']},'OperatingSystem':['ProcessCpuLoad','SystemCpuLoad']}



def getInstanceDetails(filename):
	instances = []
	with open(filename, 'rb') as csvFile:
		instancereader = csv.reader(csvFile, delimiter=',')
		for row in instancereader:
			print row
			instance = []
			instance.append(row[0])
			instance.append(row[1])
			print row[0]
			print row[1]
			instances.append(instance)
	return instances


def getindex(col_name):
    if col_name == "NonHeapMemoryUsage":
        return 9001
    elif col_name == "HeapMemoryUsage":
        return 9002
    elif col_name == "ProcessCpuLoad":
        return 9003
    elif col_name == "SystemCpuLoad":
        return 9004



#instances = [['instance1','http://localhost:8080/jolokia'],['instance2','http://localhost:8080/jolokia']]



requestJson = {}
requestJson["type"]="read"
requestJson["mbean"]="java.lang:type=*"


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
date = time.strftime("%Y%m%d")
filename = os.path.join(homepath,datadir+date+".csv")
print 'filename: ', filename

#if(os.path.isfile(filename)):
#	resource_usage_file = open(os.path.join(filename),'a+')
#	csvContent = resource_usage_file.readlines()
#	numlines = len(csvContent)
#	resource_usage_file.close()
#	if(numlines > 0):
#		oldFile = os.path.join(homepath,datadir+date+".csv")
#		newFile = os.path.join(homepath,datadir+date+"."+time.strftime("%Y%m%d%H%M%S")+".csv")
#		os.rename(oldFile,newFile)

		
print 'RequestJson: '
print requestJson
header = 'timestamp'

instances = getInstanceDetails(os.path.join(homepath,"jolokia","instancelist.csv"))


if( not (os.path.isfile(filename)) or (os.stat(filename).st_size == 0)):

	for instance in instances:
		for metric in metrics['Memory']:
			for path in metrics['Memory'][metric]:
				header = header + COMMA_DELIMITER
				header = header+metric+"-"+path+"["+instance[0]+"]:"+str(getindex(metric))

		for cpuMetric in metrics['OperatingSystem']:
			header = header + COMMA_DELIMITER
			header = header + cpuMetric + "["+instance[0]+"]:"+str(getindex(cpuMetric))

	header += NEWLINE_DELIMITER

	print header



with open(filename, "a+") as csvFile:
	if( not (os.path.isfile(filename)) or (os.stat(filename).st_size == 0)):
		csvFile.write(header)
	line = ""
	proc = subprocess.Popen(['curl -H "Content-Type: application/json" -X POST -d \''+ json.dumps(requestJson)+'\' '+instances[0][1]], stdout=subprocess.PIPE, shell=True)
	(out,err) = proc.communicate()
	output = json.loads(out)
	line += str(output['timestamp']*1000)

	for instance in instances:
		proc = subprocess.Popen(['curl -H "Content-Type: application/json" -X POST -d \''+ json.dumps(requestJson) +'\' '+instance[1]], stdout=subprocess.PIPE, shell=True)		
		(out,err) = proc.communicate()
		output = json.loads(out)

		for metric in metrics['Memory']:
			for path in metrics['Memory'][metric]:
				line += COMMA_DELIMITER
				line += str(output['value']['java.lang:type=Memory'][metric][path])

		for cpuMetric in metrics['OperatingSystem']:
			line += COMMA_DELIMITER
			line += str(output['value']['java.lang:type=OperatingSystem'][cpuMetric]*100)

	line += NEWLINE_DELIMITER
	print line
	csvFile.write(line)


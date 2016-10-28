import subprocess
import json
import os
import time
from optparse import OptionParser
import ConfigParser

COMMA_DELIMITER = ","
NEWLINE_DELIMITER = "\n"

def getindex(col_name):
    if col_name == "cpu":
        return 11001
    elif col_name == "cpu_stolen":
        return 11002
    elif col_name == "disk_io":
        return 11003
    elif col_name == "memory":
        return 11004
    elif col_name == "memory_used":
        return 11005
    elif col_name == "memory_total":
        return 11006
    elif col_name == "fullest_disk":
        return 11007
    elif col_name == "fullest_disk_free":
        return 11008

usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",
    action="store", dest="homepath", help="Directory to run from")
(options, args) = parser.parse_args()

now = int(time.time())

if options.homepath is None:
	homepath = os.getcwd()
else:
	homepath = options.homepath

config = ConfigParser.ConfigParser()

instance_file = os.path.join(homepath,"newrelic/newrelic.cfg");
config.read(instance_file)

instances=[]
instances = [e.strip() for e in config.get('HOSTNAME', 'HOSTLIST').split(',')]

datadir = 'data/'
date = time.strftime("%Y%m%d")
filename = os.path.join(homepath,datadir+date+".csv")

API_KEY = config.get('KEYS', 'API_KEY')

proc = subprocess.Popen(['curl -X GET "https://api.newrelic.com/v2/servers.json"  -H "X-Api-Key:' + API_KEY + '" -i'] , stdout=subprocess.PIPE,stderr=subprocess.PIPE , shell=True)
(out,err) = proc.communicate()


outlist = out.split("\n")

status = outlist[6]

metric = {}

colvalues = ['cpu' , 'cpu_stolen' , 'disk_io' , 'memory' , 'memory_used' , 'memory_total' , 'fullest_disk' , 'fullest_disk_free']

if "OK" in status:
    output = json.loads(outlist[14])
    for i in range(0,len(output['servers'])):
        name = output['servers'][i]['name']
        sid = output['servers'][i]['id']
        tempdict = {}
        tempdict['id'] = sid
        if name in instances:
            for val in colvalues:
                tempdict[val] = output['servers'][i]['summary'][val]
            metric[name]= tempdict


    header = 'timestamp'
    line = str(now*1000)


    for key in metric:
        for val in colvalues:
                header += COMMA_DELIMITER + val + '[' + key + ']:'+ str(getindex(val))
                line += COMMA_DELIMITER + str(metric[key][val])
        header += NEWLINE_DELIMITER
        line += NEWLINE_DELIMITER

    csvFile = open(filename, "a+")
    if( not (os.path.isfile(filename)) or (os.stat(filename).st_size == 0)):
        csvFile.write(header)
    csvFile.write(line)
    csvFile.close()

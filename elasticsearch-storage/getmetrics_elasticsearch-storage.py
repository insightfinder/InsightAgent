# -*- coding: utf-8 -*-
from datetime import datetime
from elasticsearch import Elasticsearch
from optparse import OptionParser
import csv
import time
import os
import socket

'''
this script gathers system info from elasticsearch and add to daily csv file
'''

usage = """Usage: %prog [options].. \n
\n-d\t--directory\tDirectory to run from"""

# Command line options
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",
                  action="store", dest="homepath", help="Directory to run from")
(options, args) = parser.parse_args()


if options.homepath is None:
    homepath = os.getcwd()
else:
    homepath = options.homepath


last_timestamp = ''
hostname = socket.gethostname().partition(".")[0]
es_index = "if_metric_csv"
es_type = "csv"
header = ''

# path to write the daily csv file
datadir = 'data/'

# change python timestamp to unix timestamp in millis
def current_milli_time(): return int(round(time.time() * 1000))

# get groupid for a metric
def getindex(col_name):
    if col_name == "CPU":
        return 1001
    elif col_name == "DiskRead" or col_name == "DiskWrite":
        return 1002
    elif col_name == "DiskUsed":
        return 1003
    elif col_name == "NetworkIn" or col_name == "NetworkOut":
        return 1004
    elif col_name == "MemUsed":
        return 1005
    elif "DiskUsed" in col_name:
        return 1006
    elif "LoadAvg" in col_name:
        return 1007


try:
    # daily csv file data/<current_date>_es.csv
    date = time.strftime("%Y%m%d")
    resource_usage_file = open(os.path.join(homepath, datadir + date + "_es.csv"), "a+")


    # Elasticsearch consumer configuration for file data/es_config.txt
    if os.path.exists(os.path.join(homepath, datadir + "es_config.txt")):
        config_file = open(os.path.join(homepath, datadir + "es_config.txt"), "r")
        host = config_file.readline()
        host = host.strip('\n\r')  # remove newline character from read line
        if len(host) == 0:
            print "using default host"
            host = 'localhost'
        port = config_file.readline()
        port = port.strip('\n\r')
        if len(port) == 0:
            print "using default port"
            port = '9200'
        es_index = config_file.readline()
        es_index = es_index.strip('\n\r')
        if len(es_index) == 0:
            print "using default index"
            es_index = 'if_metric_csv'
        es_type = config_file.readline()
        es_type = es_type.strip('\n\r')
        if len(es_type) == 0:
            print "using default type"
            es_type = 'csv'
    else:
        host = 'localhost'
        port = '9200'

    # read the last read timestamp if file exists and is not blank
    if os.path.exists(os.path.join(homepath, datadir + "es_lastime.txt")):
        config_file = open(os.path.join(homepath, datadir + "es_lastime.txt"), "r+")
        read_timestamp = config_file.readline()
        read_timestamp = read_timestamp.strip('\n\r')  # remove newline character from read line
        print read_timestamp
        if len(read_timestamp) == 0:
            print "using default timestamp"
            last_timestamp = ''
        else:
            last_timestamp = read_timestamp

    # if first-run then use the unix epoch start as the beginning of range
    if len(last_timestamp) == 0:
        start_time = '0000000001000'
    else:
        start_time = str(int(last_timestamp) + 1)


    # connect to the elasticsearch server and get the data
    es = Elasticsearch([{'host': host, 'port': port}])
    res2 = es.search(index=es_index, doc_type=es_type, body={"query":
        {"range":
            {"timestamp":
                {"from": start_time, "to": str(current_milli_time())}
            }
        },
        "sort": [
            {"timestamp": "desc"}
        ],
        "size": 1440 # max number or records per min per day
    })
    latest_time = 0

    if len(res2['hits']['hits']) != 0: # if there are updated values after the last read record
        latest_time = res2['hits']['hits'][0]["_source"]['timestamp'] # update the last read record timestamp
        header_fields = res2['hits']['hits'][0]["_source"]['header']
        header_tokens = header_fields.split(",")

        #generate the header from the header fields in the message
        for token in header_tokens:
            header += token +"["+ host +"]:" + str(getindex(token)) +","
        header = "timestamp,"+header
        header = header[:-1]

    # only write the header if the file is blank
    if os.path.getsize(os.path.join(homepath, datadir + date + "_es.csv")) == 0:
        resource_usage_file.write(header + "\n")

    # write the last read record timestamp to file for keeping track every time the script is run
    if latest_time != 0:
        print "Latest timestamp read: " + str(latest_time)
        time_file = open(os.path.join(homepath, datadir + "es_lastime.txt"), "w")
        time_file.write(str(latest_time))

    # append timestamp to the retrieved value string
    for val in res2['hits']['hits']:
       if val['_source']['header'] == None:
           continue
       resource_usage_file.write(str(val['_source']['timestamp'])+","+val['_source']['values']+"\n");

except KeyboardInterrupt:
    print "Interrupt from keyboard"

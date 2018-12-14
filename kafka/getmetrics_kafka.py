#!/usr/bin/env python
import csv
import os
import socket
import time
from optparse import OptionParser

from kafka import KafkaConsumer

'''
this script gathers system info from kafka and add to daily csv file
'''

usage = """Usage: %prog [options].. \n -t\t--timeout\tTimeout in seconds. Default is 30
\n-d\t--directory\tDirectory to run from
\n-p\t--topic\tKafka topic to read data from"""

# Command line options
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",
                  action="store", dest="homepath", help="Directory to run from")
parser.add_option("-t", "--timeout",
                  action="store", dest="timeout", help="Timeout in seconds. Default is 30")
parser.add_option("-p", "--topic",
                  action="store", dest="topic", help="Kafka topic to read data from")
(options, args) = parser.parse_args()


if options.homepath is None:
    homepath = os.getcwd()
else:
    homepath = options.homepath

if options.timeout is None:
    timeout = 30
else:
    timeout = int(options.timeout)
# kafka topic to read data from
if options.topic is None:
    topic = 'insightfinder_csv'
else:
    topic = options.topic

# path to write the daily csv file
datadir = 'data/'

header = "timestamp,"
hostname = socket.gethostname().partition(".")[0]

try:
    date = time.strftime("%Y%m%d")
    resource_usage_file = open(os.path.join(
        homepath, datadir + date + "_kafka.csv"), "a+")

    # Kafka consumer to configuration
    if os.path.exists(os.path.join(homepath, datadir + "config.ini")):
        config_file = open(os.path.join(homepath, datadir + "config.ini"), "r")
        host = config_file.readline()
        host = host.strip('\n\r')  # remove newline character from read line
        if len(host) == 0:
            print "using default host"
            host = 'localhost'
        port = config_file.readline()
        port = port.strip('\n\r')
        if len(port) == 0:
            print "using default port"
            port = '9092'
        topic = config_file.readline()
        topic = topic.strip('\n\r')
        if len(topic) == 0:
            print "using default topic"
            topic = 'insightfinder_csv'
    else:
        host = 'localhost'
        port = '9092'

    # timeout controls the timeout of the consumer
    consumer = KafkaConsumer(bootstrap_servers=[host + ':' + port],
                             auto_offset_reset='earliest', consumer_timeout_ms=1000 * timeout)
    consumer.subscribe([topic])

    # get the hostname of the system whose data is getting reported
    if os.path.exists(os.path.join(homepath, datadir + "hostname.txt")):  # check if file exists
        host_file = open(os.path.join(homepath, datadir + "hostname.txt"), "r")
        hostname = host_file.readline()
        # remove newline character from read line
        hostname = hostname.strip('\n\r')
        if len(hostname) == 0:
            print "using default host"
            hostname = socket.gethostname().partition(
                ".")[0]  # use hostname of the current system
    else:
        print "using default host"
        hostname = socket.gethostname().partition(
            ".")[0]  # use hostname of the current system

    # get custom header data. Format: Property,Group ID
    with open(os.path.join(homepath, datadir + "header.txt"), 'rb') as csvfile:
        header_fields = csv.reader(csvfile, delimiter=',', quotechar='|')
        for row in header_fields:
            header += row[0] + "[" + hostname + "]" + ":" + row[1] + ","
        header = header[:-1]

    # only write the header if the file is blank
    if os.path.getsize(os.path.join(homepath, datadir + date + "_kafka.csv")) == 0:
        resource_usage_file.write(header + "\n")

    # write the read messages from kafka to file (data/<date>_kafka.csv)
    for message in consumer:
        print (message.value)
        if header in message:
            continue
        resource_usage_file.write(message.value)

    print ("Server timed out\n")

except KeyboardInterrupt:
    print "Interrupt from keyboard"

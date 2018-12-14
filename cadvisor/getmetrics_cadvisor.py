#!/usr/bin/python

import time
import requests
import sys
import os
import subprocess
import socket
from optparse import OptionParser
import json
from ConfigParser import SafeConfigParser
import logging


class LessThanFilter(logging.Filter):
    def __init__(self, exclusive_maximum, name=""):
        super(LessThanFilter, self).__init__(name)
        self.max_level = exclusive_maximum

    def filter(self, record):
        # non-zero return means we log this message
        return 1 if record.levelno < self.max_level else 0


def set_logger_config():
    # Get the root logger
    logger = logging.getLogger(__name__)
    # Have to set the root logger level, it defaults to logging.WARNING
    logger.setLevel(logging.DEBUG)
    # route INFO and DEBUG logging to stdout from stderr
    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
    logging_handler_out.addFilter(LessThanFilter(logging.WARNING))
    logger.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logger.addHandler(logging_handler_err)
    return logger


logger = set_logger_config()
usage = "Usage: %prog [options]"
parser = OptionParser(usage=usage)
parser.add_option("-d", "--directory",
                  action="store", dest="homepath", help="Directory to run from")
(options, args) = parser.parse_args()

if options.homepath is None:
    homepath = os.getcwd()
else:
    homepath = options.homepath
data_dir = 'data/'

hostname = socket.gethostname()
cadvisor_address = "http://" + hostname + ":8080/api/v1.3/docker/"

try:
    if os.path.exists(os.path.join(homepath, "cadvisor", "config.ini")):
        parser = SafeConfigParser()
        parser.read(os.path.join(homepath, "cadvisor", "config.ini"))
        sampling_interval = parser.get('cadvisor', 'sampling_interval')
        if len(sampling_interval) == 0:
            sampling_interval = '60s'
except IOError:
    logger.info("config.ini file is missing")

if sampling_interval[-1:] == 's':
    sampling_interval = int(sampling_interval[:-1])
else:
    sampling_interval = int(sampling_interval) * 60 / 2

counter_time_map = {}
counter = 0
##the default value it 60-1, when cAdvisor started, the code need to calculate the index because of the sliding window
index = 59


def getindex(col_name):
    if col_name == "CPU":
        return 3001
    elif col_name == "DiskRead" or col_name == "DiskWrite":
        return 3002
    elif col_name == "NetworkIn" or col_name == "NetworkOut":
        return 3003
    elif col_name == "MemUsed":
        return 3004


def update_container_count(cadvisor_json, date):
    docker_instances = []
    new_instances = []
    if os.path.isfile(os.path.join(homepath, data_dir + "totalInstances.json")) == False:
        towrite_previous_instances = {}
        for containers in cadvisor_json:
            if containers != "":
                docker_instances.append(containers)
        towrite_previous_instances["overallDockerInstances"] = docker_instances
        with open(os.path.join(homepath, data_dir + "totalInstances.json"), 'w') as f:
            json.dump(towrite_previous_instances, f)
    else:
        with open(os.path.join(homepath, data_dir + "totalInstances.json"), 'r') as f:
            docker_instances = json.load(f)["overallDockerInstances"]
        for containers in cadvisor_json:
            if containers != "":
                new_instances.append(containers)
        if cmp(new_instances, docker_instances) != 0:
            towrite_previous_instances = {}
            towrite_previous_instances["overallDockerInstances"] = new_instances
            with open(os.path.join(homepath, data_dir + "totalInstances.json"), 'w') as f:
                json.dump(towrite_previous_instances, f)
            if os.path.isfile(os.path.join(homepath, data_dir + date + ".csv")) == True:
                old_file = os.path.join(homepath, data_dir + date + ".csv")
                new_file = os.path.join(homepath, data_dir + date + "." + time.strftime("%Y%m%d%H%M%S") + ".csv")
                os.rename(old_file, new_file)


def getmetric():
    global counter_time_map
    global counter
    global index
    global cadvisor_address
    global docker_instances
    global sampling_interval

    try:
        start_time = int(round(time.time() * 1000))
        date = time.strftime("%Y%m%d")
        while True:
            try:
                r = requests.get(cadvisor_address)
            except:
                currTime = int(round(time.time() * 1000))
                if currTime > start_time + 10000:
                    logger.error("unable to get requests from ", cadvisor_address)
                    sys.exit()
                continue
            update_container_count(r.json(), date)
            try:
                for key, value in r.json().items():
                    index = len(r.json()[key]["stats"]) - 1
                    break;
            except KeyError, ve:
                logger.error("Unable to get stats information from cAdvisor")
                sys.exit()
            time_stamp = start_time
            if (time_stamp in counter_time_map.values()):
                continue
            counter_time_map[counter] = time_stamp
            counter = (counter + 1) % 60
            log = str(start_time)
            cpu_all = 0
            resource_usage_file = open(os.path.join(homepath, data_dir + date + ".csv"), 'a+')
            numlines = len(resource_usage_file.readlines())
            i = 0
            for key, value in r.json().items():
                index = len(r.json()[key]["stats"]) - 1
                if index - int(sampling_interval) < 0:
                    sampling_interval = 1
                try:
                    cpu_used = r.json()[key]["stats"][index]["cpu"]["usage"][
                        "total"]
                    prev_cpu = r.json()[key]["stats"][index - int(sampling_interval)]["cpu"][
                        "usage"]["total"]
                    cur_cpu = float(float(cpu_used - prev_cpu) / 1000000000)
                    cur_cpu = abs(cur_cpu)
                except KeyError, e:
                    logger.error("Failed to get cpu information")
                    cur_cpu = "NaN"

                # get mem
                try:
                    curr_mem = r.json()[key]["stats"][index]['memory']['usage']
                    mem = float(float(curr_mem) / (1024 * 1024))  # MB
                    mem = abs(mem)
                except KeyError, e:
                    logger.error("Failed to get memory information")
                    mem = "NaN"
                # get disk
                try:
                    curr_block_num = len(r.json()[key]["stats"][index]["diskio"]["io_service_bytes"])
                    curr_io_read = 0
                    curr_io_write = 0
                    prev_io_read = 0
                    prev_io_write = 0
                    for j in range(curr_block_num):
                        curr_io_read += r.json()[key]["stats"][index]["diskio"]["io_service_bytes"][j]["stats"]["Read"]
                        curr_io_write += r.json()[key]["stats"][index]["diskio"]["io_service_bytes"][j]["stats"][
                            "Write"]
                    prev_block_num = len(
                        r.json()[key]["stats"][index - int(sampling_interval)]["diskio"]["io_service_bytes"])
                    prev_io_read = 0
                    prev_io_write = 0
                    for j in range(prev_block_num):
                        prev_io_read += \
                            r.json()[key]["stats"][index - int(sampling_interval)]["diskio"]["io_service_bytes"][j][
                                "stats"][
                                "Read"]
                        prev_io_write += \
                            r.json()[key]["stats"][index - int(sampling_interval)]["diskio"]["io_service_bytes"][j][
                                "stats"][
                                "Write"]
                    io_read = float(float(curr_io_read - prev_io_read) / (1024 * 1024))  # MB
                    io_write = float(float(curr_io_write - prev_io_write) / (1024 * 1024))  # MB
                except KeyError, e:
                    logger.error("Failed to get disk information")
                    io_read = "NaN"
                    io_write = "NaN"
                # get network
                try:
                    prev_network_t = r.json()[key]["stats"][index - int(sampling_interval)]["network"]["tx_bytes"]
                    prev_network_r = r.json()[key]["stats"][index - int(sampling_interval)]["network"]["rx_bytes"]
                    curr_network_t = r.json()[key]["stats"][index]["network"]["tx_bytes"]
                    curr_network_r = r.json()[key]["stats"][index]["network"]["rx_bytes"]
                    network_t = float(float(curr_network_t - prev_network_t) / (1024 * 1024))  # MB
                    network_r = float(float(curr_network_r - prev_network_r) / (1024 * 1024))  # MB
                except KeyError, e:
                    logger.error("Failed to get network information")
                    network_t = "NaN"
                    network_r = "NaN"
                log = log + "," + str(cur_cpu) + "," + str(io_read) + "," + str(io_write) + "," + str(
                    network_r) + "," + str(network_t) + "," + str(mem)
                if (numlines < 1):
                    fields = ["timestamp", "CPU", "DiskRead", "DiskWrite", "NetworkIn", "NetworkOut", "MemUsed"]
                    if i == 0:
                        fieldnames = fields[0]
                    host = hostname.partition(".")[0]
                    for k in range(1, len(fields)):
                        if (fields[k] == "timestamp"):
                            continue
                        if (fieldnames != ""):
                            fieldnames = fieldnames + ","
                        groupid = getindex(fields[k])

                        docker_id = r.json()[key]["aliases"][0]
                        docker_id_split = []
                        for c in reversed(docker_id):
                            if c == '_':
                                docker_id_split = docker_id.rsplit('_', 1)
                                break
                            if c == '.':
                                docker_id_split = docker_id.rsplit('.', 1)
                                break
                        if len(docker_id_split) != 0:
                            docker_id = docker_id_split[0]
                        metric = fields[k] + "[" + docker_id + "_" + host + "]"
                        fieldnames = fieldnames + metric + ":" + str(groupid)
                i = i + 1
            if (numlines < 1):
                resource_usage_file.write("%s\n" % (fieldnames))
            logger.error("Log: " + str(log))
            write_log = log
            resource_usage_file.write("%s\n" % (write_log))
            resource_usage_file.flush()
            resource_usage_file.close()
            break;
    except KeyboardInterrupt:
        logger.error("Keyboard Interrupt")


def main():
    try:
        getmetric()
    except (KeyboardInterrupt, SystemExit):
        logger.error("Keyboard Interrupt")
        sys.exit()


if __name__ == "__main__":
    main()

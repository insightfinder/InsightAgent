#!/usr/bin/python

import time
import requests
import sys
import os
import subprocess
import socket
from optparse import OptionParser
import json


def get_index(column_name):
    if column_name == "CPU":
        return 3001
    elif column_name == "DiskRead" or column_name == "DiskWrite":
        return 3002
    elif column_name == "NetworkIn" or column_name == "NetworkOut":
        return 3003
    elif column_name == "MemUsed":
        return 3004


def update_container_count(cadvisor_json, date, datadir):
    docker_instances = []
    new_instances = []
    previous_instances = {}
    if not os.path.isfile(os.path.join(homepath, datadir + "totalInstances.json")):
        for container in cadvisor_json:
            if container != "":
                docker_instances.append(container)
        previous_instances["overallDockerInstances"] = docker_instances
        with open(os.path.join(homepath, datadir + "totalInstances.json"), 'w') as f:
            json.dump(previous_instances, f)
    else:
        with open(os.path.join(homepath, datadir + "totalInstances.json"), 'r') as f:
            docker_instances = json.load(f)["overallDockerInstances"]
        for container in cadvisor_json:
            if container != "":
                new_instances.append(container)
        if cmp(new_instances, docker_instances) != 0:
            previous_instances["overallDockerInstances"] = new_instances
            with open(os.path.join(homepath, datadir + "totalInstances.json"), 'w') as f:
                json.dump(previous_instances, f)
            if os.path.isfile(os.path.join(homepath, datadir + date + ".csv")):
                oldFile = os.path.join(homepath, datadir + date + ".csv")
                newFile = os.path.join(homepath, datadir + date + "." + time.strftime("%Y%m%d%H%M%S") + ".csv")
                os.rename(oldFile, newFile)


def get_metric():
    global counter_time_map
    global counter
    global index

    datadir = 'data/'
    hostname = socket.gethostname()
    cAdvisoraddress = "http://" + hostname + ":8000/api/v1.3/docker/"
    sampling_interval = get_project_settings()
    try:
        startTime = int(round(time.time() * 1000))
        date = time.strftime("%Y%m%d")
        while True:
            try:
                r = requests.get(cAdvisoraddress)
            except:
                currTime = int(round(time.time() * 1000))
                if currTime > startTime + 10000:
                    print "unable to get requests from ", cAdvisoraddress
                    sys.exit()
                continue

            update_container_count(r.json(), date, datadir)

            try:
                for key, value in r.json().items():
                    index = len(r.json()[key]["stats"]) - 1
                    break;
            except KeyError:
                print "Unable to get stats information from cAdvisor"
                sys.exit()

            time_stamp = startTime
            if (time_stamp in counter_time_map.values()):
                continue
            counter_time_map[counter] = time_stamp
            counter = (counter + 1) % 60
            log = str(startTime)
            resource_usage_file = open(os.path.join(homepath, datadir + date + ".csv"), 'a+')
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
                    print "Failed to get cpu information"
                    cur_cpu = "NaN"

                # get mem
                try:
                    curr_mem = r.json()[key]["stats"][index]['memory']['usage']
                    mem = float(float(curr_mem) / (1024 * 1024))  # MB
                    mem = abs(mem)
                except KeyError, e:
                    print "Failed to get memory information"
                    mem = "NaN"
                # get disk
                try:
                    curr_block_num = len(r.json()[key]["stats"][index]["diskio"]["io_service_bytes"])
                    curr_io_read = 0
                    curr_io_write = 0
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
                    print "Failed to get disk information"
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
                    print "Failed to get network information"
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
                        groupid = get_index(fields[k])

                        dockerID = r.json()[key]["aliases"][0]
                        docker_id_split = []
                        for c in reversed(dockerID):
                            if c == '_':
                                docker_id_split = dockerID.rsplit('_', 1)
                                break
                            if c == '.':
                                docker_id_split = dockerID.rsplit('.', 1)
                                break
                        if len(docker_id_split) == 2 and len(docker_id_split[0]) > len(docker_id_split[1]):
                            # if c == '_' and not docker_id_split[1].isdigit():
                            #     dockerID = r.json()[key]["aliases"][0]
                            # else:
                            dockerID = docker_id_split[0]
                        metric = fields[k] + "[" + dockerID + "_" + host + "]"
                        fieldnames = fieldnames + metric + ":" + str(groupid)
                i = i + 1
            if (numlines < 1):
                resource_usage_file.write("%s\n" % (fieldnames))
            print "Log: " + str(log)  # is it possible that print too many things?
            # writelog = log
            resource_usage_file.write("%s\n" % (log))
            resource_usage_file.flush()
            resource_usage_file.close()
            break;
    except KeyboardInterrupt:
        print "Keyboard Interrupt"


def parse_options():
    global homepath
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    (options, args) = parser.parse_args()
    if options.homepath is None:
        homepath = os.getcwd()
    else:
        homepath = options.homepath


def get_project_settings():
    command = ['bash', '-c', 'source ' + str(homepath) + '/.agent.bashrc && env']
    proc = subprocess.Popen(command, stdout=subprocess.PIPE)
    for line in proc.stdout:
        (key, _, value) = line.partition("=")
        os.environ[key] = value.strip()
    proc.communicate()
    samplingInterval = os.environ["SAMPLING_INTERVAL"]
    if samplingInterval[-1:] == 's':
        samplingInterval = int(samplingInterval[:-1])
    else:
        samplingInterval = int(samplingInterval) * 60 / 2
    return samplingInterval


if __name__ == "__main__":
    parse_options()
    get_project_settings()
    counter_time_map = {}
    counter = 0
    ##the default value it 60-1, when cAdvisor started, the code need to calculate the index because of the sliding window
    index = 59
    try:
        get_metric()
    except (KeyboardInterrupt, SystemExit):
        print "Keyboard Interrupt"
        sys.exit()

#!/usr/bin/env python
# coding=utf-8

import json
import logging
import os
import sys
import time
from ConfigParser import SafeConfigParser
from optparse import OptionParser
import requests

import arrow
from redis.sentinel import Sentinel

'''
this script gathers system info from redis and use http api to send to server
'''


def get_timestamp_now():
    return int(time.time()*1000)


def get_today_date():
    return arrow.utcnow().format('YYYYMMDD')


def get_logger_config(log_level, name=None):
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    logging_handler_out = logging.StreamHandler(sys.stdout)
    logging_handler_out.setLevel(logging.DEBUG)
    logging_handler_out.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", '%Y-%m-%d %H:%M:%S'))
    logger.addHandler(logging_handler_out)

    logging_handler_err = logging.StreamHandler(sys.stderr)
    logging_handler_err.setLevel(logging.WARNING)
    logging_handler_err.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", '%Y-%m-%d %H:%M:%S'))
    logger.addHandler(logging_handler_err)
    return logger


def get_parameters():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-i", "--project-name", dest="project_name",
                      help="required, send data to this project")
    parser.add_option("-w", "--server-url", dest="server_url", default='https://app.insightfinder.com',
                      help="optional, send data to this server, defaults to https://app.insightfinder.com")
    parser.add_option("-p", "--file-path", dest="file_path", default=os.getcwd(),
                      help="optional, the path which stored config.ini and HOST_IDS, defaults to current directory")
    (options, args) = parser.parse_args()

    parameters = {
        "project_name": options.project_name,
        "server_url": options.server_url,
        "file_path": options.file_path,
    }

    if str(parameters["server_url"]).endswith("/"):
        parameters["server_url"] = parameters["server_url"][:-1]
    if str(parameters["file_path"]).endswith("/"):
        parameters["file_path"] = parameters["file_path"][:-1]

    assert parameters["project_name"] is not None
    assert os.path.exists("{path}/{file}".format(path=parameters["file_path"], file="config.ini"))
    assert os.path.exists("{path}/{file}".format(path=parameters["file_path"], file="HOST_IDS"))

    return parameters


def get_redis_config():
    cp = SafeConfigParser()
    cp.read("{path}/{file}".format(path=params["file_path"], file="config.ini"))
    redis_config = {
        "username": cp.get("user_info", "username"), 
        "license_key": cp.get("user_info", "license_key"), 
        "startup_nodes": eval(cp.get("sentinels", "startup_nodes")),
        "conf_service_name": cp.get("sysmgr-conf", "service_name"),
        "conf_password": cp.get("sysmgr-conf", "password"),
        "conf_db": cp.getint("sysmgr-conf", "db"),
        "data_service_name": cp.get("sysmgr-data", "service_name"),
        "data_password": cp.get("sysmgr-data", "password"),
        "data_db": cp.getint("sysmgr-data", "db"),
    }
    return redis_config


def get_host_ids(file_name, file_path=""):
    with open("{path}/{file}".format(path=file_path, file=file_name), "r") as f:
        title = f.readline()
        host_ids = []
        for line in f.readlines():
            line = line.strip()
            if line == "":
                continue
            instance, host_id = line.split(",")
            host_ids.append((instance.strip(), host_id.strip()))
    return host_ids


def get_key_ids(file_name, file_path=""):
    with open("{path}/{file}".format(path=file_path, file=file_name), "r") as f:
        title = f.readline()
        key_ids = []
        for line in f.readlines():
            line = line.strip()
            if line == "":
                continue
            instance, host_id, cpu_id, mem_id = line.split(",")
            key_ids.append((instance.strip(), host_id.strip(), cpu_id.strip(), mem_id.strip()))
    return key_ids


def get_usage_value(usage):
    # usage like "\x01\x00[Ljava.lang.Object\xbb\x04\t\xa0\x98\xbe\xb6\xd8Y\t\xa0\x98\xbe\xb6\xd8Y\x030.23\xb4"
    if usage is not None:
        index = usage.find("Y\x03")
        if index != -1:
            usage = usage[index + 1: -1]
    return usage


def get_metric_info():
    sentinel = Sentinel(config["startup_nodes"])
    slave_data = sentinel.slave_for(config["data_service_name"], password=config["data_password"], db=config["data_db"])

    file_name = file_name_pattern.replace("*", get_today_date())
    try:
        key_ids = get_key_ids(file_name, params["file_path"])
        logger.info("get {} key_ids by file {}/{}".format(len(key_ids), params["file_path"], file_name))
    except:
        slave_conf = sentinel.slave_for(config["conf_service_name"], password=config["conf_password"], db=config["conf_db"])
        host_ids = get_host_ids("HOST_IDS", params["file_path"])
        os.system("rm -rf {path}/{file}".format(path=params["file_path"], file=file_name_pattern))
        with open("{path}/{file}".format(path=params["file_path"], file=file_name), "w") as f:
            key_ids = []
            f.write("instance,host_id,cpu_id,mem_id\n")
            for instance, host_id in host_ids:
                cpu_id = slave_conf.lrange("cm:mo:{}:children:host_cpu".format(host_id), 0, -1)[0]
                mem_id = slave_conf.lrange("cm:mo:{}:children:host_mem".format(host_id), 0, -1)[0]
                key_ids.append((instance, host_id, cpu_id, mem_id))
                f.write("{},{},{},{}\n".format(instance, host_id, cpu_id, mem_id))
        logger.info("get {} key_ids by HOST_IDS and create file {}/{}".format(len(key_ids), params["file_path"], file_name))

    metric_info = []
    for instance, host_id, cpu_id, mem_id in key_ids:
        cpu_used = get_usage_value(slave_data.hget("pm:snapsl:{}".format(cpu_id), "cpuusage"))
        mem_used = get_usage_value(slave_data.hget("pm:snapsl:{}".format(mem_id), "mem_used"))
        metric_info.append({"instance": instance, "cpu": cpu_used, "memory": mem_used})
    return metric_info


def get_metric_data(metric_info):
    metric_data = {}
    for info in metric_info:
        for metric_name, metric_value in info.items():
            if metric_name == "instance":
                continue
            header = "{metric}[{instance}]:{grouping_id}"\
                .format(metric=metric_name, instance=info["instance"], grouping_id=grouping_map[metric_name])
            metric_data[header] = str(metric_value)
    metric_data['timestamp'] = str(get_timestamp_now())
    return [metric_data]


def send_data(metric_data):
    start = time.time()
    # prepare data for metric streaming agent
    body_data = {
        "userName": config["username"],
        "licenseKey": config["license_key"],
        "projectName": params['project_name'],
        "agentType": "custom",
        "metricData": json.dumps(metric_data)
    }
    data_length = len(bytearray(json.dumps(body_data)))
    logger.debug("ready to send {length} bytes data to {server}".format(length=data_length, server=params["server_url"]))

    # send the data
    url = params["server_url"] + "/customprojectrawdata"
    response = requests.post(url, data=body_data)
    if response.status_code == 200:
        logger.warning("Successfully send {length} bytes data to {server}".format(length=data_length, server=params["server_url"]))
    else:
        logger.error("Failed to send data to {server}".format(server=params["server_url"]))
    logger.debug("--- send data cost {cost_time} seconds ---".format(cost_time=(time.time()-start)))


if __name__ == "__main__":
    logger = get_logger_config(logging.DEBUG, "redis for cmcc")

    file_name_pattern = "REDIS_AGENT_*_KEY_IDS"
    grouping_map = {
        "cpu": 1,
        "memory": 2
    }
    params = get_parameters()
    config = get_redis_config()

    data = get_metric_data(get_metric_info())
    send_data(data)

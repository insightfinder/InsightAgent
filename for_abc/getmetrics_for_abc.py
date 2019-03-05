#!/usr/bin/env python
# coding=utf-8

import time
import json
import traceback
import logging
import urllib
from logging.handlers import TimedRotatingFileHandler
from optparse import OptionParser
from collections import defaultdict


def get_logger_config(logger_name=__name__, file_name="insightfinder.log", backup=2, file_level=logging.INFO, stream_level=logging.WARNING):
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", '%Y-%m-%d %H:%M:%S')

    file_handler = TimedRotatingFileHandler(file_name, when="MIDNIGHT", backupCount=backup)
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setLevel(stream_level)
    console.setFormatter(formatter)
    logger.addHandler(console)
    return logger


def load_grouping_map(file_name="grouping_map"):
    try:
        with open(file_name, "r") as f:
            logger.info("load grouping map")
            return json.loads(f.read())
    except:
        logger.warning(traceback.format_exc())
        logger.warning("create file {}".format(file_name))
        return {}


def get_grouping_id(metric_name):
    group_id = grouping_map.get(metric_name, None)
    if group_id is None:
        group_id = len(grouping_map) + 1 + grouping_id_start
        grouping_map[metric_name] = group_id
        logger.info("add new group_id - {}: {}".format(metric_name, group_id))
    return group_id


def save_grouping_map(file_name="grouping_map"):
    with open(file_name, "w") as f:
        f.write(json.dumps(grouping_map))
        logger.info("save grouping map")

# ---------------------------------------------------------------------------------------------------------------------


def get_filename():
    usage = "Usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--directory",
                      action="store", dest="homepath", help="Directory to run from")
    parser.add_option("-f", dest="filename", help="the filename you want to replay")
    (options, args) = parser.parse_args()

    if not options.filename:
        parser.error("missing filename, use --help to see more details")

    return options.filename


def get_metric_info(file_name):
    metric_info = defaultdict(dict)
    try:
        with open(file_name, "r") as f:
            for line_index, line in enumerate(f.readlines()):
                line = line.strip()
                if line == "":
                    continue
                try:
                    instance, a, b, metric_name, date_time, metric_value = line.split(",")
                    timestamp = str(int((time.mktime(time.strptime(date_time.strip(), "%Y-%m-%d %H:%M:%S")) - adjust_timezone * 60*60)* 1000))
                    grouping_id = get_grouping_id(metric_name.strip())
                    header = "{metric}[{instance}]:{grouping_id}"\
                        .format(metric=metric_name.strip(), instance=instance.strip(), grouping_id=grouping_id)
                    metric_info[timestamp][header] = metric_value.strip()
                except:
                    logger.error("line {}: {}\n{}".format(line_index, line, traceback.format_exc()))
    except:
        logger.error("there is something wrong with {}\n{}".format(file_name, traceback.format_exc()))
    return metric_info  # {timestamp: {header: value, ..}, ..}


def to_metric_data(metric_info):
    metric_data = []
    for timestamp, info in metric_info.items():
        metric_data.append(dict({"timestamp": str(timestamp)}, **info))
    return metric_data   # [{"timestamp": timestamp, header: value, ...}]


def send_data(metric_data):
    body_data = {
        "userName": username,
        "licenseKey": license_key,
        "projectName": project_name,
        "agentType": "custom",
        "metricData": json.dumps(metric_data)
    }
    data_length = len(bytearray(json.dumps(body_data)))
    logger.info("{project} - ready to send {length} bytes data".format(project=project_name, length=data_length))

    start = time.time()
    url = protocol + "://" + server_address + "/customprojectrawdata"
    response = urllib.urlopen(url, data=urllib.urlencode(body_data))
    if response.getcode() == 200:
        logger.warning("{project} - Successfully send {length} bytes data".format(project=project_name, length=data_length))
    else:
        logger.debug("{project} - Failed to send data to {url} with body data - {data}".format(project=project_name, url=url, data=body_data))
        logger.error("{project} - Failed to send data - {reason}".format(project=project_name, reason=response.raise_for_status()))
    logger.info("{project} - send data cost {cost_time} seconds".format(project=project_name, cost_time=(time.time()-start)))


def main():
    file_name = get_filename()
    metric_info = get_metric_info(file_name)
    metric_data = to_metric_data(metric_info)
    send_data(metric_data)
    save_grouping_map()


if __name__ == "__main__":
    grouping_id_start = 500

    # config
    adjust_timezone = -8
    username = ""
    license_key = ""
    server_address = ""  # host:port
    project_name = ""
    protocol = "http"

    # main
    logger = get_logger_config(logger_name="for abc")
    grouping_map = load_grouping_map()
    main()

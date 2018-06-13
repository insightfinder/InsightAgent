"""
Supports flushing metrics to InsightFinder
"""

import re
import sys
import logging
import socket
import requests
import json
import time
import os
import random

##
# InsightFinder sink for statsite
# ==========================
#
# Use with the following stream command:
#
#  stream_command = python sinks/insightfinder.py insightfinder.ini INFO 3
#
# The InsightFinder sink takes an INI format configuration file as a first
# argument , log level as a second argument and no. of re-connect attempts as the third argument.
# The following is an example configuration:
#
# Configuration example:
# ---------------------
#
# [insightfinder]
# username = user
# project_name = statsite
# license_key = c123439662ad1edf64e99e97e4b776112345678
# sampling_interval = 10
# url = https://app.insightfinder.com
#
# Options:
# --------
#  - username:  Insightfinder application user-name. You can get it from this page: https://app.insightfinder.com/account-info
#  - project_name: InsightFinder project to send data to
#  - license_key: InsightFinder license key. You can get it from this page: https://app.insightfinder.com/account-info
#  - sampling_interval: statsite sampling interval
#  - url (optional) : Host url to send data to. Its https://app.insightfinder.com by default
#  - host_get: point index of host start to host end, Its 2,4 by default
#  - metric_name_get: point index of metric start to metric end, Its 4,5 by default
###

SPACES = re.compile(r"\s+")
SLASHES = re.compile(r"\/+")
NON_ALNUM = re.compile(r"[^a-zA-Z_\-0-9\.]")
GROUPING_START = 10000
GROUPING_END = 20000


class InsightfinderStore(object):
    def __init__(self, cfg="/etc/insightfinder.ini", lvl="INFO", attempts=3):
        """
        Implements an interface that allows metrics to be persisted to InsightFinder.

        Raises a :class:`ValueError` on bad arguments or `Exception` on missing
        configuration section.

        :Parameters:
                - `cfg` (optional) : INI configuration file.
                - `lvl` (optional) : logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
                - `attempts` (optional) : The number of re-connect retries before failing.
        """
        if attempts < 1:
            raise ValueError("Must have at least 1 attempt!")

        attempts = int(attempts)
        self.logger = logging.getLogger("statsite.insightfinderstore")
        self.logger.setLevel(lvl)
        self.attempts = attempts
        self.metrics_map = {}
        self.to_send_metrics = []
        self.cfg = cfg
        self.load(cfg)
        self.temp_group_id = 10000
        self._load_grouping()

    def load(self, cfg):
        """Loads configuration from an INI format file"""
        import ConfigParser
        ini = ConfigParser.RawConfigParser()
        ini.read(cfg)

        sect = "insightfinder"
        if not ini.has_section(sect):
            raise Exception("Can not locate config section '" + sect + "'")

        if ini.has_option(sect, 'username'):
            self.username = ini.get(sect, 'username')
        else:
            raise ValueError("username must be set in config")

        if ini.has_option(sect, 'project_name'):
            self.project_name = ini.get(sect, 'project_name')
        else:
            raise ValueError("project_name must be set in config")

        if ini.has_option(sect, 'license_key'):
            self.license_key = ini.get(sect, 'license_key')
        else:
            raise ValueError("license_key must be set in config")

        self.url = 'https://app.insightfinder.com'
        if ini.has_option(sect, 'url'):
            self.url = ini.get(sect, 'url')
        self.sampling_interval = 10
        if ini.has_option(sect, 'sampling_interval'):
            self.sampling_interval = int(ini.get(sect, 'sampling_interval'))

        self.host_get = '2,4'
        if ini.has_option(sect, 'host_get'):
            self.host_get = ini.get(sect, 'host_get')

        self.metric_name_get = '4,5'
        if ini.has_option(sect, 'metric_name_get'):
            self.metric_name_get = ini.get(sect, 'metric_name_get')

    def _load_grouping(self):
        if (os.path.isfile('grouping.json')):
            self.logger.debug("Grouping file exists. Loading..")
            with open('grouping.json', 'r+') as f:
                try:
                    self.grouping_map = json.loads(f.read())
                except ValueError:
                    self.grouping_map = json.loads("{}")
                    self.logger.debug("Error parsing grouping.json.")
        else:
            self.grouping_map = json.loads("{}")

    def _get_grouping_id(self, metric_key):
        """
        Get grouping id for a metric key

        Parameters:
        - `metric_key` : metric key str to get group id.
        - `temp_id` : proposed group id integer
        """
        for i in range(3):
            grouping_candidate = random.randint(GROUPING_START, GROUPING_END)
            if metric_key in self.grouping_map:
                grouping_id = int(self.grouping_map[metric_key])
                return grouping_id
            else:
                grouping_id = grouping_candidate
                self.grouping_map[metric_key] = grouping_id
                return grouping_id
        return GROUPING_START

    def save_grouping(self):
        """
        Saves the grouping data to grouping.json

        :return: None
        """
        with open('grouping.json', 'w+') as f:
            f.write(json.dumps(self.grouping_map))

    def normalize_key(self, key):
        """
        Take a single key string and return the same string with spaces, slashes and
        non-alphanumeric characters subbed out and prefixed by self.prefix.
        """
        key = SPACES.sub("_", key)
        key = SLASHES.sub("-", key)
        key = NON_ALNUM.sub("", key)
        # key = "%s%s" % (self.prefix, key)
        return key

    def append(self, metric):
        """
        Flushes the metrics provided to InsightFinder.

        Parameters:
        - `metric` : A string entry with format key|value|timestamp.
        """
        if not metric and metric.count("|") != 2:
            return
        hostname = socket.gethostname()

        if len(metric) != 0:
            metric_split = metric.split("|")
            metric_key = self.normalize_key(metric_split[0])
            metric_value = metric_split[1]
            timestamp = int(metric_split[2])

            hostname = self.get_details_by_metric(metric_key, self.host_get, hostname)
            metric_name = self.get_details_by_metric(metric_key, self.metric_name_get, metric_key)

            if timestamp in self.metrics_map:
                value_map = self.metrics_map[timestamp]
            else:
                value_map = {}

            value_map[metric_name + '[' + hostname + ']:' +
                      str(self._get_grouping_id(metric_name))] = metric_value
            self.temp_group_id += 1
            self.metrics_map[timestamp] = value_map

    @staticmethod
    def get_details_by_metric(metric_key, get_key, default):
        res = default
        try:
            if metric_key and get_key:
                spl_list = get_key.split(',')
                spl_left = int(spl_list[0])
                spl_right = int(spl_list[1])
                metric_info = metric_key.split('.')
                if len(metric_info) > spl_right:
                    res = '.'.join(metric_info[spl_left:spl_right])
        except:
            pass
        return res


def send_metrics(self):
    self.logger.info("Outputting %d metrics", sum(len(v)
                                                  for v in self.metrics_map.itervalues()))
    self._flush_lines()
    self.metrics_map = {}
    self.to_send_metrics = []


def _flush_lines(self):
    """ Flushes the metrics provided to InsightFinder. """
    if not self.metrics_map:
        return
    # reformat data as a list of JSON Objects for each timestamp
    for timestamp in self.metrics_map.keys():
        value_map = self.metrics_map[timestamp]
        value_map['timestamp'] = str(timestamp) + '000'
        self.to_send_metrics.append(value_map)

    try:
        self._write_metric(self.to_send_metrics)
    except StandardError:
        self.logger.exception("Failed to write out the metrics!")


def _write_metric(self, metric):
    """Tries to create a JSON message and send to the InsightFinder URL, reconnecting on any errors"""
    for _ in xrange(self.attempts):
        try:
            self._send_data(metric)
            return
        except IOError:
            self.logger.exception(
                "Error while flushing to InsightFinder. Reattempting...")

    self.logger.critical(
        "Failed to flush to Insightfinder! Gave up after %d attempts.", self.attempts)


def _send_data(self, metric_data):
    if not metric_data or len(metric_data) == 0:
        self.logger.warning("No data to send for this flush.")
        return

    send_data_time = time.time()

    # prepare data for metric streaming agent
    to_send_data_dict = {}
    to_send_data_dict["metricData"] = json.dumps(metric_data)
    to_send_data_dict["licenseKey"] = self.license_key
    to_send_data_dict["projectName"] = self.project_name
    to_send_data_dict["userName"] = self.username
    to_send_data_dict["instanceName"] = socket.gethostname().partition(".")[
        0]
    to_send_data_dict["samplingInterval"] = str(self.sampling_interval)
    to_send_data_dict["agentType"] = "custom"

    to_send_data_json = json.dumps(to_send_data_dict)
    self.logger.debug(
        "TotalData: " + str(len(bytearray(to_send_data_json))))

    # send the data
    postUrl = self.url + "/customprojectrawdata"
    response = requests.post(postUrl, data=json.loads(to_send_data_json))
    if response.status_code == 200:
        self.logger.info(str(len(bytearray(to_send_data_json))
                             ) + " bytes of data are reported.")
    else:
        self.logger.exception("Failed to send data.")
        raise IOError("Failed to send request to " + postUrl)
    self.logger.debug("--- Send data time: %s seconds ---" %
                      (time.time() - send_data_time))


def main():
    # Initialize the logger
    logging.basicConfig()

    # Intialize from our arguments
    insightfinder = InsightfinderStore(*sys.argv[1:])

    METRICS_BYTES_PER_FLUSH = 3000000

    # Get all the inputs
    for line in sys.stdin:
        map_size = len(bytearray(json.dumps(insightfinder.metrics_map)))
        if map_size >= METRICS_BYTES_PER_FLUSH:
            insightfinder.send_metrics()
        insightfinder.append(line.strip())

    insightfinder.send_metrics()
    insightfinder.save_grouping()


if __name__ == "__main__":
    main()

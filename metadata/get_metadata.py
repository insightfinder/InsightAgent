#!/usr/bin/env python
import csv
import socket
from optparse import OptionParser
import os
import json
import requests
import logging
import sys
import time


class InsightfinderStore(object):

    def __init__(self, *args):
        """
        Implements an interface that allows topology/metadata data to be sent to InsightFinder.
        """
        self._get_parameters()
        #Set up logging
        self.logger = logging.getLogger(__name__)
        # create a file handler
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setLevel(self.log_level)
        # create a logging format
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(process)d - %(threadName)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        # add the handlers to the logger
        self.logger.addHandler(handler)
        self.logger.setLevel(self.log_level)

        self._get_agent_config_vars()
        self._get_reporting_config_vars()

    def _get_parameters(self):
        usage = """Usage: %prog [options]..
        \n-d\t--directory\tDirectory to run from
        \n -p\t--file-type\tType of metadata file
        \n-w\t--server-url\tServer URL to send data to
        \n-i\t--inst-col\tInstance column name
        \n-g\t--group-col\tGrouping column name
        \n-k\t--causal-key\tCausal Key
        \n-l\t--log_level\tLog Level(INFO, DEBUG, WARN, ERROR)
        \n-f\t--filepath\tMeta-data file path
        """

        # Command line options
        parser = OptionParser(usage=usage)
        parser.add_option("-d", "--directory",
                          action="store", dest="homepath", help="Directory to run from")
        parser.add_option("-p", "--file-type",
                          action="store", dest="file_type", help="Type of metadata file")
        parser.add_option("-w", "--serverUrl",
                          action="store", dest="server_url", help="Server Url")
        parser.add_option("-i", "--inst-col",
                          action="store", dest="instance_col", help="Instance column name")
        parser.add_option("-g", "--group-col",
                          action="store", dest="group_col", help="Grouping column name")
        parser.add_option("-k", "--causal-key",
                          action="store", dest="causal_key", help="Causal Key")
        parser.add_option("-l", "--log-level",
                          action="store", dest="log_level", help="Log Level(INFO, DEBUG, WARN, ERROR)")
        parser.add_option("-f", "--filepath",
                          action="store", dest="file_path", help="Meta-data file path")

        (options, args) = parser.parse_args()
        if options.homepath is None:
            self.homepath = os.getcwd()
        else:
            self.homepath = options.homepath
        if options.server_url is not None:
            self.server_url = options.server_url
        else:
            self.server_url = 'https://app.insightfinder.com'
        if options.file_type is None:
            self.file_type = "topology"
        else:
            self.file_type = options.file_type
        if options.instance_col is None:
            self.instance_col = "IP Address"
        else:
            self.instance_col = options.instance_col
        if options.group_col is None:
            self.group_col = "Environment Name"
        else:
            self.group_col = options.group_col
        if options.log_level is None:
            self.log_level = "INFO"
        else:
            self.log_level = options.log_level
        if options.file_path is None:
            self.file_path = os.path.join(self.homepath, "data", "metadata.csv")
        else:
            self.file_path = options.file_path
        if self.file_type == "topology" and options.causal_key is None:
            exit()
        else:
            self.causal_key = options.causal_key

    def _get_agent_config_vars(self):
        with open(os.path.join(self.homepath, ".agent.bashrc"), 'r') as configFile:
            file_content = configFile.readlines()
            if len(file_content) < 6:
                self.logger.error("Agent not correctly configured. Check .agent.bashrc file.")
                sys.exit(1)
            # get license key
            license_key_line = file_content[0].split(" ")
            if len(license_key_line) != 2:
                self.logger.error("Agent not correctly configured(license key). Check .agent.bashrc file.")
                sys.exit(1)
            self.license_key = license_key_line[1].split("=")[1].strip()
            # get project name
            project_name_line = file_content[1].split(" ")
            if len(project_name_line) != 2:
                self.logger.error("Agent not correctly configured(project name). Check .agent.bashrc file.")
                sys.exit(1)
            self.project_name = project_name_line[1].split("=")[1].strip()
            # get username
            user_name_line = file_content[2].split(" ")
            if len(user_name_line) != 2:
                self.logger.error("Agent not correctly configured(username). Check .agent.bashrc file.")
                sys.exit(1)
            self.user_name = user_name_line[1].split("=")[1].strip()
            # get sampling interval
            sampling_interval_line = file_content[4].split(" ")
            if len(sampling_interval_line) != 2:
                self.logger.error("Agent not correctly configured(sampling interval). Check .agent.bashrc file.")
                sys.exit(1)
            self.sampling_interval = sampling_interval_line[1].split("=")[1].strip()

    def _get_reporting_config_vars(self):
        with open(os.path.join(self.homepath, "reporting_config.json"), 'r') as f:
            config = json.load(f)
        reporting_interval_string = config['reporting_interval']
        is_second_reporting = False
        if reporting_interval_string[-1:] == 's':
            is_second_reporting = True
            reporting_interval = float(config['reporting_interval'][:-1])
            self.reporting_interval = float(reporting_interval / 60.0)
        else:
            self.reporting_interval = int(config['reporting_interval'])
            self.keep_file_days = int(config['keep_file_days'])
            self.prev_endtime = config['prev_endtime']
            self.deltaFields = config['delta_fields']

        self.keep_file_days = int(config['keep_file_days'])
        self.prev_endtime = config['prev_endtime']
        self.deltaFields = config['delta_fields']

    def parse_topology_file(self, file_path):
        topology_list = []
        if os.path.isfile(file_path):
            with open(file_path) as topology_file:
                topology_file_csv = csv.reader(topology_file)
                for row in topology_file_csv:
                    map_size = len(bytearray(json.dumps(topology_list)))
                    if map_size >= BYTES_PER_FLUSH:
                        self._send_data(topology_list)
                        topology_list = []
                    if topology_file_csv.line_num == 1:
                        continue
                    key = ""
                    for index in xrange(len(row)):
                        if index == 0:
                            key = row[index]
                            continue
                        value1 = str(key) + "@@@@" + str(row[index])
                        value2 = str(row[index]) + "@@@@" + str(key)
                        if value1 not in topology_list:
                            topology_list.append(value1)
                        if value2 not in topology_list:
                            topology_list.append(value2)
                self._send_data(topology_list)

    def _send_data(self, metric_data_list):
        if not metric_data_list or len(metric_data_list) == 0:
            self.logger.warning("No data to send for this flush.")
            return

        send_data_time = time.time()

        to_send_data_dict = {}
        if len(metric_data_list) == 0:
            print "No metadata to sent."
            return
        # update projectKey, userName in dict
        to_send_data_dict["licenseKey"] = self.license_key
        to_send_data_dict["userName"] = self.user_name
        to_send_data_dict["fileType"] = self.file_type
        if self.file_type == "topology":
            to_send_data_dict["topologyData"] = json.dumps(metric_data_list)
            to_send_data_dict["causalKey"] = self.causal_key
        else:
            to_send_data_dict["instanceName"] = socket.gethostname()
            to_send_data_dict["groupingData"] = json.dumps(metric_data_list)
            to_send_data_dict["isMetricAgent"] = "true"
            to_send_data_dict["projectName"] = self.project_name

        to_send_data_json = json.dumps(to_send_data_dict)

        self.logger.debug(
            "TotalData: " + str(len(bytearray(to_send_data_json))))

        # send the data
        post_url = self.server_url + "/api/v1/customgrouping"
        try:
            response = requests.post(post_url, data=json.loads(to_send_data_json))
            if response.status_code == 200:
                self.logger.info(str(len(bytearray(to_send_data_json))
                                     ) + " bytes of data are reported.")
            else:
                self.logger.exception("Failed to send data.")
                raise IOError("Failed to send request to " + post_url)
            self.logger.debug("--- Send data time: %s seconds ---" %
                              (time.time() - send_data_time))
        except requests.exceptions.ConnectionError:
            self.logger.error("Failed to send request to " + post_url)

    # def parseCsvfile(filePath, instanceColumn, groupColumn):
    #     if os.path.isfile(filePath):
    #         grouping_file = open(filePath)
    #         try:
    #             grouping_file_csv = csv.reader(grouping_file)
    #         except IOError:
    #             print "No meta-data file!"
    #         fieldnames = []
    #         grouping_dict = {}
    #         for row in grouping_file_csv:
    #             print grouping_file_csv.line_num
    #             if grouping_file_csv.line_num == 1:
    #                 fieldnames = row
    #                 instance_column_index = fieldnames.index(instanceColumn)
    #                 group_column_index = fieldnames.index(groupColumn)
    #             else:
    #                 group_name = row[group_column_index]
    #                 instance_name = row[instance_column_index]
    #                 if group_name not in grouping_dict:
    #                     grouping_dict[group_name] = ""
    #                     grouping_dict[group_name] = grouping_dict[group_name] + instance_name
    #                 else:
    #                     grouping_dict[group_name] = grouping_dict[group_name] + "," + instance_name
    #         return grouping_dict

if __name__ == "__main__":
    BYTES_PER_FLUSH = 3000000
    insightfinder = InsightfinderStore(*sys.argv[1:])
    insightfinder.parse_topology_file(insightfinder.file_path)
    insightfinder.logger.debug("File parsing done")
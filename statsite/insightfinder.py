"""
Supports flushing metrics to InsightFinder
"""

import re
import sys
import socket
import logging
import pickle
import struct
import socket
import requests
import json
import time
import os

# Initialize the logger
logging.basicConfig()

SPACES = re.compile(r"\s+")
SLASHES = re.compile(r"\/+")
NON_ALNUM = re.compile(r"[^a-zA-Z_\-0-9\.]")


class InsightfinderStore(object):

		def __init__(self, cfg="/home/moharnab/statsite/insightfinder.ini", prefix="statsite.", attempts=3):

			attempts = int(attempts)
			self.logger = logging.getLogger("statsite.insightfinderstore")
			self.prefix = prefix
			self.attempts = attempts
			self.metrics_map = {}
			self.to_send_metrics = []
			self.cfg = cfg
			self.load(cfg)

		def load(self, cfg):
			# Loads configuration from an INI format file
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

		def get_grouping_id(self, metricName, tempID):
			
			if(os.path.isfile('grouping.json')):
				self.logger.info("Grouping file exists. Continuing..");
			else:
				self.logger.info("Grouping file doesn't exist. Creating new file.");
				grouping_file = open('grouping.json', "w")
				grouping_file.write('{}')
				grouping_file.close()
			grouping_id = 0
			with open('grouping.json', 'r+') as f:
				grouping_obj = json.loads(f.read())
				if metricName in grouping_obj.keys():
					grouping_id = int(grouping_obj[metricName])
				else:
					grouping_id = tempID
				grouping_obj[metricName] = grouping_id
				f.seek(0)
				f.write(json.dumps(grouping_obj))
				f.truncate()
			return grouping_id				

		def flush(self, metrics):
			"""
			Flushes the metrics provided to InfluxDB.

			Parameters:
			- `metrics` : A list of (key,value,timestamp) tuples.
			"""
			if not metrics:
				return
			hostname = socket.gethostname()
			temp_group_id = 10000
			for metric in metrics:
				if len(metric) != 0:
					metric_split = metric.split("|")
					metric_key = metric_split[0]
					metric_value = metric_split[1]
					timestamp = int(metric_split[2])

					if timestamp in self.metrics_map:
						value_map = self.metrics_map[timestamp]
					else:
						value_map = {}

					value_map[metric_key + '[' + hostname + ']:' + str(self.get_grouping_id(metric_key, temp_group_id))] = metric_value
					temp_group_id += 1
					print value_map
					self.metrics_map[timestamp] = value_map
			print self.metrics_map
			for timestamp in self.metrics_map.keys():
				value_map = self.metrics_map[timestamp]
				value_map['timestamp'] = str(timestamp) + '000'
				self.to_send_metrics.append(value_map)

			print self.to_send_metrics

			self.send_data(self.to_send_metrics)

		def send_data(self, metric_data):
			
			if not metric_data or len(metric_data) == 0:
				return
			
			send_data_time = time.time()
			# prepare data for metric streaming agent
			to_send_data_dict = {}
			to_send_data_dict["metricData"] = json.dumps(metric_data)
			to_send_data_dict["licenseKey"] = self.license_key
			to_send_data_dict["projectName"] = self.project_name
			to_send_data_dict["userName"] = self.username
			to_send_data_dict["instanceName"] = socket.gethostname().partition(".")[0]
			to_send_data_dict["samplingInterval"] = str(int(10))
			to_send_data_dict["agentType"] = "custom"

			to_send_data_json = json.dumps(to_send_data_dict)
			print "to send"
			print to_send_data_json
			self.logger.info("TotalData: " + str(len(bytearray(to_send_data_json))))

		    # send the data
			postUrl = self.url + "/customprojectrawdata"
			response = requests.post(postUrl, data=json.loads(to_send_data_json))
			if response.status_code == 200:
				print "successfully sent data"
				self.logger.info(str(len(bytearray(to_send_data_json))) + " bytes of data are reported.")
				# updateLastSentFiles(pcapFileList)
			else:
				self.logger.info("Failed to send data.")
				print "failed to send data"
			self.logger.debug("--- Send data time: %s seconds ---" % (time.time() - send_data_time))




def main():
	# Intialize from our arguments
	insightfinder = InsightfinderStore(*sys.argv[1:])

	METRICS_PER_FLUSH = 50

	lines = sys.stdin.read().split("\n")
	insightfinder.flush(lines)
	# Get all the inputs
	# for line in lines:
	# 	print "Output: " + str(line)
	# 	if len(insightfinder.metrics) >= METRICS_PER_FLUSH:
	# 		print "Output: " + str(line)
            # insightfinder.send_metrics()
        # insightfinder.append(line.strip())

    # insightfinder.send_metrics()
	# print "End"


if __name__ == "__main__":
	main()


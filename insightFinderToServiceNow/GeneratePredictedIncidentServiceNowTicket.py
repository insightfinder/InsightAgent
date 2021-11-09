#!/usr/bin/env python
# coding: utf-8

import os
import sys
import requests
import time
from datetime import date, datetime, timedelta

import json
import pickle
import logging
from collections import deque
from configparser import ConfigParser
from ifobfuscate import decode

import warnings
warnings.filterwarnings('ignore')

class GeneratePredictedIncidentServiceNowTicket:
    '''
    Get predicted incident data from InsightFinder and send to ServiceNow
    '''
    
    def __init__(self):

        if os.path.exists(config_path):
            self.get_config_vars()
        else:
            message = "No config file found. Exiting."
            print(message)
            logger.error(message)
            sys.exit(1)
        self.incident_record = incident_record

    def get_config_vars(self):
        '''
        Get config variables from the config file
        '''

        config = ConfigParser()
        config.read(config_path)

        self.insightFinder_vars = {}
        self.insightFinder_vars['host_url'] = config.get('insightFinder_vars', 'host_url')
        self.insightFinder_vars['http_proxy'] = config.get('insightFinder_vars', 'http_proxy')
        self.insightFinder_vars['https_proxy'] = config.get('insightFinder_vars', 'https_proxy')
        self.insightFinder_vars['api'] = config.get('insightFinder_vars', 'api')
        self.insightFinder_vars['licenseKey'] = config.get('insightFinder_vars', 'licenseKey')
        self.insightFinder_vars['retries'] = config.getint('insightFinder_vars', 'retries')
        self.insightFinder_vars['sleep_seconds'] = config.getint('insightFinder_vars', 'sleep_seconds')

        self.serviceNow_vars = {}
        self.serviceNow_vars['host_url'] = config.get('serviceNow_vars', 'host_url')
        self.serviceNow_vars['http_proxy'] = config.get('serviceNow_vars', 'http_proxy')
        self.serviceNow_vars['https_proxy'] = config.get('serviceNow_vars', 'https_proxy')
        self.serviceNow_vars['api'] = config.get('serviceNow_vars', 'api')
        self.serviceNow_vars['username'] = config.get('serviceNow_vars', 'username')
        self.serviceNow_vars['password'] = decode(config.get('serviceNow_vars', 'password'))
        self.serviceNow_vars['target_table'] = config.get('serviceNow_vars', 'target_table')
        self.serviceNow_vars['retries'] = config.getint('serviceNow_vars', 'retries')
        self.serviceNow_vars['sleep_seconds'] = config.getint('serviceNow_vars', 'sleep_seconds')
        self.serviceNow_vars['dampening_minutes'] = config.getint('serviceNow_vars', 'dampening_minutes')

        self.payload_vars = {}
        self.payload_vars['environment_name'] = config.get('payload_vars', 'environment_name')
        self.payload_vars['system_id_list'] = config.get('payload_vars', 'system_id_list').split(',')
        self.payload_vars['system_id_list'] = str([{'id': id.strip()} for id in self.payload_vars['system_id_list']])
        self.payload_vars['customer_name'] = config.get('payload_vars', 'customer_name')
        self.payload_vars['start_date'] = config.get('payload_vars', 'start_date')
        self.payload_vars['end_date'] = config.get('payload_vars', 'end_date')

    def post_all_incidents(self):
        '''
        Process all incidents between the start and end dates
        If either date variable is a null value, it is set to today's datetime
        '''

        time_now = datetime.now()
        start_date = datetime.fromisoformat(self.payload_vars['start_date']) if self.payload_vars['start_date'] else time_now
        end_date = datetime.fromisoformat(self.payload_vars['end_date']) if self.payload_vars['end_date'] else time_now

        if start_date > end_date:
            message = "WARNING: Start Date ({}) > End Date ({}). No incidents would be transferred.".format(
                start_date, end_date)
            print(message)
            logger.info(message)

        day = start_date
        while day <= end_date:
            data = self.get_predicted_incident_json(day)
            self.post_day_incidents(data)

            day += timedelta(days=1)

    def get_predicted_incident_json(self, day):
        '''
        Get predicted incident data for EXACTLY a day from InsightFinder in JSON format
        RETURNS: dict/JSON
        '''
        
        url = self.insightFinder_vars['host_url'] + self.insightFinder_vars['api']
        proxies = {}
        if len(self.insightFinder_vars['http_proxy']) > 0:
            proxies['http'] = self.insightFinder_vars['http_proxy']
        if len(self.insightFinder_vars['https_proxy']) > 0:
            proxies['https'] = self.insightFinder_vars['https_proxy']

        data = {
            'environmentName': self.payload_vars['environment_name'],
            'systemIds': self.payload_vars['system_id_list'],
            'customerName': self.payload_vars['customer_name'],
            'licenseKey': self.insightFinder_vars['licenseKey'],
            'targetTable': self.serviceNow_vars['target_table'],
            'startTime': int(time.mktime(day.astimezone().timetuple())) * 1000
        }

        attempts = 1
        response = requests.get(url, params=data, proxies=proxies, verify=False)
        while response.status_code != 200 and attempts < self.insightFinder_vars['retries']:
            print("Failed to get data for {}. Retrying in {} seconds.".format(
                day, self.insightFinder_vars['sleep_seconds']))
            time.sleep(self.insightFinder_vars['sleep_seconds'])
            response = requests.get(url, params=data, proxies=proxies, verify=False)
            attempts += 1

        if response.status_code == 200:
            message = "\nSuccessfully retrieved the incident data for {} from InsightFinder.".format(day)
            print(message)
            logger.info(message)
            return response.json()
        else:
            message = "Failed to get data for {} in {} attempts. Check logs for details.".format(
                day, self.insightFinder_vars['retries'])
            print(message)
            logger.warning("{} Status Code: {}. Response Text: {}. Response URL: {}.".format(
                message, response.status_code, response.text, response.url))
            return {}

    def post_day_incidents(self, day_data):
        '''
        Process all incidents in a day's worth of incident data
        EXCEPT those re-observed in 'dampening_minutes' interval
        '''

        total_incidents = len(day_data)
        queued = 0
        dampened = 0
        for incident_data in day_data:
            print("Total incidents: {} ; Queued for ServiceNow : {} ; Dampened : {}".format(
                total_incidents, queued, dampened), end='\r')
            incident_key = incident_data['incidentId']
            incident_last_observed = self.incident_record.get(incident_key, None)

            if incident_last_observed and ((incident_data['startTime'] - incident_last_observed) / (1000*60)
                                                                < self.serviceNow_vars['dampening_minutes']):
                dampened += 1
                continue
            
            payload = self.create_serviceNow_payload(incident_data)
            payload_queue.append(payload)
            self.incident_record[incident_key] = incident_data['startTime']
            queued += 1

        message = "Total incidents: {} ; Queued for ServiceNow : {} ; Dampened : {}".format(
            total_incidents, queued, dampened)
        print(message)
        logger.info(message)

        queue_len = len(payload_queue)
        while payload_queue:
            if self.post_serviceNow_ticket(payload_queue[0]):
                payload_queue.popleft()
                print("Total incidents in the queue: {} ; Successfully sent: {}".format(
                    queue_len, queue_len - len(payload_queue)), end='\r')
            else:
                break
        
        message = "Total incidents in the queue: {} ; Successfully sent: {}".format(
            queue_len, queue_len - len(payload_queue))
        print(message)
        logger.info(message)

    def create_serviceNow_payload(self, incident_data):
        '''
        Create single incident data paylaod to send to ServiceNow
        RETURNS: str/JSON
        '''
        
        payload = incident_data.copy()
        del payload['incidentId'], payload['startTime']
        payload = json.dumps(payload)
        
        return payload

    def post_serviceNow_ticket(self, payload):
        '''
        Send a single incident ticket to ServiceNow
        RETURNS: Boolean // whether the ticket was posted successfully
        '''
        
        url = self.serviceNow_vars['host_url'] + self.serviceNow_vars['api']
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        proxies = {}
        if len(self.serviceNow_vars['http_proxy']) > 0:
            proxies['http'] = self.serviceNow_vars['http_proxy']
        if len(self.serviceNow_vars['https_proxy']) > 0:
            proxies['https'] = self.serviceNow_vars['https_proxy']

        attempts = 1
        response = requests.post(url, auth=(self.serviceNow_vars['username'], self.serviceNow_vars['password']),
        headers=headers, data=payload, proxies=proxies, verify=False)
        while response.status_code != 201 and attempts < self.serviceNow_vars['retries']:
            print("Failed to post data to ServiceNow. Retrying in {} seconds.".format(
                self.serviceNow_vars['sleep_seconds']))
            time.sleep(self.serviceNow_vars['sleep_seconds'])
            response = requests.post(url, auth=(self.serviceNow_vars['username'], self.serviceNow_vars['password']),
            headers=headers, data=payload, proxies=proxies, verify=False)
            attempts += 1

        if response.status_code != 201:
            message = "Failed to post data to ServiceNow in {} attempts. Check logs for details.".format(
                self.serviceNow_vars['retries'])
            print(message)
            logger.warning("Status Code: {}. Response Text: {}. Response URL: {}.".format(
                response.status_code, response.text, response.url))
        return response.status_code == 201

if __name__ == '__main__':
    config_path = 'config.ini'
    incident_record_path = 'incident_record.pkl'
    payload_queue_path = 'payload_queue.pkl'
    log_record_path = 'log_record.log'

    '''
    The incident_record pickle stores the past post requests made as a dictionary object
    ** ('projectName', 'componentName', 'patternId') -> latest_timeStamp_of_corresponding_post_request **
    No same incident (defined by the key) will be posted before or within the 'dampening_minutes' interval of last such request
    Delete the pickle file to reset the record (may especially be required for processing historical data)
    '''
    if os.path.exists(incident_record_path):
        with open(incident_record_path, 'rb') as handle:
            incident_record = pickle.load(handle)
    else:
        incident_record = {}

    if os.path.exists(payload_queue_path):
        with open(payload_queue_path, 'rb') as handle:
            payload_queue = pickle.load(handle)
    else:
        payload_queue = deque()

    logging.basicConfig(filename = log_record_path,
                        format = ('%(asctime)s %(filename)s: %(levelname)s: %(funcName)s(): %(lineno)d:\t %(message)s'))
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    try:
        generator = GeneratePredictedIncidentServiceNowTicket()
        generator.post_all_incidents()

    except Exception as e:
        print("ERROR. Check logs.")
        logger.error(e, exc_info=True)
        
    with open(incident_record_path, 'wb') as handle:
        pickle.dump(incident_record, handle, protocol=pickle.HIGHEST_PROTOCOL)

    with open(payload_queue_path, 'wb') as handle:
        pickle.dump(payload_queue, handle, protocol=pickle.HIGHEST_PROTOCOL)
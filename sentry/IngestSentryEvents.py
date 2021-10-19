#!/usr/bin/env python
# coding: utf-8

import os
import sys
import requests
import pickle
from collections import deque
import time
import arrow

import json
import logging
from configparser import ConfigParser

import warnings
warnings.filterwarnings('ignore')

class IngestSentryEvents:
    '''
    Get new events from a Sentry project and send to an IF alert project
    '''
    
    def __init__(self):
        if os.path.exists(config_path):
            self.get_config_vars()
        else:
            message = "No config file found. Exiting."
            print(message)
            logger.error(message)
            sys.exit(1)

    def get_config_vars(self):
        '''
        Get config variables from the config file
        '''

        config = ConfigParser()
        config.read(config_path)

        self.insightFinder_vars = {}
        self.insightFinder_vars['host_url'] = config.get('insightFinder_vars', 'host_url')
        self.insightFinder_vars['api'] = config.get('insightFinder_vars', 'api')
        self.insightFinder_vars['licenseKey'] = config.get('insightFinder_vars', 'licenseKey')
        self.insightFinder_vars['project_name'] = config.get('insightFinder_vars', 'project_name')
        self.insightFinder_vars['username'] = config.get('insightFinder_vars', 'username')
        self.insightFinder_vars['retries'] = config.getint('insightFinder_vars', 'retries')
        self.insightFinder_vars['sleep_seconds'] = config.getint('insightFinder_vars', 'sleep_seconds')

        self.sentry_vars = {}
        self.sentry_vars['host_url'] = config.get('sentry_vars', 'host_url')
        self.sentry_vars['api'] = config.get('sentry_vars', 'api')
        self.sentry_vars['organization_name'] = config.get('sentry_vars', 'organization_name')
        self.sentry_vars['project_name'] = config.get('sentry_vars', 'project_name')
        self.sentry_vars['auth_token'] = config.get('sentry_vars', 'auth_token')
        self.sentry_vars['retries'] = config.getint('sentry_vars', 'retries')
        self.sentry_vars['sleep_seconds'] = config.getint('sentry_vars', 'sleep_seconds')

    def get_events_from_sentry(self):
        '''
        Get new events from a Sentry project (page 1 only)
        '''

        url = self.sentry_vars['host_url'] + self.sentry_vars['api']
        url = url.format(self.sentry_vars['organization_name'], self.sentry_vars['project_name'])

        attempts = 1
        response = requests.get(url, headers={'Authorization': 'Bearer ' + self.sentry_vars['auth_token']})
        while response.status_code != 200 and attempts < self.sentry_vars['retries']:
            print("Failed to send data. Retrying in {} seconds.".format(
                self.sentry_vars['sleep_seconds']))
            time.sleep(self.sentry_vars['sleep_seconds'])
            response = requests.get(url, headers={'Authorization': 'Bearer ' + self.sentry_vars['auth_token']})
            attempts += 1
        
        if response.status_code != 200:
            message = "Failed to connect to Sentry in {} attempts. Check logs for details. Exiting.".format(
                self.sentry_vars['retries'])
            print(message)
            logger.warning("{} Status Code: {}. Response Text: {}. Response URL: {}.".format(
                message, response.status_code, response.text, response.url))
            sys.exit(1)
        
        events = response.json()
        if len(events) == 0:
            print("No events in the Sentry project. Exiting.")
            sys.exit(1)
        
        if os.path.exists(last_event_path):
            with open(last_event_path, 'rb') as handle:
                last_event_id = pickle.load(handle)
        else:
            last_event_id = None

        with open(last_event_path, 'wb') as handle:
            pickle.dump(events[0]['id'], handle, protocol=pickle.HIGHEST_PROTOCOL)
        
        payload = []
        for event in events:
            if event['id'] == last_event_id:
                break
            
            for tag in event['tags']:
                event[tag['key']] = tag['value']

            entry = {
                'eventId': arrow.get(event['dateCreated']).timestamp() * 1000,
                'tag': event['server_name'],
                'data': event
            }
            
            del event['dateCreated'], event['server_name'], event['tags']
            payload.append(entry)
        
        print("New events retrieved from Sentry: {}".format(len(payload)))
        return payload

    def send_payload_to_IF(self, payload):
        '''
        Send parsed alert events to an InsightFinder Alert project
        '''

        start_time = time.time()
        url = self.insightFinder_vars['host_url'] + self.insightFinder_vars['api']
        data = {
            'metricData': json.dumps(payload),
            'licenseKey': self.insightFinder_vars['licenseKey'],
            'projectName': self.insightFinder_vars['project_name'],
            'userName': self.insightFinder_vars['username'],
            'agentType': 'LogStreaming'
        }

        attempts = 1
        response = requests.post(url, data=data, verify=False)
        while response.status_code != 200 and attempts < self.insightFinder_vars['retries']:
            print("Failed to send data. Retrying in {} seconds.".format(
                self.insightFinder_vars['sleep_seconds']))
            time.sleep(self.insightFinder_vars['sleep_seconds'])
            response = requests.post(url, data=data, verify=False)
            attempts += 1

        if response.status_code == 200:
            message = "Successfully sent {} Sentry event(s) in {} seconds.".format(
                len(payload), time.time() - start_time)
            print(message)
            logger.info(message)
            return True
        else:
            message = "Failed to send Sentry event data in {} attempts. Check logs for details.".format(
                self.insightFinder_vars['retries'])
            print(message)
            print("The payload will be stored locally.")
            logger.warning("{} Status Code: {}. Response Text: {}. Response URL: {}.".format(
                message, response.status_code, response.text, response.url))
            return False

if __name__ == '__main__':
    # paths to local files; config.ini is required, rest will be created if not found
    config_path = 'config.ini'
    log_record_path = 'log_record.log'
    last_event_path = 'last_event_id.pkl'
    payload_queue_path = 'payload_queue.pkl'

    logging.basicConfig(filename = log_record_path,
                        format = ('%(asctime)s %(filename)s: %(levelname)s: %(funcName)s(): %(lineno)d:\t %(message)s'))
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    if os.path.exists(payload_queue_path):
        with open(payload_queue_path, 'rb') as handle:
            payload_queue = pickle.load(handle)
    else:
        payload_queue = deque()

    try:
        obj = IngestSentryEvents()
        payload = obj.get_events_from_sentry()
        if len(payload) > 0:
            payload_queue.append(payload)
        while payload_queue:
            if obj.send_payload_to_IF(payload_queue[0]):
                payload_queue.popleft()
            else:
                break

    except Exception as e:
        print("ERROR. Check logs.")
        logger.error(e, exc_info=True)

    with open(payload_queue_path, 'wb') as handle:
        pickle.dump(payload_queue, handle, protocol=pickle.HIGHEST_PROTOCOL)

#!/usr/bin/env python
import json
import logging
import os
import requests
import time

IF_URL = 'http://app.insightfinder.com:8080/api/v1/deploymentEventReceive'
IF_USER = 'user'
IF_LICENSE_KEY = ''
IF_PROJECT_NAME = ''


def main():
    job_type = os.environ['JOB_TYPE']
    build_status = os.environ['STATUS']

    workspace = os.environ['JOB_CORE_WORKSPACE']
    os.system('cd ' + workspace)
    git_log_core = os.popen('cd ' + workspace + ' && git log -1').read()
    print(git_log_core)

    workspace = '/home/ubuntu/workspace/CI_Pipelines/1-Test_Branch_Pipeline/1-Build_Web_Repository'
    os.system('cd ' + workspace)
    git_log_web = os.popen('cd ' + workspace + ' && git log -1').read()
    print(git_log_web)

    data_array = []
    ticket_data = dict()
    ticket_data['timestamp'] = int(round(time.time() * 1000))
    ticket_data['instanceName'] = 'build-server'
    ticket_data['data'] = 'jobType: ' + job_type + '\nbuildStatus: ' + build_status + '\nUI git log: ' + str(
        git_log_web) + '\nCore git log: ' + str(git_log_core)
    data_array.append(ticket_data)
    send_data(data_array)
    print(json.dumps(data_array))


def send_data(deployment_data):
    parameters = dict()
    parameters["deploymentData"] = json.dumps(deployment_data)
    parameters["userName"] = IF_USER
    parameters["licenseKey"] = IF_LICENSE_KEY
    parameters["projectName"] = IF_PROJECT_NAME
    parameters["instanceName"] = 'build-server'
    response = requests.post(IF_URL, data=parameters)
    print(response)


if __name__ == '__main__':
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    main()

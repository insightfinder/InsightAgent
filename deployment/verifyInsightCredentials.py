#!/usr/bin/python

import requests
import json
import argparse
import sys
import time

serverUrl = 'https://agent-data.insightfinder.com'

def get_args():
    global serverUrl
    parser = argparse.ArgumentParser(description='Script retrieves arguments for insightfinder agent.')
    parser.add_argument('-i', '--PROJECT_NAME_IN_INSIGHTFINDER', type=str, help='Project Name registered in Insightfinder', required=True)
    parser.add_argument('-u', '--USER_NAME_IN_INSIGHTFINDER', type=str, help='User Name in Insightfinder', required=True)
    parser.add_argument('-k', '--LICENSE_KEY', type=str, help='License key for the user', required=True)
    parser.add_argument('-w', '--SERVER_URL', type=str, help='Server Url of Insightfinder server', required=False)
    args = parser.parse_args()
    projectName = args.PROJECT_NAME_IN_INSIGHTFINDER
    userInsightfinder = args.USER_NAME_IN_INSIGHTFINDER
    licenseKey = args.LICENSE_KEY
    if args.SERVER_URL != None:
        serverUrl = args.SERVER_URL
    print serverUrl
    return projectName, userInsightfinder, licenseKey

def sendData():
    global projectName
    global userInsightfinder
    global licenseKey
    alldata["userName"] = userInsightfinder
    alldata["operation"] = "verify"
    alldata["licenseKey"] = licenseKey
    alldata["projectName"] = projectName
    json_data = json.dumps(alldata)
    #print json_data
    url = serverUrl + "/api/v1/agentdatahelper"
    print serverUrl
    try:
        response = requests.post(url, data = json.loads(json_data), verify=False)
    except requests.ConnectionError, e:
        print "Connection failure : " + str(e)
        print "Verification with InsightFinder credentials Failed"
        sys.exit(1)
    if response.status_code != 200:
        print "Response from server: "+str(response.status_code)
        print "Verification with InsightFinder credentials Failed"
        sys.exit(1)
    try:
        jsonResponse = response.json()
    except ValueError:
        print "Not a valid response from server"
        print "Verification with InsightFinder credentials Failed"
        sys.exit(1)
    return jsonResponse

if __name__ == '__main__':
    global projectName
    global userInsightfinder
    global licenseKey
    alldata = {}
    projectName, userInsightfinder, licenseKey = get_args()
    responseContent = sendData()
    #print responseContent
    if "success" not in responseContent:
        print "Verification of InsightFinder credentials Failed"
        sys.exit(1)
    if responseContent["success"] == False:
        try:
            print responseContent["message"]
            print "Verification of InsightFinder credentials Failed"
        except KeyError:
            print "Verification of InsightFinder credentials Failed"
        sys.exit(1)

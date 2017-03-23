#!/usr/bin/python

import sys
import time
import os
import getpass
import getopt
import argparse
import re
import paramiko
import socket
import Queue
import threading
import pickle
import subprocess
import json
import csv
from datetime import datetime
#from dateutil import parser

#serverUrl = 'http://localhost:8888'
serverUrl = 'https://agentdata-dot-insightfindergae.appspot.com'

def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]

def sshInstall(retry,hostname,hostMap):
    global user
    global password
    global userInsightfinder
    global licenseKey
    global samplingInterval
    global reportingInterval
    global agentType
    global projectName

    arguments = " -i "+projectName+" -u " + userInsightfinder + " -k " + licenseKey + " -s " + samplingInterval + " -r " + reportingInterval + " -t " + agentType + " -w " +serverUrl
    if retry == 0:
        print "Install Fail in", hostname
        q.task_done()
        return

    print "Start installing agent in", hostname, "..."
    try:
        s = paramiko.SSHClient()
        s.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        if os.path.isfile(password) == True:
            s.connect(hostname, username=user, key_filename = password, timeout=60)
        else:
            s.connect(hostname, username=user, password = password, timeout=60)
        transport = s.get_transport()
        session = transport.open_session()
        session.set_combine_stderr(True)
        session.get_pty()
        command = "[ -f /etc/cron.d/ifagent ] && echo 'File exist' || echo 'File does not exist'"
        session.exec_command(command)
        stdout = session.makefile('rb', -1)
        if stdout.read().strip(' \t\n\r') == 'File exist':
            s.close()
            hostMap[hostname] = 0
            print "Installation stopped in ", hostname
            q.task_done()
            return
        else:
            hostMap[hostname] = 1
            session = transport.open_session()
            session.set_combine_stderr(True)
            session.get_pty()
            nextcommand = "sudo rm -rf insightagent* InsightAgent* && \
            wget --no-check-certificate https://github.com/amurark/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz && \
            tar xzvf insightagent.tar.gz && \
            cd InsightAgent-master && deployment/checkpackages.sh && \
            deployment/install.sh "+ arguments + "\n"
            #print 'Command: ', command
            session.exec_command(nextcommand)
            stdin1 = session.makefile('wb', -1)
            stdout1 = session.makefile('rb', -1)
            stdin1.write(password+'\n')
            stdin1.flush()
            session.recv_exit_status() #wait for exec_command to finish
            s.close()
            print "Install Succeed in", hostname
            q.task_done()
            return
    except paramiko.SSHException, e:
        print "Invalid Username/Password for %s:"%hostname , e
        return sshInstall(retry-1,hostname,hostMap)
    except paramiko.AuthenticationException:
        print "Authentication failed for some reason in %s:"%hostname
        return sshInstall(retry-1,hostname,hostMap)
    except socket.error, e:
        print "Socket connection failed in %s:"%hostname, e
        return sshInstall(retry-1,hostname,hostMap)
    except:
        print "Unexpected error in %s:"%hostname
        return sshInstall(retry-1,hostname,hostMap)

def sshInstallHypervisor(retry,hostname):
    global user
    global password
    global userInsightfinder
    global licenseKey
    global samplingInterval
    global reportingInterval
    global agentType
    if retry == 0:
        print "Install Fail in", hostname
        q.task_done()
        return
    print "Start installing agent in", hostname, "..."
    try:
        s = paramiko.SSHClient()
        s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        if os.path.isfile(password) == True:
            s.connect(hostname, username=user, key_filename = password, timeout=60)
        else:
            s.connect(hostname, username=user, password = password, timeout=60)
        ftp = s.open_sftp()
        ftp.put('insightagent.tar.gz', 'insightagent.tar.gz')
        transport = s.get_transport()
        session = transport.open_session()
        session.set_combine_stderr(True)
        session.get_pty()
        session.exec_command("rm -rf InsightAgent*\n \
        tar xzvf insightagent.tar.gz\n \
        cd InsightAgent-master\n")
        stdin = session.makefile('wb', -1)
        stdout = session.makefile('rb', -1)
        stdin.write(password+'\n')
        stdin.flush()
        session.recv_exit_status() #wait for exec_command to finish
        if "IOError" in stdout.readlines():
             print "Not enough space in host"
             print "Install Failed in ",hostname
             s.close()
             return sshInstallHypervisor(retry-1,hostname)
        s.close()
        print "Install Succeed in", hostname
        q.task_done()
        return
    except paramiko.SSHException, e:
        print "Invalid Username/Password for %s:"%hostname , e
        return sshInstallHypervisor(retry-1,hostname)
    except paramiko.AuthenticationException:
        print "Authentication failed for some reason in %s:"%hostname
        return sshInstallHypervisor(retry-1,hostname)
    except socket.error, e:
        print "Socket connection failed in %s:"%hostname, e
        return sshInstallHypervisor(retry-1,hostname)
    except IOError,e :
        print "Not enough disk space in host"
        return sshInstallHypervisor(retry-1,hostname)
    except:
        print "Unexpected error in %s:"%hostname
        return sshInstallHypervisor(retry-1,hostname)



def get_args():
    parser = argparse.ArgumentParser(
        description='Script retrieves arguments for insightfinder agent.')
    parser.add_argument(
        '-n', '--USER_NAME_IN_HOST', type=str, help='User Name in Hosts', required=True)
    parser.add_argument(
        '-i', '--PROJECT_NAME', type=str, help='Project Name', required=True)
    parser.add_argument(
        '-u', '--USER_NAME_IN_INSIGHTFINDER', type=str, help='User Name in Insightfinder', required=True)
    parser.add_argument(
        '-k', '--LICENSE_KEY', type=str, help='License key for the user', required=True)
    parser.add_argument(
        '-s', '--SAMPLING_INTERVAL_MINUTE', type=str, help='Sampling Interval Minutes', required=True)
    parser.add_argument(
        '-r', '--REPORTING_INTERVAL_MINUTE', type=str, help='Reporting Interval Minutes', required=True)
    parser.add_argument(
        '-t', '--AGENT_TYPE', type=str, help='Agent type: proc or cadvisor or docker_remote_api or cgroup or daemonset or elasticsearch or collectd or hypervisor or ec2monitoring', choices=['proc', 'cadvisor', 'docker_remote_api', 'cgroup', 'daemonset', 'elasticsearch', 'collectd', 'hypervisor', 'ec2monitoring'],required=True)
    parser.add_argument(
        '-p', '--PASSWORD', type=str, help='Password for hosts', required=True)
    parser.add_argument(
        '-w', '--SERVER_URL', type=str, help='Server URL for InsightFinder', required=False)
    parser.add_argument(
        '-d', '--DIRECTORY', type=str, help='Home path', required=True)
    args = parser.parse_args()
    user = args.USER_NAME_IN_HOST
    userInsightfinder = args.USER_NAME_IN_INSIGHTFINDER
    licenseKey = args.LICENSE_KEY
    samplingInterval = args.SAMPLING_INTERVAL_MINUTE
    reportingInterval = args.REPORTING_INTERVAL_MINUTE
    agentType = args.AGENT_TYPE
    password = args.PASSWORD
    projectName = args.PROJECT_NAME
    homepath = args.DIRECTORY
    global serverUrl
    if args.SERVER_URL != None:
        serverUrl = args.SERVER_URL
    return user, projectName, userInsightfinder, licenseKey, samplingInterval, reportingInterval, agentType, password, homepath


if __name__ == '__main__':
    global user
    global password
    global hostfile
    global userInsightfinder
    global licenseKey
    global samplingInterval
    global reportingInterval
    global agentType
    global projectName
    global newInstances
    #File containing list of instances the agent is installed on. The file doesn't exit the first time the agent runs.
    jsonFile="instancesMetaData.json"
    #File containing blacklisted instances.
    excludeListFile="excludeList.csv"
    user, projectName, userInsightfinder, licenseKey, samplingInterval, reportingInterval, agentType, password, homepath = get_args()
    q = Queue.Queue()
    newInstances = []
    try:
        #Data to be sent with the POST request to fetch list of instances associated with the project.
        dataString = "projectName="+projectName+"&userName="+userInsightfinder+"&licenseKey="+licenseKey
        #URL for POST request
        url = serverUrl + "/api/v1/instanceMetaData"
        print "url", url
        print "dataString", dataString
        #Subprocess to run the CURL command for POST reqest.
        proc = subprocess.Popen(['curl -s --data \''+ dataString +'\' '+url], stdout=subprocess.PIPE, shell=True)
        #Get the ouput data and err data.
        (out,err) = proc.communicate()
        print 'Output', out
        output = json.loads(out)
        #If the output doesn't create success field, exit because of error in POST.
        if not output["success"]:
            print "Error: " + output["message"]
            sys.exit(output["message"])

        #Get the dictionary of instances from the output.
        instances = output["data"]
        #This will hold the list of allowed instances, by eliminating the existing instances and the blacklisted instances.
        allowed_instances = {}
        self_ip = get_ip_address()
        #If the instance has the flag 'AutoDeployInsightAgent' set to False, then ignore the instance for auto agent install.
        for key in instances:
            if 'AutoDeployInsightAgent' in instances[key] and instances[key]['AutoDeployInsightAgent'] == False:
                continue
            else:
                if str('privateip' in instances[key] and instances[key]['privateip']) == str(self_ip):
                    continue
                else:
                    allowed_instances[key] = instances[key]
        newInstances = {}
        oldInstances = {}
        excludeList = []
        newKeys = []
        print "Checking Path: ",os.path.join(homepath,excludeListFile)

        #Also, check the exclude list for blacklisted instances and create a list of excluded instances.
        if os.path.exists(os.path.join(homepath,excludeListFile)):
            with open(os.path.join(homepath,excludeListFile), 'rb') as f:
                reader = csv.reader(f)
                for row in reader:
                    excludeList.append(row[0])
                    print "Added Exclude List: ", row[0]

        print "Checking Path: ",os.path.join(homepath,jsonFile)
        #If the file doesn't exist, then all allowed instances should be included for agent installation
        if not os.path.exists(os.path.join(homepath,jsonFile)):
            newInstances = allowed_instances
            newKeys = allowed_instances.keys()
        #If the file exists, remove the instances which already exist in the file.
        else:
            oldInstances = json.load(open(os.path.join(homepath,jsonFile), "rb" ))
            #Get the final list of instances.
            newKeys = set(allowed_instances.keys()) - set(oldInstances.keys())
            #If the instance is in oldInstances list then, check the time difference between them, if the instances are more than 1 day old then put them in the newlist again.
            """
            for instance in allowed_instances:
                if instance in oldInstances:
                    print "Instance", instance
                    print "DateTimeDiff: ", datetime.now()-parser.parse(oldInstances[instance]["lastSeen"])
                    if (datetime.now()-parser.parse(oldInstances[instance]["lastSeen"])).days > 0:
                        newInstances[instance]=oldInstances[instance]
                        newInstances[instance]["lastSeen"]=str(datetime.now())
            """
        for newKey in newKeys:
            newInstances[newKey]=allowed_instances[newKey]
            newInstances[newKey]["agentExist"] = False
            """
            newInstances[newKey]["lastSeen"]=str(datetime.now())
            """

        #Deploy on all the instances except the blacklisted ones.
        for instanceKey in newInstances:
                host = newInstances[instanceKey]["privateip"]#Changed from publicIp
                if host in excludeList:
                    continue
                print host
                #q.put(host)
        hostMap = {}
        while q.empty() != True:
            host = q.get()
            if agentType == "hypervisor":
                t = threading.Thread(target=sshInstallHypervisor, args=(3,host,))
            else:
                t = threading.Thread(target=sshInstall, args=(3,host,hostMap))
            t.daemon = True
            t.start()
        q.join()
        #Update the json file, if an agent exists on certain host machines, then update flag accordingly.
        updatedInstances = oldInstances.copy()
        updatedInstances.update(newInstances)
        for key in updatedInstances.keys():
            ip = str(updatedInstances[key]['privateip'])
            if ip in hostMap and hostMap[ip] == 0:
                updatedInstances[key]['agentExist'] = True
        json.dump(updatedInstances,open(os.path.join(homepath,jsonFile), "wb" ))

    except (KeyboardInterrupt, SystemExit):
        print "Keyboard Interrupt!!"
        sys.exit()
    except IOError as e:
        print "I/O error({0}): {1}: {2}".format(e.errno, e.strerror, e.filename)
        sys.exit()

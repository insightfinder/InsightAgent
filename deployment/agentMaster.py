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
from dateutil import parser

#serverUrl = 'http://localhost:8888'
serverUrl = 'https://agentdata-dot-insightfindergae.appspot.com'

def sshInstall(retry,hostname):
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
        command = "sudo rm -rf insightagent* InsightAgent* && \
        wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz && \
        tar xzvf insightagent.tar.gz && \
        cd InsightAgent-master && deployment/checkpackages.sh && \
        deployment/install.sh "+ arguments + "\n"
        #print 'Command: ', command
        session.exec_command(command)
        stdin = session.makefile('wb', -1)
        stdout = session.makefile('rb', -1)
        stdin.write(password+'\n')
        stdin.flush()
        session.recv_exit_status() #wait for exec_command to finish
        s.close()
        print "Install Succeed in", hostname
        q.task_done()
        return
    except paramiko.SSHException, e:
        print "Invalid Username/Password for %s:"%hostname , e
        return sshInstall(retry-1,hostname)
    except paramiko.AuthenticationException:
        print "Authentication failed for some reason in %s:"%hostname
        return sshInstall(retry-1,hostname)
    except socket.error, e:
        print "Socket connection failed in %s:"%hostname, e
        return sshInstall(retry-1,hostname)
    except:
        print "Unexpected error in %s:"%hostname

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
    args = parser.parse_args()
    user = args.USER_NAME_IN_HOST
    userInsightfinder = args.USER_NAME_IN_INSIGHTFINDER
    licenseKey = args.LICENSE_KEY
    samplingInterval = args.SAMPLING_INTERVAL_MINUTE
    reportingInterval = args.REPORTING_INTERVAL_MINUTE
    agentType = args.AGENT_TYPE
    password = args.PASSWORD
    projectName = args.PROJECT_NAME
    global serverUrl
    if args.SERVER_URL != None:
        serverUrl = args.SERVER_URL
    return user, projectName, userInsightfinder, licenseKey, samplingInterval, reportingInterval, agentType, password


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
    jsonFile="instancesMetaData.json"
    excludeListFile="excludeList.csv"
    user, projectName, userInsightfinder, licenseKey, samplingInterval, reportingInterval, agentType, password = get_args()
    q = Queue.Queue()
    newInstances = []
    try:
        dataString = "projectName="+projectName+"&userName="+userInsightfinder+"&licenseKey="+licenseKey
        url = serverUrl + "/api/v1/instanceMetaData"
        print "url", url
        print "dataString", dataString
        proc = subprocess.Popen(['curl --data \''+ dataString +'\' '+url], stdout=subprocess.PIPE, shell=True)
        (out,err) = proc.communicate()
        print 'Output', out
        output = json.loads(out)   
        if not output["success"]:
            print "Error: " + output["message"]
            sys.exit(output["message"])
        instances = output["data"]
        newInstances = {} 
        oldInstances = {}
        excludeList = []
        newKeys = []
        print "Checking Path: ",os.path.join(os.getcwd(),excludeListFile)
        if os.path.exists(os.path.join(os.getcwd(),excludeListFile)):
            with open(os.path.join(os.getcwd(),excludeListFile), 'rb') as f:
                reader = csv.reader(f)
                for row in reader:
                    excludeList.append(row[0])
                    print "Added Exclude List: ", row[0]

        print "Checking Path: ",os.path.join(os.getcwd(),jsonFile)
        if not os.path.exists(os.path.join(os.getcwd(),jsonFile)):
            newInstances = instances
            newKeys = instances.keys()
        else:
            oldInstances = json.load(open(os.path.join(os.getcwd(),jsonFile), "rb" ))
            newKeys = set(instances.keys()) - set(oldInstances.keys())
            for instance in instances:
                if instance in oldInstances:
                    print "Instance", instance
                    print "DateTimeDiff: ", datetime.now()-parser.parse(oldInstances[instance]["lastSeen"])
                    if (datetime.now()-parser.parse(oldInstances[instance]["lastSeen"])).days > 0:
                        newInstances[instance]=oldInstances[instance]
                        newInstances[instance]["lastSeen"]=str(datetime.now())  
                              
        for newKey in newKeys:
            newInstances[newKey]=instances[newKey]
            newInstances[newKey]["lastSeen"]=str(datetime.now())



                
        print 'New Instances: ', newInstances   
        updatedInstances = oldInstances.copy()
        updatedInstances.update(newInstances) 
        json.dump(updatedInstances,open(os.path.join(os.getcwd(),jsonFile), "wb" ))
        
        for instanceKey in newInstances:
                host = newInstances[instanceKey]["publicIp"]
                if host in excludeList:
                    continue;
                q.put(host)
        
        while q.empty() != True:
            host = q.get()
            if agentType == "hypervisor":
                t = threading.Thread(target=sshInstallHypervisor, args=(3,host,))
            else:
                t = threading.Thread(target=sshInstall, args=(3,host,))
            t.daemon = True
            t.start()
        q.join()

    except (KeyboardInterrupt, SystemExit):
        print "Keyboard Interrupt!!"
        sys.exit()
    except IOError as e:
        print "I/O error({0}): {1}: {2}".format(e.errno, e.strerror, e.filename)
        sys.exit()

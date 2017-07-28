# Install Ansible
#python install_anshible.py
#Take lots of input parameters - write the basic host file.
###Create Cron job -  This cron job will call updatehosts.py (with a few parameters)
import argparse
import time
import subprocess
import json
import os
import pickle
import sys

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
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '-p', '--PASSWORD', type=str, help='Password for hosts', required=False)
    group.add_argument(
        '-q', '--PRIVATE_KEY_PATH', type=str, help='Private ket for hosts', required=False)
    parser.add_argument(
        '-w', '--SERVER_URL', type=str, help='Server URL for InsightFinder', required=True)
    parser.add_argument(
        '-d', '--DIRECTORY', type=str, help='Home path', required=True)
    parser.add_argument(
        '-f', '--FORCE_INSTALL', type=str, help='Force Install', required=False)
    args = parser.parse_args()
    userNameHost = args.USER_NAME_IN_HOST
    userInsightfinder = args.USER_NAME_IN_INSIGHTFINDER
    licenseKey = args.LICENSE_KEY
    samplingInterval = args.SAMPLING_INTERVAL_MINUTE
    reportingInterval = args.REPORTING_INTERVAL_MINUTE
    agentType = args.AGENT_TYPE
    password = args.PASSWORD
    privateKey = args.PRIVATE_KEY_PATH
    projectName = args.PROJECT_NAME
    homepath = args.DIRECTORY
    forceInstall = args.FORCE_INSTALL
    global serverUrl
    if args.SERVER_URL != None:
        serverUrl = args.SERVER_URL
    return userNameHost, projectName, userInsightfinder, licenseKey, samplingInterval, reportingInterval, agentType, password, privateKey, homepath, forceInstall

def computeInstanceList():
    global projectName
    global newInstances
    global homepath
    global oldInstancesFile
    global oldInstances
    #File containing list of instances the agent is installed on. The file doesn't exit the first time the agent runs.
    oldInstancesFile="instancesMetaData.txt"
    #File containing blacklisted instances.
    excludeListFile="excludeList.txt"
    print "FORCE_INSTALL flag: ",forceInstall
    newInstances = set()
    oldInstances = set()
    allInstances = set()
    excludedInstances = set()
    try:
        #Data to be sent with the POST request to fetch list of instances associated with the project.
        dataString = "projectName="+projectName+"&userName="+userInsightfinder+"&licenseKey="+licenseKey
        #URL for POST request
        url = serverUrl + "/api/v1/instanceMetaData"
        print "Running at time: ", time.strftime('%X %x %Z')
        print "Rest URL", url
        #Subprocess to run the CURL command for POST reqest.
        proc = subprocess.Popen(['curl -s --data \''+ dataString +'\' '+url], stdout=subprocess.PIPE, shell=True)
        #Get the ouput data and err data.
        (out,err) = proc.communicate()
        output = json.loads(out)
        
        #If the output doesn't create success field, exit because of error in POST.
        if not output["success"]:
            print "Error: " + output["message"]
            sys.exit(output["message"])
        
        
        #Get the dictionary of instances from the output.
        instances = output["data"]
        #This will hold the list of allowed instances, by eliminating the existing instances and the blacklisted instances.
        allowed_instances = {}
        ###
        #If the instance has the flag 'AutoDeployInsightAgent' set to False, then ignore the instance for auto agent install.
        print "EC2 Instances:"
        for key in instances:
            if 'AutoDeployInsightAgent' in instances[key] and instances[key]['AutoDeployInsightAgent'] == False:
                continue
            else:
                if 'privateip' in instances[key] and instances[key]['privateip']:
                    print instances[key]['privateip']
                    allInstances.add(instances[key]['privateip'])
        
        print "Checking Path: ",os.path.join(homepath,excludeListFile)
        if os.path.exists(os.path.join(homepath,excludeListFile)):
            excludedInstances = set(line.strip() for line in open(os.path.join(homepath,excludeListFile)))

        print "Checking Path: ",os.path.join(homepath,oldInstancesFile)
        if os.path.exists(os.path.join(homepath,oldInstancesFile)):
            #Loading Old Instance List
            oldInstances = pickle.load(open(os.path.join(homepath,oldInstancesFile)))
        newInstances = allInstances - oldInstances - excludedInstances
    except ValueError:
        print 'Decoding JSON has failed'
        sys.exit()
    except (KeyboardInterrupt, SystemExit):
        print "Keyboard Interrupt!!"
        sys.exit()
    except IOError as e:
        print "I/O error({0}): {1}: {2}".format(e.errno, e.strerror, e.filename)
        sys.exit()


def writeInventoryFile():
    global userNameHost
    global oldInstances
    global password
    global userInsightfinder
    global licenseKey
    global samplingInterval
    global reportingInterval
    global agentType
    global projectName
    global newInstances
    global homepath
    global privateKey
    global forceInstall
    f = open(os.path.join(homepath,"inventory"), 'w')
    f.write('[nodes]\n')
    f.write('\n'.join(newInstances))
    f.write('\n\n[nodes:vars]\n')
    f.write('ansible_user=%s\n'%userNameHost)
    if(privateKey == ""):
        f.write('ansible_ssh_pass=%s\n'%password)
    else:
        f.write('ansible_ssh_private_key_file=%s\n'%privateKey)
    f.write('\n[all:vars]\n')
    f.write('ifUserName=%s\n'%userInsightfinder)
    f.write('ifProjectName=%s\n'%projectName)
    f.write('ifLicenseKey=%s\n'%licenseKey)
    f.write('ifSamplingInterval=%s\n'%samplingInterval)
    f.write('ifReportingInterval=%s\n'%reportingInterval)
    f.write('ifAgent=%s\n'%agentType)
    f.write('ifReportingUrl=%s\n'%serverUrl)
    f.close() 


if __name__ == '__main__':
    global userNameHost
    global oldInstancesFile
    global password
    global userInsightfinder
    global licenseKey
    global samplingInterval
    global reportingInterval
    global agentType
    global projectName
    global newInstances
    global homepath
    global privateKey
    global forceInstall
    userNameHost, projectName, userInsightfinder, licenseKey, samplingInterval, reportingInterval, agentType, password, privateKey, homepath, forceInstall = get_args()
    computeInstanceList()
    writeInventoryFile()
    #Merging the old instances and the new instances!
    oldInstances = oldInstances | newInstances
    print "Agent will be installed on following hosts"
    print '\n'.join(newInstances)
    #Executing the playbook
    proc = subprocess.Popen(['ansible-playbook insightagent.yaml'], stdout=subprocess.PIPE,cwd=homepath, shell=True)
    (out,err) = proc.communicate()
    print "\nAnsible Output\n"
    print out
    print >> sys.stderr, "Ansible Error"
    print >> sys.stderr, err
    if(proc.returncode==0):
        pickle.dump( oldInstances, open(os.path.join(homepath,oldInstancesFile), "wb" ))
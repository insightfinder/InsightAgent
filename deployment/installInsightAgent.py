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

def sshInstall(retry,hostname):
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
        transport = s.get_transport()
        session = transport.open_session()
        session.set_combine_stderr(True)
        session.get_pty()
        session.exec_command("sudo rm -rf insightagent* InsightAgent*\n \
        wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz\n \
        tar xzvf insightagent.tar.gz\n \
        cd InsightAgent-master && deployment/checkpackages.sh\n")
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
        '-u', '--USER_NAME_IN_INSIGHTFINDER', type=str, help='User Name in Insightfinder', required=True)
    parser.add_argument(
        '-k', '--LICENSE_KEY', type=str, help='License key for the user', required=True)
    parser.add_argument(
        '-s', '--SAMPLING_INTERVAL_MINUTE', type=str, help='Sampling Interval Minutes', required=True)
    parser.add_argument(
        '-r', '--REPORTING_INTERVAL_MINUTE', type=str, help='Reporting Interval Minutes', required=True)
    parser.add_argument(
        '-t', '--AGENT_TYPE', type=str, help='Agent type: proc or cadvisor or docker_remote_api or cgroup or daemonset or elasticsearch or collectd or hypervisor', choices=['proc', 'cadvisor', 'docker_remote_api', 'cgroup', 'daemonset', 'elasticsearch', 'collectd', 'hypervisor'],required=True)
    parser.add_argument(
        '-p', '--PASSWORD', type=str, help='Password for hosts', required=True)
    args = parser.parse_args()
    user = args.USER_NAME_IN_HOST
    userInsightfinder = args.USER_NAME_IN_INSIGHTFINDER
    licenseKey = args.LICENSE_KEY
    samplingInterval = args.SAMPLING_INTERVAL_MINUTE
    reportingInterval = args.REPORTING_INTERVAL_MINUTE
    agentType = args.AGENT_TYPE
    password = args.PASSWORD
    return user, userInsightfinder, licenseKey, samplingInterval, reportingInterval, agentType, password


if __name__ == '__main__':
    global user
    global password
    global hostfile
    global userInsightfinder
    global licenseKey
    global samplingInterval
    global reportingInterval
    global agentType
    hostfile="hostlist.txt"
    user, userInsightfinder, licenseKey, samplingInterval, reportingInterval, agentType, password = get_args()
    q = Queue.Queue()
    try:
        with open(os.getcwd()+"/"+hostfile, 'rb') as f:
            while True:
                line = f.readline()
                if line:
                    host=line.split("\n")[0]
                    q.put(host)
                else:
                    break
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

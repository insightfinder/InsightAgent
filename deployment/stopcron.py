#!/usr/bin/python

import argparse
import getpass
import os
import sys
import paramiko
import socket
import Queue
import threading
import time

def sshStopCron(retry,hostname):
    global user
    global password
    if retry == 0:
        print "Stop Cron Failed in", hostname
        q.task_done()
        return
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
        command = "sudo mv /etc/cron.d/ifagent InsightAgent-master/ifagent."+time.strftime("%Y%m%d%H%M%S")+"\n"
        session.exec_command(command)
        stdin = session.makefile('wb', -1)
        stdout = session.makefile('rb', -1)
        stdin.write(password+'\n')
        stdin.flush()
        session.recv_exit_status() #wait for exec_command to finish
        s.close()
        print "Stopped Cron in ", hostname
        q.task_done()
        return
    except paramiko.SSHException, e:
        print "Invalid Username/Password for %s:"%hostname , e
        return sshStopCron(retry-1,hostname)
    except paramiko.AuthenticationException:
        print "Authentication failed for some reason in %s:"%hostname
        return sshStopCron(retry-1,hostname)
    except socket.error, e:
        print "Socket connection failed in %s:"%hostname, e
        return sshStopCron(retry-1,hostname)

def get_args():
    parser = argparse.ArgumentParser(
        description='Script retrieves arguments for stopping insightfinder agent.')
    parser.add_argument(
        '-n', '--USER_NAME_IN_HOST', type=str, help='User Name in Hosts', required=True)
    parser.add_argument(
        '-p', '--PASSWORD', type=str, help='Password for hosts', required=True)
    args = parser.parse_args()
    user = args.USER_NAME_IN_HOST
    password = args.PASSWORD
    return user, password

if __name__ == '__main__':
    hostfile="hostlist.txt"
    q = Queue.Queue()
    user, password = get_args()

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
                t = threading.Thread(target=sshStopCron, args=(3,host,))
                t.daemon = True
                t.start()
            q.join()
    except (KeyboardInterrupt, SystemExit):
        print "Keyboard Interrupt!!"
        sys.exit()
    except IOError as e:
        print "I/O error({0}): {1}: {2}".format(e.errno, e.strerror, e.filename)
        sys.exit()

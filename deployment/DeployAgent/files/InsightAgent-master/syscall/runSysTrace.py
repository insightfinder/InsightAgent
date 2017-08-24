#!/usr/bin/python

import threading
import argparse
import getpass
import subprocess
import os
import sys
import time
import datetime

def get_args():
    parser = argparse.ArgumentParser(description='Script retrieves arguments for insightfinder system call tracing.')
    parser.add_argument('-d', '--HOME_DIR', type=str, help='The HOME directory of Insight syscall trace', required=True)
    args = parser.parse_args()
    homepath = args.HOME_DIR
    return homepath


class SysTraceThreads(threading.Thread):
    def __init__(self,command):
        super(SysTraceThreads, self).__init__()
        self.command=command
    
    def run(self):
        global homepath
        proc = subprocess.Popen(self.command, cwd=homepath, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out,err) = proc.communicate()
        print out
        if "failed" in str(err) or "ERROR" in str(err):
            print "System call tracing cannot be executed."
            sys.exit()


def updateFile(filepath, filename, newSession):
    global homepath
    file = os.path.join(homepath,filepath,filename)
    oldSession = "null"
    currentSession = "null"
    if (os.stat(file).st_size == 0):
        open(os.path.join(file), 'a+').writelines(newSession+"\n")
    else:
        lines = open(file).readlines()
        if len(lines) == 1:        
            currentSession = lines[0].rstrip('\n')
            lines.append(newSession+'\n')
            open(os.path.join(file), 'w+').writelines(lines[0:])
        else:
            lines.append(newSession+'\n')
            oldSession = lines[0].rstrip('\n')
            currentSession = lines[1].rstrip('\n')
            open(os.path.join(file), 'w+').writelines(lines[1:])
    return oldSession, currentSession


def main():
    global homepath
    newSession = str(int(round(time.time() * 1000)))
    oldSession, currentSession = updateFile("log","SessionID.txt", newSession)
    command = "sudo "+os.path.join(homepath,"updateSysCall.sh")+" -o "+oldSession+" -c "+currentSession+" -n "+newSession
    #print command
    thread1 = SysTraceThreads(command)
    thread1.start()
    thread1.join()

if __name__ == '__main__':
    global homepath
    homepath = get_args()
    main()





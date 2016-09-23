#!/usr/bin/python

import threading
import argparse
import getpass
import subprocess
import os
import sys
import time


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
    open(os.path.join(file), 'a+').writelines(newSession+"\n")
    
def deleteFile(filepath, filename):
    global homepath
    file = os.path.join(homepath,filepath,filename)
    if os.path.exists(file):
        os.remove(file)

def main():
    global homepath
    deleteFile("log","SessionID.txt")
    newSession = str(int(round(time.time() * 1000)))
    print newSession
    updateFile("log","SessionID.txt", newSession)
    command="sudo "+os.path.join(homepath,"startSysCall.sh")+" -i "+newSession 
    thread1 = SysTraceThreads(command)
    thread1.start()
    time.sleep(60) #sleep for 60 seconds
    newSession = str(int(round(time.time() * 1000)))
    print newSession
    updateFile("log","SessionID.txt", newSession)
    command="sudo "+os.path.join(homepath,"startSysCall.sh")+" -i "+newSession
    thread2 = SysTraceThreads(command)
    thread2.start()
    thread1.join()
    thread2.join()  

if __name__ == '__main__':
    global homepath
    homepath = get_args()
    main()





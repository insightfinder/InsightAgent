#!/usr/bin/python 
import SocketServer
import socket
import threading
import sys
import os
import shlex
import subprocess
import Queue
import platform
import time
import argparse

#uploadPort=4445
downloadPort=4445

def get_args():
    parser = argparse.ArgumentParser(description='Script retrieves arguments for insightfinder system call tracing.')
    parser.add_argument('-d', '--HOME_DIR', type=str, help='The HOME directory of Insight syscall trace', required=True)
    args = parser.parse_args()
    homepath = args.HOME_DIR
    return homepath

class prepareThreads(threading.Thread):
    def __init__(self,command):
        super(prepareThreads, self).__init__()
        self.command=command

    def run(self):
        global homepath
        proc = subprocess.Popen(self.command, cwd=homepath, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out,err) = proc.communicate()
        if "failed" in str(err) or "ERROR" in str(err):
            print "Running PerfCompass failed."
            sys.exit()


def process(syscallFile, processName):
    global homepath
    command = os.path.join(homepath,"perfCompass/start.sh") + " -d " + homepath+"/perfCompass" + " -F " + syscallFile + " -N " + processName
    print command
    thread = prepareThreads(command)
    thread.start()
    thread.join()

        
def requestFile(msg,sysTrace_start,clientHost,clientPort):
    global homepath
    global downloadPort
    try:
        s=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        s.bind(('',int(downloadPort)))
        s.connect((clientHost,int(clientPort)))
        s.send(msg)
        reply = s.recv(1024)  # limit reply to 16K
        s.send("StartSending")
        exist=shlex.split(reply)
        fname="syscall_"+sysTrace_start+".log_segmented_withContext.log"
        if str(exist[1])=='200':
            print("Output Response from "+str(clientHost)+":"+str(clientPort)+":")
            print ("Receiving file...")
            f=open(homepath+"/data/"+fname,'wb')
            data=s.recv(1024)
            try:
                while(data):
                    f.write(data)
                    s.settimeout(10)
                    data=s.recv(1024)
            except socket.timeout:
                f.close()
                print("File Downloaded!")
            rel = 0
        else:
            print("Output Response from "+str(clientHost)+":"+str(clientPort)+":")
            print ("SYSCALL-TRACE/1.0 404 NOT FOUND")
            rel = -1
        s.close()
        return homepath+"/data/"+fname
    except socket.error:
        OS = platform.system()+" "+platform.release()
        Time = time.strftime("%a, %d %b %Y %X %Z", time.localtime())
        msg="SYSCALL-TRACE/1.0 400 Bad Request\n"\
            "Date: "+Time+"\n"
        print(msg)
        rel = -2
    return "error"
        

def requestThread():
    sysTrace_start = str(int(round(time.time() * 1000)))
    procname = "apache,apache2,httpd"
    msg="GET " + sysTrace_start + " " + procname +" SYSCALL-TRACE/1.0"+"\n"\
        "Host: "+socket.gethostname()+"\n"
    #clientHost="cairo.csc.ncsu.edu"
    print msg
    clientHost="52.90.241.26"
    clientPort=4445

    try:
        fname = requestFile(msg,sysTrace_start,clientHost,clientPort)
        if fname != "error":
            print "Starting processing using PerfCompass..."
            process(fname, procname)   
    except socket.error:
        Time = time.strftime("%a, %d %b %Y %X %Z", time.localtime())
        msg="SYSCALL-TRACE/1.0 400 Bad Request\n"\
            "Date: "+Time+"\n"
        print(msg)

 


def main():
    thread1=threading.Thread(target=requestThread)
    thread1.daemon=True
    thread1.start()
    #thread1.join()
    try:
        while 1:
            time.sleep(.1)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__=="__main__":
    global homepath
    homepath = get_args()
    main()

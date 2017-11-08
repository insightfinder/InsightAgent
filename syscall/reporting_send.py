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
import datetime
import argparse
import traceback

uploadPort=4445
#syscallList=list()
Timer=0
TimerInterval = 15 * 60 * 1000 #15 mins
serverUrl = 'https://agent-data.insightfinder.com'

def get_args():
    parser = argparse.ArgumentParser(description='Script retrieves arguments for insightfinder system call tracing.')
    parser.add_argument('-d', '--HOME_DIR', type=str, help='The HOME directory of Insight syscall trace', required=True)
    parser.add_argument('-D', '--ROOT_DIR', type=str, help='The Root directory of Insight agent', required=True)
    parser.add_argument('-w', '--SERVER_URL', type=str, help='URL of the insightfinder Server', required=False)
    args = parser.parse_args()
    homepath = args.HOME_DIR
    rootpath = args.ROOT_DIR
    global serverUrl
    if args.SERVER_URL != None:
        serverUrl = args.SERVER_URL
    return homepath, rootpath

def checkPrivilege():
    euid = os.geteuid()
    if euid != 0:
        args = ['sudo', sys.executable] + sys.argv + [os.environ]
        os.execlpe('sudo', *args)

class prepareThreads(threading.Thread):
    def __init__(self,command,path):
        super(prepareThreads, self).__init__()
        self.command=command
        self.path=path

    def run(self):
        global homepath
        global rootpath
        proc = subprocess.Popen(self.command, cwd=self.path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out,err) = proc.communicate()
        if "failed" in str(err) or "ERROR" in str(err):
            print "Preparing System call tracing logs failed."
            sys.exit()
        print out
 

def sendFile(self):
    global homepath
    global rootpath
    global Timer
    global TimerInterval
    request = self.recv(1024)
    print str(datetime.datetime.now())
    print request
    sysTrace=shlex.split(request)
    msgType = sysTrace[0]
    sysTrace_timestamp = sysTrace[1]
    procname = sysTrace[2]
    if msgType != "GET":
        return
    current = int(round(time.time() * 1000))
    if Timer == 0:
        Timer = current
    else:
        if current - Timer < TimerInterval:
            print "Two continious msg interval is " + str(current - Timer) + "ms < " + str(TimerInterval) + "ms"
            return
    os.chdir(homepath+"/buffer")
    buffers = list()
    for files in os.listdir("."):
        if files.startswith("buffer_"):
            buffers.append(files.split('buffer_')[1])
    buffers.sort()
    if int(sysTrace_timestamp) <= int(buffers[0]):
        response="SYSCALL-TRACE/1.0 404 Not Found\n"
        print response
        #self.send(response)
    else:
        Timer = current
        command = "sudo " + homepath + "/fetchSysCall.sh" + " -i " + buffers[0]
        print command
        thread = prepareThreads(command,homepath)
        thread.start()
        thread.join()
        filename="syscall_" + buffers[0] + ".log"
        #The only thing matters here is that we don't know the procname
        #command = "sudo python " + homepath + "/preProcessing.py" + " -d " + homepath + " -p " + procname + " -f " + filename
        #print command
        #thread = prepareThreads(command,homepath)
        #thread.start()
        #thread.join()

        fnameSeg = filename
        #fnameSeg = filename + "_segmented_withContext.log"
        fname = homepath + "/data/" + fnameSeg
        
        command = "tar zcvf " + homepath + "/data/" + fnameSeg + ".tar.gz " + homepath + "/data/" + fnameSeg
        print command
        thread = prepareThreads(command,homepath)
        thread.start()
        thread.join()

        command = "cd " + rootpath +" && unset http_proxy https_proxy && python common/reportBinary.py -f syscall/data/" + fnameSeg + ".tar.gz -m binaryFileReplay -T 1 -S " + sysTrace_timestamp + " -w "+serverUrl
        print command
        thread = prepareThreads(command,rootpath)
        thread.start()
        thread.join()
        
        #command = "sudo rm -rf " + homepath + "/data/" + filename + "*"
        #print command
        #thread = prepareThreads(command,homepath)
        #thread.start()
        #thread.join()


def acceptThread():       
    acceptor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)        
    acceptor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    acceptor.bind(('', int(uploadPort)))
    acceptor.listen(5)
        
    cur_thread=threading.current_thread()
    while True:            
        (clientSock,clientAddr)=acceptor.accept()
        print "====Output Request:"
        msg = "Connected to " + str(clientAddr[0]) + ":" + str(clientAddr[1])
        print msg
        thread3=threading.Thread(target=sendFile(clientSock))
        thread3.daemon=True
        thread3.start()
        #thread3.join()            
    acceptor.close()
    return


def main():
    thread1=threading.Thread(target=acceptThread)
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
    global rootpath
    checkPrivilege()
    homepath, rootpath = get_args()
    main()

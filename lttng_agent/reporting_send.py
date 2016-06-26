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

uploadPort=4445
#syscallList=list()

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
            print "Preparing System call tracing logs failed."
            sys.exit()



def prepareFile(sysTrace_start, sysTrace_end):
    #global syscallList
    global homepath
    #updateSyscallList()
    errno, startIndex, endIndex = findIndex(int(sysTrace_start), int(sysTrace_end))
    if errno == "Succeed":
        threads = list()
        catcommand="sudo cat "
        for i in range(startIndex, endIndex+1):
            command = "sudo "+os.path.join(homepath,"fetchSysCall.sh")+" -i "+syscallList[i]
            thread = prepareThreads(command)
            thread.start()
            threads.append(thread)
            catcommand += homepath+"/data/syscall_"+syscallList[i]+".log "
        print threads
        for i in range(0, endIndex-startIndex+1):
            print threads[i]
            threads[i].join()
            print threads[i]
        catcommand += "> "+homepath+"/data/syscall_"+syscallList[startIndex]+"_"+syscallList[endIndex]+".log "
        print catcommand
        catthread = prepareThreads(catcommand)
        catthread.start()
        catthread.join()
        return "syscall_"+syscallList[startIndex]+"_"+syscallList[endIndex]+".log"
    else:
        return errno
        
          

def sendFile(self):
    global homepath

    request=self.recv(1024)
    print (request)
    sysTrace=shlex.split(request)
    sysTrace_timestamp = sysTrace[1]
    procname = sysTrace[2]
    os.chdir(homepath+"/buffer")
    buffers = list()
    for files in os.listdir("."):
        if files.startswith("buffer_"):
            buffers.append(files.split('buffer_')[1])
    buffers.sort()
    if int(sysTrace_timestamp) <= int(buffers[0]):
        response="SYSCALL-TRACE/1.0 404 Not Found\n"
        print response
        self.send(response)
    else:
        command = "sudo "+os.path.join(homepath,"fetchSysCall.sh")+" -i "+buffers[0]
        thread = prepareThreads(command)
        thread.start()
        thread.join()
        filename="syscall_"+buffers[0]+".log"
        #The only thing matters here is that we don't know the procname
        command = "sudo python "+os.path.join(homepath,"preProcessing.py")+" -d "+homepath+" -p "+procname+" -f "+filename
        thread = prepareThreads(command)
        thread.start()
        thread.join()
        fname = homepath+"/data/"+filename+"_segmented_withContext.log"
        c1=['ls','-lrt']
        c2=['grep','-w',fname]
        c3=['tr','-s','" "']
        c4=['awk','{print $5}']
    
        p1=subprocess.Popen(c1,stdout=subprocess.PIPE)
        p2=subprocess.Popen(c2,stdin=p1.stdout,stdout=subprocess.PIPE)
        p3=subprocess.Popen(c3,stdin=p2.stdout,stdout=subprocess.PIPE)
        p4=subprocess.Popen(c4,stdin=p3.stdout,stdout=subprocess.PIPE)
        p3.stdout.close()
        fsize=p4.communicate()
        #print (fsize)
       
        Time = time.strftime("%a, %d %b %Y %X %Z", time.localtime()) 
        response="SYSCALL-TRACE/1.0 200 OK"+"\n"\
                 "Date: "+Time+"\n"\
                 "Content-Length: "+str(fsize[0])+"\n"
        self.send(response)
        
        stat = self.recv(1024)
        if (stat == "StartSending"):
            print "Sending file "+filename+"_segmented_withContext.log ..."
            f=open(fname,'rb')
            data = f.read(1024)
            while (data):
                if(self.send(data)):
                    data=f.read(1024)
            print("File Transfered!")
            f.close()

                   

def acceptThread():       
    acceptor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)        
    acceptor.bind(('', int(uploadPort)))
    acceptor.listen(5)
        
    cur_thread=threading.current_thread()
    while True:            
        (clientSock,clientAddr)=acceptor.accept()
        print("Output Request:")
        msg = "Connected to " + str(clientAddr[0]) + ":" + str(clientAddr[1])
        print (msg)
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
    homepath = get_args()
    main()

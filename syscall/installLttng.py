#!/usr/bin/python
import threading
import sys
import os
import subprocess
import platform
import time
import argparse
import traceback
from pkg_resources import parse_version

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


kernelMinVersion = "2.6.36"
ubuntuMinRelease = "12.04"
gccMinVersion = "3.2"
BabeltraceLatestStable = "babeltrace-1.3.2"
BabeltraceTar = BabeltraceLatestStable + ".tar.bz2"
BabeltraceHttp = "http://www.efficios.com/files/babeltrace/" + BabeltraceTar
LttngUSTLatest = "lttng-ust-2.8.1"
LttngUSTLatestTar = LttngUSTLatest + ".tar.bz2"
LttngUSTLatestHttp = "http://lttng.org/files/lttng-ust/" + LttngUSTLatestTar
LttngToolsLatest = "lttng-tools-2.8.0"
LttngToolsLatestTar = LttngToolsLatest + ".tar.bz2" 
LttngToolsLatestHttp = "http://lttng.org/files/lttng-tools/" + LttngToolsLatestTar
LttngModuleLatest = "lttng-modules-2.8.0"
LttngModuleLatestTar = LttngModuleLatest + ".tar.bz2"
LttngModuleLatestHttp = "http://lttng.org/files/lttng-modules/" + LttngModuleLatestTar
System = ""


dependenciesDebian = ["libc6", "libc6-dev", 
                      "libglib2.0-0", "libglib2.0-dev",
                      "uuid-dev",
                      #"libpopt-dev", #>=1.13
                      #"libxml2-dev", #>=2.7.6
                      #"liburcu", #>=0.8.0
                      "bison",
                      "flex",
                      "elfutils", "libelf-dev", "libdw-dev"]

dependenciesDebianWithVersion = [["libxml2-dev", "2.7.6"],
                                 ["libpopt-dev", "1.13"],
                                 ["liburcu-dev", "0.8.0"]]


dependenciesFedora = ["glibc", "glibc-devel",
                      "glib2", "glib2-devel",
                      "uuid-devel", "libuuid-devel"
                      "popt", "popt-devel"
                      "bison", "bison-devel",
                      "flex", "flex-devel",
                      "elfutils-libelf", "elfutils-libelf-devel",
                      "libdwarf", "libdwarf-devel"]


dependenciesAWS = ["glibc", "glibc-devel",
                   "glib2", "glib2-devel",
                   "uuid-devel", "libuuid-devel",
                   #"popt", "popt-devel",
                   #"libxml2-devel",
                   #"libtool",
                   "bison", "bison-devel",
                   "flex", "flex-devel",
                   "elfutils-libelf", "elfutils-libelf-devel",
                   "libdwarf", "libdwarf-devel",
                   "kernel-devel",
                   "git"]

dependenciesAWSWithVersion = [["popt", "1.13"],
                              ["popt-devel", "1.13"],
                              ["libxml2-devel", "2.7.6"],
                              ["libtool", "2.2"],
                              ["automake", "1.10"],
                              ["autoconf", "2.50"]]

packagesDebian = ["lttng-tools",
                  "lttng-modules-dkms",
                  "liblttng-ust-dev"]

def get_args():
    parser = argparse.ArgumentParser(description='Script retrieves arguments for insightfinder system call tracing.')
    parser.add_argument('-d', '--HOME_DIR', type=str, help='The HOME directory of Insight syscall trace', required=True)
    args = parser.parse_args()
    homepath = args.HOME_DIR
    return homepath


def checkPrivilege():
    euid = os.geteuid()
    if euid != 0:
        args = ['sudo', sys.executable] + sys.argv + [os.environ]
        os.execlpe('sudo', *args)


#run in default homepath dir
def runCommand(command):
    global homepath
    proc = subprocess.Popen(command, cwd=homepath, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (out,err) = proc.communicate()
    if "failed" in str(err) or "ERROR" in str(err) or "error" in str(err) or "Error" in str(err):
        print err
        print "ERROR: Intalling Packages FAILED."
        sys.exit()
    return out


#run in the specific dir
def runCommand1(command, path):
    proc = subprocess.Popen(command, cwd=path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (out,err) = proc.communicate()
    if "certs/signing_key.pem: No such file or directory" in err:
        pass
    elif "failed" in str(err) or "ERROR" in str(err) or "error" in str(err) or "Error" in str(err):
        print err
        print "ERROR: Intalling Packages FAILED."
        sys.exit()
    return out, err


#run with the input, "\r\n" and "y\n"
def runCommand2(command, input):
    global homepath
    proc = subprocess.Popen(command, cwd=homepath, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = proc.communicate(input)
    if "failed" in str(err) or "ERROR" in str(err) or "error" in str(err) or "Error" in str(err):
        print err
        print "ERROR: Intalling Packages FAILED."
        sys.exit()
    return out


#run with expecting error msg
def runCommandWithErrorMsg(command):
    global homepath
    proc = subprocess.Popen(command, cwd=homepath, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = proc.communicate()
    return out, err


def checkKernel():
    global kernelMinVersion
    print "Checking kernel version..."
    command = "uname -r"
    out = runCommand(command)
    #print out
    Kversion = out.split("\n")[0].split("-")[0]
    if parse_version(Kversion) < parse_version(kernelMinVersion): 
        print bcolors.FAIL + "ERROR: Kernal version is " + Kversion + " < " + kernelMinVersion + bcolors.ENDC
        print "Install LTTng FAILED."
        sys.exit()
    else:
        print "Kernel version is " + Kversion + " >= " + kernelMinVersion + bcolors.OKGREEN + " [OK]" + bcolors.ENDC


def checkKernelHeader():
    global System
    if "Ubuntu" in System or "ubuntu" in System:
        command = "ls /usr/src | grep $(uname -r)"
        out = runCommand(command)
        if "linux-headers" in out or "linux-image" in out:
            return
        else:
            command = "sudo apt-get install linux-headers-$(uname -r)"
            out = runCommand2(command, "y\n")


def checkDistribution():
    print "Checking Linux Distribution..."
    command = "cat /etc/*-release"
    out = runCommand(command)
    outSplit = out.split("\n")
    for i in range(0, len(outSplit)):
        if ("NAME" == outSplit[i].split("=")[0]):
            sysname = outSplit[i].split("=")[1]
    print "Linux Distribution Name is " + bcolors.HEADER + sysname + bcolors.ENDC
    return sysname


def checkRelease():
    global System
    print "Checking OS release number..."
    if "Ubuntu" in System or "ubuntu" in System:
        command = "cat /etc/*-release"
        out = runCommand(command)
        outSplit = out.split("\n")
        for i in range(0, len(outSplit)):
            if("DISTRIB_RELEASE" ==  outSplit[i].split("=")[0]):
                release = outSplit[i].split("=")[1]
                if parse_version(release) < parse_version(ubuntuMinRelease):
                    print bcolors.FAIL + "ERROR: OS release number is " + release + " < " + ubuntuMinRelease + bcolors.ENDC
                    print "Install LTTng FAILED."
                    sys.exit()
                print "OS release number is " + release + " >= " + ubuntuMinRelease + bcolors.OKGREEN + " [OK]" + bcolors.ENDC


def installPackageForDebian():
    global System
    checkRelease()
    print "Installing LTTng from package into " + System + "..."
    command = "sudo apt-add-repository ppa:lttng/ppa"
    print command
    runCommand2(command, "\r\n")
    command = "sudo apt-get update"
    print command
    runCommand(command)
    for i in range(0, len(packagesDebian)):
        command = "sudo apt-get install " + packagesDebian[i]
        print command
        runCommand2(command, "y\n")    


def checkInstalledSuccess(sysname):
    commands = ["lttng",
                "babeltrace"]
    for command in commands:
        out = runCommand("sudo " + command)
        if "No such file or directory" in out or "command not found" in out:
           print "install " + command + " FAILED"


def testBabeltrace():
    print "Testing babeltrace..."
    command = "babeltrace --help"
    out, err = runCommandWithErrorMsg(command)
    if "error" in err or "Error" in err or "ERROR" in err:
        print err.split("\n")[0]
        return "error"
    else:
        return "succeed"
        

def testLttngToolUST():
    print "Testing LTTng Tools and UST..."
    command = "lttng --help"
    out, err = runCommandWithErrorMsg(command)
    if "error" in err or "Error" in err or "ERROR" in err:
        print err.split("\n")[0]
        return "error"
    else:
        return "succeed"
 

def testLttngModule():
    print "Testing LTTng Module..."
    command = "./startSysCall.sh -i 1234"
    out, err = runCommandWithErrorMsg(command)
    if "error" in err or "Error" in err or "ERROR" in err:
        print err.split("\n")[0]
        command = "./forceStop.sh"
        runCommand(command)
        return "error"
    else:
        command = "./forceStop.sh"
        runCommand(command)
        return "succeed"



def checkDependenceforBabeltrace():
    global System
    print "Checking dependencies before installing Babeltrace..."
    checkGCC()
    #dependencies = ["libc6-dev libc6",
    #                "libglib2.0-0 libglib2.0-dev",
    #                "uuid-dev",
    #                "libpopt-dev libpopt0",
    #                "bison",
    #                "flex",
    #                "elfutils libelf-dev"]
    if "Ubuntu" in System or "ubuntu" in System:
        for dependency in dependenciesBabeltraceDebian:
            runCommand2("sudo apt-get install "+ dependency, "y\n")
    if "CentOS" in System or "centos" in System:
        for dependency in dependenciesBabeltraceFedora:
            runCommand2("sudo yum install "+ dependency, "y\n")


def checkGCC():
    global System
    global gccMinVersion
    print "Checking GCC version..."
    command = "gcc --version | grep -Eo '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}'"
    out = runCommand(command)
    gccVersion = out.split("\n")[0]
    if parse_version(gccVersion) < parse_version(gccMinVersion):
        if "Ubuntu" in System or "ubuntu" in System:
            command = "sudo apt-get install gcc"
        elif "Amazon Linux AMI" in System:
            command = "sudo yum install gcc"
        runCommand2(command, "y\n")
    command = "gcc --version | grep -Eo '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}'"
    gccVersion = out.split("\n")[0]
    if parse_version(gccVersion) < parse_version(gccMinVersion):
        print "Error: GCC version is " + gccVersion + " < " + gccMinVersion
        sys.exit()
    else:
        print "GCC version is " + gccVersion + " >= " + gccMinVersion + bcolors.OKGREEN + " [OK]" + bcolors.ENDC


def installURCUFromSource():
    global homepath
    print "Installing Userspace RCU from source..."
    command = "git clone https://github.com/urcu/userspace-rcu.git"
    print command
    runCommand(command)
    commands = ["./bootstrap",
                "./configure",
                "make",
                "make install",
                "ldconfig"]
    for command in commands:
        print command
        runCommand1(command, homepath+"/userspace-rcu")
    print "Installing Userspace RCU from source..." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC


def installBabeltraceFromSource():
    global homepath
    #checkDependenceforBabeltrace()
    print "Installing Babeltrace from source..."
    commands = ["wget " + BabeltraceHttp,
                "tar xjvf " + BabeltraceTar]
    for command in commands:
        print command
        runCommand(command)
    commands2 = ["./configure",
                "make",
                "make install",
                "ldconfig",
                "sudo mv /usr/bin/babeltrace /usr/bin/babeltrace.fromPackage", #make sure to replace the babeltrace 
                "sudo ln -s /usr/local/bin/babeltrace /usr/bin/babeltrace",    #installed from package
                "sudo mv /usr/bin/babeltrace-log /usr/bin/babeltrace-log.fromPackage",
                "sudo ln -s /usr/local/bin/babeltrace-log /usr/bin/babeltrace-log"]
    for command in commands2:
        print command
        runCommand1(command, homepath+"/"+BabeltraceLatestStable)
    print "Installing Babeltrace from source..." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC


def installLttngUSTFromSource():
    global homepath
    #checkDependenceforBabeltrace()
    print "Installing LTTng UST from source..."
    commands = ["wget " + LttngUSTLatestHttp,
                "tar xjvf " + LttngUSTLatestTar]
    for command in commands:
        print command
        runCommand(command)
    commands2 = ["./configure",
                "make",
                "make install",
                "ldconfig"]
    for command in commands2:
        print command
        runCommand1(command, homepath+"/"+LttngUSTLatest)
    print "Installing LTTng UST from source..." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC



def installLttngToolsFromSource():
    global homepath
    #checkDependenceforBabeltrace()
    print "Installing LTTng Tools from source..."
    commands = ["wget " + LttngToolsLatestHttp,
                "tar xjvf " + LttngToolsLatestTar]
    for command in commands:
        print command
        runCommand(command)
    commands2 = ["./configure",
                "make",
                "make install",
                "ldconfig"]
    for command in commands2:
        print command
        runCommand1(command, homepath+"/"+LttngToolsLatest)
    print "Installing LTTng Tools from source..." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC


#This function is for avoid `make` errors for LTTng Module
def preForInstallingLttngModule():
    global homepath
    global System
    print "Preparing for Installing LTTng Module..."
    if "AMI" in System:
        commands = ["sudo mv /usr/src/kernels/$(uname -r)/include/linux/version.h /usr/src/kernels/$(uname -r)/include/linux/version.h.bak",
                    "sudo dd if=/dev/zero of=/swapfile1 bs=1024 count=524288",
                    "sudo chown root:root /swapfile1",
                    "sudo chmod 0600 /swapfile1",
                    "sudo mkswap /swapfile1",
                    "sudo swapon /swapfile1"]
                    #"echo -e \"/swapfile1\tnone\tswap\tsw\t0\t0\" >> /etc/fstab"]
        for command in commands:
            print command
            runCommand(command)
    print "Preparing for Installing LTTng Module..." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC

#This function is for restoring the system after installing LTTng Module
def postForInstallingLttngModule():
    global homepath
    global System
    print "Restoring System after installing LTTng Module..."
    if "AMI" in System:
        commands = [#"sudo mv /usr/src/kernels/$(uname -r)/include/linux/version.h.bak /usr/src/kernels/$(uname -r)/include/linux/version.h",
                    #"sudo swapoff -v /swapfile1",
                    "if [ $(swapon -s | grep -o swapfile1 | wc -l) -ge 1 ]; then sudo swapoff -v /swapfile1; fi",
                    #"sudo rm -f /swapfile1",
                    "if [ $(ls /swapfile1 | wc -l) -ge 1 ]; then sudo rm -f /swapfile1; fi; sleep 1 "]
                    #"echo -e \"/swapfile1\tnone\tswap\tsw\t0\t0\" >> /etc/fstab"]
        for command in commands:
            print command
            runCommand(command)
    print "Restoring System after installing LTTng Module..." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC


def installLttngModuleFromSource():
    global homepath
    postForInstallingLttngModule()
    preForInstallingLttngModule()
    print "Installing LTTng Modules..."
    commands = ["wget " + LttngModuleLatestHttp,
                "tar xjvf " + LttngModuleLatestTar]
    for command in commands:
        print command
        runCommand(command)
    commands2 = ["make",
                "sudo make modules_install",
                "sudo depmod -a"]
    for command in commands2:
        print command
        out, err = runCommand1(command, homepath+"/"+LttngModuleLatest)
    print "Installing LTTng Modules from source..." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC
    postForInstallingLttngModule()


def main():
    global System
    checkings()
    if "Ubuntu" in System or "ubuntu" in System:
        installPackageForDebian()
        #installLttngModuleFromSource()
        out = testBabeltrace()
        if "error" in out:
            print bcolors.WARNING + "Install Babeltrace from package FAILED." + bcolors.ENDC
            installBabeltraceFromSource()
            out = testBabeltrace()
            if "error" in out:
                print bcolors.FAIL + "Install Babeltrace from source FAILED." + bcolors.ENDC
            if "succeed" in out:
                print "Babeltrace installed." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC
        elif "succeed" in out:
            print "Babeltrace installed." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC
        out = testLttngToolUST()
        if "error" in out:
            print bcolors.FAIL + "Install LTTng Tools and UST from package FAILED." + bcolors.ENDC
        elif "succeed" in out:
            print "LTTng Tools and UST installed." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC
        out = testLttngModule()
        if "error" in out:
            print bcolors.FAIL + "Install LTTng Modules from source FAILED." + bcolors.ENDC
        elif "succeed" in out:
            print "LTTng Modules installed." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC
    #for AWS, install all from source
    elif "Amazon Linux AMI" in System:
       installURCUFromSource()
       installBabeltraceFromSource() 
       installLttngUSTFromSource()
       installLttngToolsFromSource()
       installLttngModuleFromSource()
       out = testBabeltrace()
       if "error" in out:
           print bcolors.FAIL + "Install Babeltrace from source FAILED." + bcolors.ENDC
       elif "succeed" in out:
           print "Babeltrace installed." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC
       out = testLttngToolUST()
       if "error" in out:
            print bcolors.FAIL + "Install LTTng from package FAILED." + bcolors.ENDC
       elif "succeed" in out:
           out = testLttngModule()
           if "error" in out:
               print bcolors.FAIL + "Install LTTng from package FAILED." + bcolors.ENDC
           elif "succeed" in out:
               print "LTTng installed." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC



def checkDependenceWithVersionDebian():
    global dependenciesDebianWithVersion
    for dependency in dependenciesDebianWithVersion:
        print "Checking " + dependency[0] + "..."
        command = "dpkg -s " + dependency[0] + " | grep 'Version' | rev | cut -d \" \" -f 1 | rev"
        #print command
        out = runCommand(command)
        if "is not installed" not in out:
            version = out.split("\n")[0]
            if parse_version(version) >= parse_version(dependency[1]):
                print dependency[0] + " version is " + version + " >= " + dependency[1] + bcolors.OKGREEN + " [OK]" + bcolors.ENDC
                continue
        command = "sudo apt-get install " + dependency[0]
        print command
        runCommand2(command, "y\n")
        command = "dpkg -s " + dependency[0] + " | grep 'Version' | rev | cut -d \" \" -f 1 | rev"
        #print command
        out = runCommand(command)
        if "is not installed" not in out:
            version = out.split("\n")[0]
            if parse_version(version) >= parse_version(dependency[1]):
                print dependency[0] + " version is " + version + " >= " + dependency[1] + bcolors.OKGREEN + " [OK]" + bcolors.ENDC
                continue
            else:
                print bcolors.FAIL + dependency[0] + " version is " + version + " < " + dependency[1] + bcolors.ENDC
        else:
            print bcolors.FAIL + dependency[0] + " is not intalled." + bcolors.ENDC


def checkDependenceDebian():
    global dependenciesDebian
    for dependency in dependenciesDebian:
        print "Checking " + dependency + " ..."
        command = "dpkg -s " + dependency
        #print command
        out = runCommand(command)
        if "is not installed" not in out:
            print dependency + " is installed." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC
            continue
        command = "sudo apt-get install " + dependency
        print command
        runCommand2(command, "y\n")
        command = "dpkg -s " + dependency
        #print command
        out = runCommand(command)
        if "is not installed" in out:
            print bcolors.FAIL + dependency + " is not intalled." + bcolors.ENDC
        else:
            print dependency + " is installed." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC


def checkDependenceWithVersionAWS():
    global dependenciesAWSWithVersion
    for dependency in dependenciesAWSWithVersion:
        print "Checking " + dependency[0] + "..."
        command = "rpm -q " + dependency[0] + " | rev | cut -d \"-\" -f 2 | rev"
        #print command
        out = runCommand(command)
        if "is not installed" not in out:
            version = out.split("\n")[0]
            if parse_version(version) >= parse_version(dependency[1]):
                print dependency[0] + " version is " + version + " >= " + dependency[1] + bcolors.OKGREEN + " [OK]" + bcolors.ENDC
                continue
        command = "sudo yum install " + dependency[0]
        print command
        runCommand2(command, "y\n")
        command = "rpm -q " + dependency[0] + " | rev | cut -d \"-\" -f 2 | rev"
        #print command
        out = runCommand(command)
        if "is not installed" not in out:
            version = out.split("\n")[0]
            if parse_version(version) >= parse_version(dependency[1]):
                print dependency[0] + " version is " + version + " >= " + dependency[1] + bcolors.OKGREEN + " [OK]" + bcolors.ENDC
                continue
            else:
                print bcolors.FAIL + dependency[0] + " version is " + version + " < " + dependency[1] + bcolors.ENDC
        else:
            print bcolors.FAIL + dependency[0] + " is not intalled." + bcolors.ENDC


def checkDependenceAWS():
    global dependenciesAWS
    for dependency in dependenciesAWS:
        print "Checking " + dependency + " ..."
        command = "rpm -q " + dependency
        #print command
        out = runCommand(command)
        if "is not installed" not in out:
            print dependency + " is installed." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC
            continue
        command = "sudo yum install " + dependency
        print command
        runCommand2(command, "y\n")
        command = "rpm -q " + dependency
        #print command
        out = runCommand(command)
        if "is not installed" in out:
            print bcolors.FAIL + dependency + " is not intalled." + bcolors.ENDC
        else:
            print dependency + " is installed." + bcolors.OKGREEN + " [OK]" + bcolors.ENDC


#checking all the OS releated info and the dependencies
def checkings():
    global System
    System = checkDistribution()
    checkKernel()
    checkKernelHeader()
    checkGCC()
    print "Checking dependencies..."
    if "Ubuntu" in System or "ubuntu" in System:
        checkDependenceWithVersionDebian()
        checkDependenceDebian()
    elif "Amazon Linux AMI" in System:
        checkDependenceWithVersionAWS()
        checkDependenceAWS()


if __name__=="__main__":
    global homepath
    checkPrivilege()
    homepath = get_args()
    main()


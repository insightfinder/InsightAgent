#!/bin/python
import os
import sys
import subprocess
required_packages = ["requests","paramiko"]

'''
This script checks for required packages and installs using pip
'''

try:
    import pip
except ImportError as e:
    #Install pip if not found
    homepath = os.getcwd()
    proc = subprocess.Popen(["sudo python "+os.path.join(homepath,"get-pip.py")], cwd=homepath, stdout=subprocess.PIPE, shell=True)
    (out,err) = proc.communicate()
    try:
	import pip
    except ImportError as e:
	print "Dependencies are missing. Please install the dependencies as stated in README"
	sys.exit()

installed_packages = pip.get_installed_distributions()
flat_installed_packages = [package.project_name for package in installed_packages]

for eachpackage in required_packages:
    if eachpackage in flat_installed_packages:
        print "%s already Installed"%eachpackage
    else:
        print "%s not found. Installing..."%eachpackage
        try:
            pip.main(['install','-q',eachpackage])
        except:
            print "Unable to install %s using pip. Please install the dependencies as stated in README"%eachpackage

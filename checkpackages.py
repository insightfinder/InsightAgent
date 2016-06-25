#!/bin/python
import os
import sys
import subprocess
required_packages = ["requests","paramiko"]

'''
This script checks for required packages and installs using pip
'''
homepath = os.getcwd()
user = os.getlogin()
try:
    import pip
except ImportError as e:
    #Install pip if not found
    proc = subprocess.Popen(["sudo python "+os.path.join(homepath,"get-pip.py")], cwd=homepath, stdout=subprocess.PIPE, shell=True)
    (out,err) = proc.communicate()
    try:
        import pip
    except ImportError as e:
        print "Dependencies are missing. Please install the dependencies as stated in README"
        sys.exit()
pyVersion = sys.version
versionElements = pyVersion.split(" ")[0].split(".")
version = versionElements[0] + "." + versionElements[1]
command = "pip install --user virtualenv\n \
        python  /home/"+user+"/.local/lib/python"+version+"/site-packages/virtualenv.py pyenv\n \
        source pyenv/bin/activate\n \
        pip install -r requirements\n"
proc = subprocess.Popen([command], cwd=homepath, stdout=subprocess.PIPE, shell=True)
(out,err) = proc.communicate()

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
    if os.path.isfile("deployment/get-pip.py") == False:
        proc = subprocess.Popen(["sudo python "+os.path.join(homepath,"get-pip.py")], cwd=homepath, stdout=subprocess.PIPE, shell=True)
    else:
        proc = subprocess.Popen(["sudo python "+os.path.join(homepath,"deployment","get-pip.py")], cwd=homepath, stdout=subprocess.PIPE, shell=True)
    (out,err) = proc.communicate()
    try:
        import pip
    except ImportError as e:
        print "Dependencies are missing. Please install the dependencies as stated in README"
        sys.exit()
if os.path.isfile("deployment/requirements") == False:
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
else:
    pyVersion = sys.version
    versionElements = pyVersion.split(" ")[0].split(".")
    version = versionElements[0] + "." + versionElements[1]
    command = "sudo chown -R "+user+" /home/"+user+"/.local"
    proc = subprocess.Popen([command], cwd=homepath, stdout=subprocess.PIPE, shell=True, executable="/bin/bash")
    (out,err) = proc.communicate()
    command = "pip install -U --force-reinstall --user virtualenv\n \
        python  /home/"+user+"/.local/lib/python"+version+"/site-packages/virtualenv.py pyenv\n \
        source pyenv/bin/activate\n \
        pip install -r deployment/requirements\n"
    proc = subprocess.Popen([command], cwd=homepath, stdout=subprocess.PIPE, shell=True, executable="/bin/bash")
    (out,err) = proc.communicate()

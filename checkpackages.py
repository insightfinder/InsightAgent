#!/bin/python
import pip
import os

required_packages = ["pexpect","requests"]

installed_packages = pip.get_installed_distributions()
flat_installed_packages = [package.project_name for package in installed_packages]

for eachpackage in required_packages:
    if eachpackage in flat_installed_packages:
        print "%s already Installed"%eachpackage
    else:
        print "%s not found. Installing..."%eachpackage
        pip.main(['install',eachpackage])

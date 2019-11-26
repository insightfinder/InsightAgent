#!/bin/bash

# anything in requirements.txt?
if [[ $(cat requirements.txt | wc -l) -eq 0 ]];
then
    echo "No pip packages to install."
    exit 0
else
    echo "Attempting to set up pip packages: "
    cat requirements.txt
fi

# are offline packages available?
TRY_OFFLINE=0
if [[ -d ./offline/pip/ ]];
then
    TRY_OFFLINE=1
fi

# can use pip?
if [[ -z $(command -v pip) ]];
then
    echo "Package \"pip\" not installed. Attempting to install now..."
    if [[ ${TRY_OFFLINE} -gt 0 ]];
    then
        ./offline/pip/get-pip.py
    fi
fi
if [[ -z $(command -v pip) ]];
then
    python <(curl --connect-timeout 3 https://bootstrap.pypa.io/get-pip.py)
fi
if [[ -z $(command -v pip) ]];
then
    echo "Could not install pip. Exiting..."
    exit 1
fi

# as root or user
PIP_CMD_BASE="pip install"
if [[ $EUID -ne 0 ]];
then
    PIP_CMD_BASE="${PIP_CMD_BASE} --user"
fi

# install packages
if [[ ${TRY_OFFLINE} -gt 0 ]];
then
    PIP_CMD_BASE="${PIP_CMD_BASE} --no-index --find-links=./offline/pip/packages/"
fi
echo "Installing pip packages"
${PIP_CMD_BASE} -r requirements.txt

#!/bin/bash

# check input
AGENT="$1"
if [[ -z ${AGENT} ]];
then
    echo "No agent specified for installation."
    exit 1
else
    AGENT=$(echo ${AGENT} | sed -E -e 's:^(.*)\/$:\1:')
    AGENT_TAR="${AGENT}.tar.gz"
fi

echo "Setting up agent ${AGENT}"

# get agent dir if needed
if [[ ! -d ${AGENT} ]];
then 
    echo "Downloading..."
    curl -L "https://github.com/insightfinder/InsightAgent/raw/master/${AGENT}/${AGENT_TAR}" -o ${AGENT_TAR}
    echo "Extracting..."
    tar xvf ${AGENT_TAR}
fi

# enter agent dir and copy the config
cd ${AGENT}
cp config.ini.template config.ini

# install script call
echo "Created config.ini. Once that has been configured, run"
echo "    ./install.sh"
echo "to test out the installation, then"
echo "    ./install.sh --create"
echo "to commit the installation."

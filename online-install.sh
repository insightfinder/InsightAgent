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
    wget "https://github.com/insightfinder/InsightAgent/raw/master/${AGENT}/${AGENT_TAR}"
    echo "Extracing..."
    tar xvf ${AGENT_TAR}
fi

# enter agent dir and copy the config
cd ${AGENT}
cp config.ini.template config.ini

# install script call
INSTALL_CALL="./install.sh"
CRONIT=$(\ls -l | awk '{print $NF}' | grep ^.*-config\.sh$ | sed -E  -e 's:^(monit|cron)-config\.sh$:\1:')
if [[ "${CRONIT}" = "cron" ]];
then
    INSTALL_CALL="${INSTALL_CALL} --sampling-interval <N>"
fi

echo "Created config.ini. Once that has been configured, run"
echo "${INSTALL_CALL}"
echo "to test out the installation, then"
echo "${INSTALL_CALL} --create"
echo "to commit the installation."

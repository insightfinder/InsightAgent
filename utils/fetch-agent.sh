#!/bin/bash

# check input
AGENT="$1"
if [[ -z ${AGENT} ]];
then
    echo "No agent specified for installation."
    exit 1
else
    AGENT=$(sed -E -e 's:^(.*)\/$:\1:' <<< ${AGENT})
    # for now, we exist in multiple worlds for agent installs and can't guarentee anything made without make-agent-installer will work
    if [[ ! ${AGENT} =~ $(curl -sS https://github.com/insightfinder/InsightAgent/raw/master/utils/new-agents) ]];
    then
        echo "Not a valid option for this style of installer. Please see the relevant README."
        exit 1
    fi
    AGENT_TAR="${AGENT}.tar.gz"
fi

echo "Setting up agent ${AGENT}"

# get agent dir if needed
if [[ ! -d ${AGENT} ]];
then 
    echo "Downloading..."
    curl -sSL "https://github.com/insightfinder/InsightAgent/raw/master/${AGENT}/${AGENT_TAR}" -o ${AGENT_TAR}
    echo "Extracting..."
    tar xvf ${AGENT_TAR}
fi

# enter agent dir and copy the config
cd ${AGENT}
cp config.ini.template config.ini

# install script call
echo "Created config.ini. Once that has been configured,"
echo "  in order to install on one machine, run:"
echo "    ./install.sh"
echo "  to test out the installation, then"
echo "    ./install.sh --create"
echo "  to commit the installation."
echo "Or, if you want to install on multiple nodes,"
echo "    ./remote-cp-run.sh node1 node2 .. nodeN"
echo "Run either with --help for further information"

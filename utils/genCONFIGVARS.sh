#!/bin/bash

PWD=$(pwd)
DIR=$(pwd | awk -F '/' '{print $NF}')
if [[ $(\ls -l | awk '{print $NF}' | grep ${DIR} | wc -l) -eq 0 ]]; # probably not an agent folder
then
    # pass agent as parameter
    AGENT=$1
    if [[ -z ${AGENT} || ! -d ${AGENT} ]]; then
        AGENT=$(\ls -lrt | grep ^d | tail -n1 | awk '{print $NF}')
        echo "No agent to build specified. Using most recently modified folder: ${AGENT}"
        read -p "Press [Enter] to continue, [Ctrl+C] to quit"
    fi

    cd ${AGENT}
else
    AGENT=${DIR}
fi

# check for config.ini.template file
if [[ ! -f config.ini.template ]];
then
    echo "This script requires that the agent uses config.ini.template."
    exit 1
fi

FILE="@CONFIGVARS.md"
PARAMS=$(cat config.ini.template | grep ^[^#].*=.* | awk '{print $1}')

touch ${FILE}
echo "### Config Variables" > ${FILE}
for PARAM in $PARAMS;
do
    echo "* \`${PARAM}\`: " >> ${FILE}
done

echo "${FILE} created"
cat ${FILE}

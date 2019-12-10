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

FILE=".CONFIGVARS.md"
if [[ ! -f "${FILE}" ]];
then
    cp ../template/${FILE} .
fi
CONTENTS=$(cat ${FILE})
PARAMS=$(cat config.ini.template | grep ^[^#].*=.* | awk '{print $1}')

echo "### Config Variables" > ${FILE}
for PARAM in $PARAMS;
do
    EXISTING_LINE=$(echo "${CONTENTS}" | grep -E \`${PARAM}\`)
    if [[ -n ${EXISTING_LINE} ]];
    then
        echo "${EXISTING_LINE}" >> ${FILE}
    else
        echo "* \`${PARAM}\`: " >> ${FILE}
    fi
done

echo "${FILE} created"
cat ${FILE}

#!/bin/bash

# agent directory to find file in
DIR="$1"
if [[ -z ${DIR} ]];
then
    DIR="."
elif [[ "${DIR: -1}" == '/' ]];
then
    DIR="${DIR:0:${#DIR}-1}"
fi 
# get py file, fallback to template file
AGENT_SCRIPT=$(\ls -l ${DIR} | grep get[^\-].*\.py | awk '{print $NF}')
if [[ -z ${AGENT_SCRIPT} ]];
then
    AGENT_SCRIPT=$(\ls -l ${DIR} | grep replay.*\.py | awk '{print $NF}')
fi
if [[ -z ${AGENT_SCRIPT} ]];
then
    AGENT_SCRIPT="insightagent-boilerplate.py"
fi

###
EXT='.bck'
SHEBANG='#!/usr/bin/env'

if [[ -n ${AGENT_SCRIPT} ]];
then
    AGENT_SCRIPT="${DIR}/${AGENT_SCRIPT}"
    echo "${AGENT_SCRIPT}"
    # py
    sed -e "1s:.*:${SHEBANG} python:" -i "" ${AGENT_SCRIPT}
fi

# sh
find ${DIR} -type f -name '*.sh' -exec sed -e "1s:.*:${SHEBANG} bash:" -i "" {} \;

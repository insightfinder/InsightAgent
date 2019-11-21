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
if [[ -z ${AGENT_SCRIPT} ]];
then
    echo "No script found. Exiting..."
    exit 1
fi
AGENT_SCRIPT="${DIR}/${AGENT_SCRIPT}"
echo "${AGENT_SCRIPT}"

###
EXT="$2"

if [[ $(grep -E "instance = COLONS\.sub\(\'\-\', instance\)" ${AGENT_SCRIPT} | wc -l) -eq 0 ]];
then 
    echo "adding to instance string building"
    sed -E -e "/instance = UNDERSCORE\.sub\(\'\.\', instance\)/a\\                  
\ \ \ \ instance = COLONS\.sub\(\'\-', instance\)" -i ${EXT} ${AGENT_SCRIPT}
fi
 
if [[ $(grep -E "COLONS = re\.compile\(r\"\\\:\+\"\)" ${AGENT_SCRIPT} | wc -l) -eq 0 ]];
then
    echo "adding to global declaratinos"
    sed -E -e "/UNDERSCORE = re\.compile\(r\"\\\_\+\"\)/a\\
\ \ \ \ COLONS = re\.compile\(r\"\\\:\+\"\)" -i ${EXT} ${AGENT_SCRIPT}
fi


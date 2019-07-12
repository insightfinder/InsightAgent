#!/bin/bash

AGENT="kafka2"
AGENT_SCRIPT="getmessages_kafka.py"
AGENT_CONFIG="config.ini"
AGENT_FOLDER="InsightAgent-${AGENT}"
AGENT_BASE_PATH=$(cd .. && pwd && cd ->/dev/null)
AGENT_DIR_PATH="${AGENT_BASE_PATH}/${AGENT_FOLDER}"
AGENT_FULL_PATH="${AGENT_DIR_PATH}/${AGENT_SCRIPT}"
AGENT_FULL_PATH_CONFIG="${AGENT_DIR_PATH}/${AGENT_CONFIG}"

# setup files
sudo mkdir -p ${AGENT_DIR_PATH}
cp ${AGENT_SCRIPT} ${AGENT_DIR_FULL_PATH}
cp ${AGENT_CONFIG} ${AGENT_FULL_PATH_CONFIG}

# monit
MONIT_FILE="/etc/monit.d/${AGENT}.monit"
touch ${MONIT_FILE}
echo \
"check process kafka_agent matching \"${AGENT_FULL_PATH}\"
    if does not exist then start
    start program = \"/usr/bin/nohup /usr/bin/python ${AGENT_FULL_PATH}\"
    stop program = \"pkill -f ${AGENT_FULL_PATH}\"

check file kafka_agent_config matching \"${AGENT_FULL_PATH_CONFIG}\"
    if changed mtime then restart
    start program = \"/usr/bin/nohup /usr/bin/python ${AGENT_FULL_PATH}\"
    stop program = \"pkill -f ${AGENT_FULL_PATH}\" " >> ${MONIT_FILE}

sudo monit reload

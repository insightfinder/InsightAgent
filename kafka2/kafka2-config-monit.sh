#!/bin/bash

AGENT="kafka2"
AGENT_SCRIPT="getmessages_kafka.py"
AGENT_FULL_PATH="$(pwd)/${AGENT_SCRIPT}"
AGENT_FULL_PATH_CONFIG="$(pwd)/config.ini"

# monit control
MONIT_FILE="/etc/monit.d/${AGENT}.monit"
touch ${MONIT_FILE}
echo \
"check process kafka_agent matching \"${AGENT_FULL_PATH}\"
    if does not exist then start
    start program = \"/usr/bin/nohup /usr/bin/python ${AGENT_FULL_PATH}\"
    stop program = \"pkill -f ${AGENT_FULL_PATH}\"

check file kafka_agent_config path \"${AGENT_FULL_PATH_CONFIG}\"
    if changed timestamp then restart
    start program = \"/usr/bin/nohup /usr/bin/python ${AGENT_FULL_PATH}\"
    stop program = \"pkill -f ${AGENT_FULL_PATH}\"" > ${MONIT_FILE}

# reload monit
monit reload

#!/bin/bash

# TODO: fill out agent name
AGENT=""

# run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script should be ran as root. Exiting..."
   exit 1
fi

AGENT_SCRIPT="${AGENT}.py"
AGENT_FULL_PATH="$(pwd)/${AGENT_SCRIPT}"
AGENT_FULL_PATH_CONFIG="$(pwd)/config.ini"
AGENT_FULL_PATH_LOG="$(pwd)/log.out"
touch ${AGENT_FULL_PATH_LOG}

# monit control
MONIT_FILE="/etc/monit.d/${AGENT}"
touch ${MONIT_FILE}
echo \
"check process ${AGENT_SCRIPT} matching \"${AGENT_FULL_PATH}\"
    if does not exist then start
    start program = \"\$(command -v python) ${AGENT_FULL_PATH} &>${AGENT_FULL_PATH_LOG}\"
    stop program = \"\$(command -v pkill) -f ${AGENT_FULL_PATH}\"

check file ${AGENT}_config path \"${AGENT_FULL_PATH_CONFIG}\"
    if changed timestamp then restart
    start program = \"\$(command -v python) ${AGENT_FULL_PATH} &>${AGENT_FULL_PATH_LOG}\"
    stop program = \"\$(command -v pkill) -f ${AGENT_FULL_PATH}\"" > ${MONIT_FILE}

echo "monit config file created at ${MONIT_FILE}"
cat ${MONIT_FILE}

# reload monit
monit reload

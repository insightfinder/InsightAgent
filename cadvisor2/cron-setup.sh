#!/bin/bash

# TODO: fill here
AGENT="cadvisor2"
AGENT_SCRIPT="getmetrics_cadvisor.py"

# run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script should be ran as root. Exiting..."
   exit 1
fi

AGENT_FULL_PATH="$(pwd)/${AGENT_SCRIPT}"
AGENT_FULL_PATH_CONFIG="$(pwd)/config.ini"
AGENT_FULL_PATH_LOG="$(pwd)/log.out"
touch ${AGENT_FULL_PATH_LOG}

# crontab
CRON_FILE="/etc/cron.d/${AGENT}"
touch ${CRON_FILE}
CRON_USER="root"
CRON_COMMAND="\$(command -v python) ${AGENT_FULL_PATH} &>${AGENT_FULL_PATH_LOG}"

### special handling for cadvisor
echo "*/3 * * * * ${CRON_USER} ${CRON_COMMAND}" > ${CRON_FILE}
echo "*/3 * * * * ${CRON_USER} sleep 90; ${CRON_COMMAND}" >> ${CRON_FILE}
echo "" >> ${CRON_FILE}

echo "Cron config created at ${CRON_FILE}"

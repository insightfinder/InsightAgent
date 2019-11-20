#!/bin/bash

# run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script should be ran as root. Exiting..."
   exit 1
fi

# check for monit
if [[ -z $(command -v monit) ]]; then
    echo "Warning: monit not installed. Please install monit before running this script."
    exit 1
fi

# get agent
AGENT=$(pwd | awk -F "/" '{print $NF}')
#AGENT_SCRIPT=$(find . -type f -name "get[^\-]*.py" -print)
AGENT_SCRIPT=$(\ls -l | grep get[^\-]*.py | awk '{print $NF}')
if [[ -z ${AGENT_SCRIPT} ]];
then
    AGENT_SCRIPT=$(find . -type f -name "replay*.py" -print)
fi
if [[ -z ${AGENT_SCRIPT} ]];
then
    echo "No script found. Exiting..."
    exit 1
fi
AGENT_SCRIPT=${AGENT_SCRIPT:2:${#AGENT_SCRIPT}}
AGENT_FULL_PATH="$(pwd)/${AGENT_SCRIPT}"
AGENT_FULL_PATH_CONFIG="$(pwd)/config.ini"
AGENT_FULL_PATH_LOG="$(pwd)/log.out"
touch ${AGENT_FULL_PATH_LOG}

# monit control
MONIT_FILE="/etc/monit.d/${AGENT}"
touch ${MONIT_FILE}
cat <<EOF > ${MONIT_FILE}
check process ${AGENT} matching \"${AGENT_FULL_PATH}\"
    if does not exist then start
    start program = \"\$(command -v python) ${AGENT_FULL_PATH} >${AGENT_FULL_PATH_LOG}\"
    stop program = \"\$(command -v pkill) -f ${AGENT_FULL_PATH}\"

check file ${AGENT}_config path \"${AGENT_FULL_PATH_CONFIG}\"
    if changed timestamp then restart
    start program = \"\$(command -v python) ${AGENT_FULL_PATH} >${AGENT_FULL_PATH_LOG}\"
    stop program = \"\$(command -v pkill) -f ${AGENT_FULL_PATH}\"
EOF

echo "monit config file created at ${MONIT_FILE}"
cat ${MONIT_FILE}

# reload monit
monit reload
exit 0

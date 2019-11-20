#!/bin/bash

# run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script should be ran as root. Exiting..."
   exit 1
fi

function echo_usage() {
    echo "No or invalid run interval specified. Please call this script as"
    echo "./cron-config.sh <run-interval>"
    echo "Where run-interval is how often the cron should run in"
    echo "\tseconds: \"6s\" - must be an integer divisor of 60,"
    echo "\tminutes: \"6m\" or \"6\" (default),"
    echo "\thours: \"6h\", or"
    echo "\tdays: \"6d\""
}

RUN_INTERVAL="$1"
if [[ -z "${RUN_INTERVAL}" ]];
then
    echo_usage
    exit 1
fi

# get agent
AGENT=$(pwd | awk -F "/" '{print $NF}')
AGENT_SCRIPT=$(\ls -l | grep get[^\-]*.py | awk '{print $NF}')
#AGENT_SCRIPT=$(find . -type f -name "get[^\-]*.py" -print)
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

# crontab
CRON_FILE="/etc/cron.d/${AGENT}"
touch ${CRON_FILE}
CRON_USER="root"
CRON_COMMAND="\$(command -v python) ${AGENT_FULL_PATH} >${AGENT_FULL_PATH_LOG}"
RUN_INTERVAL_VAL=${RUN_INTERVAL}
RUN_INTERVAL_UNIT="${RUN_INTERVAL: -1}"

# strip unit
if [[ ${RUN_INTERVAL_UNIT} =~ [^0-9] ]];
then
    RUN_INTERVAL_VAL="${RUN_INTERVAL:0:${#RUN_INTERVAL}-1}"
fi

# check input
if [[ "${RUN_INTERVAL_UNIT}" =~ [dhm0-9] || "${RUN_INTERVAL_VAL}" -le 0 || $((${RUN_INTERVAL_VAL} % 1)) -ne 0 || ("${RUN_INTERVAL_UNIT}" = "s" && $((60 % ${RUN_INTERVAL_VAL})) -eq 0) ]];
then
    echo_usage
    exit 1
fi

case "${RUN_INTERVAL_UNIT}" in
    s)      # seconds
        echo "* * * * * ${CRON_USER} ${CRON_COMMAND}" > ${CRON_FILE}
        SLEEP="${RUN_INTERVAL_VAL}"
        while [[ "${SLEEP}" -lt 60 ]]; do
            echo "* * * * * ${CRON_USER} sleep ${SLEEP}; ${CRON_COMMAND}" >> ${CRON_FILE}
            SLEEP=$((${SLEEP}+${RUN_INTERVAL_VAL}))
        done
        ;;
    d)      # days
        echo "* * */${RUN_INTERVAL_VAL} * * ${CRON_USER} ${CRON_COMMAND}" > ${CRON_FILE}
        ;;
    h)      # hours
        echo "* */${RUN_INTERVAL_VAL} * * * ${CRON_USER} ${CRON_COMMAND}" > ${CRON_FILE}
        ;;
    [m0-9]) # minutes
        echo "*/${RUN_INTERVAL_VAL} * * * * ${CRON_USER} ${CRON_COMMAND}" > ${CRON_FILE}
        ;;
    *)      # shouldn't get here
        echo_usage
        exit 1
        ;;
esac
# end with a blank line
echo "" >> ${CRON_FILE}

echo "Cron config created at ${CRON_FILE}"
cat ${CRON_FILE}
exit 0

#!/bin/bash

AGENT="spark-logs"
AGENT_SCRIPT="getlogs_spark.py"

# run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script should be ran as root. Exiting..."
   exit 1
fi

RUN_INTERVAL=$1
if [[ -z "${RUN_INTERVAL}" ]]; then
    echo "Please specify the run interval for this agent as the first parameter"
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
CRON_COMMAND="\$(command -v python) ${AGENT_FULL_PATH} >${AGENT_FULL_PATH_LOG}"
RUN_INTERVAL_UNIT="${RUN_INTERVAL: -1}"
RUN_INTERVAL_VAL="${RUN_INTERVAL:0:${#RUN_INTERVAL}-1}"

# handle secs
if [[ "${RUN_INTERVAL_UNIT}" = "s" ]] && [[ "${RUN_INTERVAL_VAL}" -gt 0 ]] && [[ $((${RUN_INTERVAL_VAL} % 1)) -eq 0 ]] && [[ $((60 % ${RUN_INTERVAL_VAL})) -eq 0 ]]; then
    echo "* * * * * ${CRON_USER} ${CRON_COMMAND}" > ${CRON_FILE}
    SLEEP=${RUN_INTERVAL_VAL}
    while [[ ${SLEEP} -lt 60 ]]; do
        echo "* * * * * ${CRON_USER} sleep ${SLEEP}; ${CRON_COMMAND}" >> ${CRON_FILE}
        let SLEEP=${SLEEP}+${RUN_INTERVAL_VAL}
    done
# handle days
elif [[ "${RUN_INTERVAL_UNIT}" = "d" ]] && [[ "${RUN_INTERVAL_VAL}" -gt 0 ]] && [[ $((${RUN_INTERVAL_VAL} % 1)) -eq 0 ]]; then
    echo "* * */${RUN_INTERVAL_VAL} * * ${CRON_USER} ${CRON_COMMAND}" > ${CRON_FILE}
# handle hours
elif [[ "${RUN_INTERVAL_UNIT}" = "h" ]] && [[ "${RUN_INTERVAL_VAL}" -gt 0 ]] && [[ $((${RUN_INTERVAL_VAL} % 1)) -eq 0 ]]; then
    echo "* */${RUN_INTERVAL_VAL} * * * ${CRON_USER} ${CRON_COMMAND}" > ${CRON_FILE}
# handle minutes
elif [[ "${RUN_INTERVAL_UNIT}" = "m" ]]  && [[ "${RUN_INTERVAL_VAL}" -gt 0 ]] && [[ $((${RUN_INTERVAL_VAL} % 1)) -eq 0 ]]; then
    echo "*/${RUN_INTERVAL_VAL} * * * * ${CRON_USER} ${CRON_COMMAND}" > ${CRON_FILE}
elif [[ "${RUN_INTERVAL}" -gt 0 ]] && [[ $((${RUN_INTERVAL} % 1)) -eq 0 ]]; then
    echo "*/${RUN_INTERVAL} * * * * ${CRON_USER} ${CRON_COMMAND}" > ${CRON_FILE}
else
    echo "Invalid run interval specified. Please specify how often the cron should run in seconds (\"6s\" - must be an integer divisor of 60), minutes (default, \"6m\" or \"6\"), hours (\"6h\"), or days (\"6d\")"
    exit 1
fi
# end with a blank line
echo "" >> ${CRON_FILE}

echo "Cron config created at ${CRON_FILE}"
cat ${CRON_FILE}

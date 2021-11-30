#!/usr/bin/env bash

## Utility Functions

# get input params
function echo_params() {
    echo "Usage:"
    echo "-c --create   Install the cron command (root)."
    echo "-d --display  Display the cron command (non-root)."
    exit 1
}

# Dry run mode
function is_dry_run() {
    [[ ${DRY_RUN} -gt 0 ]]
}

# Get value from config.ini settings
function get_config_setting() {
    cat config.ini | grep "$1" | awk -F '=' '{print $NF}' | tr -d [:space:]
}

# Get value from agent.txt settings
function get_agent_setting() {
    cat agent.txt | grep "$1" | awk -F '=' '{print $NF}' | tr -d [:space:]
}

# Get absolute path from relative path
function abspath() {
    # $1     : relative filename
    # return : absolute path
    if [ -d "$1" ]; then
        # dir
        (cd "$1"; pwd)
    elif [ -f "$1" ]; then
        # file
        if [[ $1 = /* ]]; then
            echo "$1"
        elif [[ $1 == */* ]]; then
            echo "$(cd "${1%/*}"; pwd)/${1##*/}"
        else
            echo "$(pwd)/$1"
        fi
    fi
}

case "$1" in
    -c|--create)
        DRY_RUN=0
        ;;  
    -d|--display)
        DRY_RUN=1
        ;;  
    *) 
        echo_params
        ;;  
esac

# Check if root for non-dry run
if [[ $EUID -ne 0 ]] && ! is_dry_run ; then
    echo "This script should be ran as root. Exiting..."
    exit 1
fi

ORIGIN="$( pwd )"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Change to agent directory
cd $SCRIPT_DIR && cd ..

# verify python has been set up, and config.ini is present
if [[ ! -f venv/bin/python3 ]];
then 
    echo "Missing virtual env. Please run configure_python.sh." 
    exit 1
elif [[ ! -f config.ini ]];
then 
    echo "Missing config.ini.  Please copy config.ini.template to config.ini and update the configuration file."
    exit 1
fi

# agent settings
PY_CMD="$(abspath "./venv/bin/python3")"
AGENT="$(get_agent_setting ^name)"
AGENT_FULL_PATH="$(abspath "./$(get_agent_setting ^script_name)")"
AGENT_FULL_PATH_LOG="$(abspath "./")/log.out"

# get interval
RUN_INTERVAL=$(get_config_setting ^run_interval)
if [[ -z "${RUN_INTERVAL}" ]];
then
    RUN_INTERVAL=$(get_config_setting ^sampling_interval)
fi
if [[ -z "${RUN_INTERVAL}" ]];
then
    echo "Missing run_interval/ sampling_interval config.ini. Exiting..."
    exit 1
fi

# crontab settings
CRON_FILE="/etc/cron.d/${AGENT}"
CRON_USER="$( logname )"
CRON_COMMAND="command -p ${PY_CMD} ${AGENT_FULL_PATH} > ${AGENT_FULL_PATH_LOG} 2>&1"
RUN_INTERVAL_VAL=${RUN_INTERVAL}
RUN_INTERVAL_UNIT="${RUN_INTERVAL: -1}"

# create files
if ! is_dry_run;
then
    touch ${CRON_FILE}
    touch ${AGENT_FULL_PATH_LOG}
    chmod 0666 ${AGENT_FULL_PATH_LOG}
fi

# strip unit
if [[ ${RUN_INTERVAL_UNIT} =~ [^0-9] ]];
then
    RUN_INTERVAL_VAL="${RUN_INTERVAL:0:${#RUN_INTERVAL}-1}"
fi

# check input
if [[ "${RUN_INTERVAL_UNIT}" =~ [^dhm0-9s] || "${RUN_INTERVAL_VAL}" -le 0 || $((${RUN_INTERVAL_VAL} % 1)) -ne 0 || ("${RUN_INTERVAL_UNIT}" = "s" && $((60 % ${RUN_INTERVAL_VAL})) -ne 0) ]];
then
    echo_usage
fi

# make scron file
case "${RUN_INTERVAL_UNIT}" in
    s)      # seconds
        echo "* * * * * ${CRON_USER} ${CRON_COMMAND}" 2>&1 | if is_dry_run; then awk '{print}'; else tee ${CRON_FILE}; fi
        SLEEP="${RUN_INTERVAL_VAL}"
        while [[ "${SLEEP}" -lt 60 ]]; do
            echo "* * * * * ${CRON_USER} sleep ${SLEEP}; ${CRON_COMMAND}" 2>&1 | if is_dry_run; then awk '{print}'; else tee -a ${CRON_FILE}; fi
            SLEEP=$((${SLEEP}+${RUN_INTERVAL_VAL}))
        done
        ;;
    d)      # days
        echo "* * */${RUN_INTERVAL_VAL} * * ${CRON_USER} ${CRON_COMMAND}" 2>&1 | if is_dry_run; then awk '{print}'; else tee ${CRON_FILE}; fi
        ;;
    h)      # hours
        echo "* */${RUN_INTERVAL_VAL} * * * ${CRON_USER} ${CRON_COMMAND}" 2>&1 | if is_dry_run; then awk '{print}'; else tee ${CRON_FILE}; fi
        ;;
    [m0-9]) # minutes
        echo "*/${RUN_INTERVAL_VAL} * * * * ${CRON_USER} ${CRON_COMMAND}" 2>&1 | if is_dry_run; then awk '{print}'; else tee ${CRON_FILE}; fi
        ;;
    *)      # shouldn't get here
        echo_usage
        ;;
esac
# end with a blank line
echo "" 2>&1 | if is_dry_run; then awk '{print}'; else tee -a ${CRON_FILE}; fi

if is_dry_run;
then
    echo "To create a cron config at ${CRON_FILE}, run this again as"
    echo "  sudo ./setup/install_cron.sh --create"
else
    echo "Cron config created at ${CRON_FILE}"
fi
exit 0

# Return to original directory
cd $ORIGIN
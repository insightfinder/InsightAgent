#!/usr/bin/env bash

# run as root
if [[ $EUID -ne 0 ]]; then
    echo "This script should be ran as root. Exiting..."
    exit 1
fi

# get input params
function echo_params() {
    echo "Usage:"
    echo "-c --create   Set to run this in commit mode."
    echo "-h --help     Display this help text and exit."
    exit 1
}

DRY_RUN=1
while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--create)
            DRY_RUN=0
            ;;  
        -h|--help)
            echo_params
            ;;
        *)
            echo "Improper flag or parameter passed to script."
            echo_params
            ;;
    esac
    shift
done

# is config.ini configured?
function get_config_setting() {
    cat config.ini | grep "$1" | awk -F '=' '{print $NF}' | tr -d [:space:]
}
function echo_config_err() {
    echo "config.ini is not configured."
    echo "Please configure config.ini before running this script"
    exit 1
}
if [[ ! -f "config.ini" ]];
then
    cp config.ini.template config.ini
    echo_config_err
else
    USER_NAME=$(get_config_setting ^user_name)
    LICENSE_KEY=$(get_config_setting ^license_key)
    PROJECT_NAME=$(get_config_setting ^project_name)
    PROJECT_TYPE=$(get_config_setting ^project_type)
    if [[ -z ${USER_NAME} || -z ${LICENSE_KEY} || -z ${PROJECT_NAME} || -z ${PROJECT_TYPE} ]];
    then
        echo_config_err
    fi
fi

# Dry run mode?
function is_dry_run() {
    [[ ${DRY_RUN} -gt 0 ]]
}

#######################
# shared portion done #
#######################

function echo_usage() {
    echo "No or invalid run interval specified in config.ini."
    echo "Please edit config.ini and specify how often the cron should run in"
    echo "\tseconds: \"6s\" - must be an integer divisor of 60,"
    echo "\tminutes: \"6m\" or \"6\" (default),"
    echo "\thours: \"6h\", or"
    echo "\tdays: \"6d\""
    exit 1
}

# get interval
RUN_INTERVAL=$(get_config_setting ^run_interval)
if [[ -z "${RUN_INTERVAL}" ]];
then
    RUN_INTERVAL=$(get_config_setting ^sampling_interval)
fi
if [[ -z "${RUN_INTERVAL}" ]];
then
    echo_usage
fi

# get agent
AGENT=$(pwd | awk -F "/" '{print $NF}')
function get_agent_script() {
    \ls -l | awk '{print $NF}' | grep $1
}
AGENT_SCRIPT=$(get_agent_script ^get[^\-].*\.py$)
if [[ -z ${AGENT_SCRIPT} ]];
then
    AGENT_SCRIPT=$(get_agent_script ^replay*\.py$)
fi
if [[ -z ${AGENT_SCRIPT} ]];
then
    echo "No script found. Exiting..."
    exit 1
fi
AGENT_FULL_PATH="$(pwd)/${AGENT_SCRIPT}"
AGENT_FULL_PATH_CONFIG="$(pwd)/config.ini"
AGENT_FULL_PATH_LOG="$(pwd)/log.out"

# crontab
CRON_FILE="/etc/cron.d/${AGENT}"
CRON_USER="root"
CRON_COMMAND="command -p python ${AGENT_FULL_PATH} >${AGENT_FULL_PATH_LOG}"
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
    echo "  ./scripts/cron-config --create"
else
    echo "Cron config created at ${CRON_FILE}"
fi
exit 0

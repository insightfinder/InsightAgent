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

# check for monit
if [[ -z $(command -v monit) ]]; then
    echo "Warning: monit not installed. Please install monit before running this script."
    exit 1
fi

# get agent
AGENT=$(pwd | awk -F "/" '{print $NF}')
AGENT_SCRIPT=$(\ls -l  | awk '{print $NF}' | grep ^get[^\-].*\.py$)
if [[ -z ${AGENT_SCRIPT} ]];
then
    AGENT_SCRIPT=$(\ls -l  | awk '{print $NF}' | grep ^replay.*\.py$)
fi
if [[ -z ${AGENT_SCRIPT} ]];
then
    echo "No script found. Exiting..."
    exit 1
fi
AGENT_FULL_PATH="$(pwd)/${AGENT_SCRIPT}"
AGENT_FULL_PATH_CONFIG="$(pwd)/config.ini"
AGENT_FULL_PATH_LOG="$(pwd)/log.out"
MONIT_FILE="/etc/monit.d/${AGENT}"

if ! is_dry_run;
then
    touch ${MONIT_FILE}
    touch ${AGENT_FULL_PATH_LOG}
    chmod 0666 ${AGENT_FULL_PATH_LOG}
fi

# monit control
echo "
check process ${AGENT} matching \"${AGENT_FULL_PATH}\"
    if does not exist then start
    start program = \"\$(command -v bash) -c '\$(command -v python) ${AGENT_FULL_PATH} &>${AGENT_FULL_PATH_LOG}'\"
    stop program = \"\$(command -v bash) -c '\$(command -v pkill) -f ${AGENT_FULL_PATH}'\"

check file ${AGENT}_config path \"${AGENT_FULL_PATH_CONFIG}\"
    if changed timestamp then restart
    start program = \"\$(command -v bash) -c '\$(command -v python) ${AGENT_FULL_PATH} &>${AGENT_FULL_PATH_LOG}'\"
    stop program = \"\$(command -v bash) -c '\$(command -v pkill) -f ${AGENT_FULL_PATH}'\"
" 2>&1 | if is_dry_run; then awk '{print}'; else tee ${MONIT_FILE}; fi
echo ""

if ! is_dry_run;
then
    echo "Monit config file created at ${MONIT_FILE}"
    monit reload
else
    echo "In dry-run mode. Run as"
    echo "  ./scripts/monit-cronfig.sh --create"
    echo "to create the monit config."
fi
exit 0

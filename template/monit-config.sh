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

# Dry run mode?
function is_dry_run() {
    [[ ${DRY_RUN} -gt 0 ]]
}

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

if is_dry_run;
then
    echo "In dry-run mode. Run as"
    echo "    ./monit-cronfig.sh --create"
    echo "to create the monit config."
else
    touch ${AGENT_FULL_PATH_LOG}
    touch ${MONIT_FILE}
fi

# monit control
echo "
check process ${AGENT} matching \"${AGENT_FULL_PATH}\"
    if does not exist then start
    start program = \"/bin/bash -c \'\$(command -v python) ${AGENT_FULL_PATH} &>${AGENT_FULL_PATH_LOG}\"'
    stop program = \"/bin/bash -c \'\$(command -v pkill) -f ${AGENT_FULL_PATH}\"'

check file ${AGENT}_config path \"${AGENT_FULL_PATH_CONFIG}\"
    if changed timestamp then restart
    start program = \"/bin/bash -c \'\$(command -v python) ${AGENT_FULL_PATH} &>${AGENT_FULL_PATH_LOG}\"'
    stop program = \"/bin/bash -c \'\$(command -v pkill) -f ${AGENT_FULL_PATH}\"'
" |& if is_dry_run; then awk '{print}'; else tee ${MONIT_FILE}; fi
echo ""

if ! is_dry_run;
then
    echo "Monit config file created at ${MONIT_FILE}"
    monit reload
fi
exit 0

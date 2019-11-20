#!/bin/bash

# run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script should be ran as root. Exiting..."
   exit 1
fi

function echo_usage() {
    echo "Usage:"
    echo "'-c'   or '--commit'             : Set this flag to commit the changes from the install."
    echo "'-s N' or '--sampling-interval N': How often to run the cron for this agent in seconds (\"6s\" - must be an integer divisor of 60), minutes (default, \"6m\" or \"6\"), hours (\"6h\"), or days (\"6d\")."
    echo "'-h'   or '--help'               : Display this help text and exit."
    exit 1
}

# Get parameters
DRY_RUN=1
SAMPLING_INTERVAL=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--commit)
            DRY_RUN=0
            ;;
        -s|--sampling-interval)
            shift
            SAMPLING_INTERVAL="$1"
            ;;
        -cs)
            DRY_RUN=0
            shift
            SAMPLING_INTERVAL="$1"
            ;;
        -h|--help)  
            echo_usage
            ;;
        *)
            echo "Improper parameter or flag passed."
            echo_usage
            ;;
    esac
    shift
done

# check sampling interval
#CRONIT_SCRIPT=$(find . -type f -name '*-config.sh' -print)
CRONIT_SCRIPT=$(\ls -l | grep config\.sh | awk '{print $NF}')
CRONIT=$(echo "${CRONIT_SCRIPT}" | sed -E  -e 's:^\.\/(monit|cron)-config\.sh$:\1:')
ERR_MSG="No sampling interval given, but this agent runs on a cron."
if [[ "${CRONIT}" == "cron" ]];
then
    if [[ -n ${SAMPLING_INTERVAL} ]];
    then
        SAMPLING_INTERVAL_VAL=${SAMPLING_INTERVAL}
        SAMPLING_INTERVAL_UNIT="${SAMPLING_INTERVAL: -1}"

        # strip unit
        if [[ ${SAMPLING_INTERVAL_UNIT} =~ [^0-9] ]];
        then
            SAMPLING_INTERVAL_VAL="${SAMPLING_INTERVAL:0:${#SAMPLING_INTERVAL}-1}"
        fi

        # check input
        if [[ "${SAMPLING_INTERVAL_UNIT}" =~ [dhm0-9] || "${SAMPLING_INTERVAL_VAL}" -le 0 || $((${SAMPLING_INTERVAL_VAL} % 1)) -ne 0 || ("${SAMPLING_INTERVAL_UNIT}" = "s" && $((60 % ${SAMPLING_INTERVAL_VAL})) -eq 0) ]];
        then
            echo "${ERR_MSG}"
            echo_usage
        fi

        CRONIT_SCRIPT="${CRONIT_SCRIPT} ${SAMPLING_INTERVAL}"
    else
        echo "${ERR_MSG}"
        echo_usage
    fi
fi

# Dry run mode?
function is_dry_run() {
    [[ ${DRY_RUN} -gt 0 ]]
}

if is_dry_run;
then
    echo "Running in dry-run mode. Run with '-c' or '--commit' flag to execute the changes below."
else
    # check if config.ini exists
    if [[ ! -f "config.ini" ]];
    then
        echo "Please configure config.ini before running this in commit mode."
        echo "Ignoring commit flag and running in dry-run mode"
        cp config.ini.template config.ini
        DRY_RUN=1
    else
        read -p "Running in commit mode. Press [Enter] to continue, or [Ctrl+C] to quit"
    fi
fi

# Python 3 compatability
echo "== Check Python version =="
PY_VER=$(python -V 2>&1 | awk '{print $NF}')
PY_MAJ_VER=${PY_VER:0:1}
echo "Using Python version ${PY_VER}."
if [[ ${PY_MAJ_VER} -eq 3 ]];
then
    echo "Need to upgrade the python script for compatability."
    #AGENT_SCRIPT=$(find . -type f -name "get[^\-]*.py" -print)
    AGENT_SCRIPT=$(\ls -l | grep get[^\-]*.py | awk '{print $NF}')
    if [[ -z ${AGENT_SCRIPT} ]];
    then
        #AGENT_SCRIPT=$(find . -type f -name "replay*.py" -print)
        AGENT_SCRIPT=$(\ls -l | grep replay*.py | awk '{print $NF}')
    fi
    if [[ -z ${AGENT_SCRIPT} ]];
    then
        echo "No script found. Exiting..."
        exit 1
    fi
    AGENT_SCRIPT=${AGENT_SCRIPT:2:${#AGENT_SCRIPT}}
    if is_dry_run;
    then
        echo "Proposed changes:"
        2to3 ${AGENT_SCRIPT}
    else
        echo "Upgrading ${AGENT_SCRIPT}"
        2to3 -w ${AGENT_SCRIPT}
    fi
fi

# pip
if ! is_dry_run;
then
    echo "Setting up pip..."
    ./pip-setup.sh
fi

# Set up cron/monit
echo "== Setting up ${CRONIT} =="
echo "Setup script: \"${CRONIT_SCRIPT}\""
if ! is_dry_run;
then
    ${CRONIT_SCRIPT}
fi

# done
echo "Done with installation."
if is_dry_run;
then
    echo "Please run with '-c' or '--commit' in order to commit these changes."
fi
exit 0

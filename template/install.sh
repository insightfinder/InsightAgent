#!/bin/bash

# run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script should be ran as root. Exiting..."
   exit 1
fi

# is config.ini configured?
if [[ ! -f "config.ini" ]];
then
    echo "Please configure config.ini before running this script"
    cp config.ini.template config.ini
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

if is_dry_run;
then
    echo "Running in dry-run mode. Run with '-c' or '--create' flag to execute the changes below."
else
    read -p "Running in commit mode. Press [Enter] to continue, or [Ctrl+C] to quit"
fi

# Python 3 compatability
echo "== Check Python version =="
PY_VER=$(python -V 2>&1 | awk '{print $NF}')
PY_MAJ_VER=${PY_VER:0:1}
echo "Using Python version ${PY_VER}."
if [[ ${PY_MAJ_VER} -eq 3 ]];
then
    echo "Need to upgrade the python script for compatability."
    AGENT_SCRIPT=$(\ls -l | awk '{print $NF}' | grep ^get[^\-].*\.py$)
    if [[ -z ${AGENT_SCRIPT} ]];
    then
        AGENT_SCRIPT=$(\ls -l | awk '{print $NF}' | grep ^replay.*\.py$)
    fi
    if [[ -z ${AGENT_SCRIPT} ]];
    then
        echo "No script found. Exiting..."
        exit 1
    fi
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
if ! is_dry_run && [[ -f "pip-setup.sh" ]];
then
    echo "Setting up pip..."
    ./pip-setup.sh
fi

# Set up cron/monit
CRONIT_SCRIPT="$(\ls -l | awk '{print $NF}' | grep ^.*-config\.sh$)"
CRONIT=$(echo "${CRONIT_SCRIPT}" | sed -E  -e 's:^(monit|cron)-config\.sh$:\1:')
echo "== Setting up ${CRONIT} =="
if ! is_dry_run;
then
    CRONIT_SCRIPT="${CRONIT_SCRIPT} --create"
fi
echo "Setup script: \"${CRONIT_SCRIPT}\""
./${CRONIT_SCRIPT}

# done
echo "Done with installation."
if is_dry_run;
then
    echo "Please run with '-c' or '--commit' in order to commit these changes."
fi
exit 0

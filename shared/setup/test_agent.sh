#!/usr/bin/env bash

# Utility Functions

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

PY_CMD="$( abspath "venv/bin/python3")"
AGENT_FULL_PATH="$(abspath "./$(get_agent_setting ^script_name)")"

# Test agent with the -t flag, Tests configuration without sending data to IF
echo "Testing Agent Configuration:"
echo "   ${PY_CMD} ${AGENT_FULL_PATH} -t"
echo ""
echo "" 
echo "Agent Output:"
${PY_CMD} ${AGENT_FULL_PATH} -t

# Return to original directory
cd $ORIGIN
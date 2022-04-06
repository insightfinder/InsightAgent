#!/usr/bin/env bash

# Get min value from ./*.ini settings
function get_config_setting() {
  min=1
  config_files=$(find -name "*.ini")
  for file in $config_files; do
    interval=$(cat "$file" | grep "$1" | awk -F '=' '{print $NF}' | tr -d [:space:])
    [ $min -gt "$interval" ] && min=$interval
  done
  echo "$min"
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
    (
      cd "$1"
      pwd
    )
  elif [ -f "$1" ]; then
    # file
    if [[ $1 == /* ]]; then
      echo "$1"
    elif [[ $1 == */* ]]; then
      echo "$(
        cd "${1%/*}"
        pwd
      )/${1##*/}"
    else
      echo "$(pwd)/$1"
    fi
  fi
}

PY_CMD="$(abspath "./venv/bin/python3")"
AGENT="$(get_agent_setting ^name)"
AGENT_FULL_PATH="$(abspath "./$(get_agent_setting ^script_name)")"
AGENT_FULL_PATH_LOG="$(abspath "./")/log.out"
CRON_COMMAND="command -p nohup ${PY_CMD} ${AGENT_FULL_PATH} > ${AGENT_FULL_PATH_LOG} 2>&1"

status=`ps x | grep -v grep | grep -c "$(get_agent_setting ^script_name)"`
  if [[ $status == 0 ]] ; then
        echo "Restarting Kafka Agent:     $(date)" >> "$(abspath "./")/restarter.log" ## Add path to restarter log file
        $CRON_COMMAND ## Add the command here to start the kafka agent
  fi
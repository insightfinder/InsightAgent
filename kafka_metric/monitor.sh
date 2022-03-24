#!/usr/bin/env bash

status=`ps x | grep -v grep | grep -c "$(get_agent_setting ^script_name)"`
  if [[ $status == 0 ]] ; then
        echo "Restarting Kafka Agent:     $(date)" >> "$(abspath "./")/restarter.log" ## Add path to restarter log file
        $CRON_COMMAND ## Add the command here to start the kafka agent
  fi
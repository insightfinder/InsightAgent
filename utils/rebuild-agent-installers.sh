#!/usr/bin/env bash

# make sure we're in top-level dir
if [[ $(pwd | awk -F '/' '{print $NF}') = "utils" ]];
then
    cd ..
fi

# new agents only
AGENTS=$(cat utils/new-agents | tr '|' '\n')
for AGENT in ${AGENTS};
do
    echo "Setting up installer for ${AGENT}"
    
    # find the existing cronit
    CRONIT_SCRIPT="$(\ls -l ${AGENT} | awk '{print $NF}' | grep -E ^\(monit\|cron\)-config\.sh$)"
    CRONIT=$(sed -E  -e 's:^(monit|cron)-config\.sh$:\1:' <<< ${CRONIT_SCRIPT})

    ./utils/make-agent-installer.sh ${AGENT} --${CRONIT} "$@"
done

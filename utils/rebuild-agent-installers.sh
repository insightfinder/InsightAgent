#!/usr/bin/env bash

AGENTS=$(cat new-agents | tr '|' '\n')
for AGENT in ${AGENTS};
do
    echo "Setting up installer for ${AGENT}"
    ./make-agent-installer.sh ${AGENT} "$@"
done

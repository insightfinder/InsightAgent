#!/bin/bash

AGENT_BINARY="{path}/PositronAgent"
AGENT_WORKDIR="{path}"

if pgrep -f "PositronAgent" > /dev/null; then
    exit 0
else
    cd "$AGENT_WORKDIR"
    nohup "$AGENT_BINARY" > nohup.out 2>&1 &
fi
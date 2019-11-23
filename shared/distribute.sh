#!/bin/bash

NODES="$@"
PWD=$(pwd)
AGENT=$(pwd | awk -F '/' '{print $NF}')
AGENT_TAR="${AGENT}-offline.tar.gz"
cd ..
tar czvf ${AGENT_TAR} ${AGENT}

for NODE in ${NODES};
do
    scp ${AGENT_TAR} ${NODE}:/tmp
    ssh ${NODE} 'bash -s' < ${PWD}/install-remote.sh ${AGENT_TAR} ${AGENT}
done

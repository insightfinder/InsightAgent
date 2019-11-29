#!/usr/bin/env bash

# get list of nodes to install on.
function echo_params() {
    echo "Usage:"
    echo "./install-remote.sh node1 node 2 .. nodeN [-f|--node-file <nodefile>]"
    echo "-f --node-file    A file containing a list of nodes to install on"
    echo "-h --help         Display this help text and exit"
    exit 0
}

NODES=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--node-file)
            shift
            NODES="${NODES} $(cat $1)"
            ;;  
        -h|--help)
            echo_params
            ;;
        *)  
            NODES="${NODES} $1"
            ;;  
    esac
    shift
done

if [[ -z ${NODES} ]];
then
    echo "No nodes specified."
    echo_params
else
    echo "Installing this agent on ${NODES}"
fi

# build script to run on remote machines since it's small and only needed for this
REMOTE_SCRIPT=remote-install-autogen.sh
cat <<EOF > ${REMOTE_SCRIPT}
#!/bin/bash

tar xvf /tmp/\$1 && cd \$2
./install.sh --create
EOF
sudo chmod ug+x ${REMOTE_SCRIPT}

PWD=$(pwd)
AGENT=$(pwd | awk -F '/' '{print $NF}')
AGENT_TAR="${AGENT}-offline.tar.gz"
cd ..
tar czvf ${AGENT_TAR} ${AGENT}

for NODE in ${NODES};
do
    scp ${AGENT_TAR} ${NODE}:/tmp
    ssh ${NODE} 'sudo bash -s' < ${PWD}/${REMOTE_SCRIPT} ${AGENT_TAR} ${AGENT}
done

rm -f ${PWD}/${REMOTE_SCRIPT}

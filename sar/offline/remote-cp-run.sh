#!/bin/bash

# get list of nodes to install on.
function echo_params() {
    echo "Usage:"
    echo "./remote-cp-run.sh node1 node 2 .. nodeN [-f <nodefile>] [-p param1 -p param2 ... ]"
    echo "-f --node-file    A file containing a list of target nodes."
    echo "-t --tarball <>   The tarball to copy to the remote machine(s); done before running any script. Optional."
    echo "-s --script <>    The script to execute on the remote machine(s). Optional."
    echo "-p --param <>     A parameter to pass through to ./configure. Can be used multiple times to pass multiple flags."
    echo "-h --help         Display this help text and exit"
    exit 0
}

NODES=""
PARAMS=""
TARBALL=""
SCRIPT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--node-file)
            shift
            NODES="${NODES} $(cat $1)"
            ;;  
		-p|--param)
			shift
            PARAMS="${PARAMS} $1"
            ;;
		-t|--tarball)
			shift
            TARBALL="$1"
            ;;
		-s|--script)
			shift
            SCRIPT="$1"
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
fi

for NODE in ${NODES};
do
    if [[ -f ${TARBALL} ]];
    then
        echo "Copying ${TARBALL} to ${NODE}:/tmp"
        scp ${TARBALL} ${NODE}:/tmp
    fi

    if [[ -f ${SCRIPT} ]];
    then
        echo "Running ${SCRIPT} ${PARAMS} on ${NODE}"
        ssh ${NODE} 'sudo bash -s' < ${SCRIPT} ${PARAMS}
    fi
done


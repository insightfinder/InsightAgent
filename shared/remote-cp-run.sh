#!/usr/bin/env bash

function echo_params() {
    if [[ ${QUIET} -eq 1 ]];
    then
        exit 0
    fi

    echo "Usage:"
    echo "./remote-cp-run.sh [-d <definitionfile>] [node1 node2 .. nodeN [-f <nodefile>] [-c <file_to_copy>] [-s <script>|-x <command> [-p param1 -p param2 ... ]]]"
    echo "-d --definition-file <>   The file containing definitions for the other parameters in this script. Default is '${DEFNS_DEFAULT}'"
    echo "                              The file will be generated/updated on each run."
    echo "-f --node-file <>         The file containing a list of target nodes. Optional if nodes passed as list. Default is '${NODE_FILE_DEFAULT}'"
    echo "-c --copy-file <>         A file to copy to the remote machine(s); done before running any script. Can be used multiple times to copy multiple files. Optional."
    echo "-s --script <>            The script to execute on the remote machine(s). Optional."
    echo "-x --execute <>           The command to execute on the remote machine(s). Optional."
    echo "-p --param <>             A parameter to pass through to BOTH the script and commands to execute. Can be used multiple times to pass multiple flags. Optional."
    echo "-h --help                 Display this help text and exit."
    exit 1
}

NEWLINE=$'\n'
QUIET=0
DEFNS_DEFAULT="definitions"
NODE_FILE_DEFAULT="nodes"
DEFNS=${DEFNS_DEFAULT}
NODE_FILE=${NODE_FILE_DEFAULT}
NODES=""
TO_COPY=""
COMMAND=""
SCRIPT=""
PARAMS=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--node-file)
            shift
            NODE_FILE="$1"
            NODES="${NODES}${NEWLINE}$(cat $1 | tr [:space:] '\n')"
            ;;  
		-c|--copy-file)
			shift
            TO_COPY="${TO_COPY} $1"
            ;;
		-s|--script)
			shift
            SCRIPT="$1"
            ;;
        -x|--execute)
            shift
            COMMAND="$1"
            ;;
		-p|--param)
			shift
            PARAMS="${PARAMS} $1"
            ;;
        -d|--definition-file)
            shift
            DEFNS="$1"
            ;;
        -h|--help)
            echo_params
            ;;  
        --quiet)
            QUIET=1
            ;;
        *)  
            NODES="${NODES}${NEWLINE}$1"
            ;;  
    esac
    shift
done

# see if there's a definitions file for fallback values
if [[ -f ${DEFNS} ]];
then
    if [[ -z ${TO_COPY} ]];
    then
        TO_COPY=$(cat ${DEFNS} | grep TO_COPY | awk -F '=' '{print $NF}')
    fi
    if [[ -z ${SCRIPT} ]];
    then
        SCRIPT=$(cat ${DEFNS} | grep SCRIPT | awk -F '=' '{print $NF}')
    fi
    if [[ -z ${COMMAND} ]];
    then
        COMMAND=$(cat ${DEFNS} | grep COMMAND | awk -F '=' '{print $NF}')
    fi
    if [[ -z ${PARAMS} ]];
    then
        PARAMS=$(cat ${DEFNS} | grep PARAMS | awk -F '=' '{print $NF}')
    fi
    if [[ -z ${NODES} ]];
    then
        # see if a node file is defined here; if not, fall back to 'nodes', as the -n|--node-file flag must not have added any nodes 
        NODE_FILE_temp=$(cat ${DEFNS} | grep NODE_FILE | awk -F '=' '{print $NF}')
        if [[ -f ${NODE_FILE_temp} ]];
        then
            NODE_FILE=${NODE_FILE_temp}
        else
            NODE_FILE=${NODE_FILE_DEFAULT}
        fi
        NODES=$(cat ${NODE_FILE} 2>/dev/null)
    fi
fi

## If no proper parameters are set, assume we're installing an agent
INSTALL_AGENT=0
if [[ -z ${COMMAND} && ! -f ${SCRIPT} && ! -f ${TO_COPY} ]];
then
    # build script
    SCRIPT="AUTOGEN-remote-install.sh"
    if [[ ! -f ${SCRIPT} ]];
    then
        echo "#!/usr/bin/env bash" > ${SCRIPT}
        echo "" >> ${SCRIPT}
        echo "dir=\$(tar tf /tmp/\$1 | head -n1)" >> ${SCRIPT}
        echo "tar xvf /tmp/\$1 && cd \$dir" >> ${SCRIPT}
        echo "./install.sh --create" >> ${SCRIPT}
    fi
    sudo chmod ug+x ${SCRIPT}

    AGENT_DIR=$(pwd)
    AGENT=$(pwd | awk -F '/' '{print $NF}')
    AGENT_TAR="${AGENT}-offline.tar.gz"

    # set params
    PARAMS="${AGENT_TAR}"
    TO_COPY="${AGENT_TAR}"
    INSTALL_AGENT=1
fi

# make nodefile
echo "Creating/updating node file ${NODE_FILE}"
echo "${NODES}" > "${NODE_FILE}"

# create definitions
echo "Creating/updating definitions file ${DEFNS}"
echo "NODE_FILE=${NODE_FILE}" > ${DEFNS}
echo "TO_COPY=${TO_COPY}" >> ${DEFNS}
echo "SCRIPT=${SCRIPT}" >> ${DEFNS}
echo "COMMAND=${COMMAND}" >> ${DEFNS}
echo "PARAMS=${PARAMS}" >> ${DEFNS}

# make offline installer tar; move check here so
#  defn file is created anyway
if [[ ${INSTALL_AGENT} -eq 1 ]];
then
    if [[ -f config.ini ]];
    then
        cd ..
        tar czvf ${AGENT_TAR} ${AGENT_DIR}
        mv ${AGENT_TAR} ${AGENT_DIR}
        cd -
    else
        if [[ ${QUIET} -eq 1 ]];
        then
            exit 0
        fi

        echo "Agent not configured - set up config.ini first. Exiting..."
        exit 1
    fi
fi

# must have nodes to run on
if [[ -z ${NODES} ]]; 
then
    echo "No nodes specified."
    echo_params
fi

# actually do the work on each node
for NODE in ${NODES};
do
    if [[ -f ${TO_COPY} ]];
    then
        echo "Copying ${TO_COPY} to ${NODE}:/tmp"
        scp ${TO_COPY} ${NODE}:/tmp
    fi

    if [[ -f ${SCRIPT} ]];
    then
        echo "Running ${SCRIPT} ${PARAMS} on ${NODE}"
        ssh ${NODE} 'sudo bash -s' < ${SCRIPT} ${PARAMS}
    fi

    if [[ -n ${COMMAND} ]];
    then
        echo "Running ${COMMAND} ${PARAMS} on ${NODE}"
        ssh ${NODE} ${COMMAND} ${PARAMS}
    fi
done

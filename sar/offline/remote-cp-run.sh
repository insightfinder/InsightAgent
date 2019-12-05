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
NODE_FILE_DEFAULT="nodefile"
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
		-cp) # used for installing from source using 
			shift
            TO_COPY="$1"
            PARAMS="-t ${1##*/}"
            SCRIPT="make-install.sh"
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
    if [[ -z ${COMMAND} && -z ${SCRIPT} ]];
    then
        SCRIPT=$(cat ${DEFNS} | grep SCRIPT | awk -F '=' '{print $NF}')
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
    AGENT=$(pwd | awk -F '/' '{print $NF}')
    if [[ ${AGENT} == "offline" ]];
    then
        NODE_FILE="$(pwd)/${NODE_FILE}"
        if [[ -f ${NODE_FILE} ]];
        then
            NODE_FILE="$(pwd)/${NODE_FILE}"
        fi
        cd ..
        AGENT=$(pwd | awk -F '/' '{print $NF}')
    fi
    AGENT_TAR="${AGENT}-offline.tar.gz"

    # set params
    INSTALL_AGENT=1
    TO_COPY="${AGENT_TAR}"
    PARAMS="${AGENT_TAR##*/}"
    SCRIPT="AUTOGEN-remote-install.sh"

    # build script
    if [[ ! -f ${SCRIPT} ]];
    then
        echo "#!/usr/bin/env bash"                  >  ${SCRIPT}
        echo ""                                     >> ${SCRIPT}
        echo "dir=\$(tar tf /tmp/\$1 | head -n1)"   >> ${SCRIPT}
        echo "tar xvf /tmp/\$1 && cd \$dir"         >> ${SCRIPT}
        echo "./install.sh --create"                >> ${SCRIPT}
    fi
    sudo chmod ug+x ${SCRIPT}
fi

# make nodefile
NODES=$(sed '/^$/d' <<< "${NODES}")
echo "Creating/updating node file ${NODE_FILE}"
echo "${NODES}" > "${NODE_FILE}"

# create definitions
echo "Creating/updating definitions file ${DEFNS}"
echo "NODE_FILE=${NODE_FILE}" | sed -E -e 's/\=\s*(.*)\s*$/=\1/' >  ${DEFNS}
echo "TO_COPY=${TO_COPY}"     | sed -E -e 's/\=\s*(.*)\s*$/=\1/' >> ${DEFNS}
echo "SCRIPT=${SCRIPT}"       | sed -E -e 's/\=\s*(.*)\s*$/=\1/' >> ${DEFNS}
echo "COMMAND=${COMMAND}"     | sed -E -e 's/\=\s*(.*)\s*$/=\1/' >> ${DEFNS}
echo "PARAMS=${PARAMS}"       | sed -E -e 's/\=\s*(.*)\s*$/=\1/' >> ${DEFNS}

# make offline installer tar
if [[ ${INSTALL_AGENT} -eq 1 ]];
then
    if [[ -f config.ini ]];
    then
        cd ..
        tar czvf ${TO_COPY} ${AGENT}
        mv ${TO_COPY} ${AGENT_DIR}
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

function scp_ssh_syntax() {
    TO_COPY_tmp="$1"
    shift
    DEST="$@"
    if [[ $(echo ${DEST} | wc -w) -gt 1 ]];
    then
        FLAGS_tmp=${DEST% *}
        NODE_tmp=${DEST##* }
    else
        FLAGS_tmp=""
        NODE_tmp=${DEST}
    fi
    scp ${FLAGS_tmp} ${TO_COPY_tmp} ${NODE_tmp}:/tmp
}

# actually do the work on each node
for NODE in ${NODES};
do
    if [[ -n ${TO_COPY} ]];
    then
        echo "Copying ${TO_COPY} to ${NODE}:/tmp"
        scp_ssh_syntax ${TO_COPY} ${NODE}
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

#!/bin/bash

# get input params
function echo_params() {
    echo "Usage:"
    echo "./utils/makeAgentInstaller [agent] [-r] [-b] [-m]"
    echo "-r --readme   If set, the README for this agent will be remade from the template."
    echo "-b --rebuild  If set, the supporting files will be overwritten"
    echo "-m --monit    If set, monit-config.sh will be used. Default: cron-config.sh"
    echo "-h --help     Display this help text and exit."
    echo "If no agent is specified, the most recently modified folder will be used."
    exit 1
}

README=0
REBUILD=0
CRONIT="cron"
while [[ $# -gt 0 ]]; do
    case "$1" in
        -r|--readme)
            README=1
            ;;
        -b|--rebuild)
            REBUILD=1
            ;;
        -m|--monit)
            CRONIT="monit"
            ;;
        -h|--help)
            echo_params
            ;;  
        *)  shift
            AGENT=$1
            ;;  
    esac
    shift
done

CRONIT_SCRIPT="${CRONIT}-config.sh"
PWD=$(pwd)
DIR=$(pwd | awk -F '/' '{print $NF}')
if [[ $(\ls -l | awk '{print $NF}' | grep ${DIR} | wc -l) -eq 0 ]]; # probably not an agent folder
then
    # pass agent as parameter
    if [[ -z ${AGENT} || ! -d ${AGENT} ]];
    then
        AGENT=$(\ls -lrt | grep ^d | tail -n1 | awk '{print $NF}')
        echo "No agent to build specified. Using most recently modified folder: ${AGENT}"
        read -p "Press [Enter] to continue, [Ctrl+C] to quit"
    fi
    cd ${AGENT}
else
    AGENT=${DIR}
fi

# determine agent name and path
AGENT_PATH="${AGENT}/"
if [[ "${AGENT: -1}" = '/' ]]; then
    AGENT_PATH=${AGENT}
    AGENT="${AGENT:0:${#AGENT}-1}"
fi

#### get some vars from the agent folder ####
# get agent script
function get_agent_script() {
    \ls -l | awk '{print $NF}' | grep $1
}
AGENT_SCRIPT=$(get_agent_script ^get[^\-].*\.py$)
if [[ -z ${AGENT_SCRIPT} ]];
then
    AGENT_SCRIPT=$(get_agent_script ^replay*\.py$)
fi

# update readme
sed -e '/^{{{$/,/^}}}$/{d;}' -i "" README.md
sed -e "s/{{NEWAGENT}}/${AGENT}/g" -i "" README.md
sed -e "s/{{NEWAGENT&script}}/${AGENT_SCRIPT}/g" -i "" README.md
sed -e "s/{{NEWAGENT&cronit}}/${CRONIT_SCRIPT}/g" -i "" README.md
sed -e '/^{{CONFIGVARS}}/{r _CONFIGVARS.md' -e 'd;}' -i "" README.md

# additional info
if [[ -f _SPECIAL.md && $(tail -n1 _SPECIAL.md | wc | awk '{print $NF}') -gt 0 ]];
then
    # end file with an empty line
    echo "" >> SPECIAL.md
fi
if [[ -f _SPECIAL.md && $(head -n1 _SPECIAL.md | wc | awk '{print $NF}') -gt 0 ]];
then
    # start file with an empty line
    echo $'\n'"$(cat _SPECIAL.md)" > _SPECIAL.md
fi
sed -e '/^{{EXTRA}}/{r _SPECIAL.md' -e 'd;}' -i "" README.md

# go up to top level
cd ..

# copy things from shared/
CP_CMD=\cp
if [[ ${REBUILD} -eq 0 ]];
then
    CP_CMD="${CP_CMD} -n"
fi
${CP_CMD} -r shared/offline/* ${AGENT_PATH}offline/
${CP_CMD} shared/install.sh ${AGENT_PATH}
${CP_CMD} shared/install-remote.sh ${AGENT_PATH}
${CP_CMD} shared/distribute.sh ${AGENT_PATH}
${CP_CMD} shared/pip-setup.sh ${AGENT_PATH}
${CP_CMD} shared/${CRONIT_SCRIPT} ${AGENT_PATH}
if [[ ${README} -gt 0 || ! -f "${AGENT_PATH}README.md" ]];
then
    cp shared/README.md ${AGENT_PATH}
fi

# scrub any slashes in the name (ie neseted folders)
AGENT_SCRUBBED=$(sed -e "s:\/:\-:g" <<< ${AGENT})

# determine tarball name
TARBALL_NAME="${AGENT_SCRUBBED}.tar.gz"
TARBALL_PATH="${AGENT_PATH}${TARBALL_NAME}"

echo "Removing old tarball"
rm ${TARBALL_PATH}

echo "Creating tarball ${TARBALL_NAME}"
EXCLUDE_LIST="'_*' '*.out' '*.pyc' '*.bck' '*.old' '.*' 'config.ini'"
EXCLUDE_STMT=""
for EXCLUDE in ${EXCLUDE_LIST};
do
    EXCLUDE_STMT="${EXCLUDE_STMT} --exclude=${EXCLUDE}"
done
tar czvf ${TARBALL_NAME} ${EXCLUDE_STMT} ${AGENT_PATH}

echo "Moving tarball into ${AGENT_PATH}"
mv ${TARBALL_NAME} ${AGENT_PATH}

#!/bin/bash

# get input params
function echo_params() {
    echo "Usage:"
    echo "./utils/make-agent-installer.sh [agent] [-m] [-r] [-b] [-n]"
    echo "-m --monit    If set, monit-config.sh will be used. Default: cron-config.sh"
    echo "-r --readme   If set, the README for this agent will be remade from the template."
    echo "-b --build    If set, the supporting files will be overwritten"
    echo "-n --no-git   If set, nothing will be added to git. Default: Created files are added to git"
    echo "-h --help     Display this help text and exit."
    echo "If no agent is specified, the most recently modified folder will be used."
    exit 1
}

README=0
REBUILD=0
CRONIT="cron"
add="git add "
while [[ $# -gt 0 ]]; do
    case "$1" in
        -r|--readme)
            README=1
            ;;
        -b|--build)
            REBUILD=1
            ;;
        -m|--monit)
            CRONIT="monit"
            ;;
        -n|--no-git)
            add="ls -l "
            ;;
        -h|--help)
            echo_params
            ;;  
        *)
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
echo "Updating README.md"
if [[ ${README} -gt 0 || ! -f "${AGENT_PATH}README.md" ]];
then
    echo "  Copying template README.md"
    \cp ../template/README.md .
fi
sed -e '/^{{{$/,/^}}}$/{d;}' -i "" README.md
sed -e "s/{{NEWAGENT}}/${AGENT}/g" -i "" README.md
sed -e "s/{{NEWAGENT@script}}/${AGENT_SCRIPT}/g" -i "" README.md
sed -e "s/{{NEWAGENT@cronit}}/${CRONIT_SCRIPT}/g" -i "" README.md

echo "  Adding config variables"
sed -e '/^{{CONFIGVARS}}/{r @CONFIGVARS.md' -e 'd;}' -i "" README.md

# additional info
echo "  Adding extra data"
if [[ -f @EXTRA.md && $(tail -n1 @EXTRA.md | wc | awk '{print $NF}') -gt 0 ]];
then
    # end file with an empty line
    echo "" >> EXTRA.md
fi
if [[ -f @EXTRA.md && $(head -n1 @EXTRA.md | wc | awk '{print $NF}') -gt 0 ]];
then
    # start file with an empty line
    echo $'\n'"$(cat @EXTRA.md)" > @EXTRA.md
fi
sed -e '/^{{EXTRA}}/{r @EXTRA.md' -e 'd;}' -i "" README.md

# add everything currently in agent folder
${add} ./*

# go up to top level
cd ..

echo "Copying files from shared/"
alias cp=\cp
if [[ ${REBUILD} -eq 0 ]];
then
    # no clobber
    alias cp="cp -n"
fi
cp -r shared/offline/* ${AGENT_PATH}offline/
cp shared/install.sh ${AGENT_PATH}
cp shared/install-remote.sh ${AGENT_PATH}
cp shared/pip-config.sh ${AGENT_PATH}
cp shared/${CRONIT_SCRIPT} ${AGENT_PATH}

echo "Creating package"
# scrub any slashes in the name (ie neseted folders)
AGENT_SCRUBBED=$(sed -e "s:\/:\-:g" <<< ${AGENT})

# determine tarball name
TARBALL_NAME="${AGENT_SCRUBBED}.tar.gz"
TARBALL_PATH="${AGENT_PATH}${TARBALL_NAME}"

echo "  Removing old tarball"
rm ${TARBALL_PATH}

echo "  Creating tarball ${TARBALL_NAME}"
EXCLUDE_LIST="'*.tar.gz' '@*' '*.out' '*.pyc' '*.bck' '*.old' '.*' 'config.ini'"
EXCLUDE_STMT=""
for EXCLUDE in ${EXCLUDE_LIST};
do
    EXCLUDE_STMT="${EXCLUDE_STMT} --exclude=${EXCLUDE}"
done
TAR_CMD="tar czvf ${TARBALL_NAME} ${EXCLUDE_STMT} ${AGENT_PATH}"
echo "${TAR_CMD}" | bash -

echo "  Moving tarball into ${AGENT_PATH}"
mv ${TARBALL_NAME} ${AGENT_PATH}
${add} ${TARBALL_PATH}

# add to list of valid agents
echo "Installer created."
if [[ $(cat utils/new-agents | grep ${AGENT} | wc -l) -eq 0 ]];
then
    printf "%s" "|${AGENT}" >> utils/new-agents
    ${add} utils/new-agents
fi

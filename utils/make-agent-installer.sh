#!/bin/bash

# get input params
function echo_params() {
    echo "Usage:"
    echo "./utils/make-agent-installer.sh [agent] [-m] [-r] [-b] [-g]"
    echo "-m --monit    If set, monit-config.sh will be used. Default: cron-config.sh"
    echo "-c --cron     If set, cron-config.sh will be used. This is the default"
    echo "-r --readme   If set, the README for this agent will be remade from the template"
    echo "-b --build    If set, the supporting files (other than READMEs) will be overwritten."
    echo "-g --git-add  If set, the agent folder will be added to git. Default: nothing added"
    echo "-h --help     Display this help text and exit"
    echo "If no agent is specified, the most recently modified folder will be used."
    exit 1
}

README=0
REBUILD=0
ADD="ls -l"
CRONIT_SCRIPT="cron-config.sh"
while [[ $# -gt 0 ]]; do
    case "$1" in
        -m|--monit)
            CRONIT_SCRIPT="monit-config.sh"
            ;;
        -c|--cron)
            CRONIT_SCRIPT="cron-config.sh"
            ;;
        -r|--readme)
            README=1
            ;;
        -b|--build)
            REBUILD=1
            ;;
        -g|--git-add)
            ADD="git add "
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

# make sure we have the agent to build and are in the agent directory
DIR=$(pwd | awk -F '/' '{print $NF}')
if [[ $(\ls -l | grep -E ^[^d] | awk '{print $NF}' | grep ${DIR} | wc -l) -eq 0 ]]; # probably not an agent folder
then
    if [[ -z ${AGENT} || ! -d ${AGENT} ]];
    then
        AGENT=$(\ls -lrt | grep -E $(cat utils/new-agents) | tail -n1 | awk '{print $NF}')
        echo "No agent to build specified. Using most recently modified folder: ${AGENT}"
        read -p "Press [Enter] to continue, [Ctrl+C] to quit"
    fi
    BASE_DIR=$(pwd)
else
    if [[ -z ${AGENT} ]];
    then
        AGENT=${DIR}
    fi
    BASE_DIR=$(pwd | awk -F '/' '{$NF=""; print $0}' | tr [:space:] '/')
fi
TEMPLATE_DIR="${BASE_DIR}/template"
SHARED_DIR="${BASE_DIR}/shared"
UTILS_DIR="${BASE_DIR}/utils"
AGENT_DIR="${BASE_DIR}/${AGENT}"
if [[ "${AGENT: -1}" = '/' ]]; then
    AGENT="${AGENT:0:${#AGENT}-1}"
fi

# get agent script from the agent folder
cd ${AGENT_DIR}
function get_agent_script() {
    ls -l | awk '{print $NF}' | grep $1
}
AGENT_SCRIPT=$(get_agent_script ^get[^\-].*\.py$)
if [[ -z ${AGENT_SCRIPT} ]];
then
    AGENT_SCRIPT=$(get_agent_script ^replay*\.py$)
fi

## update readme
echo "Updating README.md"
COPY=$(command -v cp)
LOCS=". offline" # agent dir, then offline
for LOC in ${LOCS};
do
    mkdir -p "${LOC}"
    cd "${LOC}"

    # copy from template
    if [[ ${README} -eq 1 || ! -f README.md ]];
    then
        echo "  Copying template README.md"
        ${COPY} ${TEMPLATE_DIR}/${LOC}/README.md .
    fi

    # remove preamble
    sed -e '/^{{{$/,/^}}}$/{d;}' -i "" README.md 2>/dev/null

    # replace AGENT variables
    sed -e "s/{{NEWAGENT}}/${AGENT}/g" -i "" README.md 2>/dev/null
    sed -e "s/{{NEWAGENT@script}}/${AGENT_SCRIPT}/g" -i "" README.md 2>/dev/null
    sed -e "s/{{NEWAGENT@cronit}}/${CRONIT_SCRIPT}/g" -i "" README.md 2>/dev/null
    
    # Replace TARGET or TARGET preamble
    TARGET=$(cat target 2>/dev/null | awk -F '/' '{print $NF}')
    if [[ -n "${TARGET}" ]];
    then
        sed -e "s/{{TARGET}}/${TARGET}/g" -i "" README.md 2>/dev/null
        sed -e '/^{{{TARGET$/{d;}' -i "" README.md 2>/dev/null
        sed -e '/^TARGET}}}$/{d;}' -i "" README.md 2>/dev/null
    else
        sed -e '/^{{{TARGET$/,/^TARGET}}}$/{d;}' -i "" README.md 2>/dev/null
    fi 

    # add separate list of config variables
    echo "  Adding config variables"
    sed -e '/^{{CONFIGVARS}}/{r .CONFIGVARS.md' -e 'd;}' -i "" README.md 2>/dev/null

    # additional info
    echo "  Adding extra data"
    if [[ -f .EXTRA.md && $(tail -n1 .EXTRA.md | wc | awk '{print $NF}') -gt 1 ]];
    then
        # end file with an empty line
        echo "" >> .EXTRA.md
    fi
    if [[ -f .EXTRA.md && $(head -n1 .EXTRA.md | wc | awk '{print $NF}') -gt 1 ]];
    then
        # start file with an empty line
        echo $'\n'"$(cat .EXTRA.md)" > .EXTRA.md
    fi
    sed -e '/^{{EXTRA}}/{r .EXTRA.md' -e 'd;}' -i "" README.md 2>/dev/null
done
cd ${AGENT_DIR}
## finished README

# set up pip if needed
if [[ (! -d ./offline/pip/packages || ! -f requirements.txt) && -f ${UTILS_DIR}/pip-requirements.sh ]];
then
   ${UTILS_DIR}/pip-requirements.sh
fi

# go up to top level
cd ${BASE_DIR}

# add supporting files
echo "Copying files from shared/"
if [[ ${REBUILD} -eq 0 ]];
then
    # no clobber
    COPY="${COPY} -n"
fi
${COPY} ${SHARED_DIR}/install.sh ${AGENT_DIR}
${COPY} ${SHARED_DIR}/pip-config.sh ${AGENT_DIR}
${COPY} ${SHARED_DIR}/${CRONIT_SCRIPT} ${AGENT_DIR}
${COPY} ${SHARED_DIR}/offline/* ${AGENT_DIR}/offline/ 2>/dev/null
if [[ "${CRONIT_SCRIPT}" =~ monit ]];
then
    ${COPY} -r ${SHARED_DIR}/offline/monit/ ${AGENT_DIR}/offline/
fi

## create tar
echo "Creating package"
# scrub any slashes in the name (ie neseted folders)
AGENT_SCRUBBED=$(sed -e "s:\/:\-:g" <<< ${AGENT})

# determine tarball name
TARBALL_NAME="${AGENT_SCRUBBED}.tar.gz"
TARBALL_PATH="${AGENT_DIR}/${TARBALL_NAME}"

echo "  Removing old tarball"
rm ${TARBALL_PATH}

echo "  Creating tarball ${TARBALL_NAME}"
EXCLUDE_LIST="'@*' '*.out' '*.pyc' '*.bck' '*.old' '.*' 'config.ini'"
EXCLUDE_STMT=""
for EXCLUDE in ${EXCLUDE_LIST};
do
    EXCLUDE_STMT="${EXCLUDE_STMT} --exclude=${EXCLUDE}"
done
TAR_CMD="tar czvf ${TARBALL_NAME} ${EXCLUDE_STMT} ${AGENT}"
echo "${TAR_CMD}" | bash -

echo "  Moving tarball into ${AGENT_DIR}"
mv ${TARBALL_NAME} ${AGENT_DIR}

echo "Installer created."
${ADD} ${AGENT_DIR}
# add to list of valid agents
if [[ $(cat ${UTILS_DIR}/new-agents | grep ${AGENT} | wc -l) -eq 0 ]];
then
    echo "$(cat ${UTILS_DIR}/new-agents)|${AGENT}" > ${UTILS_DIR}/new-agents
    ${ADD} ${UTILS_DIR}/new-agents
fi

exit 0

#!/bin/bash

# pass agent as parameter
AGENT=$1
if [[ -z ${AGENT} ]]; then
    AGENT=$(\ls -lrt | grep ^d | tail -n1 | awk '{print $NF}')
    echo "No agent to build specified. Using most recently modified folder: ${AGENT}"
    read -p "Press [Enter] to continue, [Ctrl+C] to quit"
fi

# determine agent name and path
AGENT_PATH="${AGENT}/"
if [[ "${AGENT: -1}" = '/' ]]; then
    AGENT_PATH=${AGENT}
    AGENT="${AGENT:0:${#AGENT}-1}"
fi

#### get some vars from the agent folder ####
cd ${AGENT_PATH}
# get agent script
function get_agent_script() {
    \ls -l | awk '{print $NF}' | grep $1
}
AGENT_SCRIPT=$(get_agent_script ^get[^\-].*\.py$)
if [[ -z ${AGENT_SCRIPT} ]];
then
    AGENT_SCRIPT=$(get_agent_script ^replay*\.py$)
fi

# get cronit
CRONIT_SCRIPT="$(\ls -l | awk '{print $NF}' | grep ^.*-config\.sh$)"

# update readme
sed -e '/^{{{/,/^}}}/{d;}' -i "" README.md
sed -e "s/{{NEWAGENT}}/${AGENT}/g" -i "" README.md
sed -e "s/{{NEWAGENT&script}}/${AGENT_SCRIPT}/g" -i "" README.md
sed -e "s/{{NEWAGENT&cronit}}/${CRONIT_SCRIPT}/g" -i "" README.md

# return
cd -
####

# scrub any slashes in the name (ie neseted folders)
AGENT_SCRUBBED=$(sed -e "s:\/:\-:g" <<< ${AGENT})

# determine tarball name
TARBALL_NAME="${AGENT_SCRUBBED}.tar.gz"
TARBALL_PATH="${AGENT_PATH}${TARBALL_NAME}"

echo "Removing old tarball"
rm ${TARBALL_PATH}

echo "Creating tarball ${TARBALL_NAME}"
tar czvf ${TARBALL_NAME} --exclude='*.out' --exclude='config.ini' --exclude='*.pyc' --exclude='*.bck' --exclude='.*' ${AGENT_PATH}

echo "Moving tarball into ${AGENT_PATH}"
mv ${TARBALL_NAME} ${AGENT_PATH}

#!/bin/bash

# pass agent as parameter
AGENT=$1
if [[ -z ${AGENT} ]]; then
    AGENT=$(\ls -lrt | grep ^d | tail -n1 | awk '{print $NF}')
    echo "No agent to build specified. Using most recently modified folder: ${AGENT}"
    read -p "Press [Enter] to continue, [Ctrl+C] to quit"
fi

# determine agent name and path
if [[ "${AGENT: -1}" = '/' ]]; then
    AGENT_PATH=${AGENT}
    AGENT="${AGENT:0:${#AGENT}-1}"
else
    AGENT_PATH="${AGENT}/"
fi

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

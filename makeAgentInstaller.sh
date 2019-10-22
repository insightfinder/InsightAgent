#!/bin/bash

# pass agent as parameter
AGENT=$1
if [[ -z ${AGENT} ]]; then
    echo "No agent to build specified. Please supply an agent name"
    exit 1
fi

if [[ "${AGENT: -1}" = '/' ]]; then
    AGENT_PATH=${AGENT}
    AGENT="${AGENT:0:${#AGENT}-1}"
else
    AGENT_PATH="${AGENT}/"
fi

AGENT_SCRUBBED=$(sed -e "s:\/:\-:g" <<< ${AGENT})
TARBALL_NAME="${AGENT_SCRUBBED}.tar.gz"
TARBALL_PATH="${AGENT_PATH}${TARBALL_NAME}"

echo "Removing old tarball"
rm ${TARBALL_PATH}

echo "Creating tarball ${TARBALL_NAME}"
tar czf ${TARBALL_NAME} ${AGENT_PATH}

echo "Moving tarball into ${AGENT_PATH}"
mv ${TARBALL_NAME} ${AGENT_PATH}
tar tf ${TARBALL_PATH}

#!/usr/bin/env bash

ALWAYS_DOWNLOAD=0
if [[ "$@" =~ -r|--remote ]];
then
    ALWAYS_DOWNLOAD=1
    shift
fi

GNU_MIRROR="$1"
if [[ -z ${GNU_MIRROR} ]];
then
    GNU_MIRROR="ftp://prep.ai.mit.edu/pub/gnu/"
else
    shift
fi

CURL="curl -sSL"

# get most recent make
if [[ -z $(command -v make) || ${ALWAYS_DOWNLOAD} -eq 1 ]];
then
    echo "Getting make..."
    mkdir -p make
    MAKE_MIRROR="${GNU_MIRROR}/make/"
    MAKE_VERISON=$(${CURL} ${MAKE_MIRROR} | grep -o make-[0-9\.]*tar\.gz | uniq | sort -V | tail -n1)
    MAKE_FILE="make/${MAKE_VERISON}"
    MAKE_DOWNLOAD="${CURL} ${MAKE_MIRROR}/${MAKE_VERISON} -o ${MAKE_FILE}"
    ${MAKE_DOWNLOAD}
fi

# get most recent python
if [[ -z $(command -v python) || ${ALWAYS_DOWNLOAD} -eq 1 ]];
then
    echo "Getting python..."
    mkdir -p python
    PY_MIRROR="https://www.python.org/ftp/python/"
    PY_VERSION_NUM=$(${CURL} ${PY_MIRROR} | grep -oE [0-9]+\.[0-9]+\.[0-9]+\/ | tail -n1)
    PY_MIRROR="${PY_MIRROR}/${PY_VERSION_NUM}"
    PY_VERSION=$(${CURL} ${PY_MIRROR} | grep -oE '>Python\-.*\.tgz<' | tr -d '><')
    PY_FILE="python/${PY_VERSION}"
    PY_DOWNLOAD="${CURL} ${PY_MIRROR}/${PY_VERSION} -o ${PY_FILE}"
    ${PY_DOWNLOAD}
fi

if [[ -z $(command -v pip) || ${ALWAYS_DOWNLOAD} -eq 1 ]];
then
    echo "Getting pip..."
    mkdir -p pip
    PIP_FILE="get-pip.py"
    PIP_MIRROR="https://bootstrap.pypa.io/${PIP_FILE}"
    PIP_DOWNLOAD="${CURL} ${PIP_MIRROR} -o pip/${PIP_FILE}"
    ${PIP_DOWNLOAD}
fi 

# get most recent monit
if [[ $(ls -l .. | grep monit | wc -l) -gt 0 && (-z $(command -v monit) || ${ALWAYS_DOWNLOAD} -eq 1) ]];
then
    echo "Getting monit..."
    mkdir -p monit
    MONIT_MIRROR="https://mmonit.com/monit"
    MONIT_VERSION=$(${CURL} ${MONIT_MIRROR}#download | grep -oE 'dist\/monit-[0-9]+\.[0-9]+\.[0-9]+\.tar\.gz')
    MONIT_TAR=$(echo ${MONIT_VERSION} | awk -F '/' '{print $NF}')
    MONIT_DOWNLOAD="${CURL} ${MONIT_MIRROR}/${MONIT_VERSION} -o monit/${MONIT_TAR}"
    ${MONIT_DOWNLOAD}
    echo "madler/zlib" >> target
fi


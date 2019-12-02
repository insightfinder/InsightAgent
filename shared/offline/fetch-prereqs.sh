#!/usr/bin/env bash

GNU_MIRROR="$1"
if [[ -z ${GNU_MIRROR} ]];
then
    GNU_MIRROR="ftp://prep.ai.mit.edu/pub/gnu/"
fi
# really just for debugging
ALWAYS_DOWNLOAD=1

CURL="curl -sSL"

# get most recent make
if [[ -z $(command -v make) || ${ALWAYS_DOWNLOAD} -eq 1 ]];
then
    MAKE_MIRROR="${GNU_MIRROR}/make/"
    MAKE_VERISON=$(${CURL} ${MAKE_MIRROR} | grep -o make-[0-9\.]*tar\.gz | uniq | sort -V | tail -n1)
    MAKE_DOWNLOAD="${CURL} ${MAKE_MIRROR}/${MAKE_VERISON}"
    MAKE_TAR=${MAKE_VERISON}
    ${MAKE_DOWNLOAD} > ${MAKE_TAR}
fi

# get most recent monit
if [[ -z $(command -v monit) || ${ALWAYS_DOWNLOAD} -eq 1 ]];
then
    MONIT_MIRROR="https://mmonit.com/monit"
    MONIT_VERSION=$(${CURL} ${MONIT_MIRROR}#download | grep -oE 'dist\/monit-[0-9]+\.[0-9]+\.[0-9]+\.tar\.gz')
    MONIT_DOWNLOAD="${CURL} ${MONIT_MIRROR}/${MONIT_VERSION}"
    MONIT_TAR=$(echo ${MONIT_VERSION} | awk -F '/' '{print $NF}')
    ${MONIT_DOWNLOAD} > ${MONIT_TAR}
    MONIT_DIR=$(tar tf ${MONIT_TAR} | head -n1)
    tar xf ${MONIT_TAR}
    rm ${MONIT_TAR}
    cd ${MONIT_DIR}
    ./configure
    cd -
    tar czf ${MONIT_TAR} ${MONIT_DIR}
    rm -rf ${MONIT_DIR}
fi

# get most recent python, python-utils, python-devel
if [[ -z $(command -v python) || ${ALWAYS_DOWNLOAD} -eq 1 ]];
then
    PY_MIRROR="https://www.python.org/ftp/python/"
    PY_VERSION_NUM=$(${CURL} ${PY_MIRROR} | grep -oE [0-9]+\.[0-9]+\.[0-9]+\/ | tail -n1)
    PY_MIRROR="${PY_MIRROR}/${PY_VERSION_NUM}"
    PY_VERSION=$(${CURL} ${PY_MIRROR} | grep -oE '>Python\-.*\.tgz<' | tr -d '><')
    PY_DOWNLOAD="${CURL} ${PY_MIRROR}/${PY_VERSION}"
    PY_TAR=${PY_VERSION}
    ${PY_DOWNLOAD} > ${PY_TAR}
    PY_DIR=$(tar tf ${PY_TAR} | head -n1)
    tar xf ${PY_TAR}
    rm ${PY_TAR}
    cd ${PY_DIR}
    ./configure
    cd -
    tar czf ${PY_TAR} ${PY_DIR}
    rm -rf ${PY_DIR}
fi

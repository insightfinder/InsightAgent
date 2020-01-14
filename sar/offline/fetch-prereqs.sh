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
if [[ ${ALWAYS_DOWNLOAD} -eq 1 || -z $(command -v make) ]];
then
    echo "Getting make..."
    mkdir -p make
    MAKE_MIRROR="${GNU_MIRROR}/make/"
    MAKE_VERISON=$(${CURL} ${MAKE_MIRROR} | grep -o make-[0-9\.]*tar\.gz | uniq | sort -V | tail -n1)
    MAKE_FILE="make/${MAKE_VERISON}"
    MAKE_DOWNLOAD="${CURL} ${MAKE_MIRROR}/${MAKE_VERISON} -o ${MAKE_FILE}"
    ${MAKE_DOWNLOAD}
    echo "  To install, run"
<<<<<<< HEAD
    echo "      ./make-install.sh -t ${MAKE_FILE}"
    echo "  or, to install on multiple nodes"
    echo "      ./remote-cp-run.sh -cp ${MAKE_FILE} [node1 node2 nodeN [-f nodefile]]"
=======
    echo "      ./make-install.sh -t ${MAKE_FILE} -m --prefix=/usr"
    echo "  or, to install on multiple nodes"
    echo "      ./remote-cp-run.sh -cp ${MAKE_FILE} -p -m -p --prefix=/usr [node1 node2 nodeN [-f nodefile]]"
>>>>>>> master
fi

# get most recent python
if [[ ${ALWAYS_DOWNLOAD} -eq 1 || -z $(command -v python) ]];
then
    echo "Getting python..."
    mkdir -p python
    PY_MIRROR="https://www.python.org/ftp/python/"
    PY_VERSION_NUM=$(${CURL} ${PY_MIRROR} | grep -oE [0-9]+\.[0-9]+\.[0-9]+\/ | tail -n1)
    PY_MIRROR="${PY_MIRROR}/${PY_VERSION_NUM}"
<<<<<<< HEAD
    PY_VERSION=$(${CURL} ${PY_MIRROR} | grep -oE '>Python\-.*\.tgz<' | tr -d '><')
=======
    PY_VERSION=$(${CURL} ${PY_MIRROR} | grep -oE '>Python\-.*\.tgz<' | tr -d '><' | tail -n1)
>>>>>>> master
    PY_FILE="python/${PY_VERSION}"
    PY_DOWNLOAD="${CURL} ${PY_MIRROR}/${PY_VERSION} -o ${PY_FILE}"
    ${PY_DOWNLOAD}
    echo "  To install, run"
<<<<<<< HEAD
    echo "      ./make-install.sh -t ${PY_FILE}"
    echo "  or, to install on multiple nodes"
    echo "      ./remote-cp-run.sh -cp ${PY_FILE} [node1 node2 nodeN [-f nodefile]]"
=======
    echo "      ./make-install.sh -t ${PY_FILE} -m --prefix=/usr"
    echo "  or, to install on multiple nodes"
    echo "      ./remote-cp-run.sh -cp ${PY_FILE} -p -m -p --prefix=/usr [node1 node2 nodeN [-f nodefile]]"
>>>>>>> master
fi

if [[ ${ALWAYS_DOWNLOAD} -eq 1 || -z $(command -v pip) ]];
then
    echo "Getting pip..."
    mkdir -p pip
    PIP_FILE="get-pip.py"
    PIP_MIRROR="https://bootstrap.pypa.io/${PIP_FILE}"
    PIP_DOWNLOAD="${CURL} ${PIP_MIRROR} -o pip/${PIP_FILE}"
    ${PIP_DOWNLOAD}
    echo "  To install, run" 
    echo "      python pip/${PIP_FILE}"
    echo "  or, to install on multiple nodes"
    echo "      ./remote-cp-run.sh -c pip/${PIP_FILE} -x python -p ${PIP_FILE} [node1 node2 nodeN [-f nodefile]]"
fi 

# get most recent monit
if [[ (${ALWAYS_DOWNLOAD} -eq 1 || -z $(command -v monit)) && $(ls -l .. | grep monit | wc -l) -gt 0 ]];
then
    echo "Getting monit..."
    mkdir -p monit
    MONIT_MIRROR="https://mmonit.com/monit"
    MONIT_VERSION=$(${CURL} ${MONIT_MIRROR}#download | grep -oE 'dist\/monit-[0-9]+\.[0-9]+\.[0-9]+\.tar\.gz')
    MONIT_TAR=$(echo ${MONIT_VERSION} | awk -F '/' '{print $NF}')
    MONIT_DOWNLOAD="${CURL} ${MONIT_MIRROR}/${MONIT_VERSION} -o monit/${MONIT_TAR}"
    ${MONIT_DOWNLOAD}
    echo "  To install, run"
<<<<<<< HEAD
    echo "      ./make-install.sh -t monit/${MONIT_TAR}"
    echo "  or, to install on multiple nodes"
    echo "      ./remote-cp-run.sh -cp monit/${MONIT_TAR} [node1 node2 nodeN [-f nodefile]]"

    # libz
    if [[ ${ALWAYS_DOWNLOAD} -eq 1 || -z $(ldconfig -p | grep libz) ]];
    then
        echo "Getting libz..."
        echo "madler/zlib" >> target
        ./prepare-git-repo.sh
    fi
=======
    echo "      ./make-install.sh -t monit/${MONIT_TAR} -m --prefix=/usr"
    echo "  or, to install on multiple nodes"
    echo "      ./remote-cp-run.sh -cp monit/${MONIT_TAR} -p -m -p --prefix=/usr [node1 node2 nodeN [-f nodefile]]"
>>>>>>> master
fi


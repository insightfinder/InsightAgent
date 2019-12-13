#/scripts!/usr/bin/env bash

ALWAYS_DOWNLOAD=0
if [[ "$@" =~ -r|--remote ]];
then
    ALWAYS_DOWNLOAD=1
    shift
fi

# ./fetch-prereqs.sh --remote ftp://prep.ai.mit.edu/pub/gnu/
GNU_MIRROR="${1:-ftp://prep.ai.mit.edu/pub/gnu/}"

CURL="curl -sSL"

# get most recent make
if [[ ${ALWAYS_DOWNLOAD} -eq 1 || -z $(command -v make) ]];
then
    echo "Getting make..."
    MAKE_DIR="./offline/make"
    mkdir -p "${MAKE_DIR}"
    MAKE_MIRROR="${GNU_MIRROR}/make/"
    MAKE_VERISON=$(${CURL} ${MAKE_MIRROR} | grep -o make-[0-9\.]*tar\.gz | uniq | sort -V | tail -n1)
    MAKE_FILE="${MAKE_DIR}/${MAKE_VERISON}"
    MAKE_DOWNLOAD="${CURL} ${MAKE_MIRROR}/${MAKE_VERISON} -o ${MAKE_FILE}"
    ${MAKE_DOWNLOAD}
    echo "  To install, run"
    echo "      ./scripts/make-install.sh -t ${MAKE_FILE}"
    echo "  or, to install on multiple nodes"
    echo "      ./scripts/remote-cp-run.sh -cp ${MAKE_FILE} [node1 node2 nodeN [-f nodefile]]"
fi

# get most recent python
if [[ ${ALWAYS_DOWNLOAD} -eq 1 || -z $(command -v python) ]];
then
    echo "Getting python..."
    PY_DIR="./offline/python"
    mkdir -p "${PY_DIR}"
    PY_MIRROR="https://www.python.org/ftp/python/"
    PY_VERSION_NUM=$(${CURL} ${PY_MIRROR} | grep -oE [0-9]+\.[0-9]+\.[0-9]+\/ | tail -n1)
    PY_MIRROR="${PY_MIRROR}/${PY_VERSION_NUM}"
    PY_VERSION=$(${CURL} ${PY_MIRROR} | grep -oE '>Python\-.*\.tgz<' | tr -d '><')
    PY_FILE="${PY_DIR}/${PY_VERSION}"
    PY_DOWNLOAD="${CURL} ${PY_MIRROR}/${PY_VERSION} -o ${PY_FILE}"
    ${PY_DOWNLOAD}
    echo "  To install, run"
    echo "      ./scripts/make-install.sh -t ${PY_FILE}"
    echo "  or, to install on multiple nodes"
    echo "      ./scripts/remote-cp-run.sh -cp ${PY_FILE} [node1 node2 nodeN [-f nodefile]]"
fi

if [[ ${ALWAYS_DOWNLOAD} -eq 1 || -z $(command -v pip) ]];
then
    echo "Getting pip..."
    PIP_DIR="./offline/pip"
    mkdir -p "${PIP_DIR}"
    PIP_SCRIPT="get-pip.py"
    PIP_FILE="${PIP_DIR}/${PIP_SCRIPT}"
    PIP_MIRROR="https://bootstrap.pypa.io/${PIP_SCRIPT}"
    PIP_DOWNLOAD="${CURL} ${PIP_MIRROR} -o ${PIP_FILE}"
    ${PIP_DOWNLOAD}
    echo "  To install, run" 
    echo "      python ${PIP_FILE}"
    echo "  or, to install on multiple nodes"
    echo "      ./scripts/remote-cp-run.sh -c ${PIP_FILE} -x python -p ${PIP_FILE##*/} [node1 node2 nodeN [-f nodefile]]"
fi 

# get most recent monit
if [[ (${ALWAYS_DOWNLOAD} -eq 1 || -z $(command -v monit)) && $(ls -l .. | grep monit | wc -l) -gt 0 ]];
then
    echo "Getting monit..."
    mkdir -p monit
    MONIT_MIRROR="https://mmonit.com/monit"
    MONIT_VERSION=$(${CURL} ${MONIT_MIRROR}#download | grep -oE 'dist\/monit-[0-9]+\.[0-9]+\.[0-9]+\.tar\.gz')
    MONIT_TAR=$(echo ${MONIT_VERSION} | awk -F '/' '{print $NF}')
    MONIT_FILE="../offline/monit/${MONIT_TAR}"
    MONIT_DOWNLOAD="${CURL} ${MONIT_MIRROR}/${MONIT_VERSION} -o ${MONIT_FILE}"
    ${MONIT_DOWNLOAD}
    echo "  To install, run"
    echo "      ./scripts/make-install.sh -t ${MONIT_TAR} --without-pam --without-ssl"
    echo "  or, to install on multiple nodes"
    echo "      ./scripts/remote-cp-run.sh -cp ${MONIT_TAR} --without-pam --without-ssl [node1 node2 nodeN [-f nodefile]]"
    echo "  By default, PAM and SSL are included in monit, but the prereqs are not installed on many machines. Don't"
    echo "   pass the --without-[option] flag if you can install the prereqs."

    # libz
    if [[ ${ALWAYS_DOWNLOAD} -eq 1 || -z $(ldconfig -p | grep libz) ]];
    then
        echo "Getting libz..."
        echo "madler/zlib" >> ./offline/target
    fi
fi

# other fetch scripts - scripts in this directory named similarly, but not the same
find "${0%/*}" -type f ! -name "${0##*/}" -regextype posix-extended -regex "^.*fetch-.*\.sh$" -exec {} \;
# get anything defined in target file
./prepare-git-repo.sh 

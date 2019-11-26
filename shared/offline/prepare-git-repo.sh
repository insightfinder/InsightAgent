#!/bin/bash

# read from file
if [[ -f target ]];
then
    TARGET=$(cat target)
else
    TARGET="$1"
fi

if [[ -z ${TARGET} ]];
then
    echo "Pass the target repo as the first argument, including the organization."
    echo "ie sysstat/sysstat"
    exit 1
fi

TARGET_REPO=$(echo ${TARGET} | awk -F '/' '{print $NF}')
TARGET_MASTER="${TARGET_REPO}-master"
TARGET_TAR="${TARGET_MASTER}.tar.gz"
OUTPUT_TAR="${TARGET_REPO}-make.tar.gz"

# get package if needed
if [[ ! -d "${TARGET_MASTER}" ]];
then
    curl -sSL https://github.com/${TARGET}/archive/master.tar.gz -o ${TARGET_TAR}
    tar xf ${TARGET_TAR}
fi
cd ${TARGET_MASTER}

# configure
if [[ "$@" =~ --interactive && -f ./iconfig ]];
then
    ./iconfig
elif [[ "$@" =~ --help ]];
then
    echo "Displaying configure help text"
    echo ""
    ./configure --help
    echo ""
    echo "Enter parameters to configure sysstat with."
    echo "[Enter] for none, [Ctrl+C] to quit and continue later:"
    read -p 'Parameters: ' PARAMS
    ./configure ${PARAMS}
else
    ./configure "$@"
fi

# compile
make

# make a tar from the compiled program
cd ..
TAR_CMD="tar czf ${OUTPUT_TAR} -s /^${TARGET_MASTER}/${TARGET_REPO}/ ${TARGET_MASTER}/"
echo ${TAR_CMD} | bash -
cd -

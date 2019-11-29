#!/usr/bin/env bash

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
    CONFIGURE="./iconfig"
elif [[ "$@" =~ --help ]];
then
    echo "Displaying configure help text"
    echo ""
    ./configure --help
    echo ""
    echo "Enter parameters to configure sysstat with."
    echo "[Enter] to accept (leave blank for defaults), [Ctrl+C] to quit and continue later:"
    read -p 'Parameters: ' PARAMS
    CONFIGURE="./configure ${PARAMS}">
else
    CONFIGURE="./configure $@"
fi
bash ${CONFIGURE}

# make a tar from the configured program
cd ..
tar czf ${OUTPUT_TAR} --transform "s/${TARGET_MASTER}/${TARGET_REPO}/" ${TARGET_MASTER}/
cd -

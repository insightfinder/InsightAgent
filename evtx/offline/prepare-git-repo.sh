#!/usr/bin/env bash

if [[ -n $1 ]];
then
    TARGETS="$@"
elif [[ -f target ]];
then
    TARGETS=$(cat target)
else
    echo "Pass the target repo as the first argument, including the organization."
    echo "ie sysstat/sysstat"
    exit 1
fi

for TARGET in ${TARGETS};
do
    TARGET_REPO=$(echo ${TARGET} | awk -F '/' '{print $NF}')
    TARGET_TAR="${TARGET_REPO}.tar.gz"
    curl -sSL https://github.com/${TARGET}/archive/master.tar.gz -o ${TARGET_TAR}
done

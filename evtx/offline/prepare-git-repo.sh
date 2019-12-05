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

echo "Downloading ${TARGETS[@]}"
for TARGET in ${TARGETS[@]};
do
    TARGET_REPO=${TARGET##*/}
    TARGET_TAR="${TARGET_REPO}.tar.gz"
    curl -sSL https://github.com/${TARGET}/archive/master.tar.gz -o ${TARGET_TAR}
    echo "  Downloaded ${TARGET}. To install, run"
    echo "      ./make-install.sh"
    echo "  or, to install on multiple nodes"
    echo "      ./remote-cp-run.sh -cp ${TARGET_TAR} [node1 node2 nodeN [-f nodefile]]"
done


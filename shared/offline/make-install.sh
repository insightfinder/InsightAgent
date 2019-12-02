#!/usr/bin/env bash

# read from file
if [[ -n "$1" ]];
then
    TARBALL="$1"
elif [[ -f target ]];
then
    TARGET=$(cat target | awk -F '/' '{print $NF}')
    TARBALL="${TARGET}-make.tar.gz"
else
    echo "No target file and no tarball specified (as first parameter)"
    exit 1
fi

# get tarball
TARBALL_LOC=$(find . -type f -name ${TARBALL} -print)
if [[ ! -f ${TARBALL_LOC} || -z ${TARBALL_LOC} ]];
then
    TARBALL_LOC=$(find /tmp -type f -name ${TARBALL} -print)
fi
if [[ ! -f ${TARBALL_LOC} || -z ${TARBALL_LOC} ]];
then
    echo "No tarball could be found in $(pwd) or /tmp"
    exit 1
fi

CD_DIR=$(tar tf ${TARBALL_LOC} | head -n1)
tar xf ${TARBALL_LOC}
cd ${CD_DIR}
if [[ -n $(command -v make) ]];
then
    make
    make install
else
    echo "Installing make..."
    ./build.sh
fi

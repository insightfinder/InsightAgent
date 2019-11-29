#!/bin/bash

# read from file
if [[ -f target ]];
then
    TARGET=$(cat target | awk -F '/' '{print $NF}')
else
    TARGET="$1"
fi
if [[ -z ${TARGET} ]];
then
    echo "No target specified (as first parameter)"
fi

# get tarball
TARBALL="${TARGET}-make.tar.gz"
TARBALL_LOC=$(find . -type f -name ${TARBALL} -print)
if [[ ! -f ${TARBALL_LOC} || -z ${TARBALL_LOC} ]];
then
    TARBALL_LOC=$(find /tmp -type f -name ${TARBALL} -print)
fi
if [[ ! -f ${TARBALL_LOC} || -z ${TARBALL_LOC} ]];
then
    echo "No tarball could be found in $(pwd) or /tmp"
else
    tar xf ${TARBALL_LOC}
fi

# make sure target folder exists
if [[ ! -d ${TARGET} ]];
then
    echo "Could not find directory ${TARGET}"
fi

cd ${TARGET}
make
make install

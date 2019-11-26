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

TARBALL="${TARGET}-make.tar.gz"
TARBALL_LOC=$(find . -type f -name ${TARBALL} -print)
if [[ ! -f ${TARBALL_LOC} ]];
then
    TARBALL_LOC=$(find /tmp -type f -name ${TARBALL} -print)
fi

tar xf ${TARBALL_LOC}
cd ${TARGET}
make install

#!/usr/bin/env bash

# extract flag(s)
IGNORE_ERRS=0
MAKE=0
HELP=0
PARAMS=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--ignore-errors)
            IGNORE_ERRS=1
            ;;  
        -t|--tarball)
            shift
            TARBALL="$1" 
            ;;
        -m|--make)
            MAKE=1
            ;;
        -h|--help)
            HELP=1
            ;;  
        *)  
            PARAMS="${PARAMS} $1"
            ;;  
    esac
    shift
done

# read from file
if [[ -z ${TARBALL} && -f target ]];
then
    TARGET=$(cat target | awk -F '/' '{print $NF}')
    TARBALL="${TARGET}.tar.gz"
elif [[ -z ${TARBALL} ]];
then
    echo "No target file and no tarball specified"
    exit 1
fi

echo "Unpacking tar..."
tar xf ${TARBALL}
cd $(tar tf ${TARBALL} | head -n1)

if [[ ! -f Makefile || ${MAKE} -eq 1 ]];
then
    if [[ ${HELP} -eq 1 ]];
    then
        ./configure --help
        exit 0
    fi

    echo "Configuring..."
    ERRS=$(./configure --quiet ${PARAMS} || ./configure ${PARAMS})
    if [[ -n ${ERRS} && ${IGNORE_ERRS} -eq 0 ]];
    then
        echo "  Please review these error(s) before continuing."
        echo "${ERRS}"
        echo "  If these errors can be safely ignored, run this again with -i or --ignore-errors"
        exit 1
    else
        echo "  Configured successfully."
    fi
fi

echo "Installing..."
if [[ -n $(command -v make) ]];
then
    make
    make install
else
    ./build.sh
fi

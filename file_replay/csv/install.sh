#!/bin/bash

# set up pip first. no harm if parameters are bad, should run regardless of commit mode
./pip-setup.sh

# Get parameters
DRY_RUN=1
SAMPLING_INTERVAL=0
while test $# -gt 0; do
  case "$1" in
      -c|--commit)
          DRY_RUN=0
          ;;
      -h|--help|*)  
          echo "'-s N' or '--sampling-interval N': How often to run the cron for this agent."
          echo "'-c'   or '--commit'             : Whether or not to commit the changes from the install."
          exit 1
          ;;
  esac
  shift
done

# Python 3 compatability
echo "== Check Python version =="
PY_VER=$(python -V 2>&1 | awk '{print $NF}')
PY_MAJ_VER=${PY_VER:0:1}
if [[ ${PY_MAJ_VER} -eq 3 ]];
then
    echo "Using Python version ${PY_VER}. Need to upgrade the python script for compatability."
    # get script
    PYFILE=$(find . -maxdepth1 -type f -name "get[^\-]*.py" -print)
    if [[ -z ${PYFILE} ]];
    then
        PYFILE=$(find . -maxdepth 1 -type f -name "replay*.py" -print)
    fi
    if [[ -z ${PYFILE} ]];
    then
        echo "No script found. Exiting..."
        exit 1
    fi
    PYFILE=${PYFILE:2:${#PYFILE}}
    # upgrade
    if [[ "${DRY_RUN}" -gt 0 ]];
    then
        echo "Upgrading ${PYFILE}"
        2to3 ${PYFILE}
    else
        echo "In dry-run mode. Run with '-c' or '--commit' to auto-upgrade. Proposed changes:"
        2to3 -w ${PYFILE}
    fi
fi


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
      -s|--sampling-interval)
          shift
          SAMPLING_INTERVAL=$1
          ;;
      -h|--help|*)  
          echo "'-s N' or '--sampling-interval N': How often to run the cron for this agent."
          echo "'-c'   or '--commit'             : Whether or not to commit the changes from the install."
          exit 1
          ;;
  esac
  shift
done

# check sampling interval
CRONIT_SCRIPT=$(find . -maxdepth 1 -type f -name '*-config.sh' -print)
CRONIT=$(echo "${CRONIT_SCRIPT}" | sed -E  -e 's:^\.\/(monit|cron)-config\.sh$:\1:')
if [[ "${CRONIT}" == "cron" ]];
then
    if [[ -e ${SAMPLING_INTERVAL} ]];
    then
        BREAK=0
        UNIT="${SAMPLING_INTERVAL: -1}"
        VAL="${SAMPLING_INTERVAL:0:${#SAMPLING_INTERVAL}-1}"
        # valid unit?
        case ${UNIT} in
            [mhd])
                # ok, no validation required
                ;;
            s)
                # must be an integer divisor of 60
                if [[ $((60 % ${VAL})) -ne 0 ]];
                then
                    BREAK=1
                fi
                ;;
            [0123456789])
                VAL=${SAMPLING_INTERVAL}
                ;;
            *)
               BREAK=1
               ;; 
        esac
        # valid value?
        if [[ ${VAL} -le 0 && $((${VAL} % 1)) -ne 0 ]];
        then
            BREAK=1
        fi
        # should break?
        if [[ ${BREAK} -gt 0 ]];
        then
            echo "Invalid sampling interval given. Please specify how often the cron should run in seconds (\"6s\" - must be an integer divisor of 60), minutes (default, \"6m\" or \"6\"), hours (\"6h\"), or days (\"6d\")"
            exit 1
        fi
        # all OK
        CRONIT_SCRIPT="${CRONIT_SCRIPT} ${SAMPLING_INTERVAL}"
    else
        echo "No sampling interval specified ('-s N' or '--sampling-interval N'). Exiting..."
        exit 1
    fi
fi

# Set up cron/monit
echo "== Setting up ${CRONIT} =="
if [[ ${DRY_RUN} -gt 0 ]];
then
    echo "In dry-run mode. Run with '-c' or '--commit' to auto-execute \"${CRONIT_SCRIPT}\""
else
    ${CRONIT_SCRIPT}
fi

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


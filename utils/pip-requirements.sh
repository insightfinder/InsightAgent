#!/bin/bash

PWD=$(pwd)
DIR=$(pwd | awk -F '/' '{print $NF}')
if [[ $(\ls -l | awk '{print $NF}' | grep ${DIR} | wc -l) -eq 0 ]]; # probably not an agent folder
then
    AGENT="$1"
    if [[ -z ${AGENT} || ! -d ${AGENT} ]];
    then
        AGENT=$(\ls -lrt | grep ^d | tail -n1 | awk '{print $NF}')
        echo "No agent to build specified. Using most recently modified folder: ${AGENT}"
        read -p "Press [Enter] to continue, [Ctrl+C] to quit"
    fi

    cd ${AGENT}
else
    AGENT=${DIR}
fi

# python version - works on my machine (tm)
PYTHON=python
if [[ $(python -V 2>&1 | awk '{ print substr($NF, 1, 1) }') -gt 2 && -n $(command -v python2.7) ]];
then
    PYTHON=python2.7
else
    echo "Current python version >= 3.0; no executable for python2.7 found"
    exit 1
fi

# currently used packages
echo "Freezing current environment packages"
${PYTHON} -m pip freeze > pip-freeze

# virtualenv
echo "Creating virtual environment"
${PYTHON} -m pip install virtualenv
virtualenv nopip
. nopip/bin/activate

mkdir -p ./offline/pip/packages
rm -rf ./offline/pip/packages/*

# check required pip packages
echo "Modules used in this agent:"
grep import *.py                                                            \
    | xargs -I {} ${PYTHON} -c 'exec("try: {}\nexcept: print(\"{}\")")'     \
    | sed -E -e 's/(from|import)\s+(\w+).*/\2/' | sort -u                   \
    | xargs -I {} grep -i {} pip-freeze                                     \
    | tee requirements.txt

# exit virtualenv
echo "Exiting virtual environment"
deactivate
rm -rf nopip
rm -f pip-freeze

# get packages
echo "Attempting to download pip package(s)"
${PYTHON} -m pip -qq download -r requirements.txt -d ./offline/pip/packages

echo "Please review any errors from the output above."
exit 0

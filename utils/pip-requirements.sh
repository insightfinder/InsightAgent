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
fi

# currently used packages
pip freeze > pip-freeze

# virtualenv
pip install virtualenv
virtualenv nopip
. nopip/bin/activate

mkdir -p ./offline/pip/packages

# check required pip packages
echo "Modules:"
\ls -l | awk '{print $NF}' | grep ^get[^\-].*                                   \
    | xargs cat | grep import                                                   \
    | xargs -I {} python -c 'exec "try: {}\nexcept: print(\"{}\")"'             \
    | sed -E -e 's/^(from[\s]*(.*)[\s]*import[\s]*.*)|(import[\s]*(.*))$/\2\4/' \
    | sed -E -e 's/^[\s]*([^\.]*)\..*/\1/'                                      \
    | tr -s [:space:] \\n | sort -u                                             \
    | xargs -I {} grep {} pip-freeze                                            \
    | tee requirements.txt

# get packages
echo "Attempting to download pip package(s)"
pip -qq download -r requirements.txt -d ./offline/pip/packages

echo "Please review any errors from the output above."

# exit virtualenv
deactivate
rm -rf nopip
rm -rf pip-freeze

cd -

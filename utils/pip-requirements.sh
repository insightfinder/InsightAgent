#!/bin/bash

# virtualenv
pip install virtualenv
virtualenv nopip
. nopip/bin/activate

mkdir -p ./offline/pip/packages

# check required pip packages
echo "Modules:"
AGENT_SCRIPT=$(\ls -l | awk '{print $NF}' | grep ^get[^\-].*)
PIP_PACKAGES=$(cat ${AGENT_SCRIPT} | grep import \
   | xargs -I {} python -c 'exec "try: {}\nexcept: print(\"{}\")"' \
   | sed -E -e 's/^(from[\s]*(.*)[\s]*import[\s]*.*)|(import[\s]*(.*))$/\2\4/' \
   | sed -E -e 's/^[\s]*([^\.]*)\..*/\1/' \
   | tr -s [:space:] \\n | sort -u \
   | tee requirements.txt)

# get packages
echo "Attempting to download pip package(s)"
pip -qq download -r requirements.txt -d ./offline/pip/packages

echo "Please review any errors from the output above."

# exit virtualenv
deactivate
rm -rf nopip

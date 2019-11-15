#!/bin/bash

# agent directory to find file in
DIR="$1"
if [[ -z ${DIR} ]];
then
    DIR='.'
elif [[ "${DIR: -1}" = '/' ]];
then
    DIR="${DIR:0:${#DIR}-1}"
fi 
# get py file, fallback to template file
PYFILE=$(find ${DIR} -depth 1 -type f -name "get[^\-]*.py" -print)
if [[ -z ${PYFILE} ]];
then
    PYFILE=$(find ${DIR} -depth 1 -type f -name "replay*.py" -print)
fi
if [[ -z ${PYFILE} ]];
then
    PYFILE="${DIR}/insightagent-boilerplate.py"
fi
echo "${PYFILE}"

###
EXT="$2"

if [[ $(grep -E "instance = COLONS\.sub\(\'\-\'\)" ${PYFILE} | wc -l) -eq 0 ]];
then 
    echo "adding to instance string building"
    sed -E -e "/instance = UNDERSCORE\.sub\(\'\.\', instance\)/a\\                  
\ \ \ \ instance = COLONS\.sub\(\'\-'\)" -i ${EXT} ${PYFILE}
fi
 
if [[ $(grep -E "COLONS = re\.compile\(r\"\\\:\+\"\)" ${PYFILE} | wc -l) -eq 0 ]];
then
    echo "adding to global declaratinos"
    sed -E -e "/UNDERSCORE = re\.compile\(r\"\\\_\+\"\)/a\\
\ \ \ \ COLONS = re\.compile\(r\"\\\:\+\"\)" -i ${EXT} ${PYFILE}
fi


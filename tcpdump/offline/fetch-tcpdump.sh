#!/usr/bin/env bash
### set options. can be turned off with +[opt]
# -e: Exit script on error
# -u: Unset vars are errors
# -o pipefail: Stop executing pipe on fail and return error
set -euo pipefail
### Inner Field Separator
# set to only newline and tab
IFS=$'\n\t'
### source
# source from shared sourcefile
. $($(command -v find) .. -type f -name source -print -quit)

#########
# Globals
#########
THIS_SCRIPT="${0##*/}"
FETCH="${THIS_SCRIPT##*fetch-}"
FETCH="${FETCH%.sh}"
CURL="curl -sSL"
GNU_MIRROR="http://gnu.mirror.constant.com"
DEFAULT_MIRROR="${GNU_MIRROR}/${FETCH}"

#######################
# Gets the program defined in the filename (ie fetch-tcpdump.sh will get tcpdump)
# Arguments:
#   TAR_PIPE:
#   TAR_FMT:
#   MIRRIR:
# Returns: n/a
# Assumes: n/a
# Side Effects: Downloads the tarball
#######################
:main() {
    set +u
    TAR_PIPE="$1"
    if [[ "${TAR_PIPE:0:1}" != "|" ]]; then
        TAR_PIPE=""
    else
        shift
    fi
    TAR_FMT="$1"
    if [[ "${TAR_FMT:0:4}" == "http" ]]; then
        TAR_FMT=""
    else
        shift
    fi
    MIRROR="$1"
    if [[ -z ${MIRROR} || ${MIRROR:0:4} != "http" ]]; then
        MIRROR="${DEFAULT_MIRROR}"
    fi
    set -u

    OUT_DIR="./offline/${FETCH}"
    mkdir -p "${OUT_DIR}"
    TAR=$(echo "${CURL} ${MIRROR} ${TAR_PIPE}" | bash -)
    TAR_OUT="${OUT_DIR}/$(echo "${TAR_FMT} <<< ${TAR}" | bash -)"
    $(echo "${CURL} ${MIRROR}/${TAR} -o ${TAR_OUT}" | bash -)
    echo "  To install, run"
    echo "      ./offline/make-install.sh -t ${TAR_OUT}"
    echo "  or, to install on multiple nodes"
    echo "      ./offline/remote-cp-run.sh -cp ${TAR_OUT} [node1 node2 nodeN [-f nodefile]]"
}

#######################
# Prints usage.
# Arguments: n/a
# Returns: n/a
# Assumes: n/a
# Side Effects: n/a
#######################
:usage() {
    echo "${0} [tar-pipe [tar-fmt [mirror]]]"
    echo "  tar-pipe    should be a string for a pipe to format the tar with, starting with \"|\""
    echo "  tar-fmt     should be a command that can read from STDIN to format the output tar name, ie sed"
    echo "  mirror      mirror to reach out to. If none specified, uses a gnu mirror, ${DEFAULT_MIRROR}"
}

#######################
# Print usage and exit with error
# Arguments: n/a
# Returns: 1
# Assumes: n/a
# Side Effects: n/a
#######################
:abort() {
    :usage
    exit 1
}

#######################
# Print usage and exit with success
# Arguments: n/a
# Returns: 0
# Assumes: n/a
# Side Effects: n/a
#######################
:exit() {
    :usage
    exit 0
}

if [[ "$@" =~ -h|--help ]]; then
    :exit
else
    :main "${@:-}"
    exit 0
fi

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

#######################
# <Script_Description>
# Arguments:
# Returns:
# Assumes:
# Side Effects:
#######################
:main() {
    #######################
    # <Script_Description>
    # Arguments:
    # Returns:
    # Assumes:
    # Side Effects:
    #######################
    .scoped_func() {
    }
}

#######################
# <Script_Description>
# Arguments:
# Returns:
# Assumes:
# Side Effects:
#######################
:package.func() {
}

:main "${@:-}"

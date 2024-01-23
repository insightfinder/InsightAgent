#!/usr/bin/env bash
IFS=$'\n\t'
set -euo pipefail

# run as root
if [[ $EUID -ne 0 ]]; then
    echo "This script should be ran as root. Exiting..."
    exit 1
fi

# Errors will be thrown from find no matter what, and they are tolerable.
set +e

# TO_DELETE_LOG_DIRS - List of log directories
# TO_DELETE_TMP_DIRS - List of tmp directories
# MIN_FILE_AGE - delete filess accessed more than this # days ago (rounded up)
# MIN_LINK_AGE - delete links accessed more than this # days ago (rounded up)
# MIN_SOCK_AGE - delete socks accessed more than this # days ago (rounded up)
# DISK_USED_PCT_THRESHOLD - Threshold for cleaning all tmp dirs & stopping monit
JETTY_LOG_DIR="/opt/jetty/logs"
JETTY_TMP_DIR="/opt/jetty/temp"
TO_DELETE_LOG_DIRS=(
    "${JETTY_LOG_DIR}"
    "/var/log/rabbitmq"
"/var/log"
)
TO_DELETE_TMP_DIRS=(
    "/tmp"
)
TO_DELETE_ALL_DIRS=(
    "${TO_DELETE_LOG_DIRS[*]}"
    "${TO_DELETE_TMP_DIRS[*]}"
)
MIN_FILE_AGE=+0
MIN_LINK_AGE=+0
MIN_SOCK_AGE=+0
MAX_LOG_FILE_SIZE="10M"
DISK_USED_PCT_THRESHOLD=85

# check disk usage
:get_disk_used_pct() {
    df --output=pcent / | tr -dc '0-9'
}

# log to console and syslog
:log() {
    MESSAGE="${*:-$(</dev/stdin)}"
    if [[ "${#MESSAGE}" -gt 0 ]];
    then
        LOG="clean_disk.sh [$$] ${MESSAGE[*]} [$(:get_disk_used_pct)%]"
        echo "$(date '+%Y-%m-%dT%H:%M:%S') ${LOG}"
        logger "${LOG}"
    fi
}

EXIT_CODE=1
YEAR=$(date | awk '{print $NF}')
LAST_YEAR=$(( YEAR - 1 ))

START_DISK_USED_PCT=$(:get_disk_used_pct)
START_EPOCH=$(date +'%s')
:log "BEGIN cleaning tmp and log directories."

# jetty/temp
:log "delete any old unpacked files/directories in jetty/temp."
cd "${JETTY_TMP_DIR}" && ls -t | tail -n +3 | xargs rm -rf --

# rotated log files
:log "delete any old tarred/rotated log files"
find "${TO_DELETE_LOG_DIRS[@]}"                                     \
    -depth                                                          \
    -regextype posix-extended                                       \
    -regex "(.*\.gz|.*\.bz2|.*${YEAR}[0-9]+|.*${LAST_YEAR}[0-9]+)"  \
    -type f -a -mtime "${MIN_FILE_AGE}"                             \
    -print -delete                                                  \
    2>/dev/null | :log

# jetty logs
:log "delete all but today's jetty log files"
\ls -tpI "$(date '+%Y_%m_%d')*" "${JETTY_LOG_DIR}" 2>/dev/null      \
    | tee >(xargs -I {} rm -- "${JETTY_LOG_DIR}/{}")                \
    | :log

# symlinks
:log "delete any old tmp symlinks"
find "${TO_DELETE_TMP_DIRS[@]}"                                     \
    -depth                                                          \
    -type l -a -ctime "${MIN_LINK_AGE}"                             \
    -print -delete                                                  \
    2>/dev/null | :log

# sockets
:log "delete any old Unix sockets"
find "${TO_DELETE_ALL_DIRS[@]}"                                     \
    -depth                                                          \
    -type s -a -ctime "${MIN_SOCK_AGE}" -a -size 0                  \
    -print -delete                                                  \
    2>/dev/null | :log

# empty dirs
:log "delete any empty directories (other than lost+found)"
find "${TO_DELETE_ALL_DIRS[@]}"                                     \
    -depth -mindepth 1                                              \
    -type d -a -empty -a ! -name 'lost+found'                       \
    -print -delete                                                  \
    2>/dev/null | :log

# empty files
:log "delete any empty files"
find "${TO_DELETE_ALL_DIRS[@]}"                                     \
    -depth                                                          \
    -type f -a -empty                                               \
    -print -delete                                                  \
    2>/dev/null | :log

# truncate log files
DISK_USED_PCT=$(:get_disk_used_pct)
if [[ "${DISK_USED_PCT}" -gt "${DISK_USED_PCT_THRESHOLD}" ]];
then
    :log "disk still too full; truncating log files to ${MAX_LOG_FILE_SIZE}"
    find "${TO_DELETE_LOG_DIRS[@]}"                                 \
        -type f                                                     \
        -print -exec truncate -s "<${MAX_LOG_FILE_SIZE}" {} \;      \
        2>/dev/null | :log
fi

# remove temp files
DISK_USED_PCT=$(:get_disk_used_pct)
if [[ "${DISK_USED_PCT}" -gt "${DISK_USED_PCT_THRESHOLD}" ]];
then
    :log "disk still too full; deleting all files in tmp directories"
    find "${TO_DELETE_TMP_DIRS[@]}"                                 \
         -mindepth 1                                                \
         -print -delete                                             \
         2>/dev/null | :log

    :log "  deleting rotated jetty log files"
    \ls -tp "${JETTY_LOG_DIR}/*log.*" 2>/dev/null                   \
        | tee >(xargs -I {} rm -- "${JETTY_LOG_DIR}/{}")            \
        | :log
fi

# final check; if failed, stop monit
END_DISK_USED_PCT=$(:get_disk_used_pct)
if [[ "${END_DISK_USED_PCT}" -gt "${DISK_USED_PCT_THRESHOLD}" ]];
then
    :log "Failed cleaning tmp and log directories; stopping monit"
    service monit stop
else
    :log "Script successfully executed."
    EXIT_CODE=0
fi

END_EPOCH=$(date +'%s')
:log "END cleaning tmp and log directories in $(( END_EPOCH - START_EPOCH )) seconds. Reduced file system usage by $(( START_DISK_USED_PCT - END_DISK_USED_PCT ))%."
exit ${EXIT_CODE}

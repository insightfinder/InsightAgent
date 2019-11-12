#!/bin/bash

# run as root
if [[ $EUID -ne 0 ]]; then
   echo "This script should be ran as root. Exiting..."
   exit 1
fi

# TO_DELETE_LOG_DIRS - List of log directories
# TO_DELETE_TMP_DIRS - List of tmp directories
# MIN_FILE_AGE - delete filess accessed more than this # days ago (rounded up)
# MIN_LINK_AGE - delete links accessed more than this # days ago (rounded up)
# MIN_SOCK_AGE - delete socks accessed more than this # days ago (rounded up)
# DISK_USED_PCT_THRESHOLD - Threshold for cleaning all tmp dirs & stopping monit
JETTY_LOG_DIR="/opt/jetty/logs"
TO_DELETE_LOG_DIRS="${JETTY_LOG_DIR} /var/log/rabbitmq /var/log"
TO_DELETE_TMP_DIRS="/tmp /opt/jetty/temp" 
MIN_FILE_AGE=+0
MIN_LINK_AGE=+0
MIN_SOCK_AGE=+0
MAX_LOG_FILE_SIZE="10M"
DISK_USED_PCT_THRESHOLD=85

# Set EMPTYFILES=1 to delete zero-length files
EMPTYFILES=0
#EMPTYFILES=1

# check disk usage
function GET_DISK_USED_PCT() {
    df --output=pcent / | tr -dc '0-9'
}

# log to console and syslog
function log() {
    echo ""
    echo "$(date) clean_disk.sh [$$] $1 [$(eval GET_DISK_USED_PCT)%]"
    logger "clean_disk.sh [$$] $1 [$(eval GET_DISK_USED_PCT)%]"
}

EXIT_CODE=0
YEAR=$(date | awk '{print $NF}')
LAST_YEAR=$((${YEAR} - 1))

START_DISK_USED_PCT=$(eval GET_DISK_USED_PCT)
START_EPOCH=$(date +'%s')
log "BEGIN cleaning tmp and log directories."

# jetty/temp & tmp
log "delete any old temporary files."
find ${TO_DELETE_TMP_DIRS}                                          \
     -depth                                                         \
     -type f -a -mtime ${MIN_FILE_AGE}                              \
     -print -delete

# rotated log files
log "delete any old tarred/rotated log files"
find ${TO_DELETE_LOG_DIRS}                                          \
     -depth                                                         \
     -regextype posix-extended                                      \
     -regex "(.*\.gz|.*\.bz2|.*${YEAR}[0-9]+|.*${LAST_YEAR}[0-9]+)" \
     -type f -a -mtime ${MIN_FILE_AGE}                              \
     -print -delete

# probably redundant, but only keep the current jetty log file
log "delete all but the most recent jetty log file"
\ls -tp ${JETTY_LOG_DIR}                                             \
     | grep -v '/$'                                                 \
     | tail -n +2                                                   \
     | xargs -I {} rm -- {}

# symlinks
log "delete any old tmp symlinks"
find ${TO_DELETE_TMP_DIRS}                                          \
     -depth                                                         \
     -type l -a -ctime ${MIN_LINK_AGE}                              \
     -print -delete

# sockets
log "delete any old Unix sockets"
find ${TO_DELETE_TMP_DIRS} ${TO_DELETE_LOG_DIRS}                    \
     -depth                                                         \
     -type s -a -ctime ${MIN_SOCK_AGE} -a -size 0                   \
     -print -delete

# empty dirs
log "delete any empty directories (other than lost+found)"
find ${TO_DELETE_TMP_DIRS} ${TO_DELETE_LOG_DIRS}                    \
     -depth -mindepth 1                                             \
     -type d -a -empty -a ! -name 'lost+found'                      \
     -print -delete

# empty files
if [[ "${EMPTYFILES}" -gt 1 ]];
then
     log "delete any empty files"
     find ${TO_DELETE_TMP_DIRS} ${TO_DELETE_LOG_DIRS}               \
          -depth                                                    \
          -type f -a -empty                                         \
          -print -delete
fi

# truncate log files
DISK_USED_PCT=$(eval GET_DISK_USED_PCT)
if [[ ${DISK_USED_PCT} > ${DISK_USED_PCT_THRESHOLD} ]];
then
    log "disk still too full; truncating log files to ${MAX_LOG_FILE_SIZE}"
    find ${TO_DELETE_LOG_DIRS}                                      \
        -type f                                                     \
        -exec truncate -s "<${MAX_LOG_FILE_SIZE}" {} \;
fi

# remove temp files
DISK_USED_PCT=$(eval GET_DISK_USED_PCT)
if [[ ${DISK_USED_PCT} > ${DISK_USED_PCT_THRESHOLD} ]];
then
     log "disk still too full; deleting all files in tmp directories"
     find ${TO_DELETE_TMP_DIRS}                                     \
          -mindepth 1                                               \
          -print -delete
fi

# final check; if failed, stop monit
END_DISK_USED_PCT=$(eval GET_DISK_USED_PCT)
if [[ ${END_DISK_USED_PCT} > ${DISK_USED_PCT_THRESHOLD} ]];
then
     log "Failed cleaning tmp and log directories; stopping monit"
     service monit stop
     EXIT_CODE=1
else
     log "Script successfully executed."
fi

END_EPOCH=$(date +'%s')
log "END cleaning tmp and log directories in $(( ${END_EPOCH} - ${START_EPOCH} )) seconds. Reduced file system usage by $(( ${START_DISK_USED_PCT} - ${END_DISK_USED_PCT} ))%."
exit ${EXIT_CODE}

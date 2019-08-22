#!/bin/bash
# Diskclean-Linux.sh - Remove unused files from /tmp directories

# ------------- Here are Default Configuration --------------------
# TO_DELETE_TMP_DIRS - List of directories to search
# TO_DELETE_LOG_DIRS - List of log directories to search
# DEFAULT_FILE_AGE - # days ago (rounded up) that file was last accessed
# DEFAULT_LINK_AGE - # days ago (rounded up) that symlink was last accessed
# DEFAULT_SOCK_AGE - # days ago (rounded up) that socket was last accessed
# DISK_USED_PCT_THRESHOLD - Threshold for

TO_DELETE_TMP_DIRS="/tmp /opt/jetty/temp"
TO_DELETE_LOG_DIRS="/opt/jetty/logs /var/log/rabbitmq"
DEFAULT_FILE_AGE=+0
DEFAULT_LINK_AGE=+0
DEFAULT_SOCK_AGE=+0
DISK_USED_PCT_THRESHOLD=85

# Make EMPTYFILES true to delete zero-length files
EMPTYFILES=false
#EMPTYFILES=true

RUN_TIME=$(/bin/date)
echo "$RUN_TIME Begin cleaning tmp directories"
echo ""

# jetty/temp & tmp
echo "delete any temporary files that are more than 1 days old"
sudo /usr/bin/find $TO_DELETE_TMP_DIRS                           \
     -depth                                                      \
     -type f -a -mtime $DEFAULT_FILE_AGE                         \
     -print -delete

# .gz log files
echo "delete any tarred/rotated log files that are more than 1 days old"
sudo /usr/bin/find $TO_DELETE_LOG_DIRS                           \
     -name "*.gz"                                                \
     -depth                                                      \
     -type f -a -mtime $DEFAULT_FILE_AGE                         \
     -print -delete
echo ""

echo "delete all but the most recent jetty log file"
sudo ls -tp /opt/jetty/logs                                      \
     | grep -v '/$'                                              \
     | tail -n +2                                                \
     | xargs -I {} rm -- {}
echo ""

echo "delete any old tmp symlinks"
/usr/bin/find $TO_DELETE_TMP_DIRS                                \
     -depth                                                      \
     -type l -a -ctime $DEFAULT_LINK_AGE                         \
     -print -delete
echo ""

if /usr/bin/$EMPTYFILES ;
then
     echo "delete any empty files"
     /usr/bin/find $TO_DELETE_TMP_DIRS $TO_DELETE_LOG_DIRS        \
          -depth                                                  \
          -type f -a -empty                                       \
          -print -delete
fi
echo ""

echo "Delete any old Unix sockets"
/usr/bin/find $TO_DELETE_TMP_DIRS $TO_DELETE_LOG_DIRS            \
     -depth                                                      \
     -type s -a -ctime $DEFAULT_SOCK_AGE -a -size 0              \
     -print -delete
echo ""

echo "delete any empty directories (other than lost+found)"
/usr/bin/find $TO_DELETE_TMP_DIRS $TO_DELETE_LOG_DIRS            \
     -depth -mindepth 1                                          \
     -type d -a -empty -a ! -name 'lost+found'                   \
     -print -delete
echo ""

/usr/bin/logger "cleantmp.sh[$$] - Done cleaning tmp directories"
echo ""

# check disk usage
DISK_USED_PCT=`df --output=pcent / | tr -dc '0-9'`
if [ $DISK_USED_PCT > $DISK_USED_PCT_THRESHOLD ]
then
     echo "disk still too full; deleting all files in tmp directories"
     /usr/bin/find $TO_DELETE_TMP_DIRS $TO_DELETE_LOG_DIRS       \
          -mindepth 1                                            \
          -print -delete
fi

echo "Diskcleanup Script Successfully Executed"

END_TIME=$(/bin/date)
echo "$END_TIME End cleaning tmp directories"
exit 0

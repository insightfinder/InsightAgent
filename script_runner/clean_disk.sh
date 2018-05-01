#!/bin/bash
# Diskclean-Linux.sh - Remove unused files from /tmp directories

# ------------- Here are Default Configuration --------------------
# TO_DELETE_TMP_DIRS - List of directories to search
# DEFAULT_FILE_AGE - # days ago (rounded up) that file was last accessed
# DEFAULT_LINK_AGE - # days ago (rounded up) that symlink was last accessed
# DEFAULT_SOCK_AGE - # days ago (rounded up) that socket was last accessed

TO_DELETE_TMP_DIRS="/tmp /opt/jetty/temp"
DEFAULT_FILE_AGE=+2
DEFAULT_LINK_AGE=+4
DEFAULT_SOCK_AGE=+4

# Make EMPTYFILES true to delete zero-length files
EMPTYFILES=false
#EMPTYFILES=true

RUN_TIME=$(/bin/date)
echo "$RUN_TIME Begin cleaning tmp directories"

echo ""
echo "delete any tmp files that are more than 2 days old"
sudo /usr/bin/find $TO_DELETE_TMP_DIRS                               \
     -depth                                                     \
     -type f -a -mtime $DEFAULT_FILE_AGE                        \
     -print -delete
echo ""

echo "delete any old tmp symlinks"
/usr/bin/find $TO_DELETE_TMP_DIRS                               \
     -depth                                                     \
     -type l -a -ctime $DEFAULT_LINK_AGE                        \
     -print -delete
echo ""

if /usr/bin/$EMPTYFILES ;
then
echo "delete any empty files"
/usr/bin/find $TO_DELETE_TMP_DIRS                               \
     -depth                                                     \
     -type f -a -empty                                          \
     -print -delete
fi

echo "Delete any old Unix sockets"
/usr/bin/find $TO_DELETE_TMP_DIRS                               \
     -depth                                                     \
     -type s -a -ctime $DEFAULT_SOCK_AGE -a -size 0             \
     -print -delete
echo""

echo "delete any empty directories (other than lost+found)"
/usr/bin/find $TO_DELETE_TMP_DIRS                               \
     -depth -mindepth 1                                         \
     -type d -a -empty -a ! -name 'lost+found'                  \
     -print -delete
echo ""

/usr/bin/logger "cleantmp.sh[$$] - Done cleaning tmp directories"

# send out an email about diskcleanup action
#mail -s "Disk cleanup has been performed successfully." moharnab@insightfinder.com

echo ""
echo "Diskcleanup Script Successfully Executed"
END_TIME=$(/bin/date)
echo "$END_TIME End cleaning tmp directories"
exit 0
#!/bin/bash
function usage()
{
	echo "Usage: ./deployment/undeploy.sh -i PROJECT_NAME -u USER_NAME "
}


while [ "$1" != "" ]; do
	case $1 in
		-i )	shift
			PROJECTNAME=$1
			;;
		-u )	shift
			USERNAME=$1
			;;

		* )	usage
			exit 1
	esac
	shift
done


if [ -z "$INSIGHTAGENTDIR" ]; then
	export INSIGHTAGENTDIR=`pwd`
fi


$INSIGHTAGENTDIR/pyenv/bin/python $INSIGHTAGENTDIR/common/config/delconfig.py -u $USERNAME -p $PROJECTNAME
sudo rm -r $INSIGHTAGENTDIR/log/$USERNAME/$PROJECTNAME/
sudo rm -r $INSIGHTAGENTDIR/data/$USERNAME/$PROJECTNAME/

sudo rm /etc/cron.d/ifagent_${USERNAME}_${PROJECTNAME}

echo "/etc/cron.d/ifagent_${USERNAME}_${PROJECTNAME} deleted"

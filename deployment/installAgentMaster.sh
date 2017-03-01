#!/bin/bash

function usage()
{
	echo "Usage: ./installAgentMaster.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE -c CRON_INTERVAL -p PASSWORD
AGENT_TYPE = proc or cadvisor or docker_remote_api or cgroup or metricFileReplay or logFileReplay or daemonset or hypervisor or elasticsearch or collectd or ec2monitoring or jolokia or kvm"
}

if [ "$#" -lt 16 ]; then
	echo "$#"
	usage
	exit 1
fi

while [ "$1" != "" ]; do
	case $1 in
		-k )	shift
			LICENSEKEY=$1
			;;
		-i )	shift
			PROJECTNAME=$1
			;;
		-u )	shift
			USERNAME=$1
			;;
		-s )	shift
			SAMPLING_INTERVAL=$1
			;;
		-r )	shift
			REPORTING_INTERVAL=$1
			;;
		-t )	shift
			AGENT_TYPE=$1
		;;
		-c )	shift
		CRON_INTERVAL=$1
		;;
		-p )	shift
		PASSWORD=$1
		;;
		-w )	shift
		SERVER_URL=$1
		;;
		* )	usage
			exit 1
	esac
	shift
done

if [ -z "$SERVER_URL" ]; then
	SERVER_URL='https://agent-data.insightfinder.com'
fi

if [ -z "$AGENT_TYPE" ] || [ -z "$REPORTING_INTERVAL" ] || [ -z "$CRON_INTERVAL" ] || [ -z "$PASSWORD" ] || [ -z "$SAMPLING_INTERVAL" ] || [ -z "$LICENSEKEY" ] || [ -z "$USERNAME" ] || [ -z "$PROJECTNAME" ]; then
	usage
	exit 1
fi


if [ $AGENT_TYPE != 'proc' ] && [ $AGENT_TYPE != 'cadvisor' ] && [ $AGENT_TYPE != 'docker_remote_api' ] && [ $AGENT_TYPE != 'cgroup' ] && [ $AGENT_TYPE != 'metricFileReplay' ] && [ $AGENT_TYPE != 'logFileReplay' ] && [ $AGENT_TYPE != 'daemonset' ] && [ $AGENT_TYPE != 'hypervisor' ] && [ $AGENT_TYPE != 'elasticsearch' ] && [ $AGENT_TYPE != 'collectd' ] && [ $AGENT_TYPE != 'ec2monitoring' ] && [ $AGENT_TYPE != 'jolokia'  ] && [ $AGENT_TYPE != 'kvm' ] && [ $AGENT_TYPE != 'datadog' ]; then
	usage
	exit 1
fi

if [ -z "$INSIGHTAGENTDIR" ]; then
	export INSIGHTAGENTDIR=`pwd`
fi


if [ $AGENT_TYPE == 'metricFileReplay' ] || [ $AGENT_TYPE == 'logFileReplay' ]; then
	exit 1
fi

TEMPCRON=$INSIGHTAGENTDIR/ifagentMaster
if [[ -f $TEMPCRON ]]
then
	rm $TEMPCRON
fi
USER=`whoami`

mkdir $INSIGHTAGENTDIR/log

echo "LICENSEKEY=$LICENSEKEY"
echo "INSTANCE=$PROJECTNAME"

echo "*/$CRON_INTERVAL * * * * root $INSIGHTAGENTDIR/pyenv/bin/python $INSIGHTAGENTDIR/agentMaster.py -n $USER -i $PROJECTNAME -u $USERNAME -k $LICENSEKEY -s $SAMPLING_INTERVAL -r $REPORTING_INTERVAL -t $AGENT_TYPE -w $SERVER_URL -p $PASSWORD 2>$INSIGHTAGENTDIR/log/agentMaster.err 1>$INSIGHTAGENTDIR/log/agentMaster.out" >> $TEMPCRON

sudo chown root:root $TEMPCRON
sudo chmod 644 $TEMPCRON
sudo mv $TEMPCRON /etc/cron.d/

echo "Agent configuration completed. One cron job is created via /etc/cron.d/ifagentMaster"

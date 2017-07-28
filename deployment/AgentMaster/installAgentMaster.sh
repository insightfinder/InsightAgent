#!/bin/bash
function usage()
{
	echo "Usage: ./installAgentMaster.sh -n USER_NAME_IN_HOSTS -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE -c CRON_INTERVAL -p PASSWORD -q PRIVATE_KEY -f FORCE_INSTALL
AGENT_TYPE = proc or cadvisor or docker_remote_api or cgroup or metricFileReplay or logFileReplay or daemonset or hypervisor or elasticsearch or collectd or ec2monitoring or jolokia or kvm"
}

#Installing Ansible
/bin/bash installAnsible.sh
#Checking exit status of ansible installation
rc=$?; 
if [[ $rc != 0 ]]; then 
	echo "Problems during Ansible Installation"
	exit $rc; 
fi

if [ "$#" -lt 20 ]; then
	echo "$#"
	usage
	exit 1
fi

while [ "$1" != "" ]; do
	case $1 in
		-n )	shift
			USER_NAME_IN_HOSTS=$1
			;;
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
		-f ) shift
			FORCE_INSTALL=$1
			;;
		-q ) shift
			PRIVATE_KEY=$1
			;;
		* )	usage
			exit 1
	esac
	shift
done

if [ -z "$SERVER_URL" ]; then
	SERVER_URL='https://agent-data.insightfinder.com'
fi

if [ -z "$FORCE_INSTALL" ]; then
	FORCE_INSTALL='false'
fi

if [ -z "$USER_NAME_IN_HOSTS" ] || [ -z "$AGENT_TYPE" ] || [ -z "$REPORTING_INTERVAL" ] || [ -z "$CRON_INTERVAL" ] || ( [ -z "$PASSWORD" ] && [ -z "$PRIVATE_KEY" ]) || [ -z "$SAMPLING_INTERVAL" ] || [ -z "$LICENSEKEY" ] || [ -z "$USERNAME" ] || [ -z "$PROJECTNAME" ]; then
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

#Check if log directory exists or not
if [ ! -d "$INSIGHTAGENTDIR/log" ]; then
	mkdir $INSIGHTAGENTDIR/log
fi


echo "LICENSEKEY=$LICENSEKEY"
echo "INSTANCE=$PROJECTNAME"


if [ -z "$PASSWORD" ]; then
	echo "*/$CRON_INTERVAL * * * * root python $INSIGHTAGENTDIR/agentMasterExecutor.py -n $USER_NAME_IN_HOSTS -i $PROJECTNAME -u $USERNAME -k $LICENSEKEY -s $SAMPLING_INTERVAL -r $REPORTING_INTERVAL -t $AGENT_TYPE -w $SERVER_URL -d $INSIGHTAGENTDIR -q $PRIVATE_KEY -f $FORCE_INSTALL 2>$INSIGHTAGENTDIR/log/agentMasterExecutor.err 1>$INSIGHTAGENTDIR/log/agentMasterExecutor.out" >> $TEMPCRON
else
	echo "*/$CRON_INTERVAL * * * * root python $INSIGHTAGENTDIR/agentMasterExecutor.py -n $USER_NAME_IN_HOSTS -i $PROJECTNAME -u $USERNAME -k $LICENSEKEY -s $SAMPLING_INTERVAL -r $REPORTING_INTERVAL -t $AGENT_TYPE -w $SERVER_URL -d $INSIGHTAGENTDIR -p $PASSWORD -f $FORCE_INSTALL 2>$INSIGHTAGENTDIR/log/agentMasterExecutor.err 1>$INSIGHTAGENTDIR/log/agentMasterExecutor.out" >> $TEMPCRON
fi

sudo chown root:root $TEMPCRON
sudo chmod 644 $TEMPCRON
sudo mv $TEMPCRON /etc/cron.d/

echo "Agent configuration completed. One cron job is created via /etc/cron.d/ifagentMaster"
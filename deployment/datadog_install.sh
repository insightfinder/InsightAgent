#!/bin/bash
function usage()
{
	echo "Usage: ./deployment/datadog_install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE -p API_KEY -a APP_KEY
AGENT_TYPE = proc or cadvisor or docker_remote_api or cgroup or metricFileReplay or logFileReplay or daemonset or hypervisor or elasticsearch or collectd or ec2monitoring or jolokia"
}

if [ "$#" -lt 12 ]; then
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
		-p )	shift
			API_KEY=$1
			;;
		-a )	shift
			APP_KEY=$1
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
	SERVER_URL='https://agentdata-dot-insightfindergae.appspot.com'
fi

if [ -z "$AGENT_TYPE" ] || [ -z "$APP_KEY" ] || [ -z "$API_KEY" ] || [ -z "$REPORTING_INTERVAL" ] || [ -z "$SAMPLING_INTERVAL" ] || [ -z "$USERNAME" ] || [ -z "$PROJECTNAME" ] || [ -z "$LICENSEKEY" ]; then
	usage
	exit 1
fi

if [ $AGENT_TYPE != 'proc' ] && [ $AGENT_TYPE != 'cadvisor' ] && [ $AGENT_TYPE != 'docker_remote_api' ] && [ $AGENT_TYPE != 'cgroup' ] && [ $AGENT_TYPE != 'metricFileReplay' ] && [ $AGENT_TYPE != 'logFileReplay' ] && [ $AGENT_TYPE != 'daemonset' ] && [ $AGENT_TYPE != 'hypervisor' ] && [ $AGENT_TYPE != 'elasticsearch' ] && [ $AGENT_TYPE != 'collectd' ] && [ $AGENT_TYPE != 'ec2monitoring' ] && [ $AGENT_TYPE != 'jolokia'  ] && [ $AGENT_TYPE != 'datadog' ] && [ $AGENT_TYPE != 'newrelic' ]; then
	usage
	exit 1
fi

if [ -z "$INSIGHTAGENTDIR" ]; then
	export INSIGHTAGENTDIR=`pwd`
fi

#if [[ $INSIGHTAGENTDIR != *"InsightAgent-master" ]] && [[ $INSIGHTAGENTDIR != *"InsightAgent-master/" ]];then
 #       echo "Wrong home directory. Run ./deployment/install.sh from InsightAgent-master folder"
 #       exit 1
#fi

if [ $AGENT_TYPE == 'daemonset' ]; then
	if ! python $INSIGHTAGENTDIR/deployment/verifyInsightCredentials.py -i $PROJECTNAME -u $USERNAME -k $LICENSEKEY -w $SERVER_URL
	then
            exit 1
	fi
	python $INSIGHTAGENTDIR/common/config/proxy_initconfig.py -r $REPORTING_INTERVAL
else
        if ! $INSIGHTAGENTDIR/pyenv/bin/python $INSIGHTAGENTDIR/deployment/verifyInsightCredentials.py -i $PROJECTNAME -u $USERNAME -k $LICENSEKEY -w $SERVER_URL
        then
            exit 1
        fi
	$INSIGHTAGENTDIR/pyenv/bin/python $INSIGHTAGENTDIR/common/config/proxy_initconfig.py -r $REPORTING_INTERVAL -u $USERNAME -p $PROJECTNAME
fi

#if [[ ! -d $INSIGHTAGENTDIR/data ]]
#then
mkdir -p $INSIGHTAGENTDIR/data/$USERNAME/$PROJECTNAME
#fi
#if [[ ! -d $INSIGHTAGENTDIR/log ]]
#then
mkdir -p $INSIGHTAGENTDIR/log/$USERNAME/$PROJECTNAME
#fi



TEMPCRON=${INSIGHTAGENTDIR}/ifagent_${USERNAME}_${PROJECTNAME}
if [[ -f $TEMPCRON ]]
then
	rm $TEMPCRON
fi
USER=`whoami`

echo "*/$SAMPLING_INTERVAL * * * * root $INSIGHTAGENTDIR/pyenv/bin/python $INSIGHTAGENTDIR/$AGENT_TYPE/proxy_getmetrics_$AGENT_TYPE.py -d $INSIGHTAGENTDIR -p $PROJECTNAME -u $USERNAME -k $API_KEY -a $APP_KEY  2>$INSIGHTAGENTDIR/log/$USERNAME/$PROJECTNAME/proxy_sampling.err 1>$INSIGHTAGENTDIR/log/$USERNAME/$PROJECTNAME/proxy_sampling.out" >> $TEMPCRON
echo "*/$REPORTING_INTERVAL * * * * root $INSIGHTAGENTDIR/pyenv/bin/python $INSIGHTAGENTDIR/common/proxy_reportMetrics.py -d $INSIGHTAGENTDIR -t $AGENT_TYPE -p $PROJECTNAME -u $USERNAME -k $LICENSEKEY 2>$INSIGHTAGENTDIR/log/$USERNAME/$PROJECTNAME/proxy_reporting.err 1>$INSIGHTAGENTDIR/log/$USERNAME/$PROJECTNAME/proxy_reporting.out" >> $TEMPCRON


sudo chown root:root $TEMPCRON
sudo chmod 644 $TEMPCRON
sudo mv $TEMPCRON /etc/cron.d/

echo "Agent configuration completed. Two cron jobs are created via /etc/cron.d/ifagent_${USERNAME}_${PROJECTNAME}"

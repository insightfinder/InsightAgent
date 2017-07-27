#!/bin/bash

function usage()
{
	echo "Usage: ./deployment/install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE
AGENT_TYPE = proc or cadvisor or docker_remote_api or cgroup or metricFileReplay or logFileReplay or daemonset or hypervisor or elasticsearch or collectd or ec2monitoring or jolokia or kvm or kafka or elasticsearch-storage"
}

if [ "$#" -lt 12 ]; then
	usage
	exit 1
fi


DEFAULT_SERVER_URL='https://agent-data.insightfinder.com'

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

if [ -z "$AGENT_TYPE" ] || [ -z "$REPORTING_INTERVAL" ] || [ -z "$SAMPLING_INTERVAL" ] || [ -z "$LICENSEKEY" ] || [ -z "$USERNAME" ] || [ -z "$PROJECTNAME" ]; then
	usage
	exit 1
fi

if [ $AGENT_TYPE != 'proc' ] && [ $AGENT_TYPE != 'cadvisor' ] && [ $AGENT_TYPE != 'docker_remote_api' ] && [ $AGENT_TYPE != 'cgroup' ] && [ $AGENT_TYPE != 'metricFileReplay' ] && [ $AGENT_TYPE != 'logFileReplay' ] && [ $AGENT_TYPE != 'daemonset' ] && [ $AGENT_TYPE != 'hypervisor' ] && [ $AGENT_TYPE != 'elasticsearch' ] && [ $AGENT_TYPE != 'collectd' ] && [ $AGENT_TYPE != 'ec2monitoring' ] && [ $AGENT_TYPE != 'jolokia'  ] && [ $AGENT_TYPE != 'datadog' ] && [ $AGENT_TYPE != 'newrelic' ] && [ $AGENT_TYPE != 'kvm' ] && [ $AGENT_TYPE != 'logStreaming' ] && [ $AGENT_TYPE != 'kafka' ] && [ $AGENT_TYPE != 'elasticsearch-storage' ]; then
	usage
	exit 1
fi

if [ -z "$INSIGHTAGENTDIR" ]; then
	export INSIGHTAGENTDIR=`pwd`
fi

if [[ $INSIGHTAGENTDIR != *"InsightAgent-master" ]] && [[ $INSIGHTAGENTDIR != *"InsightAgent-master/" ]];then
        echo "Wrong home directory. Run ./deployment/install.sh from InsightAgent-master folder"
        exit 1
fi
#Checking for pyenv folder. If it exists then use that else use default python
echo $INSIGHTAGENTDIR
PYTHONPATH=$INSIGHTAGENTDIR/pyenv
if [[ -d $PYTHONPATH ]]
then
	PYTHONPATH=$INSIGHTAGENTDIR/pyenv/bin/python
else
	PYTHONPATH=python
fi

if [ $AGENT_TYPE == 'daemonset' ]; then
	if ! $PYTHONPATH $INSIGHTAGENTDIR/deployment/verifyInsightCredentials.py -i $PROJECTNAME -u $USERNAME -k $LICENSEKEY -w $SERVER_URL
	then
            exit 1
	fi
	$PYTHONPATH $INSIGHTAGENTDIR/common/config/initconfig.py -r $REPORTING_INTERVAL
else
        if ! $PYTHONPATH $INSIGHTAGENTDIR/deployment/verifyInsightCredentials.py -i $PROJECTNAME -u $USERNAME -k $LICENSEKEY -w $SERVER_URL
        then
            exit 1
        fi
	$PYTHONPATH $INSIGHTAGENTDIR/common/config/initconfig.py -r $REPORTING_INTERVAL
fi

if [[ ! -d $INSIGHTAGENTDIR/data ]]
then
	mkdir $INSIGHTAGENTDIR/data
fi
if [[ ! -d $INSIGHTAGENTDIR/log ]]
then
	mkdir $INSIGHTAGENTDIR/log
fi
if [[ ! -d $INSIGHTAGENTDIR/custom ]]
then
        mkdir $INSIGHTAGENTDIR/custom
fi

AGENTRC=$INSIGHTAGENTDIR/.agent.bashrc
if [[ -f $AGENTRC ]]
then
	rm $AGENTRC
fi

echo "export INSIGHTFINDER_LICENSE_KEY=$LICENSEKEY" >> $AGENTRC
echo "export INSIGHTFINDER_PROJECT_NAME=$PROJECTNAME" >> $AGENTRC
echo "export INSIGHTFINDER_USER_NAME=$USERNAME" >> $AGENTRC
echo "export INSIGHTAGENTDIR=$INSIGHTAGENTDIR" >> $AGENTRC
echo "export SAMPLING_INTERVAL=$SAMPLING_INTERVAL" >> $AGENTRC
echo "export REPORTING_INTERVAL=$REPORTING_INTERVAL" >> $AGENTRC

if [ $AGENT_TYPE == 'metricFileReplay' ] || [ $AGENT_TYPE == 'logFileReplay' ]; then
	exit 1
fi

TEMPCRON=$INSIGHTAGENTDIR/ifagent
if [[ -f $TEMPCRON ]]
then
	rm $TEMPCRON
fi
USER=`whoami`

if [ $AGENT_TYPE == 'daemonset' ]; then
	echo "*/$SAMPLING_INTERVAL * * * * root $PYTHONPATH $INSIGHTAGENTDIR/$AGENT_TYPE/getmetrics_$AGENT_TYPE.py -d $INSIGHTAGENTDIR 2>$INSIGHTAGENTDIR/log/sampling.err 1>$INSIGHTAGENTDIR/log/sampling.out" >> $TEMPCRON
	echo "*/$REPORTING_INTERVAL * * * * root $PYTHONPATH $INSIGHTAGENTDIR/common/reportMetrics.py -d $INSIGHTAGENTDIR -t $AGENT_TYPE 2>$INSIGHTAGENTDIR/log/reporting.err 1>$INSIGHTAGENTDIR/log/reporting.out" >> $TEMPCRON
elif [ $AGENT_TYPE == 'collectd' ]; then
	echo "*/$REPORTING_INTERVAL * * * * root $PYTHONPATH $INSIGHTAGENTDIR/$AGENT_TYPE/collectdReportMetrics.py -d $INSIGHTAGENTDIR -w $SERVER_URL 2>$INSIGHTAGENTDIR/log/reporting.err 1>$INSIGHTAGENTDIR/log/reporting.out" >> $TEMPCRON

elif [ $AGENT_TYPE == 'logStreaming' ]; then
	echo "*/$REPORTING_INTERVAL * * * * root $PYTHONPATH $INSIGHTAGENTDIR/common/reportLog.py -d $INSIGHTAGENTDIR -w $SERVER_URL -m logStreaming 2>$INSIGHTAGENTDIR/log/reporting.err 1>$INSIGHTAGENTDIR/log/reporting.out" >> $TEMPCRON

else
	echo "*/$SAMPLING_INTERVAL * * * * root $PYTHONPATH $INSIGHTAGENTDIR/$AGENT_TYPE/getmetrics_$AGENT_TYPE.py -d $INSIGHTAGENTDIR 2>$INSIGHTAGENTDIR/log/sampling.err 1>$INSIGHTAGENTDIR/log/sampling.out" >> $TEMPCRON
	echo "*/$REPORTING_INTERVAL * * * * root $PYTHONPATH $INSIGHTAGENTDIR/common/reportMetrics.py -d $INSIGHTAGENTDIR -t $AGENT_TYPE -w $SERVER_URL 2>$INSIGHTAGENTDIR/log/reporting.err 1>$INSIGHTAGENTDIR/log/reporting.out" >> $TEMPCRON
fi

echo "*/$SAMPLING_INTERVAL * * * * root $PYTHONPATH $INSIGHTAGENTDIR/common/topology.py -d $INSIGHTAGENTDIR 2>$INSIGHTAGENTDIR/log/sampling_topology.err 1>$INSIGHTAGENTDIR/log/sampling_topology.out" >> $TEMPCRON
echo "*/$REPORTING_INTERVAL * * * * root $PYTHONPATH $INSIGHTAGENTDIR/common/reportTopology.py -d $INSIGHTAGENTDIR 2>$INSIGHTAGENTDIR/log/reporting_topology.err 1>$INSIGHTAGENTDIR/log/reporting_topology.out" >> $TEMPCRON

sudo chown root:root $TEMPCRON
sudo chmod 644 $TEMPCRON
sudo mv $TEMPCRON /etc/cron.d/

echo "Agent configuration completed. Two cron jobs are created via /etc/cron.d/ifagent"

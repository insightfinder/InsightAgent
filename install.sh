#!/bin/bash

function usage()
{
	echo "Usage: ./install.sh -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE
AGENT_TYPE = proc or cadvisor or docker_remote_api or cgroup or replay or daemonset"
}

if [ "$#" -lt 10 ]; then
	usage
	exit 1
fi

while [ "$1" != "" ]; do
	case $1 in
		-k )	shift
			PROJECTKEY=$1
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
		* )	usage
			exit 1
	esac
	shift
done

if [ $AGENT_TYPE != 'proc' ] && [ $AGENT_TYPE != 'cadvisor' ] && [ $AGENT_TYPE != 'docker_remote_api' ] && [ $AGENT_TYPE != 'cgroup' ] && [ $AGENT_TYPE != 'replay' ] && [ $AGENT_TYPE != 'daemonset' ]; then
	usage
	exit 1
fi

if [ -z "$INSIGHTAGENTDIR" ]; then
	export INSIGHTAGENTDIR=`pwd`
fi

python $INSIGHTAGENTDIR/initconfig.py -r $REPORTING_INTERVAL

if [[ ! -d $INSIGHTAGENTDIR/data ]]
then
	mkdir $INSIGHTAGENTDIR/data
fi
if [[ ! -d $INSIGHTAGENTDIR/log ]]
then
	mkdir $INSIGHTAGENTDIR/log
fi

AGENTRC=$INSIGHTAGENTDIR/.agent.bashrc
if [[ -f $AGENTRC ]]
then
	rm $AGENTRC
fi
echo "export INSIGHTFINDER_PROJECT_KEY=$PROJECTKEY" >> $AGENTRC
echo "export INSIGHTFINDER_USER_NAME=$USERNAME" >> $AGENTRC
echo "export INSIGHTAGENTDIR=$INSIGHTAGENTDIR" >> $AGENTRC

if [ $AGENT_TYPE == 'replay' ]; then
	exit 1
fi

TEMPCRON=$INSIGHTAGENTDIR/ifagent
if [[ -f $TEMPCRON ]]
then
	rm $TEMPCRON
fi
USER=`whoami`

if [ $AGENT_TYPE = 'proc' ]; then
	echo "*/$SAMPLING_INTERVAL * * * * root python $INSIGHTAGENTDIR/$AGENT_TYPE/getmetrics_proc.py -d $INSIGHTAGENTDIR 2>$INSIGHTAGENTDIR/log/sampling.err 1>$INSIGHTAGENTDIR/log/sampling.out" >> $TEMPCRON
elif [ $AGENT_TYPE = 'cadvisor' ]; then
	echo "*/$SAMPLING_INTERVAL * * * * root python $INSIGHTAGENTDIR/$AGENT_TYPE/getmetrics_cadvisor.py -d $INSIGHTAGENTDIR 2>$INSIGHTAGENTDIR/log/sampling.err 1>$INSIGHTAGENTDIR/log/sampling.out" >> $TEMPCRON
elif [ $AGENT_TYPE = 'docker_remote_api' ]; then
	echo "*/$SAMPLING_INTERVAL * * * * root python $INSIGHTAGENTDIR/$AGENT_TYPE/getmetrics_docker_remote_api.py -d $INSIGHTAGENTDIR 2>$INSIGHTAGENTDIR/log/sampling.err 1>$INSIGHTAGENTDIR/log/sampling.out" >> $TEMPCRON
elif [ $AGENT_TYPE = 'cgroup' ]; then
	echo "*/$SAMPLING_INTERVAL * * * * root python $INSIGHTAGENTDIR/$AGENT_TYPE/getmetrics_cgroup.py -d $INSIGHTAGENTDIR 2>$INSIGHTAGENTDIR/log/sampling.err 1>$INSIGHTAGENTDIR/log/sampling.out" >> $TEMPCRON
elif [ $AGENT_TYPE = 'daemonset' ]; then
	echo "*/$SAMPLING_INTERVAL * * * * root python $INSIGHTAGENTDIR/$AGENT_TYPE/getmetrics_daemonset.py -d $INSIGHTAGENTDIR 2>$INSIGHTAGENTDIR/log/sampling.err 1>$INSIGHTAGENTDIR/log/sampling.out" >> $TEMPCRON
fi

echo "*/$REPORTING_INTERVAL * * * * root python $INSIGHTAGENTDIR/csvtojson.py -d $INSIGHTAGENTDIR 2>$INSIGHTAGENTDIR/log/reporting.err 1>$INSIGHTAGENTDIR/log/reporting.out" >> $TEMPCRON
sudo chown root:root $TEMPCRON
sudo chmod 644 $TEMPCRON
sudo mv $TEMPCRON /etc/cron.d/

echo "Agent configuration completed. Two cron jobs are created via /etc/cron.d/ifagent" 

#!/bin/bash

function usage()
{
	echo "Usage: ./deployment/install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL -t AGENT_TYPE
AGENT_TYPE = proc or cadvisor or docker_remote_api or cgroup or metricFileReplay or logFileReplay or daemonset or hypervisor or elasticsearch or collectd or ec2monitoring or jolokia or nfdump or kvm or kafka or elasticsearch-storage or elasticsearch-log or opentsdb or kafka-log. Reporting/Sampling interval supports integer value denoting minutes and 10s i.e 10 seconds as a valid value"
}

function createCronMinute() {
	echo "*/$1 * * * * root $2" >> $3
}

function createCronSeconds() {
	echo "* * * * * root sleep 0; $1" >> $2
	echo "* * * * * root sleep 10; $1" >> $2
	echo "* * * * * root sleep 20; $1" >> $2
	echo "* * * * * root sleep 30; $1" >> $2
	echo "* * * * * root sleep 40; $1" >> $2
	echo "* * * * * root sleep 50; $1" >> $2
}

if [ "$#" -lt 10 ]; then
	usage
	exit 1
fi


DEFAULT_SERVER_URL='https://app.insightfinder.com'

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
		-t )	shift
			AGENT_TYPE=$1
			;;
		-w )	shift
			SERVER_URL=$1
			;;
		-p )	shift
			NFSEN_FOLDER=$1
			;;
		-c )	shift
			CHUNK_SIZE=$1
			;;
		-l )	shift
			CHUNK_LINES=$1
			;;
		* )	usage
			exit 1
	esac
	shift
done

REPORTING_INTERVAL=$SAMPLING_INTERVAL

#Check if sampling interval is in seconds
lastCharSampling=${SAMPLING_INTERVAL: -1}
IS_SECOND_SAMPLING=false
if [ $lastCharSampling == 's' ];then
	IS_SECOND_SAMPLING=true
	SECONDS_VALUE_SAMPLING=${SAMPLING_INTERVAL:0:-1}
	#Only allowed seconds value is 10
	if [ $SECONDS_VALUE_SAMPLING != '10' ];then
		usage
		exit 1
	fi
fi

#Check if reporting interval is in seconds
lastCharReporting=${REPORTING_INTERVAL: -1}
IS_SECOND_REPORTING=false
if [ $lastCharReporting == 's' ];then
	IS_SECOND_REPORTING=true
	SECONDS_VALUE_REPORTING=${REPORTING_INTERVAL:0:-1}
	#Only allowed seconds value is 10
	if [ $SECONDS_VALUE_REPORTING != '10' ];then
		usage
		exit 1
	fi
fi


if [ -z "$SERVER_URL" ]; then
	SERVER_URL='https://app.insightfinder.com'
fi

if [ -z "$AGENT_TYPE" ] || [ -z "$REPORTING_INTERVAL" ] || [ -z "$SAMPLING_INTERVAL" ] || [ -z "$LICENSEKEY" ] || [ -z "$USERNAME" ] || [ -z "$PROJECTNAME" ]; then
	usage
	exit 1
fi

if [ $AGENT_TYPE != 'proc' ] && [ $AGENT_TYPE != 'cadvisor' ] && [ $AGENT_TYPE != 'elasticsearch-log' ] && [ $AGENT_TYPE != 'docker_remote_api' ] && [ $AGENT_TYPE != 'cgroup' ] && [ $AGENT_TYPE != 'metricFileReplay' ] && [ $AGENT_TYPE != 'logFileReplay' ] && [ $AGENT_TYPE != 'daemonset' ] && [ $AGENT_TYPE != 'hypervisor' ] && [ $AGENT_TYPE != 'elasticsearch' ] && [ $AGENT_TYPE != 'collectd' ] && [ $AGENT_TYPE != 'ec2monitoring' ] && [ $AGENT_TYPE != 'jolokia'  ] && [ $AGENT_TYPE != 'datadog' ] && [ $AGENT_TYPE != 'newrelic' ] && [ $AGENT_TYPE != 'kvm' ] && [ $AGENT_TYPE != 'logStreaming' ] && [ $AGENT_TYPE != 'kafka' ] && [ $AGENT_TYPE != 'elasticsearch-storage' ] && [ $AGENT_TYPE != 'nfdump' ] && [ $AGENT_TYPE != 'opentsdb' ] && [ $AGENT_TYPE != 'kafka-logs' ]; then
	usage
	exit 1
fi

if [ -z "$INSIGHTAGENTDIR" ]; then
	export INSIGHTAGENTDIR=`pwd`
fi

#Checking for pyenv folder. If it exists then use that else use default python
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

## adding common parameters here
add_insightfinder_details (){
    PATH_TO_CONFIG_INI=$1
    echo -en '\n' >> $PATH_TO_CONFIG_INI
    echo "[insightfinder]" >> $PATH_TO_CONFIG_INI
    echo "insightfinder_license_key=$LICENSEKEY" >> $PATH_TO_CONFIG_INI
    echo "insightfinder_project_name=$PROJECTNAME" >> $PATH_TO_CONFIG_INI
    echo "insightfinder_user_name=$USERNAME" >> $PATH_TO_CONFIG_INI
    echo "sampling_interval=$SAMPLING_INTERVAL" >> $PATH_TO_CONFIG_INI
}

export_insightfinder_details() {
    echo "export INSIGHTFINDER_LICENSE_KEY=$LICENSEKEY" >> $AGENTRC
	echo "export INSIGHTFINDER_PROJECT_NAME=$PROJECTNAME" >> $AGENTRC
	echo "export INSIGHTFINDER_USER_NAME=$USERNAME" >> $AGENTRC
	echo "export INSIGHTAGENTDIR=$INSIGHTAGENTDIR" >> $AGENTRC
	echo "export SAMPLING_INTERVAL=$SAMPLING_INTERVAL" >> $AGENTRC
}

# initializing variables
DIRECTORY="$INSIGHTAGENTDIR""/"$AGENT_TYPE
PATH_TO_CONFIG_INI="$DIRECTORY""/config.ini"
HEADER_STR="["$AGENT_TYPE"]"

if [ "$AGENT_TYPE" = "kafka" ]; then
        if [ -d "$DIRECTORY" -a ! -f $PATH_TO_CONFIG_INI ]; then
                touch $PATH_TO_CONFIG_INI
                echo $HEADER_STR >> $PATH_TO_CONFIG_INI
                ## add agent specific parameters here
                echo "bootstrap_servers=" >> $PATH_TO_CONFIG_INI
                echo "topic=" >> $PATH_TO_CONFIG_INI
                echo "filter_hosts=" >> $PATH_TO_CONFIG_INI
                echo "all_metrics=" >> $PATH_TO_CONFIG_INI
                echo "normalization_id=" >> $PATH_TO_CONFIG_INI
                echo "group_id=" >> $PATH_TO_CONFIG_INI

                add_insightfinder_details $PATH_TO_CONFIG_INI
        else
            echo "config.ini exists or directory doesnt exist.."
        fi
elif [ "$AGENT_TYPE" = "cadvisor" ]; then
	if [ -d "$DIRECTORY" -a ! -f $DIRECTORY/config.ini ]; then
		touch $PATH_TO_CONFIG_INI
        echo $HEADER_STR >> $PATH_TO_CONFIG_INI
        ## add agent specific parameters here

        echo "sampling_interval=$SAMPLING_INTERVAL" >> $PATH_TO_CONFIG_INI

		add_insightfinder_details $AGENT_TYPE
	else
            echo "config.ini exists or directory doesnt exist.."
        fi
elif [ "$AGENT_TYPE" = "collectd" ]; then
	if [ -d "$DIRECTORY" -a ! -f $DIRECTORY/config.ini ]; then
		touch $PATH_TO_CONFIG_INI
        echo $HEADER_STR >> $PATH_TO_CONFIG_INI
        ## add agent specific parameters here

        add_insightfinder_details $AGENT_TYPE
	else
            echo "config.ini exists or directory doesnt exist.."
        fi
elif [ "$AGENT_TYPE" = "common" ]; then
	if [ -d "$DIRECTORY" -a ! -f $DIRECTORY/config.ini ]; then
		touch $PATH_TO_CONFIG_INI
        echo $HEADER_STR >> $PATH_TO_CONFIG_INI
        ## add agent specific parameters here

        add_insightfinder_details $AGENT_TYPE
	else
            echo "config.ini exists or directory doesnt exist.."
        fi
elif [ "$AGENT_TYPE" = "elasticsearch-log" ]; then
	if [ -d "$DIRECTORY" -a ! -f $DIRECTORY/config.ini ]; then
		touch $PATH_TO_CONFIG_INI
        echo $HEADER_STR >> $PATH_TO_CONFIG_INI
        ## add agent specific parameters here

        add_insightfinder_details $AGENT_TYPE
	else
            echo "config.ini exists or directory doesnt exist.."
        fi
        elif [ "$AGENT_TYPE" = "metadata" ]; then
	if [ -d "$DIRECTORY" -a ! -f $DIRECTORY/config.ini ]; then
		touch $PATH_TO_CONFIG_INI
        echo $HEADER_STR >> $PATH_TO_CONFIG_INI
        ## add agent specific parameters here

        add_insightfinder_details $AGENT_TYPE
	else
            echo "config.ini exists or directory doesnt exist.."
        fi
elif [ "$AGENT_TYPE" = "opentsdb" ]; then
	if [ -d "$DIRECTORY" -a ! -f $DIRECTORY/config.ini ]; then
		touch $PATH_TO_CONFIG_INI
        echo $HEADER_STR >> $PATH_TO_CONFIG_INI
        ## add agent specific parameters here
        echo "opentsdb_server_url=" >> $PATH_TO_CONFIG_INI
        echo "token=" >> $PATH_TO_CONFIG_INI
        echo "metrics=" >> $PATH_TO_CONFIG_INI
        add_insightfinder_details $AGENT_TYPE
	else
            echo "config.ini exists or directory doesnt exist.."
        fi
else
	echo "No agent type given.. exporting insightfinder details"
	export_insightfinder_details
fi

if [ $AGENT_TYPE == 'metricFileReplay' ] || [ $AGENT_TYPE == 'logFileReplay' ]; then
	exit 0
fi

TEMPCRON=$INSIGHTAGENTDIR/ifagent
if [[ -f $TEMPCRON ]]
then
	rm $TEMPCRON
fi
USER=`whoami`


if [ $AGENT_TYPE == 'daemonset' ]; then
	COMMAND_SAMPLING="$PYTHONPATH $INSIGHTAGENTDIR/$AGENT_TYPE/getmetrics_$AGENT_TYPE.py -d $INSIGHTAGENTDIR 2>$INSIGHTAGENTDIR/log/sampling.err 1>$INSIGHTAGENTDIR/log/sampling.out"
	COMMAND_REPORTING="$PYTHONPATH $INSIGHTAGENTDIR/common/reportMetrics.py -d $INSIGHTAGENTDIR -t $AGENT_TYPE 2>$INSIGHTAGENTDIR/log/reporting.err 1>$INSIGHTAGENTDIR/log/reporting.out"
	if [ "$IS_SECOND_SAMPLING" = true ] ; then
		createCronSeconds "${COMMAND_SAMPLING}" $TEMPCRON
	else
		createCronMinute $SAMPLING_INTERVAL "${COMMAND_SAMPLING}" $TEMPCRON
	fi
	if [ "$IS_SECOND_REPORTING" = true ] ; then
		createCronSeconds "${COMMAND_REPORTING}" $TEMPCRON
	else
		createCronMinute $REPORTING_INTERVAL "${COMMAND_REPORTING}" $TEMPCRON
	fi
elif [ $AGENT_TYPE == 'collectd' ]; then
	COMMAND_REPORTING="$PYTHONPATH $INSIGHTAGENTDIR/$AGENT_TYPE/collectdReportMetrics.py -d $INSIGHTAGENTDIR -w $SERVER_URL 2>$INSIGHTAGENTDIR/log/reporting.err 1>$INSIGHTAGENTDIR/log/reporting.out"
	if [ "$IS_SECOND_REPORTING" = true ] ; then
		createCronSeconds "${COMMAND_REPORTING}" $TEMPCRON
	else
		createCronMinute $REPORTING_INTERVAL "${COMMAND_REPORTING}" $TEMPCRON
	fi
elif [ $AGENT_TYPE == 'elasticsearch-log' ]; then
	COMMAND_REPORTING="$PYTHONPATH $INSIGHTAGENTDIR/elasticsearch-log/get_logs_elasticsearch.py -d $INSIGHTAGENTDIR -w $SERVER_URL 2>$INSIGHTAGENTDIR/log/reporting.err 1>$INSIGHTAGENTDIR/log/reporting.out"
	if [ "$IS_SECOND_REPORTING" = true ] ; then
		createCronSeconds "${COMMAND_REPORTING}" $TEMPCRON
	else
		createCronMinute $REPORTING_INTERVAL "${COMMAND_REPORTING}" $TEMPCRON
	fi
elif [ $AGENT_TYPE == 'nfdump' ]; then
    if [ -z "$NFSEN_FOLDER" ]; then
	    NFSEN_FOLDER='/data/nfsen/profiles-data/live'
    fi
	COMMAND_REPORTING="$PYTHONPATH $INSIGHTAGENTDIR/$AGENT_TYPE/getmetrics_nfdump.py -d $INSIGHTAGENTDIR -w $SERVER_URL -p $NFSEN_FOLDER 2>$INSIGHTAGENTDIR/log/reporting.err 1>$INSIGHTAGENTDIR/log/reporting.out"
	if [ "$IS_SECOND_REPORTING" = true ] ; then
		createCronSeconds "${COMMAND_REPORTING}" $TEMPCRON
	else
		createCronMinute $REPORTING_INTERVAL "${COMMAND_REPORTING}" $TEMPCRON
	fi
elif [ $AGENT_TYPE == 'opentsdb' ]; then
    if [ -z "$CHUNK_SIZE" ]; then
	    CHUNK_SIZE='50'
    fi
	COMMAND_REPORTING="$PYTHONPATH $INSIGHTAGENTDIR/$AGENT_TYPE/getmetrics_opentsdb.py -d $INSIGHTAGENTDIR -w $SERVER_URL -c $CHUNK_SIZE 2>$INSIGHTAGENTDIR/log/reporting.err 1>$INSIGHTAGENTDIR/log/reporting.out"
	if [ "$IS_SECOND_REPORTING" = true ] ; then
		createCronSeconds "${COMMAND_REPORTING}" $TEMPCRON
	else
		createCronMinute $REPORTING_INTERVAL "${COMMAND_REPORTING}" $TEMPCRON
	fi
elif [ $AGENT_TYPE == 'kafka-logs' ]; then
	MONITRCLOC=/etc/monit/monitrc
	MONITCONFIGLOC=/etc/monit/monit.conf
	echo "check process kafka-logs matching \"kafka_logs/getlogs_kafka.py\"
			start program = \"/usr/bin/nohup $PYTHONPATH $INSIGHTAGENTDIR/kafka_logs/getlogs_kafka.py -d $INSIGHTAGENTDIR -w $SERVER_URL -l $CHUNK_LINES &>$INSIGHTAGENTDIR/log/kafka-logs.log &\"
     		" >> $MONITRCLOC
    echo "check process kafka-logs matching \"kafka_logs/getlogs_kafka.py\"
			start program = \"/usr/bin/nohup $PYTHONPATH $INSIGHTAGENTDIR/kafka_logs/getlogs_kafka.py -d $INSIGHTAGENTDIR -w $SERVER_URL -l $CHUNK_LINES &>$INSIGHTAGENTDIR/log/kafka-logs.log &\"
     		" >> MONITCONFIGLOC
    /usr/bin/nohup $PYTHONPATH $INSIGHTAGENTDIR/kafka_logs/getlogs_kafka.py -d $INSIGHTAGENTDIR -w $SERVER_URL -l $CHUNK_LINES &>$INSIGHTAGENTDIR/log/kafka-logs.log &
    service monit restart
elif [ $AGENT_TYPE == 'kafka' ]; then
	MONITRCLOC=/etc/monit/monitrc
	MONITCONFIGLOC=/etc/monit/monit.conf
	echo "check process kafka matching \"kafka/getmetrics_kafka.py\"
			start program = \"/usr/bin/nohup $PYTHONPATH $INSIGHTAGENTDIR/kafka/getmetrics_kafka.py -d $INSIGHTAGENTDIR -w $SERVER_URL &>$INSIGHTAGENTDIR/log/kafka-metrics.log &\"
     		" >> $MONITRCLOC
    echo "check process kafka matching \"kafka/getmetrics_kafka.py\"
			start program = \"/usr/bin/nohup $PYTHONPATH $INSIGHTAGENTDIR/kafka/getmetrics_kafka.py -d $INSIGHTAGENTDIR -w $SERVER_URL &>$INSIGHTAGENTDIR/log/kafka-metrics.log &\"
     		" >> $MONITCONFIGLOC
    /usr/bin/nohup $PYTHONPATH $INSIGHTAGENTDIR/kafka/getmetrics_kafka.py -d $INSIGHTAGENTDIR -w $SERVER_URL &>$INSIGHTAGENTDIR/log/kafka-metrics.log &
    service monit restart
elif [ $AGENT_TYPE == 'logStreaming' ]; then
	echo "*/$REPORTING_INTERVAL * * * * root $PYTHONPATH $INSIGHTAGENTDIR/common/reportLog.py -d $INSIGHTAGENTDIR -w $SERVER_URL -m logStreaming 2>$INSIGHTAGENTDIR/log/reporting.err 1>$INSIGHTAGENTDIR/log/reporting.out" >> $TEMPCRON
else
	COMMAND_SAMPLING="$PYTHONPATH $INSIGHTAGENTDIR/$AGENT_TYPE/getmetrics_$AGENT_TYPE.py -d $INSIGHTAGENTDIR 2>$INSIGHTAGENTDIR/log/sampling.err 1>$INSIGHTAGENTDIR/log/sampling.out"
	COMMAND_REPORTING="$PYTHONPATH $INSIGHTAGENTDIR/common/reportMetrics.py -d $INSIGHTAGENTDIR -t $AGENT_TYPE -w $SERVER_URL 2>$INSIGHTAGENTDIR/log/reporting.err 1>$INSIGHTAGENTDIR/log/reporting.out"
	if [ "$IS_SECOND_SAMPLING" = true ] ; then
		createCronSeconds "${COMMAND_SAMPLING}" $TEMPCRON
	else
		createCronMinute $SAMPLING_INTERVAL "${COMMAND_SAMPLING}" $TEMPCRON
	fi
	if [ "$IS_SECOND_REPORTING" = true ] ; then
		createCronSeconds "${COMMAND_REPORTING}" $TEMPCRON
	else
		createCronMinute $REPORTING_INTERVAL "${COMMAND_REPORTING}" $TEMPCRON
	fi
fi

sudo /usr/bin/pkill -f "script_runner.py"
sudo nohup $PYTHONPATH $INSIGHTAGENTDIR/script_runner/script_runner.py -d $INSIGHTAGENTDIR -w $SERVER_URL &>$INSIGHTAGENTDIR/log/script_runner.log &


#!/bin/bash

function usage()
{
	echo "Usage: ./deployInsightAgent.sh -n USER_NAME_IN_HOST -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE
AGENT_TYPE = proc or cadvisor or docker_remote_api or cgroup or filereplay or daemonset or hypervisor or elasticsearch or collectd or ec2monitoring or jolokia or kafka or elasticsearch-storage"
}

if [ "$#" -lt 14 ]; then
	usage
	exit 1
fi

while [ "$1" != "" ]; do
	case $1 in
		-n )	shift
			INSIGHTFINDER_USERNAME=$1
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
		* )	usage
			exit 1
	esac
	shift
done

if [ $AGENT_TYPE != 'proc' ] && [ $AGENT_TYPE != 'cadvisor' ] && [ $AGENT_TYPE != 'docker_remote_api' ] && [ $AGENT_TYPE != 'cgroup' ] && [ $AGENT_TYPE != 'filereplay' ] && [ $AGENT_TYPE != 'daemonset' ] && [ $AGENT_TYPE != 'hypervisor' ] && [ $AGENT_TYPE != 'elasticsearch' ] && [ $AGENT_TYPE != 'collectd' ] && [ $AGENT_TYPE != 'ec2monitoring' ] && [ $AGENT_TYPE != 'jolokia' ] && [ $AGENT_TYPE != 'kafka' ] && [ $AGENT_TYPE != 'elasticsearch-storage' ]; then
	usage
	exit 1
fi

wget https://bootstrap.pypa.io/get-pip.py && python get-pip.py --force-reinstall --user
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/requirements
~/.local/bin/pip install -U --force-reinstall --user virtualenv
if [ "$?" -ne "0" ]; then
    echo "pip install failed. Please install the pre-requisites using the following commands and retry deployment again"
if [ "$(command -v yum)" ]; then
    echo "sudo yum update"
    echo "sudo yum install gcc libffi-devel python-devel openssl-devel wget"
else
    echo "sudo apt-get upgrade"
    echo "sudo apt-get install build-essential libssl-dev libffi-dev python-dev wget"
fi
    rm get-pip.py
    rm requirements
    exit 1
fi
version=`python -c 'import sys; print(str(sys.version_info[0])+"."+str(sys.version_info[1]))'`
if [ "$?" -ne "0" ]; then
    echo "Unable to get python version. Please install the pre-requisites using the following commands and retry deployment again"
if [ "$(command -v yum)" ]; then
    echo "sudo yum update"
    echo "sudo yum install gcc libffi-devel python-devel openssl-devel wget"
else
    echo "sudo apt-get upgrade"
    echo "sudo apt-get install build-essential libssl-dev libffi-dev python-dev wget"
fi
    rm get-pip.py
    rm requirements
    exit 1

fi
python  ~/.local/lib/python$version/site-packages/virtualenv.py pyenv
if [ "$?" -ne "0" ]; then
    echo "Unable to install python virtual environment. Please install the pre-requisites using the following commands and retry deployment again"
if [ "$(command -v yum)" ]; then
    echo "sudo yum update"
    echo "sudo yum install gcc libffi-devel python-devel openssl-devel wget"
else
    echo "sudo apt-get upgrade"
    echo "sudo apt-get install build-essential libssl-dev libffi-dev python-dev wget"
fi
    rm get-pip.py
    rm requirements
    exit 1
fi
source pyenv/bin/activate
pip install -r requirements
if [ "$?" -ne "0" ]; then
    echo "Install failed. Please install the pre-requisites using the following commands and retry deployment again"
if [ "$(command -v yum)" ]; then
    echo "sudo yum update"
    echo "sudo yum install gcc libffi-devel python-devel openssl-devel wget"
else
    echo "sudo apt-get upgrade"
    echo "sudo apt-get install build-essential libssl-dev libffi-dev python-dev wget"
fi
    rm get-pip.py
    rm requirements
    rm -rf pyenv
    deactivate
    exit 1
fi

rm requirements
rm get-pip.py

wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/verifyInsightCredentials.py
if ! python verifyInsightCredentials.py -i $PROJECTNAME -u $USERNAME -k $LICENSEKEY
then
    rm verifyInsightCredentials.py
    rm -rf pyenv
    deactivate
    exit 1
fi
rm verifyInsightCredentials.py

wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/deployInsightAgent.py
python deployInsightAgent.py -n $INSIGHTFINDER_USERNAME -i $PROJECTNAME -u $USERNAME -k $LICENSEKEY -s $SAMPLING_INTERVAL -r $REPORTING_INTERVAL -t $AGENT_TYPE
deactivate
rm -rf pyenv
rm deployInsightAgent.sh

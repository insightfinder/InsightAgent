#!/bin/bash

function usage()
{
	echo "Usage: ./stopcron.sh -n USER_NAME_IN_HOST -p PASSWORD"
}

if [ "$#" -lt 4 ]; then
	usage
	exit 1
fi

while [ "$1" != "" ]; do
	case $1 in
		-n )	shift
			USERNAME=$1
			;;
		-p )	shift
			PASSWORD=$1
			;;
		* )	usage
			exit 1
	esac
	shift
done


wget https://bootstrap.pypa.io/get-pip.py && python get-pip.py --force-reinstall --user
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/testing/deployment/requirements
/home/$USER/.local/bin/pip install -U --force-reinstall --user virtualenv
if [ "$?" -ne "0" ]; then
    echo "pip install failed. Please install the pre-requisites using the following commands and retry stopcron again"
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
    echo "Unable to get python version. Please install the pre-requisites using the following commands and retry stopcron again"
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
python  /home/$USER/.local/lib/python$version/site-packages/virtualenv.py pyenv
if [ "$?" -ne "0" ]; then
    echo "Unable to install python virtual environment. Please install the pre-requisites using the following commands and retry stopcron again"
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
    echo "Install failed. Please install the pre-requisites using the following commands and retry stopcron again"
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

wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/testing/deployment/stopcron.py
python stopcron.py -n $USERNAME -p $PASSWORD
deactivate
rm -rf pyenv
rm stopcron.sh

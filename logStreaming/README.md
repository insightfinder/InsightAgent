# InsightAgent: Log Streaming
Agent Type: LogStreaming

Platform: Linux

InsightAgent supports an integration with fluentd's td-agent, allowing log data to be streamed from log files on an "updates only" basis and in turn, sent to an InsightFinder server.

##### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Insight Agent" tab.
- Give a project name, select Project Type as "Log File".
- Note down the project name and license key which will be used for agent installation. The license key is also available in "User Account Information". To go to "User Account Information", click the userid on the top right corner.

# Pre-requisites:
## Python 2.7

For Debian and Ubuntu, the following command will ensure that the required dependencies are installed:
```
sudo apt-get upgrade
sudo apt-get install build-essential libssl-dev libffi-dev python-dev wget
```
For Fedora and RHEL-derivatives, the following command will ensure that the required dependencies are installed:
```
sudo yum update
sudo yum install gcc libffi-devel python-devel openssl-devel wget
```
# Install td-agent

Per (td-agent's web site)[http://docs.fluentd.org/v0.12/articles/before-install], please work with a system administrator to insure that the td-agent's pre-requisites are met:
- ntp is enabled
- The system's maximum number of file descriptors (both soft and hard limits) are set to 65536

## For Debian/Ubuntu systems, install td-agent with the appropriate command below:

For Xenial:
```
curl -L https://toolbelt.treasuredata.com/sh/install-ubuntu-xenial-td-agent2.sh | sh
```
For Trusty:
```
curl -L https://toolbelt.treasuredata.com/sh/install-ubuntu-trusty-td-agent2.sh | sh
```
For Precise:
```
curl -L https://toolbelt.treasuredata.com/sh/install-ubuntu-precise-td-agent2.sh | sh
```
For Lucid:
```
curl -L https://toolbelt.treasuredata.com/sh/install-ubuntu-lucid-td-agent2.sh | sh
```
For Debian Jessie:
```
curl -L https://toolbelt.treasuredata.com/sh/install-debian-jessie-td-agent2.sh | sh
```
For Debian Wheezy:
```
curl -L https://toolbelt.treasuredata.com/sh/install-debian-wheezy-td-agent2.sh | sh
```
For Debian Squeeze:
```
curl -L https://toolbelt.treasuredata.com/sh/install-debian-squeeze-td-agent2.sh | sh
```

Start the td-agent daemon:

The /etc/init.d/td-agent script is provided to start, stop, or restart the agent.
```
$ /etc/init.d/td-agent restart
$ /etc/init.d/td-agent status
td-agent (pid  21678) is running...
```
The following commands are supported:
```
$ /etc/init.d/td-agent start
$ /etc/init.d/td-agent stop
$ /etc/init.d/td-agent restart
$ /etc/init.d/td-agent status
```
Please make sure your configuration file is located at /etc/td-agent/td-agent.conf

For more details on Debian/Ubuntu-specific installation, please see the (td-agent web site)[http://docs.fluentd.org/v0.12/articles/install-by-deb].

## For td-agent on Red Hat/CentOS/Amazon Linux and other RHEL derivative distributions

Execute the following command on your system as root or equivalent:
```
$ curl -L https://toolbelt.treasuredata.com/sh/install-redhat-td-agent2.sh | sh
```

Start the td-agent daemon:

The /etc/init.d/td-agent script is provided to start, stop, or restart the agent.
```
$ /etc/init.d/td-agent start 
Starting td-agent: [  OK  ]
$ /etc/init.d/td-agent status
td-agent (pid  21678) is running...
```

The following commands are supported:
```
$ /etc/init.d/td-agent start
$ /etc/init.d/td-agent stop
$ /etc/init.d/td-agent restart
$ /etc/init.d/td-agent status
```

Please make sure your configuration file is located at /etc/td-agent/td-agent.conf.

## Download and Install InsightFinder's Insight Agent:

1) Use the following command to download the insightfinder agent code.
```
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
```
Untar using this command.
```
tar -xvf insightagent.tar.gz
```

2) In the InsightAgent-master directory, run the following commands to install and use python virtual environment for the Insight Agent:
```
./deployment/checkpackages.sh
```
```
source pyenv/bin/activate
```

3) Install and enable the Insight Agent's logStreaming agent.
```
./deployment/install.sh -i PROJECT_NAME -u INSIGHTFINDER_USER_NAME -k LICENSE_KEY -s 1 -r 1 -t logStreaming
```

## Configure the td-agent to find and monitor the log files you wish to integrate.

For your convenience, we have included a sample td-agent configuration that includes configuration directives to monitor a Cassandra system.log file and forward its contents to an InsightFinder server.

For additional information on td-agent configuration, please see the td-agent web site: http://docs.fluentd.org/v0.12/articles/config-file#list-of-directives and as always, don't hesitate to contact InsightFinder support at support@insightfinder.com

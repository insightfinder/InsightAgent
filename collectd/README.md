# InsightAgent: collectd
Agent Type: collectd

Platform: Linux

InsightFinder agent can be used to monitor system performance metrics on bare metal machines or virtual machines using collectd.

collectd is an open source daemon that collects statistics from a system and publishes them to insightfinder server.

Supported collectd version: collectd-5.5.2

Tested on Centos 7.

##### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Insight Agent" tab.
- Give a project name, select Project Type as "Private Cloud".
- Note down license key which is available in "User Account Information". To go to "User Account Information", click the userid on the top right corner.

##### Pre-requisites:
Python 2.7.

This pre-requisite is needed on the machine which launches deployInsightAgent.sh.
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

##### Collectd Configuration Requirements:

- collectd should be installed and running.
- collectd should be installed in /opt/ and the configuration file is available in /opt/collectd/etc/collectd.conf
- Check collectd.conf as the following plugins should be installed and available:
```
cpu, csv, disk, interface, load, memory, processes
```
- The following lines in the collectd.conf should be uncommented. See sample configuration file "collectdsample.conf" for example.
```
Interval 60
LoadPlugin cpu
LoadPlugin csv
LoadPlugin disk
LoadPlugin processes
LoadPlugin memory
LoadPlugin interface
LoadPlugin load

<Plugin cpu>
  ReportByCpu false
  ReportByState false
  ValuesPercentage false
</Plugin>

<Plugin csv>
        DataDir "${prefix}/var/lib/collectd/csv"
        StoreRates false
</Plugin>
```
- The Interval above is specified in seconds. Set it to required sampling value. It specifies how often data is collected.

##### To deploy agent on multiple hosts:

- Get the deployment script from github using below command:
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/deployInsightAgent.sh
```
- Change permission of "deployInsightAgent.sh" as a executable.
- Get IP address of all machines (or hosts) on which InsightFinder agent needs to be installed.
- All machines should have same login username and password.
- Include IP address of all hosts in hostlist.txt and enter one IP address per line.
- To deploy run the following command:
```
./deployInsightAgent.sh -n USER_NAME_IN_HOST
                        -i PROJECT_NAME_IN_INSIGHTFINDER
                        -u USER_NAME_IN_INSIGHTFINDER
                        -k LICENSE_KEY
                        -s SAMPLING_INTERVAL_MINUTE
                        -r REPORTING_INTERVAL_MINUTE
                        -t AGENT_TYPE
AGENT_TYPE is *collectd*.
```
- When the above script is run, if prompted for password, enter either the password or the name of the identity file along with file path.
Example: /home/insight/.ssh/id_rsa


##### To get more details on the command, run
```
./deployInsightAgent.sh
```

##### To undo agent deployment on multiple hosts:
- Get the script for stopping agents from github using below command:
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/stopcron.sh
```
and change the permissions with the command.
```
 chmod 755 stopcron.sh
```
- Include IP address of all hosts in hostlist.txt and enter one IP address per line.
- To stop the agent run the following command:
```
./stopcron.sh -n USER_NAME_IN_HOST -p PASSWORD

USER_NAME_IN_HOST - username used to login into the host machines
PASSWORD - password or name of the identity file along with path
```

##### To install agent on local machine:
```
./deployment/install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE
```


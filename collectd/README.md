# InsightAgent: collectd
Agent Type: collectd

Platform: Linux

The InsightAgent can be used to monitor system performance metrics from collectd on bare metal or virtual machines.

collectd is an open source daemon that collects statistics from a system and publishes them to insightfinder server.

Supported collectd version: collectd-5.5.2.  If you have deployed another version, please contact support@insightfinder.com for updates specific to your version.

Tested on RHEL/CentOS/AmazonLinux 6 & 7.  If you are using another distribution, please contact support@insightfinder.com for updates specific to your version.

##### Instructions to register a project in Insightfinder.com
- Go to [insightfinder.com](https://insightfinder.com/)
- Sign in with your user credentials or sign up for a new account.
- Go to Settings and Register a new project (top icon on the left navigation bar) under "Insight Agent" tab.
- Provide a project name and select the appropriate project type:  "AWS" if your host is on AWS, "GAE" if your host is on Google, or "Private Cloud" for any other provider.
- View your account information -- including license key -- by clicking on your User ID at the top right corner of the user interface. Note that the license key number is required at agent installation time.

##### Pre-requisites
Python 2.7.

Python 2.7 must be installed in order to launch deployInsightAgent.sh. For Debian and Ubuntu, the following command will ensure that the required dependencies are present
```
sudo apt-get upgrade
sudo apt-get install build-essential libssl-dev libffi-dev python-dev wget
```
For Fedora and RHEL-derivatives
```
sudo yum update
sudo yum install gcc libffi-devel python-devel openssl-devel wget
```

##### collectd Configuration Requirements

- collectd should be installed and running.
- collectd should be installed in /opt/collectd and the configuration file is available in /opt/collectd/etc/collectd.conf
    - If your collectd installation is not installed in /opt/collectd, please contact support@insightfinder.com for tips on customizing your installation  
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
  ValuesPercentage true
</Plugin>

<Plugin csv>
        DataDir "${prefix}/var/lib/collectd/csv"
        StoreRates false
</Plugin>
```
- The Interval above is specified in seconds. Set it to required sampling value. It specifies how often data is collected.

##### To Install Insight Agent Locally
1) Use the following command to download the insightfinder agent code.
```
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
```
Untar using this command.
```
tar -xvf insightagent.tar.gz
```

2) In InsightAgent-master directory, run the following commands to install and use python virtual environment for insightfinder agent:
```
./deployment/checkpackages.sh
```
```
source pyenv/bin/activate
```

3) Run the below command to install agent.
```
./deployment/install.sh -i PROJECT_NAME -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE
```
After using the agent, use command "deactivate" to get out of python virtual environment.

##### To Install Insight Agent on Multiple Hosts

- Get the deployment script from github using below command
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/deployInsightAgent.sh
```
- Change permission for "deployInsightAgent.sh" to executable.
-Ensure all machines have the same login username and password.
-Obtain the IP address for every machine (or host) the InsightFinder agent will be installed on.
-Include the IP address of all hosts in hostlist.txt, entering one IP address per line.
- To deploy run the following command
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
##### To view "Usage" in terminal, run
```
./deployInsightAgent.sh
```
To validate deployment, select to enter either a password or key. For a key, enter the identity file's path name. For example: /home/insight/.ssh/id_rsa


##### Undoing Insight Agent Installation on Multiple Hosts
- Get the script for stopping agents from GitHub using below command:
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployment/stopcron.sh
```
and change the permissions with the command
```
 chmod 755 stopcron.sh
```
- Include IP addresses of all hosts in hostlist.txt and enter one IP address per line.
- To stop the agent run the following command
```
./stopcron.sh -n USER_NAME_IN_HOST -p PASSWORD

USER_NAME_IN_HOST - username used to login into the host machines
PASSWORD - password or name of the identity file along with path
```

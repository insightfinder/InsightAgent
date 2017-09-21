# InsightAgent: cadvisor
Agent Type: cadvisor

Platform: Linux

InsightFinder agent can be used to monitor system metrics of docker containers using cadvisor.

Tested with Ubuntu 14.04, Redhat 7.2, Centos 7.2.

Required docker version: 1.9.1 and later.

Required cadvisor version: 0.19.3 and later.

## Use this script to deploy cgroup Agent on multiple Hosts

### Prerequisites:

If there are any proxy settings required for your environment, make sure they are defined for both the installation user and the root user. The InsightFinder cgroup agent requires internet access to download the packages needed for the installation process. After installation is complete, any proxy should be disabled to allow our agents to send data using the correct port. Ensure that your /tmp directory has at least 50MB of disk space available because the apt/yum package managers use /tmp as scratch space for package installation (e.g., package inflation).

### Install wget to download the required files :

#### For Debian and Ubuntu

```
sudo -E apt-get update
sudo -E apt-get install wget

```

#### For Fedora and RHEL-derivatives

```
sudo -E yum update
sudo -E yum install wget
```

#### Get copy of the deployment script:

1) Use the following command to download the insightfinder agent code.

```
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
or
wget --no-check-certificate http://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz

```
Untar using this command.

```
tar -xvf insightagent.tar.gz
```
```
cd InsightAgent-master/deployment/DeployAgent/
sudo -E ./installAnsible.sh
```
2) Open and modify the inventory file

```
[nodes]
HOST ansible_user=USER ansible_ssh_private_key_file=SOMETHING
###We can specify the host name with ssh details like this for each host
##If you have the ssh key
#192.168.33.10 ansible_user=vagrant ansible_ssh_private_key_file=/home/private_key

##If you have the password
#192.168.33.20 ansible_user=vagrant ansible_ssh_pass=ssh_password


##We can also specify the host names here and the ssh details under [nodes:vars] if they have have the same ssh credentials
##(Only one of ansible_ssh_pass OR ansible_ssh_private_key_file is required)
#192.168.33.10
#192.168.33.15

[nodes:vars]
#ansible_user=vagrant
#ansible_ssh_pass=ssh_password
#ansible_ssh_private_key_file=/home/private_key

[all:vars]
##install or uninstall
ifAction=install

##Login User In Insightfinder Application
ifUserName=

##Project Name In Insightfinder Application
ifProjectName=

##User's License Key in Application
ifLicenseKey=

##Sampling interval could be an integer indicating the number of minutes or "10s" indicating 10 seconds.
ifSamplingInterval=1

##Agent type
ifAgent=cadvisor

##The server reporting Url(Do not change unless you have on-prem deployment)
ifReportingUrl=https://app.insightfinder.com
```

3) Download the agent Code which will be distributed to other machines
```
cd files
sudo -E ./downloadAgentSSL.sh
or
sudo -E ./downloadAgentNoSSL.sh
```
4) Run the playbook(Go back to the DeployAgent directory)
```
cd ..
ansible-playbook insightagent.yaml
```


##### To check raw data in host machines
- Login into the individual host machines.
- In the InsightAgent-master/data folder, all raw data will be stored in csv files. csv files older than 5 days are moved to /tmp folder.
- To change the retention period, edit the InsightAgent-master/reporting_config.json and change the "keep_file_days" to the required value.

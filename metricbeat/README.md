## Use this script to deploy metricbeat and logstash to stream metric data from multiple Hosts

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
Note: If you are using proxy, the proxy needs to be set for both the current user and root
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
2) Open and modify the inventory file to install logstash. Logstash will receive metribeat's output on port 5044 and report data to IF system.

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
#ansible_ssh_private_key_file=/home/{{ansible_user}}/.ssh/id_rsa
#ansible_ssh_pass=ssh_password

[all:vars]
##install or uninstall
ifAction=install

##Login User In Insightfinder Application
ifUserName=

##Project Name In Insightfinder Application
ifProjectName=

##User's License Key in Application
ifLicenseKey=

##Agent type
ifAgent=logstash

##The server reporting Url(Do not change unless you have on-prem deployment)
ifReportingUrl=https://app.insightfinder.com
```

3) Run the playbook to install logstash on target hosts

```
ansible-playbook -i inventory insightagent.yaml
```

4) Open and modify the inventory file to install metricbeat to get metric data from target hosts. Set beatsLogstashHosts to the hosts on which logstash is installed in above step.

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
#ansible_ssh_private_key_file=/home/{{ansible_user}}/.ssh/id_rsa
#ansible_ssh_pass=ssh_password

[all:vars]
##install or uninstall
ifAction=install

##Sampling interval could be an integer indicating the number of minutes or "10s" indicating 10 seconds.
ifSamplingInterval=60s

##Agent type
ifAgent=metricbeat

# Hosts list for beats' logstash output, such as metricbeat,
# seperated by comma, e.g. "10.10.10.11:5044","10.10.10.12:5044"
# If empty, use default "localhost:5044".
beatsLogstashHosts=
```
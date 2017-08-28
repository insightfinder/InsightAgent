## Use this script to deploy cgroup Agent on multiple Hosts

### Install wget to download the required files :
#### For Debian and Ubuntu
```
sudo apt-get update
sudo apt-get install wget
```
#### For Fedora and RHEL-derivatives
```
sudo yum update
sudo yum install wget
```


#### Get copy of the deployment script:
1) Use the following command to download the insightfinder agent code.
```
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
```
Untar using this command.
```
tar -xvf insightagent.tar.gz
```
```
cd InsightAgent-master/deployment/DeployAgent/
sudo ./installAnsible.sh
```
2) Open and modify the inventory file

```
[nodes]
HOST ansible_user=USER ansible_shh_private_key_file=SOMETHING
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
ifAgent=collectd

##The server reporting Url(Do not change unless you have on-prem deployment)
ifReportingUrl=https://agent-data.insightfinder.com
```
3) Download the agent Code which will be distributed to other machines
```
cd roles/install/files
sudo ./downloadAgent.sh
```
4) Run the playbook(Go back to the DeployAgent directory)
```
cd ../../..
ansible-playbook insightagent.yaml
```

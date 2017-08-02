## Use this script to deploy cgroup Agent on multiple Hosts

### Install wget to download the required files :
#### For Debian and Ubuntu
```
sudo apt-get update
sudo wget
```
#### For Fedora and RHEL-derivatives
```
sudo yum update
sudo yum wget
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

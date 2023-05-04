## Deploy vCenter agent on multiple hosts by ansible

### Prerequisites:

Ansible.

#### Get copy of the deployment script:
1) Use the following command to download the insightfinder agent code.
```
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/vcenter-ansible/vCenter-ansible.tar.gz -O vCenter-ansible.tar.gz
or
wget --no-check-certificate http://github.com/insightfinder/InsightAgent/vcenter-ansible/vCenter-ansible.tar.gz -O vCenter-ansible.tar.gz

```
Untar using this command.
```
tar -xzvf vCenter-ansible.tar.gz
```
2) Go to "vcenter-ansible" directory and  modify the inventory file "hosts"

```
# List all target machines here.
# Example host with fqdn: my.host.com 
# Example host with IP address: 192.168.10.4

# You can specify different variables per host if you have multiple requirements, such as different vCenter hosts, by specifying variables in-line with the hosts.
# Example with common variables: 
# my.host.com host=my.vcenter.com vcenter_user_name=user system_name=system project_name=project

[all:vars]

# InsightFinder Vars

# URL of the InsightFinder host. Required.
if_host_url = 
if_http_proxy = 
if_https_proxy = 

# User name for the owner of the IF project. Required.
if_user_name = 
# License Key for the owner of the IF project. Required.
license_key = 
# System Name that contains the IF project. Required.
system_name = 
# Project Name that will receive data. Required.
project_name = 
# Sampling interval, determines the length of time that data will be collected from and how often the agent runs. Required.
sampling_interval = 5
# number of retries for http requests in case of failure. Defaults to 3 if left commented
#retries = 
# time between retries. Required. Defaults to 5 if left commented
#sleep_seconds = 
# Project type. defaults to metric if left commented
#project_type = 

# vCenter Vars

# skip the protocol prefix in the host and proxy URLs; only http protocol is supported currently
# e.g., use "localhost:80" instead of "http://localhost:80". Required.
host = 
http_proxy = 
vcenter_user_name = 
# do not enter the password here; instead, enter the obfuscated password (run 'ifobfuscate.py')
password = 
# enter a list of virtual machine names separated by comma(,) or a regex to match from all available virtual machine names
# if list and regex are both provided, the list is given precedence and the regex param will be ignored
# if both are missing, no virtual machines will be processed (set regex to < .* > to select all virtual machines) 
virtual_machines_list = 
virtual_machines_regex = 
# enter a list of host system names separated by comma(,) or a regex to match from all available host system names
# if list and regex are both provided, the list is given precedence and the regex param will be ignored
# if both are missing, no host systems will be processed (set regex to < .* > to select all host systems)
# NOTE: the selected hosts are also used to filter/whitelist virtual machines
hosts_list = 
hosts_regex = 
# enter a list of datastore names separated by comma(,) or a regex to match from all available datastore names
# if list and regex are both provided, the list is given precedence and the regex param will be ignored
# if both are missing, no datastores will be processed (set regex to < .* > to select all datastores)
datastores_list = 
datastores_regex = 
# enter a list of performance metrics separated by comma(,) or a regex to match from all available metrics
# if list and regex are both provided, the list is given precedence and the regex param will be ignored
# if both are missing, no metrics will be processed (set regex to < .* > to select all metrics)
# Metrics should follow the format: <counter.groupInfo.key>.<counter.nameInfo.key>.<counter.unitInfo.key>.<counter.rollupType>
# where, counter is a vim.PerformanceManager.CounterInfo object
# e.g., cpu.usage.percent.average, mem.shared.kiloBytes.maximum, disk.maxTotalLatency.millisecond.latest, net.usage.kiloBytesPerSecond.minimum
metrics_list = 
metrics_regex = 

# Agent Vars

# number of threads to be used in the multiprocessing pool. Defaults to 1 if left commented
#thread_pool = 

# Maximum size of a data chunk to be sent to IF, in kilobytes. defaults to 2048 if left commented
#chunk_size_kb = 
```

3) Run the playbook

```
ansible-playbook -i hosts install.yml
```

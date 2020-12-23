## Deploy collectd agent on multiple hosts by ansible

### Prerequisites:

Ansible.

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
2) Go to "collectd-ansible" directory and  modify the inventory file "hosts"

```
+ # List all target machines here.

  [all:vars]
  #ansible_user=
  #ansible_ssh_private_key_file=/home/{{ansible_user}}/.ssh/id_rsa

  # ifagent settings
  report_url=
  project_name=
  user_name=
  license_key=
  sampling_interval=
```

3) Run the playbook

```
ansible-playbook -i hosts install.yml
```

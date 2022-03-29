## Getting Started

### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Insight Agent" tab.
- Give a project name, select Project Type as "Log" and Agent Type as "Custom".
- Note down the project name and license key which will be used for agent installation. The license key is also available in "User Account Information". To go to "User Account Information", click the userid on the top right corner.

InsightFinder can parse log data sent via logstash. We utilize json_encode filter plugin and http-output plugin to format and send the data. 


### 1. Requirements

Ansible: Deploy and install logstash
Filebeat: Streaming data to logstash with preconfigured fields for data parsing


### 2. Configuration

In the hosts file, several things need to be specified in order to run the playbook.

In logstash-offline/hosts
   Under [logstash], add hosts to this tag in the form of an FQDN or an IP address. 
   Under [logstash:vars], the variables presented need to be filled out as such:
      - username: the username of the InsightFinder user
      - license_key: the key associated with the InsightFinder User
      - server_url: the url used to reach InsightFinder. Use only the base url, for example: app.insightfinder.com
      - logstash_user: the user to host the logstash processes
      - logstash_group: the group the logstash_user is in, also the group that can run logstash processes


### 3. Run the playbook

Run the command from the logstash-offline directory: 'ansible-playbook install.yaml -i hosts'

This will install logstash to "/etc/logstash".


### 4. Use sample Logstash config to send data

You can follow our samples under logstash/conf.d/ to send data to the Insightfinder Backend.

In logstash/conf.d/,  01-input.conf, 02-SampleFilter.conf, 98-merge.conf, 99-output.conf are filters to handle messages sent from filebeat. They are used combined with the sample filebeat config files.  

### 5. Check that logstash is running

You can check to ensure that the logstash service is running after the playbook is finished by running the command 'sudo systemctl status logstash.service'. 

If it says failed, you can try running 'sudo systemctl restart logstash'.

If it says success and you are suspicious that logs are not being sent to InsightFinder, you can check the logs using 'sudo vi /var/log/syslog'.

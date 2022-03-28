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
      - ls_user: same as logstash_user
      - ls_group: the group the logstash_user is in, also the group that can run logstash processes


### 3. Run the playbook

Run the command from the logstash-offline directory: 'ansible-playbook install.yaml -i hosts'

This will install logstash to "/etc/logstash".


### 4. Use sample Logstash config to send data

You can follow our samples under logstash/conf.d/ to send data to the Insightfinder Backend.

In logstash/conf.d/,  01-input.conf, 02-SampleFilter.conf, 98-merge.conf, 99-output.conf are filters to handle messages sent from filebeat. They are used combined with the sample filebeat config files.  


### 5. Implementation Notes

You will need a different filter for each log file format sent by filebeat. Each filter will process the log messages for the corresponding tag set by filebeat.  Each filebeat tag is handled by the filter with the corresponding tag set and sent to the InsightFinder project that is configured in that filter. If the tag does not match, the filter will not be applied. 

You can copy the 02-SampleFilter.conf file as needed and customize with the corresponding log_type tag, grok and project name configured.

Necessary fields are denoted by a brief description surrounded by <>.  Replace from < to > inclusive. 

Information that needs to be populated: 
Filebeat:
1) Log file path 
2) Log type flag
3) Logstash server with port (eg: localhost:5044) 

Logstash Filter:
1) Log type flag that matches the filebeat configuration
2) Grok regex to match and parse the log message
3) Any custom processing/ formatting of the log message. Two fields that need to be set by the end of the processing: 
   a) ts_event -- Timestamp of log message 
   b) data -- Content of log message to send 
4) Project name in InsightFinder

Output: 
1) IF server
2) IF username
3) IF license key


#### Furthermore

- Try it with different input/filter/codec plugins
- Start LogStash as a service/daemon in your production environment

## Getting Started

### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and Register for a project under "Insight Agent" tab.
- Give a project name, select Project Type as "Log" and Agent Type as "Custom".
- Note down the project name and license key which will be used for agent installation. The license key is also available in "User Account Information". To go to "User Account Information", click the userid on the top right corner.

InsightFinder can parse log data sent via logstash. We utilize json_encode filter plugin and http-output plugin to format and send the data. 



### 1. Install filebeat to harvest target log files

Following this [instruction](https://www.elastic.co/guide/en/beats/filebeat/current/filebeat-installation-configuration.html) to downoad and install Filebeat.

You can follow sample filebeat config files under filebeat/  to harvest target log files, for example IIS log. 

Sample configuration under winlogbeat/ is specific for winlogbeat. Following this [instruction](https://www.elastic.co/guide/en/beats/winlogbeat/current/winlogbeat-installation-configuration.html) to install winlogbeat for windows event logs.

### 2. Install LogStash on your machine

Following this [instruction](https://www.elastic.co/guide/en/logstash/current/getting-started-with-logstash.html) to download and install LogStash.

### 3. Install the json_encode filter plugin

``` 
bin/logstash-plugin install logstash-filter-json_encode 
```

### 4. Use sample Logstash config to send data

You can follow our sample [config](logstash-if.conf) to send data to the Insightfinder Backend.

In logstash/if-log-config/,  filter01-evtx.conf, filter02-iis-prod.conf, filter02-iis.conf, filter03-system-events.conf are filters to handle messages sent from filebeat. They are used combined with the corresponding sample filebeat config files above.  

Copy these files under logstash/if-log-config/ to /etc/logstash/conf.d/ and restart logstash service.

#### Furthermore

- Try it with different input/filter/codec plugins
- Start LogStash as a service/daemon in your production environment

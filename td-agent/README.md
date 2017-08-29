# Log File Streaming via fluentd/td-agent
Agent Type: InsightFinder provides an output plugin for fluentd/td-agent installations

Platform: Linux

fluentd/td-agent, in conjunction with the InsightFinder output plugin, can be configured to monitor your log files and forward log entries to InsightFinder for anomaly detection, keyword analysis, sequencing/clustering, and more.

Tested with td-agent version 2 (v0.12) (installer package versions 2.5 and up).

##### Instructions to register a log streaming project in Insightfinder.com
- Go to [insightfinder.com](https://insightfinder.com/)
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and register a new project with the New Project wizard.
## Steps to install td-agent on multiple hosts
The installation requires the Insightfinder repository(insightrepo) to be set up. The current installation supports Centos 7. 

1) Use the following command to download the insightfinder agent code.
```
wget --no-check-certificate https://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
or
wget http://github.com/insightfinder/InsightAgent/archive/master.tar.gz -O insightagent.tar.gz
```
Untar using this command.
```
tar -xvf insightagent.tar.gz
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


##We can also specify the host names here and the ssh details under [nodes:vars] if they have the same ssh credentials
##(Only one of ansible_ssh_pass OR ansible_ssh_private_key_file is required)
#192.168.33.10
#192.168.33.15

```

3) Open and modify the td-agent.yaml file and replace the values PROJECT_NAME, USERNAME, LICENSE_KEY and APP_SERVER with appropiate values. The USERNAME and LICENSE_KEY values can be found on your Insightfinder account profile section. PROJECT_NAME is the name of the project created in the Insightfinder app and the APP_SERVER is the data receiving server URL (e.g. https://agent-data.insightfinder.com if you use our SaaS solution or your application server address if you use our on-prem solution).

 ```
 - hosts: nodes
   vars:
    projectName: PROJECT_NAME
    userName: USERNAME
    samplingInterval: 60
    deploymentServerUrl: APP_SERVER
    licenseKey: LICENSE_KEY

  ```

  4) Run the deployment script
  ```
  sudo ./install_td-agent.sh

  ```
## Installing td-agent on single host

1. Install td-agent per the [fluentd installation documentation](http://docs.fluentd.org/v0.12/categories/installation).
2. Download [InsightFinder's fluentd output plugin](https://raw.githubusercontent.com/insightfinder/InsightAgent/master/td-agent/out_InsightFinder.rb).  Right-click on this link and choose "Save" to download it to your system.
3. Copy the output plugin to td-agent's plugin directory.  By default in package installs, this is /etc/td-agent/plugins
4. Add an appropriate configuration to your /etc/td-agent/td-agent.conf file that includes a [match directive](http://docs.fluentd.org/v0.12/articles/config-file#2-ldquomatchrdquo-tell-fluentd-what-to-do) that includes the following InsightFinder-REQUIRED values:
- A "type" that specifies the InsightFinder output plugin:
~~~~
  type InsightFinder
~~~~
- A "destinationHost" appropriate for your deployment:
~~~~
  destinationHost https://agent-data.insightfinder.com/customprojectrawdata
~~~~
- A "userName" value equivalent to your InsightFinder user name:
~~~~
  userName MyIFUserName
~~~~
- A "projectName" value equivalent to an InsightFinder log data project created above:
~~~~
  projectName LogDataProjectName
~~~~
- A "licenseKey" value from your InsightFinder account (Note: Click on your user ID in InsightFinder and select "Account Profile")
~~~~
licenseKey abcdef1234567890abcdef1234567890abc
~~~~
5. If desired, configure either or both of the InsightFinder-OPTIONAL values:
- An "instanceName" to override the default behavior of getting the system's value for 'hostname'
~~~~
  instanceName mycustomhostname
~~~~
- An "instanceType" to leverage external meta-data about this node.
~~~~
  instanceType AWS
~~~~
6. An example configuration is provided below:
~~~~
  <match iflog.**>
    type InsightFinder
    # Endpoint for messages
    destinationHost https://agent-data.insightfinder.com/customprojectrawdata
    userName guest
    projectName WorkerSysLogs
    # License Key
    licenseKey b697f8711004d32fb2e4086dc5ea0a6d8f7df947
    # instancename (OPTIONAL - leave blank to use hostname)
    instanceName
    # Instance Type
    instanceType AWS    
    # Begin td-agent & http_output_plugin configuration values
    flush_interval 60s
    buffer_chunk_limit 400k
    # Comma separated list of http statuses which need to be retried
    http_retry_statuses 500,403
    # Read timeout in seconds, supports floats
    http_read_timeout 2.2
    # Open timeout in seconds, supports floats
    http_open_timeout 2.34
  </match>
  <source>
    @type tail
    format multiline
    format_firstline /[A-Z][a-z][a-z] (([1-3][0-9])| [1-9])\, \d{4} ([0-9]|[0-9][0-9]):[0-9][0-9]:[0-9][0-9] (A|P)M/
    format1 /^(?<time>[A-Z][a-z][a-z] (([1-3][0-9])| [1-9])\, \d{4} ([0-9]|[0-9][0-9]):[0-9][0-9]:[0-9][0-9] (A|P)M) (?<data>.*)$/
    time_format %b %d, %Y %H:%M:%S %p
    path /opt/jetty/logs/%Y_%m_%d.stderrout.log
    pos_file /var/log/td-agent/jetty.pos
    encoding ISO-8859-1
    tag "iflog.#{Socket.gethostname}"
    keep_time_key true
  </source>
~~~~
7.  Start (or Restart) the td-agent service to force your new configuration to be read and the plugin to be recognized.

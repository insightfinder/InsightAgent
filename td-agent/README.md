# Log File Streaming via fluentd/td-agent
Agent Type: InsightFinder provides an output plugin for fluentd/td-agent installations

Platform: Linux

fluentd/td-agent, in conjunction with the InsightFinder output plugin, can be configured to monitor your log files and forward log entries to InsightFinder for anomaly detection, keyword analysis, sequencing/clustering, and more.

Tested with td-agent version 2 (v0.12) (installer package versions 2.5 and up).

##### Instructions to register a log streaming project in Insightfinder.com
- Go to [insightfinder.com](https://insightfinder.com/)
- Sign in with the user credentials or sign up for a new account.
- Go to Settings and register a new project with the New Project wizard.

## Installing td-agent with the InsightFinder output plugin

1. Install td-agent per the [fluentd installation documentation](http://docs.fluentd.org/v0.12/categories/installation).
2. Download [InsightFinder's fluentd output plugin](https://raw.githubusercontent.com/insightfinder/InsightAgent/master/td-agent/out_InsightFinder.rb).  Right-click on this link and choose "Save" to download it to your system.
3. Copy the output plugin to td-agent's plugin directory.  By default in package installs, this is /etc/td-agent/plugins
4. Add an appropriate configuration to your /etc/td-agent/td-agent.conf file that includes a [match directive](http://docs.fluentd.org/v0.12/articles/config-file#2-ldquomatchrdquo-tell-fluentd-what-to-do) that includes the following InsightFinder-REQUIRED values:
- A "type" that specifies the InsightFinder output plugin, a la:
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
- An "instanceType" to leverage external meta-data about this node.  Note:  The only current supported value for this is "AWS".
~~~~
  instanceType AWS
~~~~
6. An example configuration is provided below:
~~~~
  <match *>
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
    buffer_chunk_limit 200k
    # Comma separated list of http statuses which need to be retried
    http_retry_statuses 500,403
    # Read timeout in seconds, supports floats
    http_read_timeout 2.2
    # Open timeout in seconds, supports floats
    http_open_timeout 2.34
  </match>
  <source>
    @type tail
    format /^(?<time>[A-Z][a-z][a-z] (([1-3][0-9])| [1-9]) [0-9][0-9]:[0-9][0-9]:[0-9][0-9]) (?<data>.*)$/
    time_format %b %e %H:%M:%S
    path /var/log/messages
    encoding ISO-8859-1
    pos_file /var/log/td-agent/messages.pos
    tag "#{Socket.gethostname}"
    keep_time_key true
  </source>
~~~~
7.  Start (or Restart) the td-agent service to force your new configuration to be read and the plugin to be recognized.

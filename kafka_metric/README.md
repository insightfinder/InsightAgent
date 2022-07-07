# kafka
This agent collects data from kafka and sends it to Insightfinder.
## Installing the Agent

### Required Dependencies:
1. Python == 3.6.8
1. Pip3

###### Installation Steps:
1. Download the kafka_metric.tar.gz package
1. Copy the agent package to the machine that will be running the agent
1. Extract the package
1. Navigate to the extracted location 
1. Configure venv and python dependencies
1. Configure agent settings
1. Test the agent
1. Add agent to the cron

The final steps are described in more detail below. 

###### Configure venv and python dependencies:
Before configure python venv, please install `librdkafka` and `ca-certificates` first.

```bash
git clone https://github.com/edenhill/librdkafka.git
cd librdkafka
./configure --prefix=/usr && make -j && sudo make install

sudo yum reinstall ca-certificates
```

The configure_python.sh script sets up a virtual python environment and installs all required libraries for running the agent. 

```bash
./setup/configure_python.sh
```

###### Agent configuration:
The config.ini file contains all of the configuration settings needed to connect to the Kafka instance and to stream the data to InsightFinder.

The password for the Kafka user will need to be obfuscated using the ifobfuscate.py script.  It will prompt you for the password and provide the value to add to the configuration file. 

```
python ./ifobfuscate.py 
```

The configure_python.sh script will generate a config.ini file for you; however, if you need to create a new one, you can simply copy the config.ini.template file over the config.ini file to start over. 

Populate all of the necessary fields in the config.ini file with the relevant data.  More details about each field can be found in the comments of the config.ini file and the Config Variables below. 

###### Test the agent:
Once you have finished configuring the config.ini file, you can test the agent to validate the settings. 

This will connect to the Kafka instance, but it will not send any data to InsightFinder. This allows you to verify that you are getting data from Kafka and that there are no failing exceptions in the agent configuration.


```bash
./setup/test_agent.sh
```

###### Add agent to the cron:
For the agent to run continuously, it will need to be added as a cron job. 

The install_cron.sh script will add a cron file to run the agent.  

```bash
# Add the cron entry, once you are ready to start streaming
sudo ./setup/install_cron.sh --monitor
```

###### Stopping the agent:
Once the cron is running, you can stop the agent removing the cron file or commenting the line in the cron file, then kill all of it's relevant processes.

To stop the cron, you can either comment out the line in the cron file that is created, or you can delete the file itself.
```#To comment out the line, use the # symbol at the start of the line
vi /etc/cron.d/kafka_metric
# <cron>
```
```#To delete the file, run this command
sudo rm /etc/cron.d/kafka_metric
```

```#To kill the agent, first print the list of processes running, then kill the agent processes based on their process ID.
ps auwx | grep getmessages_kafka_metric.py
sudo kill <Processs ID>
```

### Config Variables
* **`bootstrap.servers`**: Comma-delimited list of `host[:port]` Kafka servers to connect to.
* **`group.id`**: Group ID to use in Kafka connection.
* `client.id`: Client ID to use in Kafka connection.
* `api.version.request`: If you use Kafka broker 0.9 or 0.8 you must set api.version.request=false and set broker.version.fallback to your broker version, e.g broker.version.fallback=0.9.0.1.
* `broker.version.fallback`: If you use Kafka broker 0.9 or 0.8 you must set api.version.request=false and set broker.version.fallback to your broker version, e.g broker.version.fallback=0.9.0.1.
* **`topics`**: Topics in Kafka to subscribe to.
* `schema.registry.url`: Comma-separated list of URLs for Schema Registry instances that can be used to register or look up schemas.
* `basic.auth.credentials.source`: Specify how to pick the credentials for the Basic authentication header. The supported values are URL, USER_INFO and SASL_INHERIT.
* `basic.auth.user.info`: Specify the user info for the Basic authentication in the form of {username}:{password}. schema.registry.basic.auth.user.info is a deprecated alias for this configuration.
* `security.protocol`: Security protocol to use. Valid options are `PLAINTEXT, SSL, SASL_PLAINTEXT or SASL_SSL`.
* `ssl.ca.location`: File or directory path to CA certificate(s) for verifying the broker's key. Defaults: On Windows the system's CA certificates are automatically looked up in the Windows Root certificate store. On Mac OSX this configuration defaults to probe. It is recommended to install openssl using Homebrew, to provide CA certificates. On Linux install the distribution's ca-certificates package. If OpenSSL is statically linked or ssl.ca.location is set to probe a list of standard paths will be probed and the first one found will be used as the default CA certificate location path. If OpenSSL is dynamically linked the OpenSSL library's default path will be used (see OPENSSLDIR in openssl version -a).
* `sasl.mechanisms`: SASL mechanism to use for authentication. Supported: GSSAPI, PLAIN, SCRAM-SHA-256, SCRAM-SHA-512, OAUTHBEARER. NOTE: Despite the name only one mechanism must be configured.
* `sasl.username`: SASL username for use with the PLAIN and SASL-SCRAM-.. mechanisms.
* `sasl.password`: SASL password for use with the PLAIN and SASL-SCRAM-.. mechanism.
* `initial_filter`: Optional preprocessing filter (regex) to eliminate raw data from being parsed. Data must match filter to be parsed if set.
* `raw_regex`: Regex used to parse raw data. Must use named capture groups `(?<name>...)` corresponding to fields defined below, as only those named capture groups will be reported.
* `project_field`: Field name for the project name. If this field is empty, agent will use project_name in insightfinder section. 
* `project_whitelist`: project_whitelist is a regex string used to define which projects form project_field will be filtered.
* **`metric_fields`**: Field name for the metric name. Multiple fields are separated by commas. A field can be named with the syntax `<metric_name>::<metric_value>`, where `<metric_name>` and `<metric_value>` can each be either a field name in message. Ex: metric1,metric_field::metric_value_field. 
* `metrics_whitelist`: metrics_whitelist is a regex string used to define which metrics will be filtered.
* `timezone`: Timezone of the timestamp data stored in/returned by the DB. Note that if timezone information is not included in the data returned by the DB, then this field has to be specified. 
* `timestamp_field`: Field name for the timestamp. Default is `timestamp`.
* `target_timestamp_timezone`: Timezone of the timestamp data to be sent and stored in InsightFinder. Default value is UTC. Only if you wish to store data with a time zone other than UTC, this field should be specified to be the desired time zone.
* `component_field`: Field name for the component name.
* `instance_field`: Field name for the instance name. If not set or the field is not found, the instance name is the `Application`. Can also set instance name from multiple fields which separated by commas. Ex: instance_name_part1,instance_name_part2.
* `instance_whitelist`: This field is a regex string used to define which instances will be filtered.
* `device_field`: Field name for the device/container for containerized projects. Can also set device name from multiple fields which separated by commas. Ex: device_name_part1,device_name_part2.
* `buffer_sampling_interval_multiple`: Number of multiples of sampling_interval witch buffered the metric data. Default is 2 multiple.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* `token`: Token from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI, If this project is not exist, agent will create it automatically.
* `system_name`: Name of system owned by project. If project_name is not exist in InsightFinder, agent will create a new system automatically from this field or project_name. 
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, alert, alertreplay, incident, incidentreplay, deployment, deploymentreplay, trace, tracereplay`.
* `containerize`: Set to `YES` if project is container.
* **`sampling_interval`**: How frequently (in Minutes) data is collected. Should match the interval used in project settings.
* **`run_interval`**: How frequently (in Minutes) the agent is ran. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.



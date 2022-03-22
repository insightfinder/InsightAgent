# kafka
This agent collects data from kafka and sends it to Insightfinder.
## Installing the Agent

### Required Dependencies:
1. Python 3.x 
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

The install_cron.sh script will add a cron file to run the agent on a regular schedule.

```bash
# Display the cron entry without adding it 
./setup/install_cron.sh  --monitor --display

# Add the cron entry, once you are ready to start streaming
sudo ./setup/install_cron.sh --monitor --create
```

###### Pausing or stopping the agent:
Once the cron is running, you can either pause the agent by commenting out the relevant line in the cron file or stop the agent by removing the cron file. 

### Config Variables
* **`bootstrap_servers`**: Comma-delimited list of `host[:port]` Kafka servers to connect to.
* **`topics`**: Topics in Kafka to subscribe to.
* **`group_id`**: Group ID to use in Kafka connection.
* `client_id`: Client ID to use in Kafka connection.
* `security_protocol`: Security protocol to use. Valid options are `PLAINTEXT, SSL, SASL_PLAINTEXT or SASL_SSL`.
* `sasl_mechanism`: Mechanism used when `security_protocol` is `SASL_PLAINTEXT or SASL_SSL`. Valid options are `PLAIN, GSSAPI, or OAUTHBEARER`.
* `ssl_context`: Pre-configured SSLContext for wrapping socket connections.
* `ssl_check_hostname`: True if hostname should be checked - whether ssl handshake should verify that the certificate matches the brokers hostname.
* `ssl_cafile`: ca file to use in certificate verification.
* `ssl_certfile`: pem file to use in certificate verification.
* `ssl_keyfile`: Client private key file to use in certificate verification.
* `ssl_password`: Password used when loading the certificate chain. Note that this is stored as plaintext!
* `ssl_crlfile`: CRL to check for certificate expiration.
* `ssl_ciphers`: Set the available ciphers for ssl connections.
* `sasl_mechanism`: Mechanism used when `security_protocol` is `SASL_PLAINTEXT or SASL_SSL`. Valid options are `PLAIN, GSSAPI, or OAUTHBEARER`.
* `sasl_plain_username`: Username for sasl PLAIN authentication.
* `sasl_plain_password`: Password for sasl PLAIN authentication. Note that this is stored as plaintext!
* `sasl_kerberos_service_name`: Service name to include in GSSAPI sasl mechanism handshake.
* `sasl_kerberos_domain_name`: kerberos domain name to use in GSSAPI sasl mechanism handshake.
* `sasl_oauth_token_provider`: OAuthBearer token provider instance.
* `raw_regex`: Regex used to parse raw data. Must use named capture groups `(?<name>...)` corresponding to fields defined below, as only those named capture groups will be reported.
* `project_field`: Field name for the project name. If this field is empty, agent will use project_name in insightfinder section. 
* `metric_field`: Field name for the metric name. 
* `metrics_whitelist`: metrics_whitelist is a regex string used to define which metrics will be filtered.
* `timezone`: Timezone of the timestamp data stored in/returned by the DB. Note that if timezone information is not included in the data returned by the DB, then this field has to be specified. 
* `timestamp_field`: Field name for the timestamp. Default is `timestamp`.
* `target_timestamp_timezone`: Timezone of the timestamp data to be sent and stored in InsightFinder. Default value is UTC. Only if you wish to store data with a time zone other than UTC, this field should be specified to be the desired time zone.
* `component_field`: Field name for the component name.
* `instance_field`: Field name for the instance name. If not set or the field is not found, the instance name is the hostname of the machine the agent is installed on. This can also use a priority list, field names can be given: `instance1,instance2`.
* `instance_whitelist`: This field is a regex string used to define which instances will be filtered.
* `device_field`: Field name for the device/container for containerized projects. This can also use a priority list, field names can be given: `device1,device2`.
* `buffer_sampling_interval_multiple`: Number of multiples of sampling_interval witch buffered the metric data. Default is 2 multiple.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* `token`: Token from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI, If this project is not exist, agent will create it automatically.
* `system_name`: Name of system owned by project. If project_name is not exist in InsightFinder, agent will create a new system automatically from this field or project_name. 
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, alert, alertreplay, incident, incidentreplay, deployment, deploymentreplay, trace, tracereplay`.
* **`sampling_interval`**: How frequently (in Minutes) data is collected. Should match the interval used in project settings.
* **`run_interval`**: How frequently (in Minutes) the agent is ran. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.



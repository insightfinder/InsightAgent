# Kafka
## Installing the Agent
**Download the agent [tarball](https://github.com/insightfinder/InsightAgent/raw/master/kafka2/kafka2.tar.gz) and untar it:**
```
wget https://github.com/insightfinder/InsightAgent/raw/master/kafka2/kafka2.tar.gz
tar xvf kafka2.tar.gz && cd kafka2
```

**Copy `config.ini.template` to `config.ini` and edit it:**
```
cp config.ini.template config.ini
vi config.ini
```
See below for a further explanation of each variable.

**Setup pip & required packages:**
```
sudo ./pip-setup.sh
```

**Test the agent:**
```
python getmessages_kafka.py -t
```

**If satisfied with the output, configure the agent to run continuously:**
```
sudo ./monit-setup.sh
```

### Config Variables
* **`bootstrap_servers`**: Comma-delimited list of bootstrap servers as host:port
* **`topics`**: Comma-delimited list of topics to subscribe to.
* `group_id`: Group ID to join. Default is None.
* `client_id`: Client ID used when subscribing to topics. Default is `kafka-python-{version}` (from KafkaConsumer API). 
* `filters_include`: Used to filter messages based on allowed values.
* `filters_exclude`: Used to filter messages based on unallowed values.
* **`data_format`**: The format of the data to parse: CSV, JSON, or RAW
* **`csv_field_names`**: A list of field names for CSV input. Required, even if the CSV to parse has a header.
* `json_top_level`: The top-level of fields to parse in JSON. For example, if all fields of interest are nested like 
```
{ 
  "output": {
    "parsed": {
      "time": time, 
      "log": log message,
      ...
    }
    ...
  }
  ...
}
```
then this should be set to `output.parsed`.
* `timestamp_format`: Format of the timestamp, in python [strftime](http://strftime.org/). If the timestamp is in Unix epoch, this can be left blank or set to `epoch`.
* `timestamp_field`: Field name for the timestamp. Default is `timestamp`.
* `instance_field`: Field name for the instance name. If not set or the field is not found, the instance name is the hostname of the machine the agent is installed on.
* `device_field`: Field name for the device/container for containerized projects.
* `data_fields`: Comma-delimited list of field names to use as data fields. If not set, all fields will be reported.

For the following fields, please refer to the [KafkaConsumer API](https://kafka-python.readthedocs.io/en/master/apidoc/KafkaConsumer.html).
* `security_protocol`: Set to `SSL` in order to use SSL.
* `ssl_context`
* `ssl_check_hostname`: `True` or `False`
* `ssl_cafile`
* `ssl_certfile`
* `ssl_keyfile`
* `ssl_password`
* `ssl_crlfile`
* `ssl_ciphers`
* `sasl_mechanism`: One of PLAIN, GSSAPI, OAUTHBEARER
* `sasl_plain_username`
* `sasl_plain_password`
* `sasl_kerberos_service_name`
* `sasl_kerberos_domain_name`
* `sasl_oauth_token_provider`
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI.
* **`project_name`**: Name of the project created in the InsightFinder UI.
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.

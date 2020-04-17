# kafka2
This agent collects data from kafka2 and sends it to Insightfinder.
## Installing the Agent

### Short Version
```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) kafka2 && cd kafka2
vi config.ini
sudo ./setup/install.sh --create  # install on localhost
                                  ## or on multiple nodes
sudo ./offline/remote-cp-run.sh list_of_nodes
```

See the `offline` README for instructions on installing prerequisites.

### Long Version
###### Download the agent tarball and untar it:
```bash
curl -fsSLO https://github.com/insightfinder/InsightAgent/raw/master/kafka2/kafka2.tar.gz
tar xvf kafka2.tar.gz && cd kafka2
```

###### Copy `config.ini.template` to `config.ini` and edit it:
```bash
cp config.ini.template config.ini
vi config.ini
```
See below for a further explanation of each variable.

#### Automated Install (local or remote)
###### Review propsed changes from install:
```bash
sudo ./setup/install.sh
```

###### Once satisfied, run:
```bash
sudo ./setup/install.sh --create
```

###### To deploy on multiple hosts, instead call 
```bash
sudo ./offline/remote-cp-run.sh list_of_nodes -f <nodelist_file>
```
Where `list_of_nodes` is a list of nodes that are configured in `~/.ssh/config` or otherwise reachable with `scp` and `ssh`.

#### Manual Install (local only)
###### Check Python version & upgrade if using Python 3
```bash
if [[ $(python -V 2>&1 | awk '{ print substr($NF, 1, 1) }') == "3" ]]; then \
2to3 -w getmessages_kafka2.py; \
else echo "No upgrade needed"; fi
```

###### Setup pip & required packages:
```bash
sudo ./setup/pip-config.sh
```

###### Test the agent:
```bash
python getmessages_kafka2.py -t
```

###### If satisfied with the output, configure the agent to run continuously:
```bash
sudo ./setup/cron-config.sh
```

### Config Variables
* **`bootstrap_servers`**: Comma-delimited list of `host[:port]` Kafka servers to connect to.
* **`topics`**: Topics in Kafka to subscribe to.
* `group_id`: Group ID to use in Kafka connection.
* `client_id`: Client ID to use in Kafka connection.
* `security_protocol`: Security protocol to use. Valid options are `PLAINTEXT, SSL, SASL_PLAINTEXT or SASL_SSL`.
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
* `filters_include`: Used to filter messages based on allowed values.
* `filters_exclude`: Used to filter messages based on unallowed values.
* **`data_format`**: The format of the data to parse: RAW, CSV, or JSON.
* `raw_regex`: Regex used to parse raw data. Must use named capture groups `(?<name>...)` corresponding to fields defined below, as only those named capture groups will be reported.
* `raw_start_regex`: Regex used to indicate the start of a new multiline message. MUST start with `^` if defined.
* `csv_field_names`: A list of field names for CSV input. Required, even if the CSV to parse has a header.
* `csv_field_delimiter`: A regex for the field delimiter to use - the default is `,|\t` for commas and tabs.
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
* `timestamp_format`: Format of the timestamp, in python [strftime](http://strftime.org/). If the timestamp is in Unix epoch, this can be left blank or set to `epoch`. If the timestamp is split over multiple fields, curlies can be used to indicate formatting, ie: `{YEAR} {MO} {DAY} {TIME}`; alternatively, if the timestamp can be in one of multiple fields, a priority list of field names can be given: `timestamp1,timestamp2`.
* `timezone`: Timezone for the data. Note that it cannot be parsed from the timestamp, and will be discarded if only present there.
* `timestamp_field`: Field name for the timestamp. Default is `timestamp`.
* `instance_field`: Field name for the instance name. If not set or the field is not found, the instance name is the hostname of the machine the agent is installed on. This can also use curly formatting or a priority list.
* `device_field`: Field name for the device/container for containerized projects. This can also use curly formatting or a priority list.
* `data_fields`: Comma-delimited list of field names to use as data fields. If not set, all fields will be reported. Each data field can either be a field name (`name`) or a labeled field (`<name>:<value>` or `<name>:=<value>`), where `<name>` and `<value>` can be raw strings (`fieldname:fieldvalue`) or curly-formatted (`{na} [{me}]:={val} - {ue}`). If `:=` is used as the separator, `<value>` is treated as a mathematical expression that can be evaluated with `numexpr.evaluate()`.
* `metric_name_field`: If this is set, only the first value in `data_fields` will be used as the field containing the value for the metric who's name is contained here. For example, if `data_fields = count` and `metric_name_field = status`, and the data is `{"count": 20, "status": "success"}`, then the data reported will be `success: 20`.
* `enable_metric_buffer`: If this is set with "true", agent will use buffer in memory to fuse metrics. Default is `false`.
* `metric_buffer_size_mb`: Size of buffer (in MB) to fuse metrics. Default is `10`.
* `metric_buffer_keep_last_time`: Keep the metric data for the last time in buffer to fused. Default is `5`.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* `token`: Token from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI. 
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in project settings.
* `run_interval`: How frequently the agent is ran.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.

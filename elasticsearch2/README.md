# ElasticSearch
This agent collects data from ElasticSearch and sends it to Insightfinder.
## Installing the Agent

### Short Version
```bash
bash <(curl -sS https://raw.githubusercontent.com/insightfinder/InsightAgent/master/utils/fetch-agent.sh) elasticsearch2 && cd elasticsearch2
vi config.ini
sudo ./scripts/install.sh --create  # install on localhost
                                    ## or on multiple nodes
sudo ./scripts/remote-cp-run.sh list_of_nodes
```

See the `offline` README for instructions on installing prerequisites.

### Long Version
###### Download the agent tarball and untar it:
```bash
curl -sSLO https://github.com/insightfinder/InsightAgent/raw/master/elasticsearch2/elasticsearch2.tar.gz
tar xvf elasticsearch2.tar.gz && cd elasticsearch2
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
sudo ./scripts/install.sh
```

###### Once satisfied, run:
```bash
sudo ./scripts/install.sh --create
```

###### To deploy on multiple hosts, instead call 
```bash
sudo ./scripts/remote-cp-run.sh list_of_nodes -f <nodelist_file>
```
Where `list_of_nodes` is a list of nodes that are configured in `~/.ssh/config` or otherwise reachable with `scp` and `ssh`.

#### Manual Install (local only)
###### Check Python version & upgrade if using Python 3
```bash
if [[ $(python -V 2>&1 | awk '{ print substr($NF, 1, 1) }') == "3" ]]; then \
2to3 -w getmessages_elasticsearch2.py; \
else echo "No upgrade needed"; fi
```

###### Setup pip & required packages:
```bash
sudo ./scripts/pip-config.sh
```

###### Test the agent:
```bash
python getmessages_elasticsearch2.py -t
```

###### If satisfied with the output, configure the agent to run continuously:
```bash
sudo ./scripts/cron-config.sh
```

### Config Variables
* **`es_uris`**: A comma delimited list of RFC-1738 formatted urls `<scheme>://[<username>:<password>@]hostname:port`
* `query_json`: JSON to add the the query
* `indeces`: Indeces to search over (comma-separated, wildcards supported)
* `port`: Port to connect to for ES. Overridden if in URI
* `http_auth`: `username:password` used to connect to ES. Overridden if in URI
* `use_ssl`: True or False if SSL should be used. Overridden if URI scheme is `https`
* `ssl_assert_hostname`: True or False if hostname verification should be done
* `ssl_assert_fingerprint`: True or False if fingerprint verification should be done
* `ssl_version`: Version of SSL to use - one of `SSLv23 (default), SSLv2, SSLv3, TLSv1`
* `verify_certs`: True or False if certificates should be verified
* `ca_certs`: Path to CA bundle
* `client_cert`: Path to certificate
* `client_key`: Path to client
* `_from`: Start date/time for replay, in ISO8601 format ie 2020-01-01T12:00:00Z
* `_to`: End date/time for replay, in ISO8601 format ie 2020-01-01T12:00:00Z
* `filters_include`: Used to filter messages based on allowed values.
* `filters_exclude`: Used to filter messages based on unallowed values.
* `json_top_level`: The top-level of fields to parse in JSON. For example, if all fields of interest are nested like 
* `timestamp_format`: Format of the timestamp, in python [strftime](http://strftime.org/). If the timestamp is in Unix epoch, this can be left blank or set to `epoch`.
* `timestamp_field`: Field name for the timestamp. Default is `timestamp`.
* `instance_field`: Field name for the instance name. If not set or the field is not found, the instance name is the hostname of the machine the agent is installed on. 
* `device_field`: Field name for the device/container for containerized projects.
* `data_fields`: Comma-delimited list of field names to use as data fields. If not set, all fields will be reported.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* `token`: Token from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI. 
* **`project_type`**: Type of the project - one of `metric, metricreplay, log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* `sampling_interval`: How frequently data is collected. Should match data frequency.
* **`run_interval`**: How frequently the script is ran. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.

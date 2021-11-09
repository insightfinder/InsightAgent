# InsightAgent: GoogleMonitoring

This agent can be used to get metric data from Google cloud and ingest it to an IF metric project.

#### Pre-requisites:

- Python 3.6+
- Pip3
- InsightFinder Credentials
- Google Cloud Credentials & Permissions

#### Installation Steps:
1. Download the googleMonitoring.tar.gz package
1. Copy the agent package to the machine that will be running the agent
1. Extract the package
1. Navigate to the extracted location 
1. Configure venv and python dependencies
1. Configure agent settings
1. Test the agent
1. Add agent to cron/any other job scheduler

###### Configuring venv and python dependencies
Set up a virutal environment. Then, to install the required python libraries, use:
```
pip3 install -r requirements.txt
```

###### Configuring and testing the agent

Set the hardcoded parameters in the CONFIG.ini file. To ingest Google Cloud metrics into an InsightFinder metric project, use:
```
python GoogleMonitoring.py 
```

### Config Variables

#### insightFinder_vars:
* **`host_url`**: URL for InsightFinder, usually `https://app.insightfinder.com`.
* **`http_proxy`**: HTTP proxy used to connect to InsightFinder.
* **`https_proxy`**: As above, but HTTPS.
* **`licenseKey`**: License Key from your Account Profile in the InsightFinder UI.
* **`project_name`**: Name of the project created in the InsightFinder UI to which the data would be sent.
* **`username`**: User name to InsightFinder account.
* **`retries`**: Number of retries for http requests in case of failure.
* **`sleep_seconds`**: Time between subsequent retries.

#### googleMonitoring_vars:
* **`service_key_json`**: Path to the JSON file downloaded from Google Cloud with a project's service account's private key.
* **`http_proxy`**: HTTP proxy used to connect to vCenter. DO NOT include the protocol prefix.
* **`https_proxy`**: As above, but HTTPS.
* **`project_id`**: Project's ProjectID on Google Cloud.
* **`metrics_list`**: Comma-separated list of metrics to be selected. Given precedence over regex.
* **`metrics_regex`**: Regular Expression for metrics to be selected.
* **`instance_field`**: Comma-separated priority list of labels to be used as IF instance name; at least one needs to valid and listed for a metric to be able to get corresponding data (required).
* **`container_field`**: Comma-separated priority list of labels to be used as IF container name (optional).
* **`instance_field_list`**: Comma-separated list of instance field values to be selected. Given precedence over regex.
* **`instance_field_regex`**: Regular Expression for instance field values to be selected.
* **`resource_type_list`**: Comma-separated list of resource types to be selected. Given precedence over regex.
* **`resource_type_regex`**: Regular Expression for resource types to be selected.
* **`zone_list`**: Comma-separated list of zones to be selected. Given precedence over regex.
* **`zone_regex`**: Regular Expression for zones to be selected.

#### agent_vars:
* **`historical_time_range`**: Time range for ingesting historical metric data; enter start and end times separated by comma (,); use the format YYYY-MM-DD HH:MM:SS. Should be left empty for live mode.
* **`query_interval`**: Time interval for the query (in minutes). Used for live mode only.
* **`thread_pool`**: Number of threads to be used in the multiprocessing pool.
* **`chunk_size_kb`**: Maximum size of a data chunk to be sent to IF, in kilobytes.

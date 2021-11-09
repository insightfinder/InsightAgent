# InsightAgent: GoogleMonitoring

This agent can be used to get metric data from Google cloud and ingest it to an IF metric project.

## Installing the Agent

### Required Dependencies:
1. Python 3.x 
1. Pip3

###### Installation Steps:
1. Download the googleMonitoring.tar.gz package
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
The config.ini file contains all of the configuration settings needed to connect to the Google Monitoring API and to stream the data to InsightFinder.

The configure_python.sh script will generate a config.ini file for you; however, if you need to create a new one, you can simply copy the config.ini.template file over the config.ini file to start over. 

Populate all of the necessary fields in the config.ini file with the relevant data.  More details about each field can be found in the comments of the config.ini file and the Config Variables section below. 

###### Test the agent:
Once you have finished configuring the config.ini file, you can test the agent to validate the settings. 

This will connect to the Google Monitoring API, but it will not send any data to InsightFinder. This allows you to verify that you are getting data from the Google Monitoring API and that there are no failing exceptions in the agent configuration. 

```bash
./setup/test_agent.sh
```

###### Add agent to the cron:
For the agent to run continuously, it will need to be added as a cron job. 

The install_cron.sh script will add a cron file to run the agent on a regular schedule.

```bash
# Display the cron entry without adding it 
./setup/install_cron.sh --display

# Add the cron entry, once you are ready to start streaming
sudo ./setup/install_cron.sh --create
```

###### Pausing or stopping the agent:
Once the cron is running, you can either pause the agent by commenting out the relevant line in the cron file or stop the agent by removing the cron file. 

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
* **`sampling_interval`**: Sampling interval/frequency for data collection by the agent; should match the interval used in project settings on IF.
* **`run_interval`**: Frequency at which the agent is ran; should match the interval used in cron.
* **`thread_pool`**: Number of threads to be used in the multiprocessing pool.
* **`chunk_size_kb`**: Maximum size of a data chunk to be sent to IF, in kilobytes.

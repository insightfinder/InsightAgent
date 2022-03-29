# servicenow
This agent collects data from servicenow and sends it to Insightfinder.
## Installing the Agent

### Required Dependencies:
1. Python 3.x 
1. Pip3

###### Installation Steps:
1. Download the servicenow.tar.gz package
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
The config.ini file contains all of the configuration settings needed to connect to the ServiceNow instance and to stream the data to InsightFinder.

The password for the ServiceNow user will need to be obfuscated using the ifobfuscate.py script.  It will prompt you for the password and provide the value to add to the configuration file. 

```
python ./ifobfuscate.py 
```

The configure_python.sh script will generate a config.ini file for you; however, if you need to create a new one, you can simply copy the config.ini.template file over the config.ini file to start over. 

Populate all of the necessary fields in the config.ini file with the relevant data.  More details about each field can be found in the comments of the config.ini file and the Config Variables below. 

###### Test the agent:
Once you have finished configuring the config.ini file, you can test the agent to validate the settings. 

This will connect to the ServiceNow instance, but it will not send any data to InsightFinder. This allows you to verify that you are getting data from ServiceNow and that there are no failing exceptions in the agent configuration. 

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
* **`base_url`**: Base URL to build the API off of.
* **`api_endpoint`**: API endpoint to call. '/api/now/v1/table/incident' or '/api/now/v1/table/change_request'
* `sysparm_offset`: Offset to use when calling the API. Generally speaking, you should not touch this setting.
* **`username`**: Username to authenticate with.
* **`password_encrypted`**: Password, encoded in base64. To set this, run `python configure.py`.
* `filter_query`: Used to filter messages. Servicenow query Eg. `state=2^ORstate=1^category=inquiry`
* `json_top_level`: The top-level of fields to parse in JSON/AVRO/XML. For example, if all fields of interest are nested like 
* `timestamp_format`: Format of the timestamp, in python [strftime](http://strftime.org/). If the timestamp is in Unix epoch, this can be left blank or set to `epoch`. If the timestamp is split over multiple fields, curlies can be used to indicate formatting, ie: `{YEAR} {MO} {DAY} {TIME}`; alternatively, if the timestamp can be in one of multiple fields, a priority list of field names can be given: `timestamp1,timestamp2`.
* `timezone`: Timezone for the data. Note that it cannot be parsed from the timestamp, and will be discarded if only present there.
* `timestamp_field`: Field name for the timestamp. Default is `timestamp`.
* `instance_field`: Field name for the instance name. If not set or the field is not found, the instance name is the hostname of the machine the agent is installed on. This can also use curly formatting or a priority list.
* `device_field`: Field name for the device/container for containerized projects. This can also use curly formatting or a priority list.
* `data_fields`: Comma-delimited list of field names to use as data fields. If not set, all fields will be reported. Each data field can either be a field name (`name`) or a labeled field (`<name>::<value>` or `<name>::==<value>`), where `<name>` and `<value>` can be raw strings (`fieldname::fieldvalue`) or curly-formatted (`{na} [{me}]::=={val} - {ue}`). If `::==` is used as the separator, `<value>` is treated as a mathematical expression that can be evaluated with `eval()`.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* `is_historical`: if it is 'true', the script will grab the data according to the data range; if it is false, it the script will grab the real time data with the Cron
* `start_time`: The start time of timestamp field, it is used to grab the history data
* `end_time`: The end time of timestamp field, it is used to grab the history data

* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI. 
* **`project_type`**: Type of the project -  `alert` or 'deployment'.
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in project settings.
* **`run_interval`**: How frequently the agent is ran. Should match the interval used in cron.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`. Change to 'https://app.insightfinder.com/api/v1/' if the project_type is 'deployment'.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.

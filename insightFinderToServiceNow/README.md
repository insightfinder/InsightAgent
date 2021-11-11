# InsightAgent: insightFinderToServiceNow

This agent can be used to get the predicted incident data from InsightFinder and send it to ServiceNow.

## Installing the Agent

### Required Dependencies:
1. Python 3.x 
1. Pip3

###### Installation Steps:
1. Download the insightFinderToServiceNow.tar.gz package
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
The config.ini file contains all of the configuration settings needed to connect to InsightFinder and to stream the incidents to ServiceNow.

The configure_python.sh script will generate a config.ini file for you; however, if you need to create a new one, you can simply copy the config.ini.template file over the config.ini file to start over. 

Populate all of the necessary fields in the config.ini file with the relevant data. More details about each field can be found in the comments of the config.ini file and the Config Variables section below. 

###### Test the agent:
Once you have finished configuring the config.ini file, you can test the agent to validate the settings. 

This will connect to InsightFinder, but it will not send any incidents to ServiceNow. This allows you to verify that you are getting incidents from the InsightFinder API and that there are no failing exceptions in the agent configuration. 

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
* **`retries`**: Number of retries for http requests in case of failure.
* **`sleep_seconds`**: Time between subsequent retries.

#### serviceNow_vars:
* **`host_url`**: URL for ServiceNow.
* **`http_proxy`**: HTTP proxy used to connect to ServiceNow.
* **`https_proxy`**: As above, but HTTPS.
* **`api`**: The API to use for ServiceNow, usually `/api/now/table/<>`.
* **`username`**: User name to the ServiceNow account.
* **`password`**: Obfuscated password to the ServiceNow account.
* **`target_table`**: Name of the ServiceNow target table.
* **`retries`**: Number of retries for http requests in case of failure.
* **`sleep_seconds`**: Time between subsequent retries.
* **`dampening_minutes`**: Minimum time between two post requests of the similar incident.

#### payload_vars:
* **`environment_name`**: Name of the environment on InsightFinder.
* **`system_id_list`**: Comma-separated list of System IDs, as seen on InsightFinder.
* **`customer_name`**: Name of the customer on InsightFinder.
* **`start_date`**: Start date for historical incident collection. Leave empty for live mode (will be assigned today's date).
* **`end_date`**: End date for historical incident collection. Leave empty for live mode (will be assigned today's date).
* **`run_interval`**: Frequency at which the agent is ran; should match the interval used in cron.

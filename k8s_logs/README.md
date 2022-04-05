# k8s_logs
This agent collects data from k8s_logs and sends it to Insightfinder.
## Installing the Agent

### Required Dependencies:
1. Python 3.x, though we provide the libraries for version 3.7
2. Pip3
3. kubernetes config file

###### Installation Steps:
1. Download the k8s_logs.tar.gz package
2. Copy the agent package to the machine that will be running the agent
3. Extract the package
4. Navigate to the extracted location 
5. Configure venv and python dependencies
6. Configure agent settings under `config.ini`
7. Test the agent
8. Add agent to the cron

The final steps are described in more detail below. 

###### Configure venv and python dependencies:
The configure_python.sh script sets up a virtual python environment and installs all required libraries for running the agent. 

```bash
./setup/configure_python.sh
```

##### Agent Configuration
The config.ini file contains all of the confiuration settings needed to use the k8s_logs instance and stream the data to InsightFinder.

The configure_python.sh script will generate a config.ini file for you; however, if you need to create a new one, you can simply copy the config.ini.template file over the config.ini file to start over. 

Populate all of the necessary fields in the config.ini file with the relevant data.  More details about each field can be found in the comments of the config.ini file and the Config Variables below. 

```
vi config.ini
```

###### Test the agent:
Once you have finished configuring the config.ini file, you can test the agent to validate the settings. 

This will run the k8s_logs instance, but it will not send any data to InsightFinder. This allows you to verify that you are getting data from Kubernetes and that there are no failing exceptions in the agent configuration.

```bash
./setup/test_agent.sh -t
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
* `filters_include`: Used to filter messages based on allowed values.
* `filters_exclude`: Used to filter messages based on unallowed values.
* `config_file`: Path to the kube config file. 
* `namespaces`: Namespaces to include.
* `namespaces_exclude`: Namespaces to exclude
* `pod_names`: Pod names to inlcude.
* `pod_field_selector`: Selector for pod field.
* `pod_label_selector`: Selector for pod label.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.
* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI. 
* `token`: Token from your Account Profile in the InsightFinder UI. 
* **`project_name`**: Name of the project created in the InsightFinder UI. 
* **`project_type`**: Type of the project - one of `log, logreplay, incident, incidentreplay, alert, alertreplay, deployment, deploymentreplay`.
* **`sampling_interval`**: How frequently data is collected. Should match the interval used in project settings.
* `chunk_size_kb`: Size of chunks (in KB) to send to InsightFinder. Default is `2048`.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.

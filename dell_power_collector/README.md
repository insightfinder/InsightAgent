# Dell Power Collector

This agent collects metric and log data from Dell Power products and sends it to Insightfinder.

## Build the Agent

The agent is written in Go. To build the agent, you need to install Go 1.13 or later.
Run the following commands to build:

```bash
# build on Linux
./build_for_linux_in_linux_env.sh

# build on Windows
./build_for_linux_in_win_env.cmd
```

## Installation Steps:

1. Copy the built binary `dell_power_collector` to the machine that will be running the agent
1. Create one or multiple config files in the conf.d directory based on below instructions and `config.ini.template`
1. Add agent to the cron

## Config Variables

### powerFlexManager section

* `apiEndpoint`: Api endpoint to retrieve logs
* `timeStampField`: Field name for the timestamp. Default is `timestamp`.
* `instanceNameField`: Field name for the instance name.
* `userName`: Username used to authenticate to the api endpoint
* `password`: password used to authenticate to the api endpoint
* `domain`: domain used to authenticate to the api endpoint
* `userAgent`: userAgent used to connect to the api endpoint
* `connectionUrl`: connection url for the log api endpoint
* `maxFetchCount`: The maximum number of entries to fetch for each run. Set to 0 if no limit.
* `timezone`: Timezone of the timestamp data stored in/returned by the DB. Note that if timezone information is not
  included in the data returned by the DB, then this field has to be specified.
* `target_timestamp_timezone`: Timezone of the timestamp data to be sent and stored in InsightFinder. Default value is
  UTC. Only if you wish to store data with a time zone other than UTC, this field should be specified to be the desired
  time zone.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.

### Insightfinder Section

* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI.
* `token`: Token from your Account Profile in the InsightFinder UI.
* **`project_name`**: Name of the project created in the InsightFinder UI, If this project is not exist, agent will
  create it automatically.
* `system_name`: Name of system owned by project. If project_name is not exist in InsightFinder, agent will create a new
  system automatically from this field or project_name.
* `project_name_prefix`: Prefix of the project name. This combines with the component in the metadata to build the
  project name.
* **`project_type`**: Type of the project - one
  of `metric, metricreplay, log, logreplay, alert, alertreplay, incident, incidentreplay, deployment, deploymentreplay, trace, tracereplay`
  .
* **`sampling_interval`**: How frequently (in Minutes) data is collected. Should match the interval used in project
  settings.
* **`run_interval`**: How frequently (in Minutes) the agent is ran. Should match the interval used in cron.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.



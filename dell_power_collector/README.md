# Dell Power Collector

This agent collects metric and log data from Dell Power products and sends it to Insightfinder.

Current supported product: powerflex, powerflex manager, powerstore, powerscale. For metric key, no nested structure is supported. For one specific key, if it has a nested structure, all its children will be collected. The metric collection will only be effective for number type value.

## Build the Agent

The agent is written in Go. To build the agent, you need to install Go 1.13 or later. The build from these 2 commends should be run in Linux environment. We don't support runnning in Windows environment yet. 

Run the following commands to build:
```bash
# build on Linux (Recommend)
./build_for_linux_in_linux_env.sh

# build on Windows
./build_for_linux_in_win_env.cmd
```

## Installation Steps:

1. Copy the built binary dell_power_collector to the machine that will be running the agent
1. Create one or multiple config files in the conf.d directory based on below instructions and `config.ini.template`
1. For metric data, please create a json file containing API and metric list inside `conf.d` directory (Refer to `sampleMetricListFile.json`) and specify its path inside config file.
1. Add agent to the cron

## Config Variables
In one config file, it should contain 2 sections. The first one is the Insightfinder section and the other one will be any type of the power product section.

Required field are in **bold**.
### powerStore section
* **`instanceType`**:  The instance type from the powerStore API documentation.
* **`instanceNameField`**:  The field key in the metric for instnace name.
* **`timeStampField`**:  The field key in the metric for timeStamp.
* **`userName`**: Username used to authenticate to the api endpoint
* **`password`**: password used to authenticate to the api endpoint
* **`metricPath`**: The json file containing the API endpoint and what metrics to collect
* **`connectionUrl`**: The host url to get the metric data.
* **`metricType`**: The POST request body key **entity**. The value should correspond to the instance type to obtain the desired metrics.

The API should not be changed and the metric list inside need to specify the metrics want to be collected. If left empty, it will collect all metrics. **This metric name MUST pair with the instnace type in the config file** to obtain the desired metric data. Please refer to https://developer.dell.com/apis/3898/versions/3.2.0/reference/openapi.json/paths/~1metrics~1generate/post for detailed documentation.
```bash
{
    "/metric/generate":[
        "metrickey1",
        "metrickey2"
    ]
}
```

### powerScale section
* **`instanceNameField`**:  The field key in the metric for instnace name.
* **`timeStampField`**:  The field key in the metric for timeStamp.
* **`userName`**: Username used to authenticate to the api endpoint
* **`password`**: password used to authenticate to the api endpoint
* **`metricPath`**: The json file containing the API endpoint and what metrics to collect
* **`connectionUrl`**: The host url to get the metric data.
* **`firstLayerkey`**: PowerScale metric return payload key that has the metric arrary in it.

Sample json file for powerScale. The metric list specify the metric needed. If left empty, it will obtain all the metrics. Refer to https://developer.dell.com/apis/4088/versions/9.4.0.0/9.4.0.0.json/paths/~1platform~13~1statistics~1summary~1drive/get for detailed documentation
```bash
{
 "/platform/3/statistics/summary/system":[
      "metrickey1",
      "metrickey2"
    ]
}
```
### powerFlex section

* **`instanceType`**:  The instance type from the powerFlex API documentation.
* **`userName`**: Username used to authenticate to the api endpoint
* **`metricPath`**: The json file containing the API endpoint and what metrics to collect
* **`password`**: password used to authenticate to the api endpoint
* **`connectionUrl`**: The host url to get the metric data.
* **`idEndPoint`**: The endpoint to get all instances ids.

Sample json file for powerflex. All the metrics name must exist.If left empty, it will collect all metrics. **The API shouldn't be changed**. Update the metrics needed based on different instances input. Refer to https://developer.dell.com/apis/4008/versions/4.0/PowerFlex_REST_API.json/paths/~1api~1instances~1ProtectionDomain::%7Bid%7D~1relationships~1Statistics/get for detailed documentation
```bash
{
  "/api/instances/{$instanceType}::{$id}/relationships/Statistics":[
        "unusedCapacityInKb",
        "totalReadBwc",
        "persistentChecksumCapacityInKb",
        "numOfVolumes",
        "currentTickerValue"
    ],
}
```

### powerFlexManager section

* **`apiEndpoint`**: Api endpoint to retrieve logs
* **`timeStampField`**: Field name for the timestamp. Default is `timestamp`.
* `instanceNameField`: Field name for the instance name.
* **`userName`**: Username used to authenticate to the api endpoint
* **`password`**: password used to authenticate to the api endpoint
* **`domain`**: domain used to authenticate to the api endpoint. Please use the one from the template.
* **`userAgent`**: userAgent used to connect to the api endpoint
* **`connectionUrl`**: connection url for the log api endpoint

Refer to https://developer.dell.com/apis/5468/versions/3.8/PowerFlexManager_REST_API.json/paths/~1Log/get for documentation.

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

Fields will be supported in the future.

* `timezone`: Timezone of the timestamp data stored in/returned by the DB. Note that if timezone information is not
  included in the data returned by the DB, then this field has to be specified.
* `target_timestamp_timezone`: Timezone of the timestamp data to be sent and stored in InsightFinder. Default value is
  UTC. Only if you wish to store data with a time zone other than UTC, this field should be specified to be the desired
  time zone.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.



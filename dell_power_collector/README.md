# Dell Power Collector

This agent collects metric and log data from Dell Power products and sends it to Insightfinder.

Current supported products: powerflex, powerflex manager, powerstore, and powerscale. For metric keys, nested structure is not currently supported. For one specific key, if it has a nested structure, all of its children will be collected. The metric collection will only be effective for numerical-typed values.

## Build the Agent

The agent is written in Go. To build the agent, you need to install Go version 1.13 or later. The application that is built from the following 2 commands should be run in a Linux environment. NOTE: While the application can be built in Windows, we currently do not support running the application in Windows environments. 

In the same directory with go.mod, run the following commands to build :
```bash
# build on Linux (Recommend)
./build_for_linux_in_linux_env.sh

# build on Windows
./build_for_linux_in_win_env.cmd
```

## Build the Agent Docker Image
1. Make sure you have the Dell Root CA certificate. Rename it to `Dell_Root_CA.pem` and put it under this repo.
2. Build docker image using `docker build . -t insightfinderinc/dellpoweragent:latest`
3. (Optional) Push the image to our DockerHub: `docker login` and `docker push insightfinderinc/dellpoweragent:latest`

## Run the Agent Docker Container
1. Make sure the image `insightfinderinc/dellpoweragent:latest` exists on the server. If not, run `docker login` and `docker pull insightfinderinc/dellpoweragent:latest`
2. Prepare Agent Configurations file by creating a `conf.d` folder and many of the `*.ini` files.
3. Run Ccontainer: `docker run --name dellpoweragent -itd -v conf.d:/root/powerAgent/conf.d insightfinderinc/dellpoweragent:latest`
4. Check the agent logs: `docker logs dellpoweragent`

## Installation Steps:

1. Copy the built binary `dell_power_collector` to the machine that will be running the agent.
2. Create one or more config files in the conf.d directory based on the following instructions and the template file `config.ini.template`.
3. For metric data, please create a json file containing API and a list of desired of metrics inside the `conf.d` directory (Refer to `sampleMetricListFile.json`) and specify its path inside of the config file.
4. Add a cronjob for the agent to run automatically. 

## Config Variables
In one config file, there should be 2 sections. The first one is the Insightfinder section and the other one will be a "power product" section.

Required fields are in **bold**.
### powerStore section
* **`instanceType`**:  The instance type from the powerStore API documentation.
* **`instanceNameField`**:  The field key in the metric for instance name.
* **`timeStampField`**:  The field key in the metric for timeStamp.
* **`userName`**: Username used to authenticate to the api endpoint.
* **`password`**: Password used to authenticate to the api endpoint.
* **`metricPath`**: The json file containing the API endpoint and what metrics to collect.
* **`connectionUrl`**: The host url to get the metric data. There can be multiple URL in this part separated by ",". For example: 127.0.0.1,198.163.0.1
* **`metricType`**: The POST request body key **entity**. The value should correspond to the instance type to obtain the desired metrics.

The API should not be changed when used, and the metric list inside will need to specify the metrics you would like to be collected. If left empty, it will collect all metrics. **This metric name MUST pair with the instance type in the config file** to obtain the desired metric data. Please refer to https://developer.dell.com/apis/3898/versions/3.2.0/reference/openapi.json/paths/~1metrics~1generate/post for detailed documentation.
```bash
{
    "/metric/generate":[
        "metrickey1",
        "metrickey2"
    ]
}
```

### powerScale section
* **`instanceNameField`**:  The field key in the metric for instance name.
* **`timeStampField`**:  The field key in the metric for timeStamp.
* **`userName`**: Username used to authenticate to the api endpoint.
* **`password`**: Password used to authenticate to the api endpoint.
* **`metricPath`**: The json file containing the API endpoint and what metrics to collect.
* **`connectionUrl`**: The host url to get the metric data. There can be multiple URL in this part separated by ",". For example: 127.0.0.1,198.163.0.1
* **`firstLayerkey`**: PowerScale metric return payload key that has the metric arrary in it.

The following is a sample json file for powerScale. The metric list inside will need to specify the metrics you would like to be collected. If left empty, it will collect all metrics. Refer to "https://developer.dell.com/apis/4088/versions/9.4.0.0/9.4.0.0.json/paths/~1platform~13~1statistics~1summary~1drive/get" for detailed documentation.
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
* **`userName`**: Username used to authenticate to the api endpoint.
* **`metricPath`**: The json file containing the API endpoint and what metrics to collect.
* **`password`**: Password used to authenticate to the api endpoint.
* **`connectionUrl`**: The host url to get the metric data. There can be multiple URL in this part separated by ",". For example: 127.0.0.1,198.163.0.1
* **`idEndPoint`**: The endpoint to get all instances ids.

The following is a sample json file for powerflex. All the metrics that are entered in the list must exist. If left empty, it will collect all metrics. **The API should not be changed**. The metrics provided should be based on the  instance. Refer to "https://developer.dell.com/apis/4008/versions/4.0/PowerFlex_REST_API.json/paths/~1api~1instances~1ProtectionDomain::%7Bid%7D~1relationships~1Statistics/get" for detailed documentation.
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

* **`apiEndpoint`**: Api endpoint to retrieve logs.
* **`timeStampField`**: Field name for the timestamp. Default is `timestamp`.
* `instanceNameField`: Field name for the instance name.
* **`userName`**: Username used to authenticate to the api endpoint.
* **`password`**: Password used to authenticate to the api endpoint.
* **`domain`**: Domain used to authenticate to the api endpoint. Please use the one from the template.
* **`userAgent`**: userAgent used to connect to the api endpoint.
* **`connectionUrl`**: Connection url for the log api endpoint. There can be multiple URL in this part separated by ",". For example: 127.0.0.1,198.163.0.1

Refer to "https://developer.dell.com/apis/5468/versions/3.8/PowerFlexManager_REST_API.json/paths/~1Log/get" for documentation.

### Insightfinder Section

* **`user_name`**: User name in InsightFinder.
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI.
* `token`: Token from your Account Profile in the InsightFinder UI.
* **`project_name`**: Name of the project created in the InsightFinder UI. If this project does not exist, agent will
  create it automatically.
* `system_name`: Name of the system that contains the project. If this system does not exist in InsightFinder, agent will create a new
  system automatically from this field or the `project_name` field.
* `project_name_prefix`: Prefix of the project name. This combines with the component in the metadata to build the
  project name.
* **`project_type`**: Type of the project - should be one of the following: 
  `metric, metricreplay, log, logreplay, alert, alertreplay, incident, incidentreplay, deployment, deploymentreplay, trace, tracereplay`
  .
* **`sampling_interval`**: How frequently (in Minutes) data is collected. Should match the interval used in project
  settings.
* **`run_interval`**: How frequently (in Minutes) the agent should run. Should match the interval used in the cronjob.
* `if_url`: URL for InsightFinder. Default is `https://app.insightfinder.com`.
* `if_http_proxy`: HTTP proxy used to connect to InsightFinder.
* `if_https_proxy`: As above, but HTTPS.

The following fields will be supported in the future:

* `timezone`: Timezone of the timestamp data stored in/returned by the DB. Note that if timezone information is not
  included in the data returned by the DB, then this field has to be specified.
* `target_timestamp_timezone`: Timezone of the timestamp data to be sent and stored in InsightFinder. Default value is
  UTC. If you wish to store data with a time zone other than UTC, this field should be specified to be the desired
  time zone.
* `agent_http_proxy`: HTTP proxy used to connect to the agent.
* `agent_https_proxy`: As above, but HTTPS.


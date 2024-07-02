All the bold fields are required.

### Opensearch Section

* **`server_url`**: The opensearch server url.
* **`cert_file_path`**: The client certificate signed by the root private key.
* **`key_file_path`**: The client private key. It could be generated using openssl.
* `root_ca_path`: If the root CA is NOT a public one. For example, if a self-assigned root CA is used, the root CA should be uploaded to pass the TLS verification for connection.
* **`instnace_name_field`**: The field in the data will be  used as instance name.
* **`timestamp_field`**: The field in the data will be used as timestamp name.
* **`query`**: What query will be used to query the  data.
* `query_endpoint`: Default is `/_plugins/_sql`. The enpoint query will be sent to. 
* `query_format`: Default is jdbc. Currently, jdbc, json, csv and raw are supported. Please refer to https://opensearch.org/docs/latest/search-plugins/sql/response-formats/ for more format detail.

### Insightfinder Section

* **`user_name`**: User name in InsightFinder
* **`license_key`**: License Key from your Account Profile in the InsightFinder UI.
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
* **`if_url`**: URL for InsightFinder. Default is `https://app.insightfinder.com`.
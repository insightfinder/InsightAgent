# InsightAgent: vSphere vCenter

This agent can be used to retrieve the performance metric data for host systems, virtual machines and datastores from vCenter, and to send it to an IF Metric Container Streaming project. The agent runs in live mode and gets the available data from the past 15 minutes. It is advised that the agent is scheduled to run at an interval of 1-10 minutes.

#### Pre-requisites:

- Python 3.6+
- InsightFinder Credentials
- vCenter

To install the required python libraries, use:
```
pip3 install -r requirements.txt
```

#### Deployment:

Set the hardcoded parameters in the CONFIG.ini file. To ingest the performance metric data from vCenter into an InsightFinder Metric project, set up a Metric Container Streaming project on IF. And then, run the following Command:
```
python vCenter.py 
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

#### vCenter_vars
* **`host`**: vCenter host and port. DO NOT include the protocol prefix.
* **`http_proxy`**: HTTP proxy used to connect to vCenter. DO NOT include the protocol prefix.
* **`username`**: User name to vCenter account.
* **`password`**: Obfuscated password to vCenter account. Obfuscate with `ifobfuscate.py`.
* **`virtual_machines_list`**: Comma-separated list of virtual machine names to be selected. Given precedence over regex.
* **`virtual_machines_regex`**: Regular Expression for virtual machine names to be selected.
* **`hosts_list`**: Comma-separated list of host system names to be selected. Given precedence over regex.
* **`hosts_regex`**: Regular Expression for host system names to be selected.
* **`datastores_list`**: Comma-separated list of datastore names to be selected. Given precedence over regex.
* **`datastores_regex`**: Regular Expression for datastore names to be selected.
* **`metrics_list`**: Comma-separated list of metrics to be selected. Given precedence over regex. Metrics should follow the format: `<counter.groupInfo.key>.<counter.nameInfo.key>.<counter.rollupType>`, where counter is a `vim.PerformanceManager.CounterInfo` object.
* **`metrics_regex`**: Regular Expression for metrics to be selected.

#### agent_vars
* **`thread_pool`**: Number of threads to be used in the multiprocessing pool.
* **`chunk_size_kb`**: Maximum size of a data chunk to be sent to IF, in kilobytes.

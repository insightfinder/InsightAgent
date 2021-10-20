# InsightAgent: IngestSentryEvents

This agent can be used to get new events from a Sentry project and to send them to an IF alert project. Note that the agent only parses the first page of events returned by the Sentry API.

#### Pre-requisites:

- Python 3.6+
- InsightFinder Credentials
- Sentry Credentials

To install the required python libraries, use:
```
pip3 install -r requirements.txt
```

#### Deployment:

Set the hardcoded parameters in the CONFIG.ini file. To ingest new Sentry events into an InsightFinder alert project, use:
```
python UpdateMetaData.py 
```

### Config Variables

#### insightFinder_vars:
* **`host_url`**: URL for InsightFinder, usually `https://app.insightfinder.com`.
* **`api`**: The InsightFinder API to send events to, always `/customprojectrawdata` for this agent.
* **`licenseKey`**: License Key from your Account Profile in the InsightFinder UI.
* **`project_name`**: Name of the project created in the InsightFinder UI to which the data would be sent.
* **`username`**: User name in InsightFinder.
* **`retries`**: Number of retries for http requests in case of failure.
* **`sleep_seconds`**: Time between subsequent retries.

#### sentry_vars
* **`host_url`**: URL for Sentry, `https://sentry.io`.
* **`api`**: The Sentry API to get events from, likely `/api/0/projects/{}/{}/events/`.
* **`organization_name`**: The slug of the organization the events belong to.
* **`project_name`**: The slug of the project the events belong to.
* **`auth_token`**: Authentication token from your Sentry account.
* **`retries`**: Number of retries for http requests in case of failure.
* **`sleep_seconds`**: Time between subsequent retries.

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

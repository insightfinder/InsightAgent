# InsightAgent: IFtoServiceNow

This agent can be used to get the predicted incident data from InsightFinder and send it to ServiceNow.

#### Pre-requisites:

- Python 3.6+
- InsightFinder license key
- ServiceNow Credentials

To install the required python libraries, use:
```
pip3 install -r requirements.txt
```

#### Deployment:

Set the hardcoded parameters in the CONFIG file. To post the predicted incidents to ServiceNow, use:
```
python GeneratePredictedIncidentServiceNowTicket.py
```

Note that the incident_record pickle stores the past post requests made as a dictionary object. No same incident (defined by the key) will be posted before or within the 'dampening_minutes' interval of last such request. Delete the pickle file to reset the record (may especially be required for processing historical data).

The payload_queue payload may also be deleted to purge payloads that could not be successfully posted in the past.
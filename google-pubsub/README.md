# InsightAgent: Google Pub/Sub
Agent Type: Google Pub/Sub
Platform: Linux

This Google Pub/Sub agent is a Logstash pipeline that reads from a subscription to a given topic. This configuration will need Logstash to be installed with the Logstash Pub/Sub plugin.  

Once that is configured, the following filters will need to be configured and set up to start streaming data from the topic to InsightFinder. 
```
filters/22-pubsub-input.conf
filters/91-pubsub.conf
filters/03-http-output.conf
```

### Prerequisites:
[Logstash](https://www.elastic.co/guide/en/logstash/current/getting-started-with-logstash.html)
[Logstash Input Plugin: Google Pub/Sub](https://www.elastic.co/guide/en/logstash/current/plugins-inputs-google_pubsub.html)
[Logstash Filter Plugin: json_encode](https://www.elastic.co/guide/en/logstash/current/plugins-filters-json_encode.html)


### Installation
1. Download and copy the filters to the filter folder for your logstash installation
    1. ```/etc/logstash/conf.d/```
1. Update 22-pubsub-input.conf with the needed fields
    1. {{ json_key_file }} - Json Key File if using JSON key authentication 
    1. {{ pubsub_project_id }} - Google PubSub Project ID
    1. {{ pubsub_topic_name }} - Google PubSub Topic Name
    1. {{ pubsub_subscription }} - Google PubSub Subscription Name
    1. {{ ifLogProjectName }} - Project Name of target project in InisightFinder
1. Update 91-pubsub.conf with the needed fields
    1. {{ pubsub_topic_name }} - Google PubSub Topic Name
1. Update 03-http-output.conf with the needed fields
    1. {{ ifReportingUrl }} - InsightFinder Host URL (https://app.insightfinder.com for example)
    1. {{ ifUserName }} - InsightFinder username
    1. {{ ifLicenseKey }} - InsightFinder license key 


### Uninstallation:
Simply remove the logstash configuration files from /etc/logstash/conf.d and stop Logstash:
```
service logstash stop
```


# InsightAgent: LogFileReplay
Agent Type: LogFileReplay
Platform: Linux, Python 2.7 or Python 3.7

InsightAgent supports replay mode of json log files in which the data from the json file is read and sent to insightfinder server. A sample log file is as follows:
- The json file contains a json array, each json obejct is a log data of the original log.
- Each json object contains 3 required fields: `eventId`, `data` and `tag`
- `eventId`: the timestamp of each log
- `data`: the log data message
- `tag`: the instance/host/source of the log data, which is the instance of a project in Insightfinder.com
- `componentName`(optional): the component of different instances, if you want to group data from different instances during the analysis, you can add this field.


```json
[{"eventId": 1481846430437, "tag": "100.34.56.137", "componentName":"Log Worker", "data": "INFO org.apache.hadoop.hdfs.server.namenode.FSNamesystem: Roll Edit Log from 127.0.0.1"}, {"eventId": 1481846430437, "tag": "100.34.56.137", "data": "INFO org.apache.hadoop.hdfs.server.namenode.FSEditLog: Rolling edit logs."}]
```

You can try the agent code with the demo data demo.json, which is a IF-format data to replay on IF system.


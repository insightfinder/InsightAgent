# InsightAgent: LogFileReplay
Agent Type: LogFileReplay
Platform: Linux

InsightAgent supports replay mode of json log files in which the data from the json file is read and sent to insightfinder server. A sample log file is as follows:

```json
[{"eventId": 1481846430437, "tag": "100.34.56.137", "data": "INFO org.apache.hadoop.hdfs.server.namenode.FSNamesystem: Roll Edit Log from 127.0.0.1"}, {"eventId": 1481846430437, "tag": "100.34.56.137", "data": "INFO org.apache.hadoop.hdfs.server.namenode.FSEditLog: Rolling edit logs."}]
```

##### Instructions to replay data to a project in Insightfinder.com
- Following the tutorial link to register a project and replay data https://docs.google.com/document/d/1D-g4w9zZtrNo-8Y1GYMbl-RDBZymmz9PG9UovYq5f6c/edit


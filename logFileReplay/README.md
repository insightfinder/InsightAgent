# InsightAgent: LogFileReplay
Agent Type: LogFileReplay
Platform: Linux

InsightAgent supports replay mode of json log files in which the data from the json file is read and sent to insightfinder server. A sample log file is as follows:
- The json file contains a json array, each json obejct is a log data of the original log.
- Each json object contains 3 required fields: eventId, data and tag
- eventId: the timestamp of each log
- data: the log data message
- tag: the instance/host/source of the log data, which is the instance of a project in Insightfinder.com

```json
[{"eventId": 1480750759682, "data": " INFO org.apache.hadoop.hdfs.server.namenode.TransferFsImage: Downloaded file fsimage.ckpt_0000000000000000020 size 120 bytes.\n", "tag": "hadoop"}, {"eventId": 1480750759725, "data": " INFO org.apache.hadoop.hdfs.server.namenode.NNStorageRetentionManager: Going to retain 2 images with txid >= 18\n", "tag": "hadoop"}, {"eventId": 1480754359850, "data": " INFO org.apache.hadoop.hdfs.server.namenode.FSNamesystem: Roll Edit Log from 127.0.0.1\n", "tag": "hadoop"}]
```



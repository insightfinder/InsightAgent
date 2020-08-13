# InsightAgent: MetricFileReplay
Agent Type: MetricFileReplay
Platform: Linux

InsightAgent supports replay mode of metric files in which the data from the file is read and sent to insightfinder server. A sample metric file is as follows:
- The file contains a json object each line, each json object contains all metric data of a instance by a timestamp.
- Each json object contains at least 1 required fields: timestamp
- timestamp: the timestamp of all metrics collect time by each instance
- {MetricData}: the metrics data, the key format is `metricName[instanceName]`


Example file:
```text
{"timestamp": 1597307741000, "DiskUsed[node1]": 1000, "CPU[node1]": 1}
{"timestamp": 1597307741000, "DiskUsed[node2]": 2000, "CPU[node2]": 2}
{"timestamp": 1597307801000, "DiskUsed[node1]": 1000, "CPU[node1]": 1}
{"timestamp": 1597307801000, "DiskUsed[node2]": 2000, "CPU[node2]": 2}
```



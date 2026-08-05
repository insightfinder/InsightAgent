# InsightAgent: LogFileReplay-csv
Agent Type: LogFileReplay
Platform: Linux, Python 3.7

InsightAgent supports replay mode of csv log files in which the data from the csv file is read and sent to insightfinder server. A sample log file is as follows:
- The csv file contains rows of log data, each row is a log entry of the original log.
- The agent configuration requires a column for the instance id and a column for the timestamp which must be present for all log entries.  The rest of the columns of data is sent as a json formatted log entry to InsightFinder.  There is also an optional field to remove a column of data from being sent. 
- The `data_format` config option (`csv` section) controls how rows are sent: `log` (default) sends each row as a raw log event via `/api/v1/customprojectrawdata`; `metric` sends the remaining columns as numeric metric values (one instance/timestamp per row) via `/api/v2/metric-data-receive`, matching the metric payload format used by other InsightFinder streaming agents.

``` 
1) Copy config.ini.template to config.ini
2) Fill out config.ini required fields 
3) pip install -r requirements
4) python3 send_csv_data_py3.py
```
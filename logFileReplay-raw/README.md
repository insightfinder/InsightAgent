# InsightAgent: LogFileReplay-raw
Agent Type: LogFileReplay
Platform: Linux, Python 3.7

InsightAgent supports replay mode of raw log files in which the data from the log file is read and sent to insightfinder server. A sample log file is as follows:
- Each line of the log file requires a timestamp
- The agent configuration requires an instance_name field for the log file and a regex to parse out the timestamp from the log message. Each line is then sent as the data with the corresponding instance name and timestamp for that entry. 

``` 
1) Copy config.ini.template to config.ini
2) Fill out config.ini required fields 
3) pip install -r requirements
4) python3 send_data_py3.py
```

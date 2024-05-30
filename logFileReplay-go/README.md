# InsightAgent: LogFileReplay
Agent Type: LogFileReplay
Platform: Linux, Go

InsightAgent supports replay mode of raw log files in which the data from the log file is read and sent to insightfinder server.

``` 
1) Copy conf.d/config.ini.template to conf.d/config.ini
2) Fill out config.ini required fields 
3) Build the agent using the following command:
   GOOS=linux GOARCH=amd64 go build -o logfilereplay
4) Run the agent using the following command:
    ./logfilereplay -collector logfilereplay
```

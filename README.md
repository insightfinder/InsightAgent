# InsightAgent

To deploy agent in several machines:
1. Get deployment script:
```
wget --no-check-certificate https://raw.githubusercontent.com/xiaohuigu/InsightAgent/master/deployInsightAgent.py
```
2. Include IP address of all machines in hostlist.txt and enter one IP address per line.
3. To deploy run the following command:
```
python deployInsightAgent.py -n USER_NAME_IN_HOST -u
                             USER_NAME_IN_INSIGHTFINDER -k LICENSE_KEY -s
                             SAMPLING_INTERVAL_MINUTE -r
                             REPORTING_INTERVAL_MINUTE -t AGENT_TYPE
```
AGENT_TYPE: {proc,docker}


To get more details on the command, run 
```
python deployInsightAgent.py -h
```

To install agent in local machine:
```
./install.sh -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE
```



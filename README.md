# InsightAgent

###### To deploy agent on multiple hosts:

- Get the 3 deployment scripts from github using below commands:
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployInsightAgent.py
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/installInsightAgent.py
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/startcron.py
```
- Include IP address of all hosts in hostlist.txt and enter one IP address per line.
- To deploy run the following command:
```
python deployInsightAgent.py -n USER_NAME_IN_HOST
                             -u USER_NAME_IN_INSIGHTFINDER 
                             -k LICENSE_KEY 
                             -s SAMPLING_INTERVAL_MINUTE 
                             -r REPORTING_INTERVAL_MINUTE 
                             -t AGENT_TYPE
```
Currently, AGENT_TYPE can be *proc* or *docker*. 



###### To get more details on the command, run 
```
python deployInsightAgent.py -h
```

###### To install agent on local machine:
```
./install.sh -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE
```



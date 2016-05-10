# InsightAgent

###### To deploy agent on multiple hosts:

- Get the deployment script from github using below command:
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/deployInsightAgent.py
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

When the above script is run, if prompted for password, enter either the password or the name of the identity file along with file path.
Example: /home/insight/.ssh/id_rsa


###### To get more details on the command, run 
```
python deployInsightAgent.py -h
```

###### To install agent on local machine:
```
./install.sh -u USER_NAME -k LICENSE_KEY -s SAMPLING_INTERVAL_MINUTE -r REPORTING_INTERVAL_MINUTE -t AGENT_TYPE
```



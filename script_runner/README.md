# InsightAgent: Script Runner
Agent Type: Script Runner

Platform: Linux

This agent is used to trigger actions from the InsightFinder.

##### Pre-requisites:
1. Python: 3.3+
2. Network access to InsightFinder (port 443)
3. Network access from InsightFinder (port 4446)

### Deploy:
##### Configure Script Runner
This agent can either be run directly on the end node or on a management node that has access to the end node. 

1. Copy the [Script Runner package](script_runner.tar.gz) to the target system
2. Extract the agent
3. Install the python dependencies located in the requirements.txt

##### Configure the Action Repository 
The Action Repository is a directory that contains all of the scripts that can be run by the Script Runner.

##### Script Runner command line options
* ```-d / --directory```  Directory that contains the Action Repository (Defaults to current working directory)
* ```-w / --serverUrl```  IF Server to verify credentials (eg: https://app.insightfinder.com)
* ```-a / --auditLog``` Directory to store audit log (Defaults to current working directory)

##### Run the script runner
``` nohup python3 ./script_runner.py -d <Action Repository Directory> -w <InsightFinder URL> &```

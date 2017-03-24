##### Agent Master
The agent master can be used for seamless automatic deployment of agent codes in user's AWS instances without any manual intervention. It periodically scans for the machines that are available in the AWS accounts and installs the codes as new instances are added to the account. However, if there are some instances in the accounts for which the code shoud not be installed, they can be added to the exclude list which can be created in the agentMaster folder. The agent codes won't be installed in those instances.



##### To deploy agent master to auto-deploy agent in new AWS machines.

- Get the deployment script from GitHub using below command
```
wget --no-check-certificate https://raw.githubusercontent.com/amurark/InsightAgent/master/deployment/deployAgentMaster.sh
```
- Change permission for "deployAgentMaster.sh" to executable.
- Ensure all machines have the same login username and password.
- Add a new file 'excludeList.txt' with Private IPs (Each IP in a new line) of instances where you don't want to install the agents.
- In case of 'Key based Authentication', add the file to the same path.
- To deploy run the following command
- To force install agent on all instance, use -f flag.
```
./deployAgentMaster.sh  -n USER_NAME_IN_HOST
                        -i PROJECT_NAME_IN_INSIGHTFINDER
                        -u USER_NAME_IN_INSIGHTFINDER
                        -k LICENSE_KEY
                        -s SAMPLING_INTERVAL_MINUTE
                        -r REPORTING_INTERVAL_MINUTE
                        -t AGENT_TYPE
                        -f
```
##### To view command in terminal, run
```
./deployAgentMaster.sh
```

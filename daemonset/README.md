# Kubernetes Daemonset for insightfinder agent
Insightfinder agent can be deployed as a kubernetes daemonset using the configuration file "insightfinder.yaml".

The insightfinder docker image is found at the link: https://hub.docker.com/r/insightfinderagent/kubernetes-daemon-set/ .

The insightfinder.yaml configuration file takes care of downloading this docker image from docker hub.

Tested with kubernetes v1.2.0 on Centos 7.

Required docker version: 1.9.1 and later.

##### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/

- Sign in with the user credentials or sign up for a new account.

- Go to Settings and Register for a project under "Insight Agent" tab.

- Give a project name, select Project Type as "Private Cloud". When registered a project license key is sent to the registered email account.

##### Instructions to get deployment file

- Get the deployment file from github using below command:
```
wget --no-check-certificate https://raw.githubusercontent.com/insightfinder/InsightAgent/master/daemonset/insightfinder.yaml
```

##### Changes to be made in insightfinder.yaml
In the env part of insightfinder.yaml, the following parameters are required:

- INSIGHTFINDER_PROJECTNAME - name of the registered project with insightfinder.

- INSIGHTFINDER_PROJECTKEY - is available in "User Account Information" as license key. To go to "User Account Information", click the userid on the top right corner.

- INSIGHTFINDER_USERNAME - username used to login into insightfinder website.

- SAMPLING_INTERVAL - The rate at which the metrics are sampled.

- REPORTING_INTERVAL - The rate at which the collected metrics are reported to insightfinder.

Modify the insightfinder.yaml with the appropriate parameter values.

Example:
```
env:
   - name: INSIGHTFINDER_PROJECTNAME
    value: "projectname"
   - name: INSIGHTFINDER_PROJECTKEY
    value: "35f2a8a9ec0650afc93e4f308a8179f497e635f8"
   - name: INSIGHTFINDER_USERNAME
    value: "insightuser"
   - name: SAMPLING_INTERVAL
    value: "1"
   - name: REPORTING_INTERVAL
    value: "2"
   - name: AGENT
    value: "daemonset"
```

##### To deploy the daemonset containing insightfinder agent
```
kubectl create -f insightfinder.yaml
```

##### To check for status of the pods created:
```
kubectl get pods
```

##### Command to check available nodes
```
kubectl get nodes
```

##### Command to check for logs of a pod
```
kubectl describe pods <pod id>
```

##### To check raw data in host machines:
- Login into insightfinder kubernetes pod.
- In the InsightAgent-master/data folder, all raw data will be stored in csv files. csv files older than 5 days are moved to /tmp folder.
- To change the retention period, edit the InsightAgent-master/reporting_config.json and change the "keep_file_days" to the required value.

# Kubernetes Daemonset for insightfinder agent
Insightfinder agent can be deployed as a kubernetes daemonset using the configuration file "insightfinder.yaml".

##### Instructions to register a project in Insightfinder.com
- Go to the link https://insightfinder.com/

- Sign in with the user credentials or sign up for a new account.

- Go to Settings and Register for a project under "Insight Agent" tab.

- Give a project name, select Project Type as "Private Cloud". When registered a project license key is sent to the registered email account.

##### Changes to be made in insightfinder.yaml
In the env part of insightfinder.yaml, the following parameters are required:

- INSIGHTFINDER_PROJECTKEY - is available via email when a project is registered with insightfinder

- INSIGHTFINDER_USERNAME - username used to login into insightfinder website.

- SAMPLING_INTERVAL - The rate at which the metrics are sampled.

- REPORTING_INTERVAL - The rate at which the collected metrics are reported to insightfinder.

Modify the insightfinder.yaml with the appropriate parameter values.

Example:
```
env:
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

##### To run config file
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

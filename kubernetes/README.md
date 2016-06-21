# Kubernetes Daemonset for insightfinder agent

###### Changes to be made in insightfinder.yaml
In the env part, use the appropriate values given by insightfinder

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
```

###### To run config file
```
kubectl create -f insightfinder.yaml
```

###### To check for status of the pods created:
```
kubectl get pods
```

###### Command to check available nodes
```
kubectl get nodes
```

###### Command to check for logs of a pod
```
kubectl describe pods <pod id>
```

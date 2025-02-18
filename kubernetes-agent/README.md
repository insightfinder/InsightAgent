# InsightFinder Kubernetes Agent
## Overview
InsightFinder Kubernetes Agent is a tool to collect metrics and logs from Prometheus and Loki.

## Deploy
Deployment is done by helm chart.
See [README.md](https://github.com/insightfinder/charts/tree/main/charts/kubernetes-agent) for more details.

## Develop
### Build
```bash
go build
```

### Configure
Rename the example config files with file extension `.ini.example` under `conf.d` and edit it:
For example:
```bash
mv conf.d/pod-metrics.ini.example conf.d/pod-metrics.ini
vim conf.d/pod-metrics.ini
```

### Docker
#### Build
```bash
docker build . --platform linux/amd64 -t docker.io/insightfinderinc/kubernetes-agent:latest
```
#### Run
```bash
docker run -itd -v ./conf.d:/app/conf.d -v ./storage:/app/storage --name if-kubernetes-agent docker.io/insightfinderinc/kubernetes-agent:latest
```

### Kubernetes
1. Edit the `values.yaml`
2. Install using `helm` command
    ```bash
    # For fresh installation
    helm install --atomic -v values.yaml if-kubernetes-agent .
    
    # For upgrade
    helm upgrade --atomic -v values.yaml if-kubernetes-agent .
    ```
3. Check the pod running logs by
    ```bash
    kubectl logs -f statefulset/if-kubernetes-agent
    ```
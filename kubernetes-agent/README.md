# InsightFinder Kubernetes Agent
## Overview
InsightFinder Kubernetes Agent is a tool to collect metrics and logs from Prometheus and Loki.

It will send those data to InsightFinder server for anomaly detection. It is designed to run as a Kubernetes StatefulSet.

## Build
```bash
go build
```

## Configure
Copy the example config files under `conf.d` and edit it:
```bash
cp conf.d/loki.ini.example conf.d/loki.ini
cp conf.d/prometheus.ini.example conf.d/prometheus.ini
vim conf.d/loki.ini
vim conf.d/prometheus.ini
```

## Docker
### Build
```bash
docker build . -t docker.io/insightfinderinc/kubernetes-agent:latest
```
### Run
```bash
docker run -itd -v ./conf.d:/app/conf.d -v ./storage:/app/storage --name if-kubernetes-agent docker.io/insightfinderinc/kubernetes-agent:latest
```

## Kubernetes
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
    kubectl logs -f deployment/if-kubernetes-agent
    ```
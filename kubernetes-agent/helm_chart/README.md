# Kubernetes Agent Helm Chart

This Helm chart deploys a Kubernetes Agent which collects metrics and logs from a Kubernetes cluster and sends them to InsightFinder.

This agent requires **Prometheus** to be installed in the cluster to collect metrics and **Grafana Loki** to be installed in the cluster to collect logs.

## Prerequisites
- Prometheus (Required to collect metric data)
- Grafana Loki (Required to collect log data)
- Any valid storageClass in the cluster (Required to store the agent's data)
- Kubernetes 1.12+
- Helm 3.0+

## Configuration

The following table lists the configurable parameters of the Kubernetes Agent chart and their default values.

| Parameter                     | Description                                              | Default                                                |
|-------------------------------|----------------------------------------------------------|--------------------------------------------------------|
| `image`                       | The image of the agent                                    | `docker.io/insightfinderinc/kubernetes-agent:0.0.3`   |
| `prometheus.endpoint`         | The API endpoint for the Prometheus server               | `http://prometheus-server.monitor.svc.cluster.local`  |
| `prometheus.username`         | Prometheus BasicAuth Username (Optional)                 | `""`                                                   |
| `prometheus.password`         | Prometheus BasicAuth Password (Optional)                 | `""`                                                   |
| `loki.endpoint`               | The API endpoint for loki-gateway server                 | `http://loki-gateway.monitor.svc.cluster.local`       |
| `loki.username`               | Loki BasicAuth Username (Optional)                       | `""`                                                   |
| `loki.password`               | Loki BasicAuth Password (Optional)                       | `""`                                                   |
| `insightfinder.url`           | The URL of InsightFinder                                 | `https://app.insightfinder.com`                       |
| `insightfinder.user_name`     | Username for InsightFinder                               | `""`                                                   |
| `insightfinder.license_key`   | License key for that InsightFinder user                  | `""`                                                   |
| `insightfinder.system_name`   | The system created in InsightFinder website              | `""`                                                   |
| `projects`                    | List of projects that will be created in InsightFinder   | `[]`                                                   |

### Projects Configuration
Each `project` represents a data receiving target in InsightFinder and the project name needs to be unique.

Each entry in the `projects` list represents a data source that needs to collect data from.

Below is an example configuration for the `projects` list:

```yaml
projects:
  # Collect Node metrics and stream to `demo-node-metrics` project in InsightFinder.
  - name: demo-node-metrics
    type: metric
    target: node
  
  # Collect Pod metrics in namespace1 and stream to `demo-pod-metrics` project in InsightFinder.
  - name: demo-pod-metrics
    type: metric
    target: pod
    namespace: namespace1
  
  # Collect Pod logs in namespace2 and stream to `demo-pod-logs` project in InsightFinder.
  - name: demo-pod-logs
    type: log
    target: pod
    namespace: namespace2
    
  # Collect PVC metrics in namespace3 and stream to `demo-pvc-metrics` project in InsightFinder.
  - name: demo-pvc-metrics
    type: metric
    target: pvc
    namespace: namespace3
  
  # Collect events data from a namespace and stream to `demo-events` project in InsightFinder.
  - name: demo-events
    type: event
    target: namespace
    namespace: namespace4
```

### Project Entry Configuration Fields
| Field      | Description                                                             | Required                             | Available Values                  |
|------------|-------------------------------------------------------------------------|--------------------------------------|-----------------------------------|
| `name`     | The name of the project in InsightFinder. This name needs to be unique. | Yes                                  | Any string                        |
| `type`     | The type of data that will be collected.                                | Yes                                  | `metric`, `log` , `event`         |
| `target`   | The target from which data will be collected.                           | Yes                                  | `node`, `pod`, `pvc`, `namespace` |
| `namespace`| The Kubernetes namespace from which to collect data.                    | Yes (For Namespace-Scoped resources) | Any valid Kubernetes namespace    |

## Installation
After editing the `values.yaml` file, run the following command to install the agent:
```bash
helm install if-kubernetes-agent .
```

## Upgrade
After editing the `values.yaml` file, run the following command to upgrade the agent:
```bash
helm upgrade if-kubernetes-agent .
```

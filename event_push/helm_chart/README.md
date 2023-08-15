# InsightFinder Event Push Agent
This agent aims to get events from Insightfinder edge cluster and sends it to Insightfinder main cluster (app.insightfinder.com).

## Installation
We use helm chart to deploy our agent to kubernetes
```bash
cd helm_chart
vim values.yaml # Edit the configuration values

# For fresh installation
helm install --atomic if-event-push-agent .

# For upgrade
helm upgrade --atomic if-event-push-agent .
```
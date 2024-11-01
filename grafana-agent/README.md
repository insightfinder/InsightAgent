# InsightFinder Grafana Agent
This is an agent that can query data from Grafana and send it to InsightFinder.

## Build
```shell
go build .
```

## Configuration
Edit the configuration file
```shell
vim config.yaml
```

## Docker
```shell
docker build -t insightfinderinc/grafana-agent .
```
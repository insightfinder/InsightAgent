# Jaeger Agent
Jaeger Agent is trace data collector, it receives trace data from Jaeger server and send it to InsightFinder.

# How to build
```shell
go build -o jaeger-agent .
```

# How to run
```shell
# -c: config file path
# -w: worker number
./jaeger-agent -c config.yaml -w 10
```

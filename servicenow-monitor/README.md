# ServiceNow Instance Monitor

On each run, for every enabled ServiceNow instance the agent:
1. creates a test incident (`POST /api/now/table/incident`)
2. reads it back by `sys_id` (`GET /api/now/table/incident/{sys_id}`) and checks that it matches
3. sends `Success` (1/0) and `Failure` (0/1) to the InsightFinder metric project, using the instance name

It creates the InsightFinder project if it doesn't exist yet. Each run is a single pass and then exits, so schedule it with cron:

```
*/30 * * * * ubuntu cd /opt/insight-agent/servicenow-monitor && /bin/bash run_script.sh >> /opt/insight-agent/servicenow-monitor/run_script.log 2>&1
```

## Setup
```
cp configs/config.yaml.example configs/config.yaml   # fill in credentials
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o ServiceNowMonitor .
./run_script.sh
```

To monitor another instance, add an entry under `servicenow.instances`. To stop monitoring one without removing it, set `enabled: false`.
Create and read are each retried up to `max_retries` times (default 10, `retry_interval_sec` apart) before an instance is reported as failed.
Set `delete_after_check: true` to delete each test incident once it has been verified.

Alert in InsightFinder on metric `Success` with a negative threshold `< 1`.

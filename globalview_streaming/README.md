# GlobalView Streaming

Streams the InsightFinder **GlobalView anomaly timeline** for a system into an
InsightFinder **LOG project**.

For each timeline record the agent produces one log entry that:

- keeps the **instance name** and **component name** exactly as reported by GlobalView, and
- carries the **anomaly score** and **priority level** in the log payload.

## How it works

1. `GET {gv_url}/api/v2/timeline?systemName=&startTime=&endTime=&predict=` on the
   InsightFinder backend, authenticated with the `X-User-Name` / `X-License-Key`
   headers of the user that owns the GlobalView system.
2. Each record in `timelineList` / `consolidatedTimelineList` is mapped to an IF
   log raw-data entry:

   ```json
   {
     "eventId": 1700000000000,
     "tag": "<instanceName>",
     "componentName": "<componentName>",
     "data": {
       "anomalyScore": 87.5,
       "priorityLevel": "1",
       "priorityLevelName": "CRITICAL",
       "type": "...", "patternName": "...", "projectName": "...",
       "zoneName": "...", "status": "...", "isIncident": true,
       "isPrediction": false, "timestamp": 1700000000000, "endTime": 1700000060000
     }
   }
   ```

   `tag` is the instance, `componentName` preserves the component, and `data`
   holds the anomaly score + priority level (priority is emitted both as the raw
   `1`–`5` level and the readable name `CRITICAL`–`PLANNING`).
3. Entries are chunked (`chunk_size_kb`) and `POST`ed form-encoded to
   `{if_url}/api/v1/customprojectrawdata` with `agentType=LogStreaming`. The
   target LOG project is auto-created if it does not exist.

## Configuration

Copy `conf.d/config.ini.template` to `conf.d/config.ini` and fill in:

- `[globalview]` — `gv_url`, `gv_user_name`, `gv_license_key`, `gv_system_name`,
  and optionally `timeline_event_type`, `predict`, `timeline_source`
  (`raw` / `consolidated` / `both`), `query_time_offset_seconds`,
  `his_time_range`, `verify_certs`, proxies.
- `[insightfinder]` — the target LOG project (`user_name`, `license_key`,
  `project_name`, `system_name`, `if_url`, `run_interval`, `chunk_size_kb`, ...).
  Keep `project_type = log`.

Each run queries a sliding window of `run_interval` (live mode), or the fixed
`his_time_range` window if set. Schedule it with cron/systemd at the same
cadence as `run_interval`.

## Multiple systems / config files

Drop one `.ini` per system into `conf.d/` (e.g. `systemA.ini`, `systemB.ini`).
Each file has its own `[globalview]` + `[insightfinder]` sections, so different
GlobalView systems can stream to different target projects.

`-c` accepts either a single file or a directory:

- `-c conf.d/systemA.ini` — process just that file.
- `-c conf.d/` (the default) — process every `*.ini` in the directory, one after
  another. A config that is invalid or whose project can't be reached is logged
  and skipped; the remaining configs still run.

## Usage

```bash
pip install -r requirements.txt

# dry run over all conf.d/*.ini: fetch + parse, do not send
python3 send_gv_data.py -t -v

# stream every config in conf.d/
python3 send_gv_data.py

# stream a single config
python3 send_gv_data.py -c conf.d/systemA.ini
```

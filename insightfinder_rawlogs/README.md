# InsightFinder Raw Logs Agent

Copies raw log events from one InsightFinder instance into project(s) on another
InsightFinder instance, using the backend's log export API:

```
POST /api/external/v1/rawlogs
```

Typical use: replicate a set of log projects from a test/staging InsightFinder
server into a production one (or vice versa), on a schedule, with backfill
support for historical ranges.

## How it works

- `rawlogs_agent.py` performs **exactly one collection cycle** per invocation:
  it fetches a time window of log events from the source instance, maps each
  source project to its configured destination project, and sends the
  (optionally chunked) events to the destination via the standard
  `check-and-add-custom-project` / `customprojectrawdata` InsightFinder APIs.
  It then exits. There is no internal loop or scheduler in this script.
- `cron.py` re-invokes `rawlogs_agent.py` on `collection.interval_seconds` using
  APScheduler, for deployments that don't have their own scheduler. You can use
  a plain system crontab entry or a Kubernetes CronJob instead if you prefer -
  either works, since each run is self-contained.
- The live collection window is derived purely from wall-clock time, snapped to
  `interval_seconds` boundaries (see "Live window vs. replay" below). No
  progress/checkpoint file is stored anywhere; consecutive runs spaced
  `interval_seconds` apart tile exactly with no gaps or overlaps as long as they
  keep running on schedule.

## Quick start

```bash
cd insightfinder_rawlogs
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp config.yaml.template config.yaml
# edit config.yaml: source/destination URLs, credentials, and the
# source-project -> destination-project map

# One dry-run collection cycle (fetches + transforms, never sends):
python rawlogs_agent.py -c config.yaml --dry-run -v

# One real collection cycle (the live trailing window):
python rawlogs_agent.py -c config.yaml

# Run forever, once per collection.interval_seconds:
python cron.py -c config.yaml
```

## Configuration

See [config.yaml.template](config.yaml.template) for the full set of options
with inline comments. The important pieces:

- **`source`**: the InsightFinder instance to export logs *from*. Requests are
  authenticated with `X-User-Name` / `X-License-Key` headers. `source.projects`
  is the required 1:1 map of source project name -> destination project name;
  its keys are exactly what gets sent as `projectNameList` to the export API,
  and every fetched event is routed to its mapped destination project.
- **`destination`**: the InsightFinder instance to send logs *to*, and the
  usual project settings (`project_type`, `sampling_interval_seconds`,
  `chunk_size_kb`, etc.), analogous to the `[insightfinder]` section other
  agents in this repo use.
- **`collection`**: `interval_seconds` controls both the live window length and
  the scheduling cadence used by `cron.py`; `slice_seconds` bounds how large a
  single export request's time range can be (the export API is unpaged, so a
  wide window can return a very large response - split it into smaller slices
  if needed); `workers` controls how many slices are fetched/sent concurrently.
  Set `collection.replay` to back-fill an explicit historical range instead of
  the live window (see below).
- **`transform`**: `include_metadata: true` sends the full
  `{rawData, patternId, patternName, eventType}` object instead of just the
  `rawData` string; `instance_whitelist` / `instance_prefix` /
  `default_instance_name` control how the source `instanceName` maps to the
  destination instance name.

License keys can also be supplied via the `IF_SOURCE_LICENSE_KEY` /
`IF_DEST_LICENSE_KEY` environment variables instead of in the YAML file.

### Live window vs. replay

By default (`collection.align_to_interval: true`), each run fetches the
trailing `interval_seconds` window, ending `offset_seconds` before "now" and
floored to an `interval_seconds` boundary (e.g. every `:00`/`:10`/`:20`... for
a 600s interval). This means: as long as runs happen every `interval_seconds`,
each run's start exactly matches the previous run's end - a contiguous stream
with nothing persisted to disk. The tradeoff is that the window can close
slightly before the actual trigger time, since it's snapped back to the last
clock boundary rather than ending exactly when the agent ran.

Set `collection.align_to_interval: false` to instead end the window at the
exact trigger time (`now - offset_seconds`, no snapping). Use this when your
own scheduler (cron.py, system crontab, k8s CronJob) already fires precisely
every `interval_seconds` - runs still tile with no gaps or overlaps, but each
window ends right when the agent actually ran instead of at the last clock
boundary.

The tradeoff either way: if a run is skipped or fails outright, that window is never
picked up automatically (nothing recorded that it was missed). Use
`--replay-start` / `--replay-end` (or `collection.replay` in the config) to
re-run an explicit range as a one-off backfill - the failed run's log line
includes the exact window it was working on.

```bash
python rawlogs_agent.py -c config.yaml \
  --replay-start "2026-07-27 18:00:00" --replay-end "2026-07-27 18:10:00"
```

Timestamps may be given as epoch milliseconds or as `YYYY-MM-DD HH:mm:ss`
(interpreted as UTC for CLI overrides; `collection.replay.timezone` in the
config file for config-driven replays).

## Running with Docker

```bash
docker build -t insightfinder-rawlogs .
docker run -d \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -v $(pwd)/logs:/app/logs \
  insightfinder-rawlogs
```

The default command is `python cron.py`, which schedules
`rawlogs_agent.py` on `collection.interval_seconds`. For a one-off backfill
container instead, override the command:

```bash
docker run --rm \
  -v $(pwd)/config.yaml:/app/config.yaml \
  insightfinder-rawlogs \
  python rawlogs_agent.py --replay-start "2026-07-27 18:00:00" --replay-end "2026-07-27 18:10:00"
```

## Exit codes

`rawlogs_agent.py` exits:
- `0` - clean run, every slice succeeded.
- `1` - configuration error, or an unhandled exception before/around the run.
- `2` - the run completed but one or more time slices failed to export; see
  the `failed_slices` field in the final summary log line for the exact
  ranges to replay.

## Troubleshooting

- **`Missing required config value: ...`**: fill in the referenced field in
  `config.yaml`, or (for the license keys) set the corresponding
  `IF_SOURCE_LICENSE_KEY` / `IF_DEST_LICENSE_KEY` environment variable.
  * "source.license_key" or "IF_SOURCE_LICENSE_KEY env var" missing.
  * "source.projects (a source-project -> destination-project map) must
    have at least one entry".
- **403 from the export request**: the source `user_name`/`license_key` pair
  is not valid for that account - double check against the InsightFinder
  Account Profile page.
- **A project logged with an export error**: that single source project
  failed on the backend (see the logged message); the rest of the run
  continues unaffected.

# accessparks-telrad-agent

Agent for querying signal metrics from the AccessParks Telrad BreezeVIEW NMS via its REST NBI API and forwarding them to InsightFinder.

## Dependencies

```bash
pip install requests
```

## Setup

Copy `example.env` to `.env` and fill in your credentials:

```
ACCESSPARKS_TELRAD_URL=http://<host>:<port>
ACCESSPARKS_TELRAD_USERNAME=<username>
ACCESSPARKS_TELRAD_PASSWORD=<password>

ACCESSPARKS_JIRA_URL=https://<org>.atlassian.net
ACCESSPARKS_JIRA_USERNAME=<jira-email>
ACCESSPARKS_JIRA_API_TOKEN=<jira-api-token>

INSIGHTFINDER_BASE_URL=https://app.insightfinder.com
INSIGHTFINDER_USER_NAME=<username>
INSIGHTFINDER_LICENSE_KEY=<key>
INSIGHTFINDER_PROJECT_NAME=<project>
INSIGHTFINDER_SYSTEM_NAME=<system>
INSIGHTFINDER_SAMPLING_INTERVAL=5   # minutes
```

> **Password note:** If the password contains `&` or `!`, wrap it in single quotes in `.env` and all shell commands.

---

## What gets sent to InsightFinder

One **instance per eNB** under component `eNB-Telrad`. Instance names are pulled from Jira Assets (e.g. `Tus-TennisCourt-eNodeB200`).

| Metric        | Value                                                              |
|---------------|--------------------------------------------------------------------|
| `avg_ulrssi`  | Average `abs(UlRSSI)` in dBm across all UEs attached to the eNB    |

Only managed (reachable) eNBs produce data. Unreachable eNBs are logged as warnings and skipped.

---

## Scripts

### `send_metrics.py` — main loop

Polls BreezeVIEW and sends averaged eNB metrics to InsightFinder.

```bash
python3 send_metrics.py               # loop at configured interval
python3 send_metrics.py --once        # single tick then exit
python3 send_metrics.py --interval 2  # override interval (minutes)
python3 send_metrics.py --dry-run     # print payload, skip POST
python3 send_metrics.py --rebuild-map # force-refresh asset_map.json then exit
```

On first run (or if `asset_map.json` is missing or older than 7 days), it automatically builds or refreshes the Jira name map. During continuous operation the map is also refreshed in-loop when it goes stale, so instance names stay current without a restart.

### `build_asset_map.py` — Jira asset name map

Queries BreezeVIEW for device IPs and Jira Assets for matching device objects, then writes `asset_map.json`. Run manually after Jira asset renames or to pre-warm the map.

```bash
python3 build_asset_map.py            # build silently
python3 build_asset_map.py --print    # build and print result
```

**Matching strategy** (in priority order):

1. **DeviceName numeric suffix** — Jira `DeviceName="eNodeB200"` → BreezeVIEW device ID `200`. Stable even if management IP changes. IP is cross-verified; a `WARNING` is logged if the Jira IP disagrees with BreezeVIEW (indicates stale Jira data).
2. **management_ip** — fallback for assets whose DeviceName has no embedded ID.
3. **BreezeVIEW display name or device ID** — final fallback (e.g. `DeathValley-Oasis`, or bare `666`) with a `WARNING` log when no Jira record exists.

### `get_metrics.py` — raw metric fetch

Queries all eNBs and prints signal metrics. Standalone diagnostic tool.

```bash
python3 get_metrics.py                        # human-readable summary
python3 get_metrics.py --json-only            # JSON to stdout
python3 get_metrics.py --device 200           # single device
python3 get_metrics.py --json-only --output metrics.json
```

### `jira_assets.py` — Jira Assets API client

Library used by `build_asset_map.py`. Provides workspace discovery and AQL-based asset lookup by management IP.

### `insightfinder.py` — InsightFinder API client

Library used by `send_metrics.py`. Handles project/system creation and metric payload submission.

---

## API notes

- **Base URL:** `http://<host>:<port>/api`
- **Auth:** HTTP Basic Auth
- **Format:** XML
- **Device list:** Use `?select=name;address` — do NOT use `?shallow` (hangs, returns only 2 devices)
- **Deduplication:** Devices 666 and 667 share an IP; `get_metrics.py` deduplicates by IP automatically

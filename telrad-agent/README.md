# accessparks-telrad-agent

Agent for querying signal metrics from the AccessParks Telrad BreezeVIEW NMS via its REST NBI API and forwarding them to InsightFinder.

## Dependencies

```bash
pip install requests
```

## Setup

Copy `example.env` to `.env` and fill in your credentials:

```
# eNB metrics via REST NBI — disabled by default (see "eNB metrics" section below).
# ACCESSPARKS_TELRAD_URL/USERNAME/PASSWORD are only required when this is "true".
ENABLE_ENB_METRICS=false
ACCESSPARKS_TELRAD_URL=http://<host>:<port>
ACCESSPARKS_TELRAD_USERNAME=<username>
ACCESSPARKS_TELRAD_PASSWORD=<password>

ASSET_CACHE_URL=http://<asset-cache-host>
ASSET_CACHE_API_KEY=<asset-cache-api-key>

INSIGHTFINDER_BASE_URL=https://app.insightfinder.com
INSIGHTFINDER_USER_NAME=<username>
INSIGHTFINDER_LICENSE_KEY=<key>
INSIGHTFINDER_PROJECT_NAME=<project>
INSIGHTFINDER_SYSTEM_NAME=<system>
INSIGHTFINDER_SAMPLING_INTERVAL=5   # minutes

# Optional — CPE-side KPIs via BreezeVIEW CLI (SSH). Requires sshpass on the host
# (see "BreezeVIEW CLI" section below). Leave blank to send eNB metrics only.
BREEZEVIEW_CLI_HOST=<breezeview-cli-ip>
BREEZEVIEW_CLI_PORT=9383
BREEZEVIEW_CLI_USER=<cli-username>
BREEZEVIEW_CLI_PASSWORD=<cli-password>
BREEZEVIEW_CLI_SNAPSHOT_TIMEOUT=240   # seconds to wait for a kpi-snapshot to finish
BREEZEVIEW_CLI_POLL_INTERVAL=10       # seconds between snapshot status polls
```

> **Password note:** If the password contains `&` or `!`, wrap it in single quotes in `.env` and all shell commands.

---

## What gets sent to InsightFinder

Wire format matches `getmessages_zabbix.py`'s device-inventory convention: the instance identifier (`in`) and all metadata (`cn`, `idn`, `i`, `z`) come from the AccessParks asset-cache server (a REST cache of Jira Assets / device-inventory data), packed into a single JSON-stringified `im` field alongside `in` and `dit` — not sent as direct `cn`/`z`/`i` keys.

**Instance identifier (`in`) priority**, per eNB/CPE:
1. MAC address (device inventory) → `MAC <mac>`
2. Serial number (device inventory) → `SERIAL <serial>`
3. Object key / Jira key (device inventory) → `JIRAKEY <object_key>`
4. Native fallback (no inventory match) — CPEs fall back to `SERIAL <own serial>` (BreezeVIEW's own serial), then IMSI; eNBs fall back to the BreezeVIEW device name, then bare device ID (eNBs have no native MAC/serial to prefix).

A device with no inventory match still sends data under its native fallback identifier — it is never skipped — logged as a `WARNING`.

**`im` metadata** (all optional, included only when non-empty):
- `cn` — component name: device-inventory `manufacturer-device_class`, else the static `eNB-Telrad` / `CPE-Telrad` default
- `idn` — native display name: BreezeVIEW's own `device_name` (eNB) or serial/IMSI (CPE) — always the *native* identity, regardless of inventory match
- `i` — IP address: device-inventory `ip_address`; eNBs fall back to BreezeVIEW's own `device_ip` if inventory has none; CPEs do **not** fall back to their own WAN IP, since those are DHCP'd/NAT'd and can be shared or stale
- `z` — zone: device-inventory `venue` only, no native fallback

### eNB metrics — component `eNB-Telrad` (fallback) — **disabled by default**

Set `ENABLE_ENB_METRICS=true` to enable. When enabled, make sure `ACCESSPARKS_TELRAD_URL` points at the REST NBI port (see "API notes" below) — **not** the `BREEZEVIEW_CLI_PORT` SSH port; they are different services on the same host and pointing at the wrong one fails every tick with a connection error.

One **instance per eNB**.

| Metric        | Value                                                              |
|---------------|--------------------------------------------------------------------|
| `avg_ulrssi`  | Average `abs(UlRSSI)` in dBm across all UEs attached to the eNB    |

Only managed (reachable) eNBs produce data. Unreachable eNBs are logged as warnings and skipped.

### CPE metrics — component `CPE-Telrad` (fallback, optional)

If `BREEZEVIEW_CLI_*` is configured, one **instance per CPE**, matched by serial number (then WAN IP fallback) against the device inventory. Only `online` CPEs produce data.

| Metric   | Value                          |
|----------|---------------------------------|
| `UlMCS`  | Uplink MCS index, if present     |
| `DlMCS`  | Downlink MCS index, if present   |
| `UlCINR` | Uplink CINR (`abs()` dB), if present |
| `UlRSSI` | Uplink RSSI (`abs()` dBm), if present |

Each field is sent individually as `abs(value)` (no averaging); a CPE's payload only includes the fields present in its KPI record.

These are the only CPE-side signal quality metrics available for Telrad — the REST NBI only exposes eNB-side readings. A CLI collection failure never blocks eNB metrics for that tick (logged as a warning) when eNB collection is enabled.

### Why CPE collection can take minutes per tick

`collect_cpe_metrics()` triggers (or reuses) BreezeVIEW's own network-wide `kpi-snapshot` — the appliance itself polls every CPE and only reports back once done, or once `BREEZEVIEW_CLI_SNAPSHOT_TIMEOUT` (default 240s) is hit. This is server-side latency, not something this agent's polling loop can speed up; `BREEZEVIEW_CLI_POLL_INTERVAL` (default 10s) only controls how often we *ask* whether it's done, not how fast BreezeVIEW actually collects. Lowering it detects completion a few seconds sooner on average, at the cost of more frequent SSH connections to an appliance that's already busy mid-collection — not a change to make casually. Disabling the (broken/unneeded) eNB REST NBI call by default removes one guaranteed-to-fail network round trip per tick, which was the one avoidable cost in the loop.

---

## Scripts

### `send_metrics.py` — main loop

Polls BreezeVIEW and sends averaged eNB metrics to InsightFinder.

```bash
python3 send_metrics.py               # loop at configured interval
python3 send_metrics.py --once        # single tick then exit
python3 send_metrics.py --interval 2  # override interval (minutes)
python3 send_metrics.py --dry-run     # print payload, skip POST
```

Per-device and per-CPE asset mappings are cached in memory: the asset cache is only queried when a new device_id/serial number appears or when a previously unmapped entry's 1-hour retry window expires, and eNB + CPE candidates are resolved via a single combined asset-cache lookup per tick (not two separate round-trips). No `asset_map.json` is written to disk.

### `build_asset_map.py` — asset resolution helper

Library used by `send_metrics.py` (for eNBs and CPEs) and `get_cli_metrics.py` (for CPEs, lazily imported — see below). Provides `resolve_subset()` (fetches assets then resolves) and `resolve_with_assets()` (resolves against an already-fetched asset list, letting a caller share one asset-cache query across multiple device-ID subsets) to map a set of BreezeVIEW device IDs or CPE serial numbers to `{label, venue, component_name, ip, mac, object_key, serial}` device-inventory records (see "What gets sent to InsightFinder" above for how `send_metrics.py` turns these into `in`/`im`). Both take a `match_by` parameter (`"ip"` for eNBs, `"serial"` for CPEs) selecting the matching strategy below.

**Matching strategy for eNBs** (`match_by="ip"`, in priority order):

1. **device_name numeric suffix** — asset `device_name="eNodeB200"` → BreezeVIEW device ID `200`. Stable even if management IP changes. IP is cross-verified; a `WARNING` is logged if the asset's IP disagrees with BreezeVIEW (indicates stale asset data).
2. **ip_address** — fallback for assets whose device_name has no embedded ID.
3. **BreezeVIEW display name or device ID** — final fallback (e.g. `DeathValley-Oasis`, or bare `666`) with a `WARNING` log when no asset record exists.

In all cases, the resolved asset's `label` (only the **first whitespace-delimited token** of its Jira name — a trailing note or MAC address appended by Jira's naming pattern, e.g. `"DVR-ResPEC44 is this PEC104 or PEC40 or TS44-ue"` or `"DVR-?h-ue 6C:AD:EF:15:B1:B9"`, is dropped upstream in `jira_assets._to_asset()`) is used only to detect whether a match was found and for collision logging — the instance name itself comes from the asset's `mac`/`serial`/`object_key` (see above), not from `label`.

**Matching strategy for CPEs (`match_by="serial"`, in priority order):**

1. **serial number** — the CPE's `serial_number` against an asset's `serial_number` field. A serial match is authoritative, so the found label (already trimmed to its first token) is used as-is (unlike the eNB path, which discards "?"-containing placeholder labels).
2. **WAN IP fallback** — tried only when serial doesn't match, against the CPE's current `ip-wan`. Weaker than serial: WAN IPs are DHCP'd/NAT'd and can be shared or stale, so a match here can point at the wrong physical device — every WAN-IP match is logged as a `WARNING` (not silently trusted like a serial match).
3. **BreezeVIEW's own serial number, then IMSI** — final fallback (as the instance identity) with a `WARNING` when no asset record matches by either tier above.

`send_metrics.py` caches CPE mappings in memory the same way as eNBs (keyed by serial number); `get_cli_metrics.py --no-jira` skips this lookup entirely.

### `get_metrics.py` — raw metric fetch (REST NBI)

Queries all eNBs and prints signal metrics. Standalone diagnostic tool.

```bash
python3 get_metrics.py                        # human-readable summary
python3 get_metrics.py --json-only            # JSON to stdout
python3 get_metrics.py --device 200           # single device
python3 get_metrics.py --json-only --output metrics.json
```

### `get_cli_metrics.py` — raw CPE KPI fetch (BreezeVIEW CLI)

Queries CPE-side KPIs (RSRP/SINR/RSRQ/CINR/rates) via the BreezeVIEW CLI over SSH. Standalone diagnostic tool — see "BreezeVIEW CLI" below. Each CPE is also matched against the asset cache (best-effort, by serial number) and the resolved name is shown alongside the serial number as its own `jira=` field in the summary (and a `jira_asset_name` key in JSON output); left empty if unresolved, asset-cache config is missing, or the `requests` package isn't installed. `build_asset_map`/`jira_assets` (and `requests`) are only imported when this lookup actually runs, so the script has no import-time dependency on them.

```bash
python3 get_cli_metrics.py                        # human-readable summary (online CPEs only)
python3 get_cli_metrics.py --all                  # include offline CPEs in the summary
python3 get_cli_metrics.py --json-only            # JSON to stdout (all CPEs, online and offline)
python3 get_cli_metrics.py --skip-collection      # read last snapshot, don't trigger a new one
python3 get_cli_metrics.py --json-only --output cpe_metrics.json
python3 get_cli_metrics.py --no-jira              # skip asset name lookup
```

### `jira_assets.py` — asset-cache client

Library used by `build_asset_map.py`, `send_metrics.py`, and `get_cli_metrics.py` (the latter imports it lazily, only when resolving CPE asset names). Provides `fetch_assets()`, which looks up devices by IP and/or serial number against the AccessParks asset-cache server (a REST cache of Jira Assets device data, auth via `X-API-Key`).

### `insightfinder.py` — InsightFinder API client

Library used by `send_metrics.py`. Handles project/system creation and metric payload submission.

---

## API notes

- **Base URL:** `http://<host>:<port>/api`
- **Auth:** HTTP Basic Auth
- **Format:** XML
- **Device list:** Use `?select=name;address` — do NOT use `?shallow` (hangs, returns only 2 devices)
- **Deduplication:** Devices 666 and 667 share an IP; `get_metrics.py` deduplicates by IP automatically

## BreezeVIEW CLI (CPE-side KPIs)

`get_cli_metrics.py` is the only source for CPE-side signal quality (RSRP/SINR/RSRQ/CINR) — see `docs/BreezeVIEW - How to Get UE(s) KPIs via BreezeVIEW CLI.md` for the full protocol.

- **Access path:** reached over SSH from wherever this agent runs; `sshpass` and `python3` must be present there (no extra Python dependency — plain `subprocess` + SSH).
- **Interactive REPL:** the CLI requires a PTY (`ssh -tt`); commands are piped via stdin and the session ends on `exit`. `| nomore` disables the pager.
- **Async, network-wide snapshot:** `show ... kpi-snapshot status` → `request ... kpi-snapshot start` → poll status until `finish-ok` → `show ... kpi-snapshot cpe-kpi`. Only one collection can run at a time.
- **Command policy — metrics only, never modify:** the only commands ever sent are `show ...` and the exact `request cpe-view cpes kpi-snapshot start`. This is enforced in code (`get_cli_metrics._run_cli`'s allowlist), not just by convention. No config/set/commit and no `kpi-snapshot {empty,cancel}` command is ever issued.

# accessparks-device-metadata

Reconciles AccessParks devices across three sources of truth — ten vendor
controllers (UniFi, UISP, Mimosa, Tarana, Baicells, NetExperience, Positron,
Cambium, Telrad, Ruckus), Jira Assets, and Zabbix — and streams the result to
InsightFinder as log data, so a device missing from Jira or Zabbix (or
disagreeing on IP/MAC) becomes queryable and alertable there.

For every device a controller reports, it's looked up in Jira Assets and in
Zabbix; one InsightFinder log record is emitted per device with what was
found (or not) in each place:

```json
{
  "controller": {"name": "UniFi", "device_name": "LRF-Clubhouse-AP", "ip": "10.194.153.12", "mac": "0C:EA:14:4F:61:E1", "serial": "F4E2C6A1B3D9"},
  "jira":       {"id": "IHS-68691", "device_name": "LRF-Clubhouse-AP", "ip": "10.194.153.12", "mac": "0C:EA:14:4F:61:E1", "zabbix_host_id": "44598", "match_method": "controller.mac"},
  "zabbix":     {"id": "44598", "device_name": "LRF-Clubhouse-AP", "match_method": "jira.id"}
}
```

Every key is always present. A device that isn't in Jira or Zabbix — or one
whose controller doesn't report an IP or MAC — gets `""` rather than a
dropped key, so "missing from Jira" stays queryable and alertable in
InsightFinder instead of vanishing from the record.

`match_method` names **the field of this record whose value was used as the
lookup key**, so you can see exactly what was matched on instead of
inferring it. Identifiers are tried strongest-first and the first hit wins:

| `jira.match_method` | Looked up | Matched against |
| --- | --- | --- |
| `controller.mac` | the controller's MAC | Jira `mac_address` |
| `controller.serial` | the controller's serial | Jira `serial_number` |
| `controller.device_name` | the controller's device name | Jira `name` |

| `zabbix.match_method` | Looked up | Matched against |
| --- | --- | --- |
| `jira.id` | the Jira device key, e.g. `IHS-68691` | the Zabbix host tag `jira_device_key` |
| `jira.zabbix_host_id` | the hostid Jira records | that Zabbix `hostid`, if it still exists |
| `controller.device_name` | the controller's device name | Zabbix host / visible name |
| `controller.ip` | the controller's IP | Zabbix primary-interface IP |

Note the two Zabbix fallbacks key off the **controller**, not Jira — only
the first two tiers use anything Jira supplied. Every field a `match_method`
can name is present in the record, which is why `controller.serial` and
`jira.zabbix_host_id` are emitted even though nothing else reads them.

Jira matching is whitespace-insensitive: a Jira label is tried exactly
(case-insensitively) first, then with all whitespace stripped, so the
controller's `DKOA-DC723-RN` matches Jira's `DKOA-DC 723-RN` and a
controller name with a stray leading space still matches. See
`src/jira_assets.py` for why that requires matching locally against
`GET /devices/export` rather than per-device registry lookups.

Whitespace is ignored when *finding* and *comparing* devices, not when
reporting them: every value in the record is shipped exactly as its source
holds it, whitespace included, so the record stays a faithful picture of
what each system actually contains. InsightFinder's ingestion rules
constrain the **instance name**, not the log payload — that's handled by
`sanitize_instance_name` (no space, `,`, `_`, `@`, `#`, `:`), which is the
only place a value is rewritten to satisfy them.

The `ip≠`/`mac≠` flags likewise compare whitespace-insensitively, so a
device matched despite stray spacing isn't then reported as disagreeing with
itself — Jira holds MACs recorded as `" 48:A9:8A:9B:EA:C9"` and
`"48:A9:8A:B6: E7:8A"`, which are the same addresses their controllers
report, not different ones.

This is a cron job, not a daemon — one pass per invocation, no internal loop.

## Requirements

- Python 3.9+
- `sshpass` (for the Zabbix/Telrad SSH tunnel scripts)
- Chromium via Playwright — **Cambium only**

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium   # one-time — required for Cambium only
```

## Configure

```bash
cp .env.example .env
```

`.env.example` ships a real, working value for everything that isn't an
actual credential (portal URLs, ports, scoping IDs, rate limits) — only
passwords/keys/tokens need filling in. It's grouped per vendor with a
comment on anything non-obvious; skim it before your first run.

Always required:

| Variable | Purpose |
|---|---|
| `INSIGHTFINDER_URL`, `INSIGHTFINDER_USER_NAME`, `INSIGHTFINDER_LICENSE_KEY`, `INSIGHTFINDER_PROJECT_NAME` | Where/how to send log data |
| `JIRAASSET_BASE`, `JIRAASSET_API_KEY` | AccessParks Asset Registry (Jira Assets mirror) |
| `ZABBIX_URL`, `ZABBIX_USER`, `ZABBIX_PASSWORD` | Zabbix, reached via the SSH tunnel below |

A controller with no credentials set in `.env` is **skipped with a warning**,
not treated as an error — only what's configured actually runs.

`INSIGHTFINDER_SAMPLING_INTERVAL` is in **hours** (default `1`) but only
affects the InsightFinder project's value at *creation* time — the real
cadence is whatever cron entry runs `main.py`. `INSIGHTFINDER_SET_COMPONENT`
(default `true`) includes each record's source controller as `componentName`.

## Run

Open the Zabbix SSH tunnel first — every run needs it, even if Zabbix isn't
the controller you're testing:

```bash
./scripts/zabbix-tunnel.sh &
```

Then:

```bash
python main.py                                  # every configured controller, resolve, send
python main.py --controllers unifi               # narrow to a subset (comma-separated)
python main.py --exclude-controllers baicells    # run all except these (comma-separated)
python main.py --dry-run                         # resolve + print a table, send nothing
python main.py --table                           # print the table AND send
python main.py --json                            # print raw log records instead of a table
python main.py --limit 10                        # cap devices per controller (quick checks)
```

`--table` output, e.g.:

```
CONTROLLER  DEVICE             CTRL IP        CTRL MAC           JIRA KEY   JIRA NAME          JIRA IP        JIRA MAC           JIRA VIA       ZBX ID  ZBX NAME           ZBX VIA          STATUS
UniFi       LRF-Clubhouse-AP   10.194.153.12  0C:EA:14:4F:61:E1  IHS-68691  LRF-Clubhouse-AP   10.194.153.12  0C:EA:14:4F:61:E1  MAC address    44598   LRF-Clubhouse-AP   Jira device key  ok
Tarana      DKOA-DC723-RN      172.27.68.142  04:F1:7D:06:11:34  IHS-67507  DKOA-DC 723-RN     10.195.96.129 ≠                   Device name    43171   DKOA-DC 723-RN     Jira device key  ip≠
UniFi       U6+                10.194.192.20  0C:EA:14:E3:D5:05  -          -                  -              -                  -              -       -                  -                no-jira, no-zabbix

8410 devices | jira: 7288 matched, 1122 missing | zabbix: 7697 matched, 713 missing | ip mismatch: 449 | mac mismatch: 864
```

The summary line prints on every run — it's the actual deliverable. With
`--json`, stdout stays pure, pipeable JSON (`python main.py --json | jq .`);
the summary is logged instead of printed to stdout in that mode.

### Cron

```cron
# every hour, tunnel + agent (adjust paths and venv)
0 * * * * pgrep -f zabbix-tunnel.sh >/dev/null || /path/to/scripts/zabbix-tunnel.sh & sleep 5
5 * * * * cd /path/to/accessparks-device-metadata && .venv/bin/python main.py >> agent.log 2>&1
```

### Example EC2 deployment

Deployed at `/home/ec2-user/accessparks-device-metadata/` with the venv at
`venv/` (not `.venv/`). This box is **not** the Zabbix-Agent-Server box
whitelisted for the Telrad BreezeVIEW CLI, so **both** tunnels — Zabbix
(which also carries Positron) and Telrad — must run here.

Both tunnels are started manually, once, as long-lived background
processes (not managed by cron):

```bash
cd /home/ec2-user/accessparks-device-metadata
nohup ./scripts/zabbix-tunnel.sh >> tunnel-zabbix.log 2>&1 &
disown
nohup ./scripts/telrad-breezeview-cli-tunnel.sh >> tunnel-telrad.log 2>&1 &
disown
```

`nohup` keeps them alive after the SSH session ends; `disown` detaches them
from the shell's job table. Verify both survived a reconnect with:

```bash
pgrep -f zabbix-tunnel.sh
pgrep -f telrad-breezeview-cli-tunnel.sh
```

Only the agent itself is on cron (`crontab -e -u ec2-user`):

```cron
0 * * * * cd /home/ec2-user/accessparks-device-metadata && /home/ec2-user/accessparks-device-metadata/venv/bin/python main.py >> /home/ec2-user/accessparks-device-metadata/agent.log 2>&1
```

Tradeoff: since the tunnels aren't cron-supervised, a dropped SSH session,
reboot, or OOM kill won't self-heal — check `agent.log` for connection
failures and relaunch the affected tunnel by hand. For self-healing,
migrate the tunnels to systemd services with `Restart=always` instead of
raw `nohup`.

## Important notes

- **SSH tunnel required before any run.** `scripts/zabbix-tunnel.sh` reads
  `ZABBIX_TUNNEL_*` from `.env` and connects via `sshpass -e`, so the
  password never appears in `ps`/shell history. It forwards **both** Zabbix
  and Positron over the same connection (`POSITRON_TUNNEL_*`) — no separate
  script needed for Positron.
- **A partial picture is never silently published as "device is missing."**
  If every controller returns zero devices, the whole run aborts. So does a
  Zabbix login/`host.get` failure, or a failed Jira Assets
  `GET /devices/export` — a network problem is never shipped to
  InsightFinder as a fleet-wide Jira or Zabbix gap. A device whose live
  Zabbix tag lookup errors is reported as unresolved and counted separately,
  never as missing.
- **An ambiguous identifier is refused, not guessed.** Jira has MACs and
  serials that appear on more than one device (placeholders like `-` and
  `n/a`, but also real duplicates left behind by device replacements). Such
  a value can't identify either device, so it's disabled as a match key and
  matching falls through to the next identifier — which is how
  `LKLV-Cabin11-GN` now matches its own asset instead of the `-GAM` sharing
  its MAC. The run logs how many devices hit one, so the Jira data can be
  cleaned up.
- **UniFi** — the Site Manager API key must be a console-owner key; a
  restricted/invited key gets `403 insufficient permissions` on the Cloud
  Connector proxy paths.
- **Cambium** — there's no password-based REST API for this product, so its
  controller drives the real login page with Playwright to lift session
  cookies. It's the most fragile controller here by construction; a broken
  login degrades to "skipped" in the run summary, never an aborted run.
- **Telrad** — implements **CPEs only**, over SSH to the BreezeVIEW CLI
  (port 9383 — a different service from the REST NBI's port 9382 on the same
  host); requires `sshpass`. Only `online` CPEs appear in a snapshot, and
  Telrad CPEs do not expose a MAC address.
- **Baicells** — rate-limited to 20 requests/min account-wide; IP requires a
  per-device call cached to `.cache/baicells_ips.json` and capped per run by
  `BAICELLS_ENRICH_BUDGET_SECONDS` — a large fleet fills in IPs over several
  runs, so `ip=""` on a given run is expected, not an error.
- **Tarana** — `TARANA_REGION_IDS` is pinned to `33,1203,1202`; leaving it
  blank falls back to runtime discovery, which is known to miss regions. The
  device-search response carries `macAddress` even though `tarana-agent`'s
  Go `Device` struct omits it, so Tarana devices do reconcile by MAC.
- **NetExperience** — `NETEXPERIENCE_BASE_URL` is the tenant API host, *not*
  `www.netexperience.com`.
- **Positron** — reached through the same SSH tunnel as Zabbix. Lists two
  disjoint populations: CPE endpoints (MAC, no IP) and GAM headend units
  (IP, no MAC).
- **Ruckus** — no tunnel needed, reachable directly at `RUCKUS_URL`.
  `RUCKUS_API_VERSION` is pinned to `v11_1`. Lists APs only.

## Adding a controller

Each vendor is one module implementing `Controller` (`src/controllers/base.py`):

```python
class Controller(Protocol):
    name: str
    def list_devices(self) -> list[ControllerDevice]: ...
```

Add the module under `src/controllers/`, then register a factory in
`src/controllers/__init__.py`'s `CONTROLLER_FACTORIES`. The "run everything"
default picks it up automatically — no other orchestration change needed. A
factory should return `None` when its required `.env` credentials are
absent, so an unconfigured controller is skipped with a warning instead of
failing the run.

## Field mappings

| Vendor | List call | name | ip | mac | serial |
|---|---|---|---|---|---|
| UniFi | `/v1/sites` (traversal only) → `/v1/connector/consoles/{hostId}/proxy/network/api/s/{slug}/stat/device` | `name` | `ip` | `mac` | `serial` |
| UISP | `/nms/api/v2.1/devices` | `identification.name` | `ipAddress` (strip `/cidr`) | `identification.mac` | `identification.serialNumber` |
| Mimosa | `/{network_id}/devices/?pageNumber&pageSize` | `friendlyName` | `ipAddress` | `macAddress` | `serialNumber` |
| Tarana | `/api/nqs/v1/regions/devices/search` | `hostName` | `ip` | `macAddress` | `serialNumber` |
| Baicells | `/device/group` → `/device/query` per group → `/cpe/infos/{serial}` for ip | `host_name` | `ipAddress` (per-device call) | `mac_address` | `serial_number` |
| NetExperience | `/portal/cmap/customer/forSp` → `/portal/equipment/forCustomer` → `/portal/status/forEquipment` for ip | `name` | `details.reportedIpV4Addr` (3rd call) | `baseMacAddress.addressAsString` | `serial` |
| Cambium | `{base}/tree/devices` | `cfg.name` → `name` | `net.wan` → `net.ip` | `mac` | `sn` |
| Telrad (CPEs only) | BreezeVIEW CLI `kpi-snapshot` over SSH | serial (no separate name) | `ip-wan` | — | `serial_number` |
| Positron endpoints | `/api/v1/endpoint/list/all` | `confEndpointName` → `confUserName` | — | `macAddress` | `serialNumber` |
| Positron devices (GAMs) | `/api/v1/device/list` | `name` | `ipAddress` (excl. `0.0.0.0`) | — | `serialNumber` |
| Ruckus | `POST /wsg/api/public/{version}/query/ap` | `deviceName` | `ip` | `apMac` | `serial` |

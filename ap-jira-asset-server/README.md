# Asset Registry Service

A standalone HTTP service that maintains a full local replica of Jira Assets (32,000+ devices) in a SQLite database and exposes a REST API for querying device data by any identifier.

Built specifically for internal services that need fast device lookups without hitting the Jira API on every request.

---

## Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Web framework | FastAPI | async, auto-docs at `/docs` |
| Database | SQLite (WAL mode) | embedded, no server, single file |
| ORM | SQLAlchemy async | upserts, recursive CTE queries |
| Scheduler | APScheduler | nightly auto-sync, cron-configurable |
| Jira source | Atlassian Cloud Assets API | workspace-scoped AQL endpoint |

---

## Setup

### 1. Install dependencies

```bash
cd asset-registry-service
pip install -e .
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Secret key clients must send in the X-API-Key request header
API_KEY=your_secret_api_key

JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=your_atlassian_api_token
JIRA_WORKSPACE_ID=469b3811-1dbc-49e8-961c-3155b8673b73

# Path to the SQLite database file (created automatically on first run)
DATABASE_PATH=./assets.db

# Cron schedule for automatic sync (default: 2am daily)
SYNC_CRON=0 2 * * *
```

### 3. Start the server

```bash
uvicorn src.main:app --host 0.0.0.0 --port 80
```

The database tables are created automatically on startup. Interactive API docs are available at `http://localhost:8080/docs`.

### 4. Run the first sync

```bash
curl -X POST http://localhost:8080/sync
```

This returns immediately (`202 Accepted`). The sync runs in the background — 32k devices typically takes 5–10 minutes depending on Jira API rate limits. Watch progress:

```bash
curl http://localhost:8080/sync/status
```

---

## Database Schema

SQLite file at `DATABASE_PATH` (default `./assets.db`). Three tables.

### `device_models`

Synced from Jira Assets objecttype **Model** (objecttype ID 13).

| Column | Type | Indexed | Description |
|--------|------|---------|-------------|
| `id` | TEXT PK | — | Jira object ID (e.g. `49719`) |
| `name` | TEXT | ✓ | Model name (e.g. `XV2-21X (indoor)`) |
| `manufacturer` | TEXT | — | Manufacturer name (e.g. `Cambium`) |
| `device_class` | TEXT | ✓ | Device class (e.g. `Wifi.Indoor`, `Backhaul`) — Jira attr 329 |
| `classtype` | TEXT | — | Lowercase class variant (e.g. `wifi.indoor`) — Jira attr 588 |
| `zabbix_model_monitoring_mode` | TEXT | — | e.g. `icmp+snmp`, `icmp` — Jira attr 457 |
| `zabbix_model_snmp_template_id` | TEXT | — | Zabbix SNMP template ID — Jira attr 281 |
| `meta` | JSON | — | All other model attributes (see below) |
| `updated_at` | DATETIME | — | Last upsert timestamp |

**`meta` fields stored for models:**
`description`, `backhaul_technology_stacks`, `input_voltage`, `input_amperage`, `poe_standard`, `beamwidth`, `required_attributes`, `required_accessories`, `install_mops`, `notes`, `access_method`, `zabbix_icon_id`, `zabbix_icon_disabled_id`, `install_hours`, `config_hours`, `group_config_hours`, `revisit_factor`, `testing_hours`, `created_date`, `updated_date`

---

### `devices`

Synced from Jira Assets objecttype **Device** (objecttype ID 45). ~32,000 rows.

| Column | Type | Indexed | Description |
|--------|------|---------|-------------|
| `id` | TEXT PK | — | Jira object ID (e.g. `78413`) |
| `object_key` | TEXT | ✓ | Jira asset key (e.g. `IHS-78413`) — Jira attr 382 |
| `name` | TEXT | ✓ | FullName / label (e.g. `ANGK-PavillionNorth-APi`) — Jira attr 387 |
| `device_name` | TEXT | ✓ | Short DeviceName (e.g. `APi`) — Jira attr 383 |
| `ip_address` | TEXT | ✓ | Management IP (e.g. `10.196.107.215`) — Jira attr 390 |
| `mac_address` | TEXT | ✓ | Management MAC (e.g. `FC:11:65:BE:AE:E2`) — Jira attr 391 |
| `serial_number` | TEXT | ✓ | Serial number (e.g. `WBBG03ZQDTBN`) — Jira attr 392 |
| `zabbix_host_id` | TEXT | ✓ | Zabbix host ID (e.g. `53014`) — Jira attr 395 |
| `model_id` | TEXT FK | ✓ | FK → `device_models.id` |
| `meta` | JSON | — | All other device attributes (see below) |
| `updated_at` | DATETIME | — | Last upsert timestamp |

**`meta` fields stored for devices:**
`full_name`, `device_name`, `subvenue`, `location`, `manufacturer`, `model`, `powered_by`, `upstream_device_port`, `upstream_junction_port`, `uplink_port`, `height`, `tilt`, `azimuth`, `behind_l3nat`, `frequency`, `channel_width`, `phy_rate`, `phy_rate_alarm_threshold`, `eirp`, `target_signal_level`, `installed_signal_level`, `installed_signal_level_alarm_threshold`, `notes`, `nonpropagated_notes`, `status`, `ipv6_address`, `dhcpv6_prefix`, `update_trigger`, `created_date`, `updated_date`, `latitude`, `longitude`, `purchase_date`, `install_date`, `subvenue_root_device_for_monitoring`, `upstream_path_bends`

---

### `device_edges`

Directed dependency graph. Each row represents one upstream relationship.

| Column | Type | Indexed | Description |
|--------|------|---------|-------------|
| `id` | TEXT PK | — | Composite key: `{source_id}-{target_id}-{type}` |
| `source_id` | TEXT FK | ✓ | Upstream device → `devices.id` |
| `target_id` | TEXT FK | ✓ | Downstream device → `devices.id` |
| `relationship_type` | TEXT | — | `upstream_device` or `upstream_junction` |
| `created_at` | DATETIME | — | Insert timestamp |

**Edge direction:** `source → target` means *source is upstream of target*. To find what a device depends on, look for edges where `target_id = device.id` (the source nodes are its upstream parents).

**Unique constraint:** `(source_id, target_id, relationship_type)` — re-syncing is idempotent.

---

## API Reference

### Authentication

All endpoints except `GET /health` require an `X-API-Key` header matching the `API_KEY` env var.

```bash
curl -H "X-API-Key: your_secret_api_key" http://localhost:8080/devices/IHS-78413
```

Missing or wrong key returns `401`. If `API_KEY` is not set on the server it returns `500`.

---

### Device Lookup

#### `GET /devices/{identifier}`

Smart lookup — resolves any of these identifiers automatically:

| Identifier type | Example |
|----------------|---------|
| Jira object ID | `78413` |
| Jira asset key | `IHS-78413` |
| Full name | `ANGK-PavillionNorth-APi` |
| Short device name | `APi` |
| Management IP | `10.196.107.215` |
| Management MAC | `FC:11:65:BE:AE:E2` |
| Serial number | `WBBG03ZQDTBN` |
| Zabbix host ID | `53014` |

```bash
# All of these return the same device
curl -H "X-API-Key: $API_KEY" http://localhost:8080/devices/IHS-78413
curl -H "X-API-Key: $API_KEY" http://localhost:8080/devices/10.196.107.215
curl -H "X-API-Key: $API_KEY" http://localhost:8080/devices/FC:11:65:BE:AE:E2
curl -H "X-API-Key: $API_KEY" http://localhost:8080/devices/WBBG03ZQDTBN
curl -H "X-API-Key: $API_KEY" http://localhost:8080/devices/53014
```

**Response:**
```json
{
  "id": "78413",
  "object_key": "IHS-78413",
  "name": "ANGK-PavillionNorth-APi",
  "device_name": "APi",
  "ip_address": "10.196.107.215",
  "mac_address": "FC:11:65:BE:AE:E2",
  "serial_number": "WBBG03ZQDTBN",
  "zabbix_host_id": "53014",
  "model_id": "49719",
  "updated_at": "2026-05-19T22:00:00",
  "meta": {
    "subvenue": "Angola KOA, IN",
    "location": "PavillionNorth",
    "powered_by": "Switch_POE",
    "upstream_device_port": "3",
    "height": "7 ft",
    "manufacturer": "Cambium",
    "model": "XV2-21X (indoor)"
  },
  "model": {
    "id": "49719",
    "name": "XV2-21X (indoor)",
    "manufacturer": "Cambium",
    "device_class": "Wifi.Indoor",
    "classtype": "wifi.indoor",
    "zabbix_model_monitoring_mode": "icmp+snmp",
    "zabbix_model_snmp_template_id": "50113",
    "meta": {
      "config_hours": "0.1",
      "required_attributes": "powered_by",
      "zabbix_icon_id": "451"
    }
  }
}
```

Returns `404` if not found.

---

#### `GET /devices`

Search with filters. All parameters are AND-combined. At least one required.

| Parameter | Match type | Example |
|-----------|-----------|---------|
| `ip` | exact | `?ip=10.196.107.215` |
| `mac` | exact | `?mac=FC:11:65:BE:AE:E2` |
| `serial` | exact | `?serial=WBBG03ZQDTBN` |
| `object_key` | exact | `?object_key=IHS-78413` |
| `zabbix_host_id` | exact | `?zabbix_host_id=53014` |
| `name` | partial (case-insensitive) | `?name=PavillionNorth` |
| `device_name` | partial (case-insensitive) | `?device_name=APi` |
| `limit` | — | `?limit=100` (default 50) |

```bash
# Find all devices at a subvenue by partial name
curl -H "X-API-Key: $API_KEY" "http://localhost:8080/devices?name=PavillionNorth&limit=100"

# Exact MAC lookup
curl -H "X-API-Key: $API_KEY" "http://localhost:8080/devices?mac=FC:11:65:BE:AE:E2"
```

Returns a JSON array of device objects (same shape as single-device response).

---

### Dependency Graph

All graph endpoints accept the same identifier types as `GET /devices/{identifier}` — IP, MAC, serial, object_key, zabbix_host_id, name, or Jira ID.

#### `GET /devices/{identifier}/upstream?max_depth=10`

All devices that this device depends on (ancestors). Uses a single recursive SQL CTE — not N+1 queries.

```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8080/devices/IHS-78413/upstream"
curl -H "X-API-Key: $API_KEY" "http://localhost:8080/devices/10.196.107.215/upstream?max_depth=3"
```

Response is a flat list ordered by depth:
```json
[
  {
    "id": "78432",
    "name": "ANGK-PavillionNorth-Swt",
    "ip_address": "10.196.105.220",
    "mac_address": "6C:4C:BC:45:2A:2B",
    "serial_number": "Y25B075002764",
    "zabbix_host_id": "53017",
    "depth": 1,
    "model_name": "TL-SG2210XMP-M2",
    "manufacturer": "TPLink"
  }
]
```

#### `GET /devices/{identifier}/downstream?max_depth=10`

All devices that depend on this device (descendants).

```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8080/devices/IHS-78432/downstream"
curl -H "X-API-Key: $API_KEY" "http://localhost:8080/devices/53017/downstream?max_depth=5"
```

Same response shape as upstream.

#### `GET /devices/{identifier}/dependency-map?max_depth=5`

Both upstream and downstream in one call. Runs both CTE queries in parallel.

```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8080/devices/IHS-78413/dependency-map"
curl -H "X-API-Key: $API_KEY" "http://localhost:8080/devices/10.196.107.215/dependency-map?max_depth=3"
```

Response:
```json
{
  "device": { ... },
  "upstream": [ ... ],
  "downstream": [ ... ]
}
```

---

### Sync

#### `POST /sync`

Triggers a full sync from Jira Assets. Returns `202` immediately; sync runs in the background. A second call while sync is running returns `{"status": "already_running"}`.

```bash
curl -X POST -H "X-API-Key: $API_KEY" http://localhost:8080/sync
```

#### `GET /sync/status`

Returns the state of the last sync plus live row counts.

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8080/sync/status
```

```json
{
  "running": false,
  "last_started": "2026-05-19T02:00:00+00:00",
  "last_finished": "2026-05-19T02:07:43+00:00",
  "last_result": {
    "models": 312,
    "devices": 32225,
    "edges": 28100,
    "fetch_seconds": 210.4,
    "write_seconds": 180.1,
    "total_seconds": 390.5
  },
  "last_error": null,
  "db": {
    "devices": 32225,
    "models": 312,
    "edges": 28100
  }
}
```

### Other

#### `GET /health`

```bash
curl http://localhost:8080/health
# {"status": "ok"}
```

#### `GET /docs`

Interactive Swagger UI — all endpoints, parameters, and response schemas.

---

## Sync Behaviour

- **Auto-sync:** runs on a cron schedule (default `0 2 * * *` = 2am daily). Configurable via `SYNC_CRON` env var.
- **On-demand:** `POST /sync` for immediate refresh.
- **Idempotent:** all writes use `INSERT ... ON CONFLICT DO UPDATE`. Re-running sync updates changed records, adds new ones, and leaves unchanged records untouched.
- **Parallel fetch:** models and devices are fetched from Jira concurrently. Write order is always models → devices → edges (FK dependency).
- **Batched writes:** 500 rows per batch, committed after each batch to avoid large transactions.
- **Retry on transient errors:** network errors during Jira pagination are retried up to 3 times with exponential backoff (2s, 4s, 8s).

### Handling new Jira attributes

- Any new attribute Jira adds automatically lands in the `meta` JSON column — no schema change required.
- To promote a meta field to a dedicated indexed column: add it to `ATTR_MAP` / `MODEL_ATTR_MAP` and `COLUMN_FIELDS` / `MODEL_COLUMN_FIELDS` in `src/jira_sync.py`, add the column to the model in `src/models.py`, then restart the service (SQLAlchemy's `create_all` adds new columns on startup).

---

## Project Structure

```
asset-registry-service/
├── .env.example          # Environment variable template
├── pyproject.toml        # Dependencies
└── src/
    ├── database.py       # SQLite engine (WAL mode), session factory, init_db()
    ├── models.py         # SQLAlchemy ORM: DeviceModel, Device, DeviceEdge
    ├── repository.py     # DB operations: upserts, find_device, search, recursive CTE traversal
    ├── jira_sync.py      # Jira API client, attribute maps, transform, run_sync()
    └── main.py           # FastAPI app, scheduler, all HTTP endpoints
```

---

## Jira Attribute ID Reference

### Device attributes (objecttype 45)

| Attr ID | Jira name | Stored as |
|---------|-----------|-----------|
| 382 | Key | `object_key` (column + meta) |
| 383 | DeviceName | `device_name` (column + meta) |
| 387 | FullName | `name` column |
| 390 | management_ip | `ip_address` (column + meta) |
| 391 | management_mac | `mac_address` (column + meta) |
| 392 | serial_number | `serial_number` (column + meta) |
| 395 | zabbix_host_id | `zabbix_host_id` (column + meta) |
| 394 | model | `model_id` FK + `meta.model` |
| 400 | upstream_device | edge: `upstream_device` |
| 461 | upstream_junction | edge: `upstream_junction` |
| 388 | Subvenue | `meta.subvenue` |
| 389 | Location | `meta.location` |
| 393 | manufacturer | `meta.manufacturer` |
| 399 | powered_by | `meta.powered_by` |
| 401 | upstream_device_port | `meta.upstream_device_port` |
| 396 | height | `meta.height` |
| 480 | Frequency | `meta.frequency` |
| 481 | Channel_Width | `meta.channel_width` |
| 479 | EIRP | `meta.eirp` |
| 550 | latitude | `meta.latitude` |
| 551 | longitude | `meta.longitude` |
| 402 | notes | `meta.notes` |

Full list in `src/jira_sync.py → ATTR_MAP`.

### Model attributes (objecttype 13)

| Attr ID | Jira name | Stored as |
|---------|-----------|-----------|
| 93 | model | `name` column |
| 96 | manufacturer | `manufacturer` (column + meta) |
| 329 | class | `device_class` (column + meta) |
| 588 | classtype | `classtype` (column + meta) |
| 457 | zabbix_model_monitoring_mode | column + meta |
| 281 | zabbix_model_snmp_template_id | column + meta |
| 373 | zabbix_icon_id | `meta.zabbix_icon_id` |
| 330 | required_attributes | `meta.required_attributes` |
| 484 | config_hours | `meta.config_hours` |
| 485 | testing_hours | `meta.testing_hours` |

Full list in `src/jira_sync.py → MODEL_ATTR_MAP`.

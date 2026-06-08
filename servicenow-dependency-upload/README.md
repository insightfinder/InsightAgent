# ServiceNow → InsightFinder Dependency Upload

Fetches Application Service dependency maps from ServiceNow and uploads them to
InsightFinder as instance relation dependencies.

## How it works

```
ServiceNow CMDB (svc_ci_assoc, cmdb_rel_ci, cmdb_ci)
                |
   get_application_services.py   -> application_services.yaml   (sys_id -> zone name)
                |
   fetch_servicenow_dependencies.py -> servicenow_dependencies.yaml (source -> target edges)
                |
   send_dependencies_to_IF.py    -> InsightFinder /api/v2/updaterelationdependency
```

1. **get_application_services.py** — resolves each configured service `sys_id` to
   a zone name. By default (`servicenow_fetch_zone_name = False`) it skips the
   ServiceNow lookup and assigns every service `servicenow_default_zone`
   (`NO_ZONE`). When enabled it queries `cmdb_ci_service` for the real display
   name.

2. **fetch_servicenow_dependencies.py** — builds each service's dependency map
   from three CMDB tables:
   - `svc_ci_assoc` — which CIs belong to the service
   - `cmdb_rel_ci` — parent/child relationships between those CIs
   - `cmdb_ci` — resolves CI sys_ids to display names

   Only edges where both endpoints belong to the service are kept. Queries are
   chunked to avoid HTTP 414 errors.

   > The `app_service/getContent` API is **not used** because it only works on
   > empty or manually-built services. Service Mapping *discovered* services
   > (behind a `$sw_topology_map.do` URL) return HTTP 400, so the table-based
   > approach above is used instead.

3. **send_dependencies_to_IF.py** — sanitizes CI names using the IF backend
   format, groups edges by zone, and POSTs one request per zone to
   `/api/v2/updaterelationdependency`.

`main.py` runs all three in order and stops on the first failure.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.py.template config.py
```

Fill in `config.py`:

| Setting | Description |
|---|---|
| `servicenow_url` | Instance base URL, e.g. `https://yourinstance.service-now.com` |
| `servicenow_user` / `servicenow_password` | Basic Auth credentials. Account needs read on `cmdb_ci`, `cmdb_rel_ci`, `cmdb_ci_service`, `svc_ci_assoc` (e.g. `cmdb_read` role). |
| `servicenow_service_sys_ids` | List of service `sys_id`s to ingest — the `sysparm_bsid` value in a topology-map URL. |
| `insightfinder_url` / `insightfinder_username` / `license_key` / `insightfinder_system` | Target InsightFinder system. |

## Run

```bash
python3 main.py
```

Or run any step individually — steps 2 and 3 depend on the YAML written by the
prior step.

## Configuration reference

### Zone name (`servicenow_fetch_zone_name`)
- **`False` (default)** — no ServiceNow call is made; all services use
  `servicenow_default_zone` (`NO_ZONE`) as the InsightFinder zone. Any missing
  or empty zone value also falls back to `NO_ZONE`.
- **`True`** — Step 1 queries `cmdb_ci_service` to resolve each `sys_id` to its
  display name. Missing or empty names fall back to `servicenow_default_zone`.

### Instance name sanitization (`use_backend_sanitization`)
- **`True` (default)** — mirrors the IF backend's `getValidatedInstance` logic:
  `[` → `(`, `]` → `)`, `,`/`:`/`@` → `.`. Uploaded names match exactly what
  IF stores after its own ingest.
- **`False`** — agent-side format (matches `elasticsearch_collector`):
  `_` → `.`, `:` → `-`, strip leading special chars.

### Relation direction (`servicenow_relation_direction`)
- **`parent_to_child` (default)** — `source = parent CI`, `target = child CI`.
- **`child_to_parent`** — flip if the arrows in InsightFinder point the wrong way.

### Test limit (`TEST_LIMIT` in `send_dependencies_to_IF.py`)
Set to a positive integer to cap how many relations are sent per run. `0` = send all.

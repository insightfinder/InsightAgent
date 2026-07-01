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
   from the CMDB tables:
   - `svc_ci_assoc` — which CIs belong to the service
   - `cmdb_rel_ci` — parent/child relationships between those CIs (with type)
   - `cmdb_rel_type` — the semantics of each relationship type
   - `cmdb_ci` — resolves CI sys_ids to display names

   Only edges where both endpoints belong to the service are kept. Queries are
   chunked to avoid HTTP 414 errors.

   **Edge direction** is resolved per relationship type, not from a fixed
   setting. InsightFinder reads `source -> target` as "an issue on `source` can
   cause issues on `target`", so each edge is oriented with the provider/root as
   `source` and the dependent as `target`. ServiceNow's `parent`/`child` columns
   alone don't encode this — for `Depends on::Used by` the parent depends on the
   child, while for `Contains::Contained by` the parent contains the child — so
   the type's parent descriptor is used to pick the direction. Edges whose type
   isn't recognized are **skipped and logged** (extend `PARENT_IS_DEPENDENT` /
   `PARENT_IS_PROVIDER` to include them). Structural hosting/containment edges
   (`Runs on`, `Contains`, ...) are gated behind `servicenow_include_containment`.

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
| `servicenow_user` / `servicenow_password` | Basic Auth credentials. Account needs read on `cmdb_ci`, `cmdb_rel_ci`, `cmdb_rel_type`, `cmdb_ci_service`, `svc_ci_assoc` (e.g. `cmdb_read` role). |
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

### Relation direction (automatic)
Direction is no longer configured. Each edge is oriented by its relationship
type so `source -> target` always means "an issue on `source` can impact
`target`". Standard CMDB types (`Depends on`, `Contains`, `Runs on`, ...) are
built in. Unrecognized types are skipped and logged.

### Custom relationship types (no code change)
Add instance-specific or Service Mapping types in `config.py` — they extend the
built-in defaults. Each entry may be the type's parent descriptor
(`Applicative Flow To`) or its full name
(`Applicative Flow To::Applicative Flow From`); matching is case-insensitive.
- `servicenow_child_is_source_types` — `source = child` (parent depends on child).
- `servicenow_parent_is_source_types` — `source = parent` (child depends on parent).
- `servicenow_containment_types` — extra types treated as containment (gated by
  `servicenow_include_containment`).

The defaults already include the common Service Mapping connection types
(`Applicative Flow To`, `Use End Point To` → child-is-source;
`Implement End Point To` → parent-is-source). If a run logs "unrecognized
relationship type" warnings, add those type names to the appropriate list.

### Containment edges (`servicenow_include_containment`)
- **`True` (default)** — include structural hosting/containment relationships
  (`Runs on`, `Contains`, `Hosted on`, ...), oriented correctly. More granular
  than the server-to-server map shown in the ServiceNow UI.
- **`False`** — emit only service dependencies; closer to the collapsed UI map.

### Common-name disambiguation (`servicenow_qualify_common_names`)
ServiceNow display names are **not unique** — generic process/software names
like `java` or `Weblogic Server` are shared by many distinct CIs. Because
relations are keyed on the display name, same-named CIs otherwise collapse into
one InsightFinder node (and same-named CIs that relate to each other become
self-loops).
- **`False` (default)** — use the raw display name (names may merge).
- **`True`** — any name shared by more than one CI (across all ingested
  services) is qualified as `<name>@<host>`, where `host` is the CI's nearest
  host-class ancestor (same host detection as `servicenow_node_host_classes`).
  Unique names are left untouched. A common name whose host can't be resolved
  (no hosting/containment edge up to a host CI) is left bare and logged — it
  will still merge, so watch the "had no resolvable host" count in the run log.

  > Note: under backend sanitization the `@` is rewritten to `.`, so
  > `java@SU03137` is uploaded as `java.SU03137`.

### Create vs. update (`causal_key`)
Controls how step 3 calls `/api/v2/updaterelationdependency`:
- **empty (default)** — **POST**: creates a new causal group for the system from
  scratch (`systemDisplayName`-based, processed asynchronously).
- **non-empty** — **PUT**: updates the *existing* causal group identified by this
  causal key, adding the relations (confirmed, probability 1.0) to it. The
  backend returns HTTP 404 if no causal group matches the key, so copy the key
  from the existing group you want to update.

### Test limit (`TEST_LIMIT` in `send_dependencies_to_IF.py`)
Set to a positive integer to cap how many relations are sent per run. `0` = send all.

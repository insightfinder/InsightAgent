# ServiceNow → InsightFinder Dependency Upload

Fetches Application Service dependency maps from ServiceNow and uploads them to
InsightFinder as instance/component relation dependencies.

It mirrors the `zabbix-jira-dependency-upload` pipeline, but the source of the
dependency graph is ServiceNow's CMDB Application Service map instead of
Zabbix + Jira.

## How it works

```
ServiceNow CMDB Application Service API
                |
   get_application_services.py   -> application_services.yaml   (sys_id -> service name = IF zone)
                |
   fetch_servicenow_dependencies.py -> servicenow_dependencies.yaml (source -> target edges)
                |
   send_dependencies_to_IF.py    -> InsightFinder /api/v2/updaterelationdependency
```

1. **get_application_services.py** — for each configured service `sys_id`, looks
   up its display name from the `cmdb_ci_service` table. The name becomes the
   InsightFinder *zone*.
2. **fetch_servicenow_dependencies.py** — calls
   `GET /api/now/cmdb/app_service/{sys_id}/getContent?mode=shallow` for each
   service. That one call returns every CI in the map plus its parent/child
   relationships, which are flattened into `source -> target` edges.
3. **send_dependencies_to_IF.py** — sanitizes the CI names, groups edges by zone,
   and POSTs one request per zone to InsightFinder.

`main.py` runs all three in order and stops on the first failure.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy the template and fill in credentials:

```bash
cp config.py.template config.py
```

In `config.py` set:
- `servicenow_url`, `servicenow_user`, `servicenow_password` — a login with read
  access to the CMDB / the service map (same permissions as the browser UI).
- `servicenow_auth_method` — `"basic"` or `"oauth"` (see **Authentication** below).
- `servicenow_oauth_client_id`, `servicenow_oauth_client_secret` — required only
  when `servicenow_auth_method = "oauth"`.
- `servicenow_service_sys_ids` — the `sys_id`(s) of the Application Service map(s)
  to ingest. This is the `sysparm_bsid` value in a topology-map URL, e.g.
  `.../$sw_topology_map.do?sysparm_bsid=<sys_id>&...`.
- `insightfinder_url`, `insightfinder_username`, `license_key`,
  `insightfinder_system` — the target InsightFinder system.

### Authentication

ServiceNow supports two methods here, selected by `servicenow_auth_method`:

- **`basic`** — HTTP Basic Auth with `servicenow_user` / `servicenow_password`.
- **`oauth`** — OAuth 2.0 password grant. The agent exchanges
  `client_id`/`client_secret` + username/password at `/oauth_token.do` for a
  Bearer token automatically.

Some instances (e.g. with MFA or security hardening enabled) **reject Basic Auth
for the REST API** — UI login works but REST returns `401 "User is not
authenticated"`. In that case use `oauth`. To get the client credentials, ask a
ServiceNow admin to register an OAuth endpoint:
*System OAuth → Application Registry → Create an OAuth API endpoint for external
clients* — which yields a `client_id` and `client_secret`.

> Note on MFA: the OAuth **password grant** still sends the user's password, so
> once MFA becomes *mandatory* for the account it can also be rejected. For a
> durable integration, request a dedicated service account that is **exempt from
> MFA**, or switch to a client-credentials OAuth flow.

> The provided `config.py` is pre-filled with the Husqvarna instance URL and the
> `JDE Global Web Services` service sys_id as a starting point. Add credentials
> and any additional sys_ids you want to ingest.

## Run

```bash
python3 main.py
```

Or run any step individually (steps 2 and 3 depend on the YAML produced by the
prior step).

## Notes / tuning

- **Zone name lookup** — `servicenow_fetch_zone_name` (default `True`) controls
  whether Step 1 calls ServiceNow to resolve each service's display name. Set it
  to `False` to skip that call entirely and assign every configured service the
  `servicenow_default_zone` value instead. Useful for testing, or when the
  account lacks read access to `cmdb_ci_service` but can still call `getContent`.
- **Relation direction** — `servicenow_relation_direction` controls whether
  `source = parent` (default) or `source = child`. Flip it if the arrows in
  InsightFinder point the wrong way.
- **Business vs Application Service** — the `getContent` API normally resolves
  both. If a particular `sys_id` returns no content, that service may need the
  `cmdb_rel_ci` fallback path (not yet implemented).
- **TEST_LIMIT** — set in `send_dependencies_to_IF.py` to cap how many relations
  are sent while testing (0 = send all).

# ServiceNow Ticket Collector — Handoff Summary

## Project
`/home/ashvat/Documents/Github/InsightAgent/servicenow-agent/` — a new InsightFinder collector agent that queries ServiceNow (Table API) for tickets and sends them to InsightFinder as LOG entries (`{eventId, tag, data}`). Modeled structurally on `elasticsearch_collector/` (conf.d + cron.py + multiprocessing pipeline).

## Current file layout
```
servicenow-agent/
├── agent.txt, cron.py, requirements.txt, Dockerfile, setup/, README.md, .CONFIGVARS.md
├── .gitignore, .dockerignore          (conf.d/config.ini and .env excluded from both)
├── example.env                        (template — copy to .env, never committed)
├── .env                                (real credentials, gitignored)
├── getmessages_servicenow.py           (~1780 lines, the whole agent)
├── servicenow_auth.py                  (OAuth2 password-grant / Basic auth, token caching)
├── conf.d/
│   ├── config.ini.template
│   └── config.ini                      (live config, gitignored, has real license_key/base_url)
└── cache/                              (OAuth token cache only — no cursor files anymore)
```
**Note:** `testing/` (pytest suite, 52 tests) and `offline/` (vendored wheels) were deleted from disk at some point — the user is testing directly against the real agent/instance instead of the unit suite. Don't try to recreate them unless asked.

## Architecture as it stands today
- **Pipeline:** collector processes (one per query, `fetch_query`) → parser processes (`process_parse_messages`) → sender ThreadPool (`process_build_buffer`/`send_data_to_if`, unchanged boilerplate).
- **Auth:** OAuth2 password grant only (hardcoded `OAUTH_GRANT_TYPE='password'`, `OAUTH_TOKEN_PATH='/oauth_token.do'`) or Basic. `client_credentials`, configurable grant type/token path/scope were all removed as unneeded complexity, matching a working reference tool (`nbc_pytest/check_servicenow.py`).
- **Credentials:** never in `config.ini`. Read from environment — `SERVICENOW_OAUTH_CLIENT_ID/SECRET/USERNAME/PASSWORD` (oauth2) or `SERVICENOW_USERNAME/PASSWORD` (basic). Loaded automatically from `<agent_dir>/.env` at startup (`load_dotenv_file()`); real env vars always win over the file. `ifobfuscate.py` removed (unused now).
- **Time windowing: fully stateless.** No cursor/checkpoint system (removed entirely per explicit request — `CursorStore`, `state_cache_key`, `collector_results` are gone). Every run queries exactly the last `sampling_interval` seconds back from now (`compute_window()`), offset by `query_time_offset_seconds`. **`run_interval` and `sampling_interval` must match**, or you get gaps (interval too short) or duplicate tickets (interval too long).
- **Historical/replay mode:** `his_time_range = <start>,<end>` bypasses the live window. `fetch_query()` is called once per query but internally pages via `sysparm_offset` in a loop — 1 real HTTP call only if total rows ≤ `query_chunk_size` (1000 default); more rows page sequentially.
- **Multi-query:** one or more `[query:NAME]` sections in `config.ini`. The `query_json_file` sidecar-JSON escape hatch was removed entirely (redundant with `[query:NAME]` sections) — `conf.d/query_json.json.template` deleted, all code/docs references removed.
- **Field normalization:** `normalize_record()` / `_resolve_ref_value()` collapses ServiceNow's `{display_value, value}` shape (present on *every* field, including `sys_id` itself, because `sysparm_display_value=all`) to a single scalar: `display_value` if non-null/non-empty, else `value` if non-null/non-empty, else `display_value`'s own null/empty (never conflates None with `''`).
- **`data_fields` semantics:** blank → fetch/send the entire record (no `sysparm_fields` sent, so no dot-walked fields exist in the response — only base field names). Set → sent as `sysparm_fields` (which is what enables ServiceNow's dot-walk syntax like `cmdb_ci.name` to exist at all) and used to select output fields. **Key gotcha:** dot notation (`cmdb_ci.name`/`.value`) only works if that literal dotted string is also in `data_fields`; with blank `data_fields`, the correct field name is the bare one (`cmdb_ci`), which is already resolved to its display name/sys_id fallback.
- **Testing/debug tooling:** `--dump-file <path>` CLI flag writes every entry that would be sent to InsightFinder as JSON lines (truncated per run, thread-safe). Combine with `-t` to inspect without sending. Also: verbose/testing mode logs one record's `Raw data (before normalization):` and `Parsed data (sent to InsightFinder):` periodically (rate-limited by `log_compression_interval`) — these are two different pipeline stages of the *same* record, not a bug.

## Bugs fixed this session
1. **Credentials moved out of config into env vars** (multi-step refactor, see above).
2. **OAuth simplified** to password-grant-only, matching a working reference (`nbc_pytest`).
3. **Default `timestamp_field`** changed from `sys_updated_on` to `sys_created_on`.
4. **Config quote-stripping**: `_strip_quotes()` added to `_cfg()` so `sysparm_query = "opened_byLIKEInsight Finder"` (and previously-quoted `base_url`) parse correctly instead of including literal `"` characters.
5. **Cursor/checkpoint system removed** entirely per explicit request — agent is now fully stateless.
6. **`--dump-file`** feature added for schema inspection.
7. **`_resolve_ref_value()`** correctness fix for the display_value/value fallback logic (the None-vs-`''` distinction).
8. **Critical crash fix:** `dedup_key` in `process_parse_messages` was reading `raw_row.get('sys_id')` — the *un-normalized* field, which is a dict (unhashable) under `sysparm_display_value=all`. Fixed to use `norm_row.get('sys_id')` (already resolved to a string). This was causing `TypeError: unhashable type: 'dict'` on every record.
9. **`instance_field_regex` was being `regex.compile()`'d per-record** in the hot parsing loop instead of once at config-parse time. Fixed: precompiled into `instance_field_regex_compiled` (list of `(field, compiled_pattern)`), consistent with how `instance_whitelist_regex` already worked.
10. **Live `config.ini` had `instance_field = cmdb_ci.value`** (and `.name` variants) — invalid given blank `data_fields`, silently breaking instance derivation on every record (caught by the per-message try/except, logged as a parse error, ticket dropped). Fixed to `instance_field = cmdb_ci` in both `[servicenow]` and `[query:P1P2_Incidents]`.
11. **`.gitignore` fixed twice**: first added `conf.d/` + `!conf.d/config.ini.template` to exclude the live `config.ini` (which has a real `license_key`) from git — but that pattern is a known git gotcha (excluding a directory blocks negation of files inside it). Corrected to `conf.d/*` + `!conf.d/config.ini.template`, verified with `git check-ignore`. Confirmed `config.ini` was never actually committed to history.
12. **`query_json_file` removed entirely** (most recent change) — code, template, docs, `.gitignore`/`.dockerignore` entries, all cleaned up.

## Open items / things to watch
- **Performance:** a recent 474-ticket run took 17.56s — ~13s of that was ServiceNow's own response time (likely because `data_fields` is blank, so ServiceNow generates/returns every column including huge free-text fields like `description`/`work_notes`), ~3.5s was two sequential POSTs to InsightFinder, ~1s was our parsing. **Recommended but not yet applied:** set `data_fields` explicitly in `[query:P1P2_Incidents]` to only needed fields — this was offered but the user hasn't confirmed a field list yet.
- **`project_name` duplication:** `[servicenow] project_name` and `[insightfinder] project_name` are both set to `test-snow-1` in the live config — redundant but harmless given only one query exists and it doesn't override; only matters if a second query with a different target project is added.
- **No pytest suite currently on disk** — `testing/` was deleted. If a future session needs to re-verify changes, either recreate tests or verify via direct `python3 -c` snippets / running the real agent against the ServiceNow instance, per the user's stated preference.
- **`.dockerignore`'s `conf.d/`+negation pattern** may have the same git-style negation gotcha that `.gitignore` had (not yet verified for Docker's ignore semantics specifically) — flagged but not fixed, since it's lower-risk (build context, not git history) and wasn't explicitly asked about.

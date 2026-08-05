#!/usr/bin/env python3
"""
Daily sync of the InsightFinder `assignment_map` (notifications_settings on
insightfinder_system_settings, "AccessParks") from Jira Assets' Support
Engineer field, pushed live via the InsightFinder API — no Terraform apply
involved.

For each venue with a Support Engineer set in Jira, resolves that engineer's
name to their Jira Cloud accountId via accessparks.atlassian.net's user
search, then reconciles it against the LIVE assignmentMap fetched fresh from
InsightFinder:
  - zone not present            -> ADDED
  - zone present, same value    -> left untouched
  - zone present, wrong value   -> FIXED (overwritten with the Jira-resolved id)

Never removes an existing zone — only adds or corrects. request formats for
talking to InsightFinder are taken from the Go provider
(terraform-provider-insightfinder: client/jwt.go GetSystemFramework,
client/system_settings.go Get/SetHealthViewSetting) and from
terraform-config-generator/auto_generate_terraform.py (session/retry/header
conventions). The healthviewsetting API has no per-key update — updating
just assignmentMap still requires GET-ing the full settings for every system
on the account, patching only this system's assignmentMap in place, and
POST-ing the complete settings array back (see SetHealthViewSetting in the
Go client): that's what push_health_view_settings() below does.

Confirmed live in an earlier run: the backend accepts pure *additions*
cleanly, but a write that also changes/removes existing entries can fail to
persist that specific delta even though the HTTP call reports success. So
every push here is followed by a re-fetch and a semantic diff against what
was intended — anything that didn't actually stick is logged as FAILED, not
silently assumed to have worked.

Usage:
    python3 generate_assignment_map.py [--dry-run] [--system-name NAME]
                                        [--support-engineers-url URL] [--zone-metadata PATH]
                                        [--output PATH] [--log PATH]
"""
import argparse
import json
import logging
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv

load_dotenv()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SUPPORT_ENGINEERS_URL = os.getenv(
    "SUPPORT_ENGINEERS_URL", "http://{baseurl}/support-engineers"
)
DEFAULT_OUTPUT_PATH = os.path.join(SCRIPT_DIR, "assignment_map")
DEFAULT_WORKING_OUTPUT_PATH = os.path.join(SCRIPT_DIR, "working-assignment-map")
DEFAULT_ZONE_METADATA_PATH = os.path.join(SCRIPT_DIR, "zone-metadata.json")
DEFAULT_LOG_PATH = os.path.join(SCRIPT_DIR, "assignment_map_sync.log")
JIRA_SITE_URL = os.getenv("JIRA_SITE_URL", "https://{orgname}.atlassian.net")
IF_BASE_URL = os.getenv("IF_BASE_URL", "https://app.insightfinder.com").rstrip("/")
COMPONENT = "All"
MAX_RETRIES = 3
RETRY_DELAY = 2.0

log = logging.getLogger("assignment_map_sync")


def setup_logging(log_path: str) -> None:
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)


def _get_with_retries(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    last_exc: BaseException = RuntimeError(f"GET {url} failed with no attempts made")
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = client.get(url, **kwargs)
            if r.status_code == 200:
                return r
            log.warning("GET %s -> HTTP %d (attempt %d/%d)", url, r.status_code, attempt, MAX_RETRIES)
            last_exc = RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        except httpx.RequestError as exc:
            log.warning("GET %s failed: %s (attempt %d/%d)", url, exc, attempt, MAX_RETRIES)
            last_exc = exc
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY)
    raise last_exc


# ── Jira Assets / support-engineers ────────────────────────────────────────

def fetch_venues(url: str, api_key: str) -> List[Dict]:
    r = _get_with_retries(httpx.Client(), url, headers={"X-API-Key": api_key}, timeout=30)
    return r.json()


def load_zone_components(path: str) -> Dict[str, List[str]]:
    """zone name -> valid component list, from zone-metadata.json's componentsByZone.
    Informational only — the production map already has many zone names not in
    this list, so it is never used to reject entries, only to flag new additions
    worth double-checking."""
    with open(path) as f:
        return json.load(f)["componentsByZone"]


def resolve_account_id(
    client: httpx.Client, name: str, cache: Dict[str, Optional[str]]
) -> Optional[str]:
    """Resolve a display name to a Jira Cloud accountId, caching by name."""
    if name in cache:
        return cache[name]

    r = client.get(f"{JIRA_SITE_URL}/rest/api/3/user/search", params={"query": name})
    r.raise_for_status()
    users = r.json()

    account_id = None
    if users:
        exact = [u for u in users if u.get("displayName", "").lower() == name.lower()]
        chosen = exact[0] if exact else users[0]
        account_id = chosen.get("accountId")
        if len(users) > 1 and not exact:
            log.warning(
                "ambiguous Jira match for %r (%d results), using %r",
                name, len(users), chosen.get("displayName"),
            )
    else:
        log.warning("no Jira user found for %r", name)

    cache[name] = account_id
    return account_id


# ── InsightFinder platform API ─────────────────────────────────────────────
# Request formats mirror terraform-provider-insightfinder's Go client
# (client/jwt.go GetSystemFramework, client/system_settings.go Get/SetHealthViewSetting)
# and auto_generate_terraform.py's api_headers()/get_own_systems() conventions.

def if_headers(username: str, license_key: str) -> Dict[str, str]:
    return {"X-User-Name": username, "X-API-Key": license_key, "Content-Type": "application/json"}


def resolve_system_id(client: httpx.Client, username: str, license_key: str, system_name: str) -> str:
    r = _get_with_retries(
        client,
        f"{IF_BASE_URL}/api/external/v1/systemframework",
        headers=if_headers(username, license_key),
        params={"customerName": username, "needDetail": "true", "tzOffset": "0"},
        timeout=30,
    )
    data = r.json()
    target = system_name.strip().lower()
    for raw in (data.get("ownSystemArr") or []) + (data.get("shareSystemArr") or []):
        try:
            sysobj = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, json.JSONDecodeError):
            continue
        names = {
            (sysobj.get("systemDisplayName") or "").strip().lower(),
            (sysobj.get("systemName") or "").strip().lower(),
        }
        if target in names:
            sid = (
                (sysobj.get("systemKey") or {}).get("systemName")
                or sysobj.get("systemId")
                or sysobj.get("systemName")
            )
            if sid:
                return sid
    raise RuntimeError(f"system {system_name!r} not found in systemframework response")


def get_all_health_view_settings(client: httpx.Client, username: str, license_key: str) -> Dict[str, Dict]:
    r = _get_with_retries(
        client,
        f"{IF_BASE_URL}/api/external/v2/healthviewsetting",
        headers=if_headers(username, license_key),
        params={"customerName": username},
        timeout=30,
    )
    return r.json()


def push_health_view_settings(
    client: httpx.Client, username: str, license_key: str,
    system_id: str, all_settings: Dict[str, Dict], new_assignment_map: Dict[str, Dict],
) -> None:
    """GET-modify-POST: the API has no per-key update, so the full settings for
    EVERY system on the account must be resent, with only this system's
    assignmentMap patched. Every other system's settings dict is passed through
    unmodified so nothing else on the account is touched."""
    current = dict(all_settings.get(system_id) or {})
    current["assignmentMap"] = new_assignment_map
    current["systemId"] = system_id
    current["id"] = system_id

    settings_array = [current]
    for sid, s in all_settings.items():
        if sid == system_id:
            continue
        s2 = dict(s)
        s2["systemId"] = sid
        s2["id"] = sid
        settings_array.append(s2)

    form = {
        "systemName": system_id,
        "settings": json.dumps(settings_array),
        "customerName": username,
        "userName": username,
        "licenseKey": license_key,
    }
    r = client.post(
        f"{IF_BASE_URL}/api/external/v2/healthviewsetting",
        data=form,
        headers={"X-User-Name": username, "X-API-Key": license_key},
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"failed to set health view settings: HTTP {r.status_code} - {r.text[:500]}")
    try:
        resp = r.json()
        if isinstance(resp, dict) and resp.get("success") is False:
            raise RuntimeError(f"failed to set health view settings: {resp.get('message')}")
    except ValueError:
        pass  # non-JSON response body on success, same as the Go client tolerates


def zone_key_for(venue_name: str) -> str:
    return json.dumps({"zone": venue_name, "component": COMPONENT}, separators=(",", ":"))


def zone_of(key: str) -> Optional[str]:
    try:
        return json.loads(key).get("zone")
    except (json.JSONDecodeError, AttributeError):
        return None


def write_local_snapshot(path: str, assignment_map: Dict[str, Dict]) -> None:
    """Human-readable Terraform-style snapshot of the live map, for reference /
    manual reconciliation with system_settings.tf. Not used as a diff base —
    escaping style may differ from what Terraform's jsonencode() would produce
    for special characters, so copy via `terraform plan`/refresh, not by hand."""
    entries = []
    for key, val in assignment_map.items():
        key_escaped = json.dumps(key)[1:-1]
        ids_json = json.dumps(val.get("jiraAssignees", []))
        entries.append(f'"{key_escaped}" : {{ "jiraAssignees" : {ids_json} }}')
    inner = "{ " + ", ".join(entries) + " }"
    with open(path, "w") as f:
        f.write(f"    assignment_map                         = jsonencode({inner})\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--support-engineers-url", default=DEFAULT_SUPPORT_ENGINEERS_URL)
    parser.add_argument("--zone-metadata", default=DEFAULT_ZONE_METADATA_PATH)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--working-output", default=DEFAULT_WORKING_OUTPUT_PATH)
    parser.add_argument("--log", default=DEFAULT_LOG_PATH)
    parser.add_argument("--system-name", default=os.getenv("IF_SYSTEM_NAME", "AccessParks"))
    parser.add_argument("--dry-run", action="store_true", help="Fetch and diff live, but don't push or write snapshots.")
    args = parser.parse_args()

    setup_logging(args.log)
    log.info("=== assignment_map sync run started (dry_run=%s) ===", args.dry_run)

    try:
        api_key = os.environ["API_KEY"]
        jira_email = os.environ["JIRA_EMAIL"]
        jira_token = os.environ["JIRA_API_TOKEN"]
        if_username = os.environ["IF_USERNAME"]
        if_license_key = os.environ["IF_LICENSE_KEY"]
    except KeyError as exc:
        log.error("missing required env var: %s", exc)
        sys.exit(1)

    try:
        venues = fetch_venues(args.support_engineers_url, api_key)
        log.info("Fetched %d venues from %s", len(venues), args.support_engineers_url)

        zone_components = load_zone_components(args.zone_metadata)

        if_client = httpx.Client()
        system_id = resolve_system_id(if_client, if_username, if_license_key, args.system_name)
        log.info("Resolved system %r -> systemId %s", args.system_name, system_id)

        all_settings = get_all_health_view_settings(if_client, if_username, if_license_key)
        current = all_settings.get(system_id) or {}
        current_map = current.get("assignmentMap") or {}
        key_by_zone = {}
        base_ids = {}
        for key, val in current_map.items():
            z = zone_of(key)
            if z is None:
                continue
            key_by_zone[z] = key
            base_ids[z] = val.get("jiraAssignees", [])
        log.info("Fetched %d existing zone entries live from InsightFinder", len(base_ids))

        cache: Dict[str, Optional[str]] = {}
        skipped_no_engineer = 0
        added: Dict[str, List[str]] = {}
        fixed: Dict[str, Tuple[List[str], List[str]]] = {}
        unresolved_zone_new = []

        with httpx.Client(auth=(jira_email, jira_token), timeout=30) as jira_client:
            for v in venues:
                engineer_name = v.get("support_engineer_name")
                venue_name = v.get("venue_name")
                if not engineer_name or not venue_name:
                    skipped_no_engineer += 1
                    continue

                account_id = resolve_account_id(jira_client, engineer_name, cache)
                if not account_id:
                    continue
                new_ids = [account_id]

                if venue_name not in base_ids:
                    if venue_name not in zone_components:
                        unresolved_zone_new.append(venue_name)
                    added[venue_name] = new_ids
                elif base_ids[venue_name] != new_ids:
                    fixed[venue_name] = (base_ids[venue_name], new_ids)

        new_map = dict(current_map)
        for zone, ids in added.items():
            new_map[zone_key_for(zone)] = {"jiraAssignees": ids}
        for zone, (_, new_ids) in fixed.items():
            new_map[key_by_zone[zone]] = {"jiraAssignees": new_ids}

        unresolved = sorted(n for n, aid in cache.items() if aid is None)
        resolved_count = len(cache) - len(unresolved)
        log.info("Resolved %d/%d distinct support engineers to Jira accountIds", resolved_count, len(cache))
        if unresolved:
            log.warning("unresolved engineer names: %s", unresolved)

        log.info("%d new zone(s) to add: %s", len(added), sorted(added))
        for z in sorted(added):
            if z in unresolved_zone_new:
                log.warning("  new zone %r not found in zone-metadata.json — double check this name", z)
        log.info("%d zone(s) with the wrong engineer to fix:", len(fixed))
        for z, (old, new) in fixed.items():
            log.info("  ! %s: %s -> %s", z, old, new)

        if args.dry_run:
            log.info("DRY RUN — not pushed to InsightFinder, no snapshot files written.")
            log.info("=== run finished (dry run) ===")
            return

        if not added and not fixed:
            log.info("Nothing to change — skipping push.")
        else:
            push_health_view_settings(if_client, if_username, if_license_key, system_id, all_settings, new_map)
            log.info("Pushed updated assignmentMap (%d total entries) to InsightFinder", len(new_map))

            # Re-fetch and verify: the backend has been observed to silently drop
            # changes to existing entries even on HTTP 200, so don't trust the
            # write — confirm it against a fresh read.
            verify_settings = get_all_health_view_settings(if_client, if_username, if_license_key)
            verify_map = (verify_settings.get(system_id) or {}).get("assignmentMap") or {}
            verify_ids = {}
            for key, val in verify_map.items():
                z = zone_of(key)
                if z is not None:
                    verify_ids[z] = val.get("jiraAssignees", [])

            failed_add = [z for z in added if verify_ids.get(z) != added[z]]
            failed_fix = [z for z in fixed if verify_ids.get(z) != fixed[z][1]]

            if failed_add or failed_fix:
                log.error(
                    "%d addition(s) and %d fix(es) did NOT persist after push "
                    "(backend accepted the write but reverted these specific entries): "
                    "added=%s fixed=%s",
                    len(failed_add), len(failed_fix), failed_add, failed_fix,
                )
            else:
                log.info("Verified: all %d addition(s) and %d fix(es) persisted correctly.", len(added), len(fixed))

            write_local_snapshot(args.output, verify_map)
            write_local_snapshot(args.working_output, verify_map)
            log.info("Wrote local snapshots (%d entries) -> %s, %s", len(verify_map), args.output, args.working_output)

        log.info("=== run finished ===")
    except Exception:
        log.exception("assignment_map sync run failed")
        sys.exit(1)


if __name__ == "__main__":
    main()

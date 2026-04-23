#!/usr/bin/env python3
"""
Fetch InsightFinder project and system data and save to JSON files.

Usage examples:
  # Project-level data only
  python fetch_insightfinder_data.py \
      --username nbcAdmin --api-key SECRET \
      --customer-name nbcAdmin --project-name "Conviva-Alerts-Stage"

  # Project + system-level data (knowledgebase & notifications)
  python3 fetch_insightfinder_data.py \
      --username nbcAdmin --api-key SECRET \
      --customer-name nbcAdmin --project-name "Conviva-Alerts-Stage" \
      --system-name "My System"

  # Metric project — also fetch component alert/escalate/ignored configurations
  python3 fetch_insightfinder_data.py \
      --username mustafa --api-key SECRET \
      --customer-name mustafa --project-name "uisp-metrics-5" \
      --data-type metric

This script calls the APIs referenced in the `apis` file and saves the
responses as JSON files in the output directory.

Project-level endpoints:
  - /api/external/v1/projectkeywords
  - /api/external/v1/watch-tower-setting
  - /api/external/v1/logsummarysettings
  - /api/external/v1/logjsontype
  - /api/v1/logdedicatedmode        (process mode; uses Cookie auth)

Metric-project endpoints (requires --data-type metric):
  - /api/external/v1/metriccomponent          (escalateIncident components)
  - /api/external/v1/metriccomponent          (ignored components)
  - /api/external/v1/componentmetricupdate    (per-metric alert settings)

System-level endpoints (requires --system-name):
  - /api/external/v1/systemframework          (resolve system name -> system ID)
  - /api/external/v1/globalknowledgebasesetting
  - /api/external/v2/IncidentPredictionSetting
  - /api/external/v2/healthviewsetting
  - /api/external/v1/systemframework          (miscellaneous: longTerm, shouldAutoShare, etc.)

By default the script uses:
  host: https://stg.insightfinder.com
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, Any, Optional

try:
    import requests
except Exception:
    print("Missing dependency: requests. Install with: pip install requests", file=sys.stderr)
    raise


DEFAULT_HOST = "https://stg.insightfinder.com"

CONFIG_DEFAULTS = {
    'username': "",
    'api_key': "",
    'customer_name': "",
    'project_name': "",
    'system_name': None,
    'host': DEFAULT_HOST,
    'out_dir': '.',
    'no_ssl_verify': False,
}


def save_json(data: Any, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_with_retries(session: requests.Session, url: str, headers: Dict[str, str],
                     params: Dict[str, Any] | None = None,
                     max_retries: int = 3, backoff: float = 1.0) -> requests.Response:
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, headers=headers, params=params, timeout=30)
            return resp
        except requests.RequestException as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(backoff * attempt)
            else:
                raise
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Failed to perform GET {url}")


def fetch_and_save(session: requests.Session, url: str, headers: Dict[str, str],
                   params: Dict[str, Any] | None, out_path: str, description: str) -> Optional[Any]:
    print(f"Fetching {description} -> {url}")
    resp = get_with_retries(session, url, headers, params=params)
    if resp.status_code != 200:
        print(f"  Error: HTTP {resp.status_code} - {resp.text[:200]}", file=sys.stderr)
        resp.raise_for_status()

    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}

    save_json(data, out_path)
    print(f"  Saved to {out_path}")
    return data


def resolve_system_id(session: requests.Session, host: str, headers: Dict[str, str],
                      customer_name: str, system_name: str) -> Optional[str]:
    """Resolve a human-readable system name to its system ID (hash) via the system framework API."""
    url = f"{host.rstrip('/')}/api/external/v1/systemframework"
    params = {"customerName": customer_name, "needDetail": "true", "tzOffset": "0"}

    print(f"Resolving system ID for '{system_name}'...")
    resp = get_with_retries(session, url, headers, params=params)
    if resp.status_code != 200:
        print(f"  Error fetching system framework: HTTP {resp.status_code}", file=sys.stderr)
        return None

    try:
        framework = resp.json()
    except ValueError:
        print("  Error: system framework response is not valid JSON", file=sys.stderr)
        return None

    all_system_strs = framework.get("ownSystemArr", []) + framework.get("shareSystemArr", [])
    if not all_system_strs:
        print("  No systems found in system framework", file=sys.stderr)
        return None

    name_lower = system_name.strip().lower()

    for system_str in all_system_strs:
        try:
            system = json.loads(system_str) if isinstance(system_str, str) else system_str
        except (json.JSONDecodeError, TypeError):
            continue

        # Resolve the canonical system ID (the hash)
        system_id = (
            (system.get("systemKey") or {}).get("systemName")
            or system.get("systemId")
            or system.get("systemName")
            or ""
        ).strip()

        if not system_id:
            continue

        # Match by display name or system name
        candidates = [
            system.get("systemDisplayName", "").strip().lower(),
            system.get("systemName", "").strip().lower(),
        ]
        if name_lower in candidates:
            print(f"  Resolved '{system_name}' -> system ID: {system_id}")
            return system_id

    print(f"  System '{system_name}' not found in system framework", file=sys.stderr)
    return None


def fetch_metric_project_data(session: requests.Session, host: str, headers: Dict[str, str],
                              username: str, customer_name: str,
                              project_name: str, out_dir: str) -> None:
    """Fetch metric-project-specific configuration data and save to JSON files."""
    base = host.rstrip('/')

    # 1. Escalate-incident component settings
    escalate_out = os.path.join(out_dir, "sample_metric_escalate_components.json")
    try:
        escalate_data = fetch_and_save(
            session,
            f"{base}/api/external/v1/metriccomponent",
            headers,
            {"projectName": project_name, "customerName": customer_name,
             "operation": "escalateIncident", "tzOffset": "-14400000"},
            escalate_out,
            "metric escalate-incident components",
        )
    except Exception as e:
        print(f"  Failed to fetch escalate-incident components: {e}", file=sys.stderr)
        escalate_data = None

    # 2. Ignored component settings
    ignored_out = os.path.join(out_dir, "sample_metric_ignored_components.json")
    try:
        ignored_data = fetch_and_save(
            session,
            f"{base}/api/external/v1/metriccomponent",
            headers,
            {"projectName": project_name, "customerName": customer_name,
             "operation": "ignored", "tzOffset": "-14400000"},
            ignored_out,
            "metric ignored components",
        )
    except Exception as e:
        print(f"  Failed to fetch ignored components: {e}", file=sys.stderr)
        ignored_data = None

    # Collect all unique metric names from both responses
    all_metric_names: set = set()
    for resp_data, key in [
        (escalate_data, "componentEscalateIncident"),
        (ignored_data, "componentIgnored"),
    ]:
        if not resp_data:
            continue
        encoded = resp_data.get(key, "")
        if not encoded:
            continue
        try:
            for entry in json.loads(encoded):
                metric = entry["metricLevelPrimaryKey"]["metricName"]
                all_metric_names.add(metric)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    if not all_metric_names:
        print("  No metrics found in component responses — skipping per-metric alert settings.")
        return

    print(f"  Found {len(all_metric_names)} metric(s): {sorted(all_metric_names)}")

    # 3. Per-metric alert settings
    all_metric_settings = {}
    for metric_name in sorted(all_metric_names):
        params = {
            "onlyIsKpi": "false",
            "onlyComputeDifference": "false",
            "projectName": f"{project_name}@{username}",
            "start": "0",
            "limit": "500",
            "metricFilter": metric_name,
            "customerName": customer_name,
            "tzOffset": "-14400000",
        }
        try:
            resp = get_with_retries(
                session,
                f"{base}/api/external/v1/componentmetricupdate",
                headers,
                params=params,
            )
            if resp.status_code != 200:
                print(f"  Warning: HTTP {resp.status_code} for metric '{metric_name}'",
                      file=sys.stderr)
                continue
            all_metric_settings[metric_name] = resp.json()
            print(f"  Metric '{metric_name}' settings fetched.")
        except Exception as e:
            print(f"  Failed to fetch settings for metric '{metric_name}': {e}", file=sys.stderr)

    if all_metric_settings:
        metric_settings_out = os.path.join(out_dir, "sample_metric_alert_settings.json")
        save_json(all_metric_settings, metric_settings_out)
        print(f"  All metric alert settings saved to {metric_settings_out}")


def fetch_system_settings(session: requests.Session, host: str, headers: Dict[str, str],
                          customer_name: str, system_id: str, out_dir: str) -> None:
    """Fetch all system-level settings for the given system ID."""

    system_ids_json = json.dumps([system_id])

    # 1) Global knowledge base setting
    kb_global_url = f"{host.rstrip('/')}/api/external/v1/globalknowledgebasesetting"
    kb_global_params = {"customerName": customer_name, "systemIds": system_ids_json}
    kb_global_out = os.path.join(out_dir, "sample_kb_global.json")
    try:
        data = fetch_and_save(session, kb_global_url, headers, kb_global_params,
                              kb_global_out, "global knowledge base settings")
        # Unwrap the first element if it's a list
        if isinstance(data, list) and len(data) > 0:
            save_json(data[0], kb_global_out)
    except Exception as e:
        print(f"  Failed to fetch global KB settings: {e}", file=sys.stderr)

    # 2) Incident prediction settings
    ip_url = f"{host.rstrip('/')}/api/external/v2/IncidentPredictionSetting"
    ip_params = {"customerName": customer_name, "systemIds": system_ids_json}
    ip_out = os.path.join(out_dir, "sample_kb_incident_prediction.json")
    try:
        data = fetch_and_save(session, ip_url, headers, ip_params,
                              ip_out, "incident prediction settings")
        if isinstance(data, list) and len(data) > 0:
            save_json(data[0], ip_out)
    except Exception as e:
        print(f"  Failed to fetch incident prediction settings: {e}", file=sys.stderr)

    # 3) Health view / notifications settings (returns all systems; we filter to ours)
    hv_url = f"{host.rstrip('/')}/api/external/v2/healthviewsetting"
    hv_params = {"customerName": customer_name}
    hv_all_out = os.path.join(out_dir, "sample_notifications.json")
    try:
        all_data = fetch_and_save(session, hv_url, headers, hv_params,
                                  hv_all_out, "notifications / health view settings (all systems)")
        # Save the filtered entry for just this system
        if isinstance(all_data, dict) and system_id in all_data:
            filtered_out = os.path.join(out_dir, "sample_notifications.json")
            save_json(all_data[system_id], filtered_out)
            print(f"  Filtered to system '{system_id}' and re-saved to {filtered_out}")
    except Exception as e:
        print(f"  Failed to fetch notifications settings: {e}", file=sys.stderr)

    # 4) Miscellaneous system framework settings (longTerm, shouldAutoShare, etc.)
    sf_url = f"{host.rstrip('/')}/api/external/v1/systemframework"
    sf_params = {"customerName": customer_name, "needDetail": "false", "tzOffset": "-18000000"}
    misc_out = os.path.join(out_dir, "sample_miscellaneous.json")
    try:
        resp = get_with_retries(session, sf_url, headers, params=sf_params)
        if resp.status_code != 200:
            print(f"  Error fetching system framework: HTTP {resp.status_code}", file=sys.stderr)
        else:
            framework = resp.json()
            misc_data = None
            for entry_str in framework.get("ownSystemArr", []):
                try:
                    entry = json.loads(entry_str) if isinstance(entry_str, str) else entry_str
                except (json.JSONDecodeError, TypeError):
                    continue
                entry_system_id = (entry.get("systemKey") or {}).get("systemName", "")
                if entry_system_id != system_id:
                    continue
                misc_data = {"longTerm": entry.get("longTerm", False)}
                system_setting_str = entry.get("systemSetting", "")
                if system_setting_str:
                    try:
                        inner = json.loads(system_setting_str)
                        misc_data["shouldAutoShare"] = inner.get("shouldAutoShare", False)
                        misc_data["rootCauseReverseEntryFilterThreshold"] = inner.get(
                            "rootCauseReverseEntryFilterThreshold", 0)
                        misc_data["enableCompositeTimeline"] = inner.get("enableCompositeTimeline", False)
                    except (json.JSONDecodeError, TypeError):
                        pass
                break
            if misc_data is not None:
                save_json(misc_data, misc_out)
                print(f"  Saved miscellaneous settings to {misc_out}")
            else:
                print(f"  System '{system_id}' not found in system framework response", file=sys.stderr)
    except Exception as e:
        print(f"  Failed to fetch miscellaneous settings: {e}", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fetch InsightFinder project and system data and save as JSON files")
    parser.add_argument("--username", help="X-User-Name header (or set CONFIG_DEFAULTS in the file)")
    parser.add_argument("--api-key", dest="api_key", help="X-API-Key header (or set CONFIG_DEFAULTS in the file)")
    parser.add_argument("--customer-name", dest="customer_name",
                        help="Customer name for APIs (or set CONFIG_DEFAULTS in the file)")
    parser.add_argument("--project-name", dest="project_name",
                        help="Project name to query (e.g. Conviva-Alerts-Stage) (or set CONFIG_DEFAULTS in the file)")
    parser.add_argument("--system-name", dest="system_name",
                        help="System display name to fetch system-level settings (knowledgebase + notifications). "
                             "If omitted, only project-level data is fetched.")
    parser.add_argument("--data-type", dest="data_type", default=None,
                        help="Project data type (e.g. 'metric'). When 'metric', also fetches "
                             "metric configurations (component alert settings, escalate/ignored).")
    parser.add_argument("--host", default=None,
                        help=f"Host for all APIs (default: {DEFAULT_HOST} or CONFIG_DEFAULTS)")
    parser.add_argument("--out-dir", default=None, dest="out_dir",
                        help="Directory to write output JSON files (or set CONFIG_DEFAULTS)")
    parser.add_argument("--no-ssl-verify", action="store_true",
                        help="Disable SSL verification (not recommended). If set here, it overrides CONFIG_DEFAULTS")

    args = parser.parse_args(argv)

    def resolve(name: str, cli_val):
        if cli_val is not None:
            return cli_val
        return CONFIG_DEFAULTS.get(name)

    username = resolve('username', args.username)
    api_key = resolve('api_key', args.api_key)
    customer_name = resolve('customer_name', args.customer_name)
    project_name = resolve('project_name', args.project_name)
    system_name = resolve('system_name', args.system_name)
    data_type = (args.data_type or "").lower()
    host = resolve('host', args.host) or DEFAULT_HOST
    out_dir = resolve('out_dir', args.out_dir) or '.'
    no_ssl_verify = args.no_ssl_verify or CONFIG_DEFAULTS.get('no_ssl_verify', False)

    missing = [k for k, v in [
        ('username', username), ('api_key', api_key),
        ('customer_name', customer_name), ('project_name', project_name),
    ] if not v]
    if missing:
        parser.error(
            f"Missing required values: {', '.join(missing)}. "
            "Provide them as CLI args or set CONFIG_DEFAULTS in the script."
        )

    # After the missing-values check these are guaranteed to be non-None strings.
    username = str(username)
    api_key = str(api_key)
    customer_name = str(customer_name)
    project_name = str(project_name)

    # Standard headers (X-API-Key) used by most endpoints.
    headers: Dict[str, str] = {
        "X-User-Name": username,
        "X-API-Key": api_key,
        "Content-Type": "application/json",
    }

    # License-key headers used by the ServiceNow third-party endpoint.
    license_headers: Dict[str, str] = {
        "X-User-Name": username,
        "X-License-Key": api_key,
        "Content-Type": "application/json",
    }

    session = requests.Session()
    session.verify = not no_ssl_verify

    print("=" * 60)
    print("Fetching PROJECT-LEVEL data")
    print("=" * 60)

    # 1) projectkeywords
    keywords_url = f"{host.rstrip('/')}/api/external/v1/projectkeywords"
    keywords_params = {"projectName": project_name}
    keywords_out = os.path.join(out_dir, "sample_keywords.json")
    try:
        fetch_and_save(session, keywords_url, headers, keywords_params, keywords_out, "project keywords")
    except Exception as e:
        print(f"  Failed: {e}", file=sys.stderr)

    # 2) watch-tower-setting
    watch_url = f"{host.rstrip('/')}/api/external/v1/watch-tower-setting"
    project_list = [{"projectName": project_name, "customerName": customer_name}]
    watch_params = {"projectList": json.dumps(project_list)}
    settings_out = os.path.join(out_dir, "sample_settings.json")
    try:
        fetch_and_save(session, watch_url, headers, watch_params, settings_out, "watch tower settings")
    except Exception as e:
        print(f"  Failed: {e}", file=sys.stderr)

    # 3) logsummarysettings
    summary_url = f"{host.rstrip('/')}/api/external/v1/logsummarysettings"
    summary_params = {"projectName": project_name}
    summary_out = os.path.join(out_dir, "sample_summary_and_metafields.json")
    try:
        fetch_and_save(session, summary_url, headers, summary_params, summary_out, "summary and metafields")
    except Exception as e:
        print(f"  Failed: {e}", file=sys.stderr)

    # 4) logjsontype
    jsonkeys_url = f"{host.rstrip('/')}/api/external/v1/logjsontype"
    jsonkeys_params = {"projectName": project_name}
    jsonkeys_out = os.path.join(out_dir, "sample_jsonkey.json")
    try:
        fetch_and_save(session, jsonkeys_url, headers, jsonkeys_params, jsonkeys_out, "json keys")
    except Exception as e:
        print(f"  Failed: {e}", file=sys.stderr)

    # 5) logdedicatedmode — process mode (cookie-based auth)
    mode_url = f"{host.rstrip('/')}/api/v1/logdedicatedmode"
    mode_params = {"userName": username, "projectName": project_name, "licenseKey": api_key}
    mode_headers = {"Cookie": f"userName={username};", "Content-Type": "application/json"}
    mode_out = os.path.join(out_dir, "sample_mode.json")
    try:
        fetch_and_save(session, mode_url, mode_headers, mode_params, mode_out, "process mode")
    except Exception as e:
        print(f"  Failed (skipping – may not be supported): {e}", file=sys.stderr)

    # 6) ServiceNow third-party settings (uses X-License-Key header)
    sn_url = f"{host.rstrip('/')}/api/external/v1/thirdpartysetting"
    sn_params = {"projectName": project_name, "cloudType": "ServiceNow", "tzOffset": "-18000000"}
    sn_out = os.path.join(out_dir, "sample_servicenow.json")
    try:
        fetch_and_save(session, sn_url, license_headers, sn_params, sn_out,
                       "ServiceNow third-party settings")
    except Exception as e:
        print(f"  Failed (skipping – project may not be a ServiceNow project): {e}", file=sys.stderr)

    # Metric-project-specific data (optional, when --data-type metric)
    if data_type == "metric":
        print()
        print("=" * 60)
        print(f"Fetching METRIC CONFIGURATION data for '{project_name}'")
        print("=" * 60)
        fetch_metric_project_data(
            session, host, headers, username, customer_name, project_name, out_dir,
        )
    elif data_type:
        print(f"Tip: Pass --data-type metric to also fetch metric configurations.")

    # System-level settings (optional)
    if system_name:
        print()
        print("=" * 60)
        print(f"Fetching SYSTEM-LEVEL data for '{system_name}'")
        print("=" * 60)

        system_id = resolve_system_id(session, host, headers, customer_name, system_name)
        if system_id:
            fetch_system_settings(session, host, headers, customer_name, system_id, out_dir)
        else:
            print(f"Skipping system-level fetch: could not resolve system '{system_name}'", file=sys.stderr)
    else:
        print()
        print("Tip: Pass --system-name to also fetch knowledgebase and notifications settings.")

    print()
    print("Done.")


if __name__ == "__main__":
    main()

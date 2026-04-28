#!/usr/bin/env python3
"""
Fully automated Terraform configuration generator for InsightFinder.

Reads config.yaml and auto-discovers all owned systems + projects via API,
then generates a complete TerraformFiles directory structure.

Usage:
    python auto_generate_terraform.py --config config.yaml
    python auto_generate_terraform.py --config config.yaml --env NBC
    python auto_generate_terraform.py --config config.yaml --output-dir TerraformFiles
    python auto_generate_terraform.py --config config.yaml --dry-run

config.yaml format:
    Delay: 2     # seconds between project API calls AND between HTTP retries (0 = no delay)
    Retries: 3   # max HTTP-level retries on non-200 responses (default 3)
    NBC:
      base_url: https://nbc.insightfinder.com/
      username: nbcAdmin
      licensekey: xyzzzz
      project_types: [metric, log]
      terraform_version: 1.7.0        # optional; defaults to ">= 1.6.1"
      only_process:                   # optional; omit to process everything
        systems: ["System A"]         # process all projects in these systems
        projects: ["Project X"]       # also process these projects (original system folder structure)
    PROD:
      base_url: https://app.insightfinder.com/
      username: mustafa
      licensekey: xyzzz
      project_types: [log]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    print("Missing dependency: pyyaml. Install with: pip install pyyaml", file=sys.stderr)
    raise

try:
    import requests
except ImportError:
    print("Missing dependency: requests. Install with: pip install requests", file=sys.stderr)
    raise

# Reuse field-generation helpers from existing script
from generate_terraform_cli import (
    format_terraform_value,
    convert_keywords_to_log_labels,
    convert_json_keys_to_terraform,
    generate_system_settings_config,
    generate_servicenow_env_config,
    _parse_servicenow_entry,
    _sn_safe_name,
    parse_project_settings,
)


# ---------------------------------------------------------------------------
# Runtime config (overridden by run() from config.yaml)
# ---------------------------------------------------------------------------

_RETRY_DELAY: float = 1.0   # seconds to sleep between HTTP retries
_MAX_RETRIES: int = 3        # max attempts per HTTP request


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def tf_resource_name(name: str) -> str:
    """Convert any string to a valid Terraform resource identifier."""
    return re.sub(r'[^a-z0-9_]', '_', name.lower())


# Map config project_type strings to API dataType values (case-insensitive)
DATATYPE_MAP: Dict[str, List[str]] = {
    "log":        ["log"],
    "metric":     ["metric"],
    "alert":      ["log", "alert"],
    "trace":      ["trace"],
    "deployment": ["deployment"],
}


def load_config(config_path: str) -> Dict[str, Any]:
    with open(config_path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def make_session(no_ssl_verify: bool = False) -> requests.Session:
    s = requests.Session()
    s.verify = not no_ssl_verify
    return s


def _build_curl(url: str, headers: Dict[str, str], params: Optional[Dict]) -> str:
    """Return a curl command string equivalent to the GET request (for debugging)."""
    import urllib.parse
    header_flags = " ".join(f"-H '{k}: {v}'" for k, v in headers.items())
    if params:
        qs = urllib.parse.urlencode(params)
        full_url = f"{url}?{qs}"
    else:
        full_url = url
    return f"curl -X GET '{full_url}' {header_flags}"


def _get(session: requests.Session, url: str, headers: Dict[str, str],
         params: Optional[Dict] = None,
         max_retries: Optional[int] = None,
         retry_delay: Optional[float] = None) -> Optional[requests.Response]:
    """GET with retries on both network errors and non-200 HTTP responses."""
    attempts = max_retries if max_retries is not None else _MAX_RETRIES
    delay = retry_delay if retry_delay is not None else _RETRY_DELAY

    last_resp: Optional[requests.Response] = None
    for attempt in range(1, attempts + 1):
        try:
            resp = session.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code == 200:
                return resp
            # Non-200: print details and maybe retry
            last_resp = resp
            print(f"  [attempt {attempt}/{attempts}] HTTP {resp.status_code} for {url}", file=sys.stderr)
            print(f"  curl: {_build_curl(url, headers, params)}", file=sys.stderr)
            print(f"  params: {json.dumps(params, indent=4) if params else '(none)'}", file=sys.stderr)
            body = resp.text.strip()
            print(f"  body:  {body[:500] if body else '(empty)'}", file=sys.stderr)
            if attempt < attempts:
                print(f"  Retrying in {delay}s...", file=sys.stderr)
                time.sleep(delay)
        except requests.RequestException as e:
            if attempt < attempts:
                print(f"  [attempt {attempt}/{attempts}] Network error: {e} — retrying in {delay}s...",
                      file=sys.stderr)
                time.sleep(delay)
            else:
                print(f"  Request failed after {attempts} attempts: {e}", file=sys.stderr)
                return None
    return last_resp  # return last non-200 response so caller can inspect status_code


def fetch_json(session: requests.Session, url: str, headers: Dict[str, str],
               params: Optional[Dict] = None) -> Optional[Any]:
    resp = _get(session, url, headers, params)
    if resp is None:
        return None
    if resp.status_code != 200:
        # Details already printed by _get; just surface the final status here.
        print(f"  Warning: HTTP {resp.status_code} for {url} (all retries exhausted)", file=sys.stderr)
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def api_headers(username: str, api_key: str, use_license: bool = False) -> Dict[str, str]:
    key_header = "X-License-Key" if use_license else "X-API-Key"
    return {
        "X-User-Name": username,
        key_header: api_key,
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# InsightFinder API calls
# ---------------------------------------------------------------------------

def get_own_systems(session: requests.Session, host: str,
                    username: str, api_key: str, customer_name: str) -> List[Dict]:
    """Return list of system dicts from ownSystemArr only."""
    url = f"{host.rstrip('/')}/api/external/v1/systemframework"
    headers = api_headers(username, api_key)
    params = {"customerName": customer_name, "needDetail": "true", "tzOffset": "0"}

    data = fetch_json(session, url, headers, params)
    if not data:
        print(f"  Could not fetch system framework for {customer_name}", file=sys.stderr)
        return []

    systems = []
    for s in data.get("ownSystemArr", []):
        try:
            system = json.loads(s) if isinstance(s, str) else s
            systems.append(system)
        except (json.JSONDecodeError, TypeError):
            continue
    return systems


def get_system_display_name(system: Dict) -> str:
    return (
        system.get("systemDisplayName")
        or (system.get("systemKey") or {}).get("systemName")
        or system.get("systemName")
        or "unknown"
    )


def get_system_id(system: Dict) -> str:
    return (
        (system.get("systemKey") or {}).get("systemName")
        or system.get("systemId")
        or system.get("systemName")
        or ""
    )


def filter_projects_by_type(project_list: List[Dict], project_types: List[str]) -> List[Dict]:
    if not project_types:
        return project_list
    allowed = set()
    for pt in project_types:
        allowed.update(DATATYPE_MAP.get(pt.lower(), [pt.lower()]))
    return [p for p in project_list if (p.get("dataType") or "").lower() in allowed]


def fetch_project_mode(session: requests.Session, base: str, username: str,
                       api_key: str, project_name: str) -> Optional[int]:
    """Fetch the process mode for a project from /api/v1/logdedicatedmode.

    This endpoint uses cookie-based auth (Cookie: userName=<username>) in addition
    to query params, mirroring DoRequestWithCookieAuth in the Go client.
    """
    url = f"{base}/api/v1/logdedicatedmode"
    params = {"userName": username, "projectName": project_name, "licenseKey": api_key}
    cookie_headers = {"Cookie": f"userName={username};", "Content-Type": "application/json"}
    resp = _get(session, url, cookie_headers, params)
    if resp is None or resp.status_code != 200:
        return None
    try:
        data = resp.json()
        entries = data.get("data") or []
        if entries:
            return entries[0].get("processMode")
    except (ValueError, KeyError, IndexError, TypeError):
        pass
    return None


def fetch_project_data(session: requests.Session, host: str, username: str,
                       api_key: str, customer_name: str, project_name: str,
                       is_metric: bool = False) -> Dict:
    """Fetch all project-level API data. Returns a dict with all fetched data."""
    headers = api_headers(username, api_key)
    lic_headers = api_headers(username, api_key, use_license=True)
    base = host.rstrip('/')
    result: Dict[str, Any] = {}

    # 1. Keywords
    kw = fetch_json(session, f"{base}/api/external/v1/projectkeywords",
                    headers, {"projectName": project_name})
    result["keywords"] = (kw or {}).get("keywords", {})

    # 2. Project settings
    project_list_param = [{"projectName": project_name, "customerName": customer_name}]
    settings = fetch_json(session, f"{base}/api/external/v1/watch-tower-setting",
                          headers, {"projectList": json.dumps(project_list_param)})
    result["settings"] = settings

    # 3. Summary/metafield settings
    summary = fetch_json(session, f"{base}/api/external/v1/logsummarysettings",
                         headers, {"projectName": project_name})
    result["summary"] = summary

    # 4. JSON key settings
    jsonkeys = fetch_json(session, f"{base}/api/external/v1/logjsontype",
                          headers, {"projectName": project_name})
    result["jsonkeys"] = jsonkeys

    # 5. ServiceNow settings (gracefully skip non-SN projects)
    sn = fetch_json(session, f"{base}/api/external/v1/thirdpartysetting",
                    lic_headers,
                    {"projectName": project_name, "cloudType": "ServiceNow",
                     "tzOffset": "-18000000"})
    # Only keep if response looks like real SN data
    result["servicenow"] = sn if sn and isinstance(sn, dict) and sn.get("host") else None

    # 6. Holiday settings — response: {"holidayName": "startDate,endDate", ...}
    holidays = fetch_json(session, f"{base}/api/external/v1/holiday",
                          lic_headers,
                          {"projectName": project_name, "customerName": customer_name})
    result["holidays"] = holidays if isinstance(holidays, dict) else {}

    # 7. Metric configurations (only for Metric-type projects)
    if is_metric:
        metric_cfgs, pattern_id_rule = fetch_metric_configurations(
            session, host, username, api_key, customer_name, project_name,
        )
        result["metric_configurations"] = metric_cfgs
        result["pattern_id_generation_rule"] = pattern_id_rule

    # 8. Instance down notification settings
    instance_down_resp = fetch_json(
        session, f"{base}/api/external/v1/projects/update",
        headers, {"operation": "display", "projectName": project_name,
                  "customerName": customer_name},
    )
    if instance_down_resp and instance_down_resp.get("success"):
        proj_model = (instance_down_resp.get("data") or {}).get("projectModelAllJSON") or {}
        result["instance_down"] = {
            "projectName": proj_model.get("projectName", project_name),
            "instanceDownEnable": proj_model.get("instanceDownEnable", False),
            "instanceDownDampening": proj_model.get("instanceDownDampening", 3600000),
            "instanceDownThreshold": proj_model.get("instanceDownThreshold", 3600000),
            "instanceDownReportNumber": proj_model.get("instanceDownReportNumber", 50),
            "instanceDownEmails": proj_model.get("instanceDownEmails") or [],
        }
    else:
        result["instance_down"] = None

    # 9. Process mode (logdedicatedmode API — uses cookie auth)
    result["mode"] = fetch_project_mode(session, base, username, api_key, project_name)

    return result


def fetch_metric_configurations(session: requests.Session, host: str, username: str,
                                api_key: str, customer_name: str,
                                project_name: str) -> Tuple[Dict[str, Any], int]:
    """Fetch all metric configuration data for a metric project.

    Returns:
        (metric_configs, pattern_id_generation_rule)

        metric_configs is a dict: metric_name -> {
            "escalate_incident_components": [...],
            "ignored_components": [...],
            "alert_settings": [...],   # list of setting dicts from API
        }
        pattern_id_generation_rule is the integer from the componentmetricupdate response.
    """
    headers = api_headers(username, api_key)
    base = host.rstrip('/')
    metric_configs: Dict[str, Any] = {}
    pattern_id_rule = 1

    # 1. Escalate-incident component map
    escalate_resp = fetch_json(
        session, f"{base}/api/external/v1/metriccomponent", headers,
        {"projectName": project_name, "customerName": customer_name,
         "operation": "escalateIncident", "tzOffset": "-14400000"},
    )
    escalate_map: Dict[str, List[str]] = {}
    if escalate_resp:
        encoded = escalate_resp.get("componentEscalateIncident", "")
        if encoded:
            try:
                for entry in json.loads(encoded):
                    metric = entry["metricLevelPrimaryKey"]["metricName"]
                    escalate_map[metric] = entry.get("componentNameSet", [])
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    # 2. Ignored component map
    ignored_resp = fetch_json(
        session, f"{base}/api/external/v1/metriccomponent", headers,
        {"projectName": project_name, "customerName": customer_name,
         "operation": "ignored", "tzOffset": "-14400000"},
    )
    ignored_map: Dict[str, List[str]] = {}
    if ignored_resp:
        encoded = ignored_resp.get("componentIgnored", "")
        if encoded:
            try:
                for entry in json.loads(encoded):
                    metric = entry["metricLevelPrimaryKey"]["metricName"]
                    ignored_map[metric] = entry.get("componentNameSet", [])
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    # 3. Alert settings — single bulk fetch for all metrics at once
    all_metrics = sorted(set(escalate_map) | set(ignored_map))
    alert_resp = fetch_json(
        session, f"{base}/api/external/v1/componentmetricupdate", headers,
        {
            "onlyIsKpi": "false",
            "onlyComputeDifference": "false",
            "projectName": f"{project_name}@{username}",
            "start": "0",
            "limit": "500000",
            "metricFilter": "",
            "customerName": customer_name,
            "tzOffset": "-14400000",
        },
    )

    smetric_to_entry: Dict[str, Any] = {}
    if alert_resp:
        pattern_id_rule = alert_resp.get("patternIdGenerationRule", pattern_id_rule)
        if not alert_resp.get("reachEnd", False):
            print("  Warning: reachEnd is not true — metric alert settings may be incomplete.",
                  file=sys.stderr)
        for entry in alert_resp.get("metricSetting", []):
            gs = entry.get("globalSetting") or {}
            smetric = gs.get("smetric", "")
            if smetric:
                smetric_to_entry[smetric] = entry

    for metric_name in all_metrics:
        entry = smetric_to_entry.get(metric_name)
        if entry is None:
            print(f"  Skipping metric '{metric_name}' — no settings found in bulk response.")
            continue
        gs = entry.get("globalSetting") or {}
        alert_settings: List[Dict] = [gs]
        for comp_setting in entry.get("componentLevelSettingList", []):
            alert_settings.append(comp_setting)
        metric_configs[metric_name] = {
            "escalate_incident_components": escalate_map.get(metric_name, []),
            "ignored_components": ignored_map.get(metric_name, []),
            "alert_settings": alert_settings,
        }

    return metric_configs, pattern_id_rule


def fetch_system_level_settings(session: requests.Session, host: str, username: str,
                                api_key: str, customer_name: str,
                                system_id: str) -> Tuple[Any, Any, Any]:
    """Return (kb_global, kb_incident, notifications) for the given system."""
    headers = api_headers(username, api_key)
    base = host.rstrip('/')
    sys_ids_json = json.dumps([system_id])

    kb_global = fetch_json(session, f"{base}/api/external/v1/globalknowledgebasesetting",
                           headers, {"customerName": customer_name, "systemIds": sys_ids_json})
    if isinstance(kb_global, list) and kb_global:
        kb_global = kb_global[0]

    kb_incident = fetch_json(session, f"{base}/api/external/v2/IncidentPredictionSetting",
                             headers, {"customerName": customer_name, "systemIds": sys_ids_json})
    if isinstance(kb_incident, list) and kb_incident:
        kb_incident = kb_incident[0]

    all_notif = fetch_json(session, f"{base}/api/external/v2/healthviewsetting",
                           headers, {"customerName": customer_name})
    notifications = None
    if isinstance(all_notif, dict) and system_id in all_notif:
        notifications = all_notif[system_id]

    return kb_global, kb_incident, notifications


def fetch_system_down_setting(session: requests.Session, host: str, username: str,
                               api_key: str, customer_name: str,
                               system_id: str) -> Optional[Dict]:
    """Return system down notification settings for the given system, or None."""
    headers = api_headers(username, api_key)
    base = host.rstrip('/')
    sys_ids_json = json.dumps([system_id])
    data = fetch_json(session, f"{base}/api/external/v2/systemdownsetting",
                      headers, {"customerName": customer_name, "systemIds": sys_ids_json})
    print(f"    [DEBUG] systemdownsetting raw response for {system_id}: {data!r}", file=sys.stderr)
    # Handle both raw list and wrapped {"data": [...], "success": true} responses
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if isinstance(data, list) and data:
        result = data[0]
        print(f"    [DEBUG] systemdownsetting parsed: {result!r}", file=sys.stderr)
        return result
    return None


def fetch_insights_report_setting(session: requests.Session, host: str, username: str,
                                   api_key: str, customer_name: str,
                                   system_id: str) -> Optional[Dict]:
    """Return insights report (daily + weekly) settings for the given system, or None."""
    headers = api_headers(username, api_key)
    base = host.rstrip('/')
    sys_ids_json = json.dumps([system_id])
    data = fetch_json(session, f"{base}/api/external/v1/insightsreportsetting",
                      headers, {"customerName": customer_name, "systemIds": sys_ids_json})
    if isinstance(data, list) and data:
        return data[0]
    return None


def fetch_miscellaneous_settings(session: requests.Session, host: str, username: str,
                                 api_key: str, customer_name: str,
                                 system_id: str) -> Optional[Dict]:
    """Return miscellaneous system framework settings for the given system, or None."""
    headers = api_headers(username, api_key)
    base = host.rstrip('/')
    data = fetch_json(session, f"{base}/api/external/v1/systemframework",
                      headers, {"customerName": customer_name, "needDetail": "false",
                                "tzOffset": "-18000000"})
    if not isinstance(data, dict):
        return None
    for entry_str in data.get("ownSystemArr", []):
        try:
            entry = json.loads(entry_str) if isinstance(entry_str, str) else entry_str
        except (json.JSONDecodeError, TypeError):
            continue
        entry_system_id = (entry.get("systemKey") or {}).get("systemName", "")
        if entry_system_id != system_id:
            continue
        misc: Dict = {"longTerm": entry.get("longTerm", False)}
        system_setting_str = entry.get("systemSetting", "")
        if system_setting_str:
            try:
                inner = json.loads(system_setting_str)
                misc["shouldAutoShare"] = inner.get("shouldAutoShare", False)
                misc["rootCauseReverseEntryFilterThreshold"] = inner.get(
                    "rootCauseReverseEntryFilterThreshold", 0)
                misc["enableCompositeTimeline"] = inner.get("enableCompositeTimeline", False)
            except (json.JSONDecodeError, TypeError):
                pass
        return misc
    return None


def fetch_servicenow_env_configs(session: requests.Session, host: str,
                                 username: str, api_key: str) -> List[Dict]:
    """Fetch all environment-level ServiceNow configurations from the API.

    Returns a list of parsed config dicts (one per extServiceAllInfo entry).
    """
    url = f"{host.rstrip('/')}/api/external/v1/system/externalServlies/list"
    headers = api_headers(username, api_key)
    params = {"serviceProvider": "ServiceNow", "tzOffset": "-14400000"}

    data = fetch_json(session, url, headers, params)
    if not data or not data.get("success"):
        return []

    entries_raw = data.get("extServiceAllInfo", [])
    configs = []
    for entry in entries_raw:
        parsed = _parse_servicenow_entry(entry)
        if parsed:
            configs.append(parsed)
    return configs


def _build_system_id_to_name(systems: List[Dict]) -> Dict[str, str]:
    """Build a mapping from system ID (hash) to display name from the systems list."""
    id_to_name: Dict[str, str] = {}
    for system in systems:
        system_id = get_system_id(system)
        display_name = get_system_display_name(system)
        if system_id and display_name:
            id_to_name[system_id] = display_name
    return id_to_name


def _servicenow_env_variables_tf(sn_configs: List[Dict]) -> str:
    """Generate variables.tf for the env-level servicenow root module."""
    lines = [
        'variable "if_username" {',
        '  description = "InsightFinder account username"',
        '  type        = string',
        '}',
        '',
        'variable "if_licensekey" {',
        '  description = "InsightFinder license key"',
        '  type        = string',
        '  sensitive   = true',
        '}',
        '',
        'variable "base_url" {',
        '  description = "Base URL of the InsightFinder instance"',
        '  type        = string',
        '}',
    ]

    for config in sn_configs:
        safe_name = _sn_safe_name(config["account"], config["service_host"])
        var_prefix = f"sn_{safe_name}"
        account = config["account"]
        service_host = config["service_host"]

        lines += [
            '',
            f'variable "{var_prefix}_password" {{',
            f'  description = "Password for ServiceNow account {account} at {service_host}"',
            '  type        = string',
            '  sensitive   = true',
            '}',
        ]

        if config.get("auth_type") == "oauth":
            lines += [
                '',
                f'variable "{var_prefix}_app_key" {{',
                f'  description = "App key for ServiceNow account {account} at {service_host}"',
                '  type        = string',
                '  sensitive   = true',
                '}',
                '',
                f'variable "{var_prefix}_app_id" {{',
                f'  description = "App id for ServiceNow account {account} at {service_host}"',
                '  type        = string',
                '  sensitive   = true',
                '}',
            ]

    return '\n'.join(lines) + '\n'


def _servicenow_env_tfvars(base_url: str, sn_configs: List[Dict]) -> str:
    """Generate terraform.tfvars for the env-level servicenow root module."""
    lines = [
        '# Environment-level ServiceNow integration settings.',
        '# ⚠️  Sensitive values (credentials) are loaded from GitHub Secrets.',
        '#     See workflows for secret naming convention: <ENV>_SN_<ACCOUNT>_<VARNAME>',
        '',
        f'base_url = "{base_url}"',
        '',
        '# InsightFinder credentials — loaded from secrets',
        '# if_username   = "..."  # Set via GitHub Secrets',
        '# if_licensekey = "..."  # Set via GitHub Secrets',
    ]

    for config in sn_configs:
        safe_name = _sn_safe_name(config["account"], config["service_host"])
        var_prefix = f"sn_{safe_name}"
        lines += [
            '',
            f'# ServiceNow: {config["account"]} @ {config["service_host"]}',
            f'# {var_prefix}_password = "..."  # Set via GitHub Secrets',
        ]
        if config.get("auth_type") == "oauth":
            lines.append(f'# {var_prefix}_app_key = "..."  # Set via GitHub Secrets')
            lines.append(f'# {var_prefix}_app_id = "..."  # Set via GitHub Secrets')

    return '\n'.join(lines) + '\n'


def process_env_servicenow(session: requests.Session, env_name: str, env_cfg: Dict,
                           systems: List[Dict], output_dir: str,
                           dry_run: bool) -> int:
    """Generate env-level ServiceNow Terraform files under ENV/servicenow/.

    Returns the number of ServiceNow configs generated (0 if none found).
    """
    base_url = env_cfg["base_url"].rstrip('/')
    username = env_cfg["username"]
    api_key = env_cfg["licensekey"]
    terraform_version = str(env_cfg.get("terraform_version", ">= 1.6.1"))

    print(f"\n  Fetching environment-level ServiceNow configurations...")
    sn_configs = fetch_servicenow_env_configs(session, base_url, username, api_key)

    if not sn_configs:
        print(f"  No ServiceNow configurations found — skipping servicenow module.")
        return 0

    print(f"  Found {len(sn_configs)} ServiceNow configuration(s).")

    # Resolve system IDs → display names using the already-fetched systems list
    system_id_to_name = _build_system_id_to_name(systems)
    for config in sn_configs:
        config["system_names"] = [
            system_id_to_name.get(sid, sid) for sid in config.get("system_ids", [])
        ]

    env_sn_dir = os.path.join(output_dir, env_name, "servicenow")

    # versions.tf — dedicated S3 backend key for the servicenow root module
    write_file(os.path.join(env_sn_dir, "versions.tf"),
               _versions_tf(env_name, "servicenow", terraform_version), dry_run)

    write_file(os.path.join(env_sn_dir, "provider.tf"),
               _provider_tf(), dry_run)

    write_file(os.path.join(env_sn_dir, "variables.tf"),
               _servicenow_env_variables_tf(sn_configs), dry_run)

    write_file(os.path.join(env_sn_dir, "terraform.tfvars"),
               _servicenow_env_tfvars(base_url, sn_configs), dry_run)

    # Write one dedicated .tf file per ServiceNow config, named by host subdomain
    for config in sn_configs:
        try:
            from urllib.parse import urlparse as _urlparse
            _host = _urlparse(config["service_host"]).netloc or config["service_host"]
            _subdomain = _host.split('.')[0]
        except Exception:
            _subdomain = _sn_safe_name(config["account"], config["service_host"])
        tf_filename = re.sub(r'[^a-z0-9-]', '-', _subdomain.lower()) + ".tf"
        sn_hcl = generate_servicenow_env_config(
            sn_entries=[config],
            include_provider=False,
            use_vars=True,
            system_id_to_name=system_id_to_name,
        )
        write_file(os.path.join(env_sn_dir, tf_filename), sn_hcl, dry_run)
        print(f"    ServiceNow: {config['account']} @ {config['service_host']}"
              + (f" → {len(config['system_names'])} system(s)" if config.get('system_names') else ""))

    return len(sn_configs)


# ---------------------------------------------------------------------------
# Terraform file generators
# ---------------------------------------------------------------------------

def _versions_tf(env_name: str, system_name: str, terraform_version: str = ">= 1.6.1") -> str:
    key = f"{env_name}/{system_name}/terraform.tfstate"
    return f'''\
terraform {{
  required_providers {{
    insightfinder = {{
      source  = "insightfinder/insightfinder"
      version = "{terraform_version}"
    }}
  }}

  backend "s3" {{
    bucket         = "insightfinder-terraform-state"
    key            = "{key}"
    region         = "us-east-1"
    dynamodb_table = "insightfinder-terraform-locks"
    encrypt        = true
  }}
}}
'''


def _provider_tf() -> str:
    return '''\
provider "insightfinder" {
  base_url    = var.base_url
  username    = var.if_username
  license_key = var.if_licensekey
}
'''


def _system_variables_tf() -> str:
    return '''\
variable "if_username" {
  description = "InsightFinder account username"
  type        = string
}

variable "if_licensekey" {
  description = "InsightFinder license key"
  type        = string
  sensitive   = true
}

variable "base_url" {
  description = "Base URL of the InsightFinder instance"
  type        = string
}

variable "system_name" {
  description = "InsightFinder system name this workspace manages"
  type        = string
}

variable "servicenow_host" {
  description = "ServiceNow host url"
  type        = string
  default     = ""
}

variable "servicenow_username" {
  description = "ServiceNow service account username"
  type        = string
  default     = ""
}

variable "servicenow_password" {
  description = "ServiceNow service account password"
  type        = string
  sensitive   = true
  default     = ""
}

variable "servicenow_clientid" {
  description = "ServiceNow service account clientId"
  type        = string
  sensitive   = true
  default     = ""
}

variable "servicenow_clientsecret" {
  description = "ServiceNow service account clientSecret"
  type        = string
  sensitive   = true
  default     = ""
}
'''


def _tfvars(base_url: str, system_name: str, servicenow_host: str = "") -> str:
    lines = [
        f"# All environment-specific values for {system_name}.",
        "# ⚠️  Sensitive values (credentials) are loaded from GitHub Secrets.",
        "#     See workflows for secret naming convention: <ENV>_<SYSTEM>_<VARNAME>",
        "",
        f'base_url    = "{base_url}"',
        f'system_name = "{system_name}"',
        "",
        "# InsightFinder credentials — loaded from secrets",
        "# if_username   = \"...\"  # Set via GitHub Secrets",
        "# if_licensekey = \"...\"  # Set via GitHub Secrets",
    ]
    if servicenow_host:
        lines += [
            "",
            "# ServiceNow connection details — passwords/secrets loaded from GitHub",
            f'servicenow_host = "{servicenow_host}"',
            "# servicenow_username     = \"...\"  # Set via GitHub Secrets",
            "# servicenow_password     = \"...\"  # Set via GitHub Secrets",
            "# servicenow_clientid     = \"...\"  # Set via GitHub Secrets",
            "# servicenow_clientsecret = \"...\"  # Set via GitHub Secrets",
        ]
    return "\n".join(lines) + "\n"


def _log_projects_tf(has_servicenow: bool) -> str:
    lines = [
        'module "log_projects" {',
        '  source = "./log-projects"',
        "",
        "  system_name = var.system_name",
    ]
    if has_servicenow:
        lines += [
            "",
            "  # ServiceNow credentials",
            "  servicenow_host         = var.servicenow_host",
            "  servicenow_username     = var.servicenow_username",
            "  servicenow_password     = var.servicenow_password",
            "  servicenow_clientid     = var.servicenow_clientid",
            "  servicenow_clientsecret = var.servicenow_clientsecret",
        ]
    lines += [
        "",
        "  providers = {",
        "    insightfinder = insightfinder",
        "  }",
        "}",
        "",
    ]
    return "\n".join(lines)


def _log_projects_variables_tf(has_servicenow: bool) -> str:
    lines = [
        'variable "system_name" {',
        '  description = "System name passed from parent module"',
        "  type        = string",
        "}",
    ]
    if has_servicenow:
        lines += [
            "",
            'variable "servicenow_host" {',
            '  description = "ServiceNow host url"',
            "  type        = string",
            '  default     = ""',
            "}",
            "",
            'variable "servicenow_username" {',
            '  description = "ServiceNow service account username"',
            "  type        = string",
            '  default     = ""',
            "}",
            "",
            'variable "servicenow_password" {',
            '  description = "ServiceNow service account password"',
            "  type        = string",
            "  sensitive   = true",
            '  default     = ""',
            "}",
            "",
            'variable "servicenow_clientid" {',
            '  description = "ServiceNow service account clientId"',
            "  type        = string",
            "  sensitive   = true",
            '  default     = ""',
            "}",
            "",
            'variable "servicenow_clientsecret" {',
            '  description = "ServiceNow service account clientSecret"',
            "  type        = string",
            "  sensitive   = true",
            '  default     = ""',
            "}",
        ]
    return "\n".join(lines) + "\n"


def _projects_versions_tf() -> str:
    """Child module versions.tf — no version lock, inherited from root."""
    return '''\
terraform {
  required_providers {
    insightfinder = {
      source = "insightfinder/insightfinder"
    }
  }
}
'''


def _generate_holiday_settings_hcl(holidays: Dict[str, str]) -> List[str]:
    """Build holiday_settings = [...] HCL lines.

    API response format: {"holidayName": "MM-DD,MM-DD", ...}
    The start and end dates are separated by a comma.
    """
    if not holidays:
        return []

    lines: List[str] = []
    lines.append("")
    lines.append("  holiday_settings = [")

    items = sorted(holidays.items())
    for idx, (name, date_range) in enumerate(items):
        parts = date_range.split(",", 1)
        start_date = parts[0].strip() if parts else ""
        end_date = parts[1].strip() if len(parts) > 1 else start_date
        is_last = idx == len(items) - 1

        escaped_name = name.replace('\\', '\\\\').replace('"', '\\"')
        lines.append("    {")
        lines.append(f'      name       = "{escaped_name}"')
        lines.append(f'      start_date = "{start_date}"')
        lines.append(f'      end_date   = "{end_date}"')
        lines.append("    }" + ("" if is_last else ","))

    lines.append("  ]")
    return lines


def generate_project_tf(project_name: str, project_data: Dict,
                        system_name: str, is_servicenow_project: bool,
                        data_type: str = "Log",
                        proj_info: Optional[Dict] = None) -> str:
    """Generate a single project's .tf content for use inside the module."""

    # --- Parse settings ---
    settings_raw = project_data.get("settings") or {}
    settings_data: Dict[str, Any] = {}
    if "settingList" in settings_raw:
        for _key, settings_str in settings_raw["settingList"].items():
            try:
                settings_data = parse_project_settings(settings_str)
            except Exception:
                pass
            break

    keywords_data = project_data.get("keywords") or {}

    summary_meta = project_data.get("summary") or {}
    summary_settings: List[str] = summary_meta.get("summarySetting", [])
    metafield_settings: List[str] = summary_meta.get("metaFieldSetting", [])
    dampening_field_settings: List[str] = summary_meta.get("dampeningFieldSetting", [])

    jsonkeys_raw = project_data.get("jsonkeys") or {}
    if isinstance(jsonkeys_raw, list):
        json_keys_data = jsonkeys_raw
    else:
        json_keys_data = jsonkeys_raw.get("jsonKeyList", [])

    servicenow_data = project_data.get("servicenow") if is_servicenow_project else None

    # Skip projects with no meaningful settings to avoid generating empty stubs
    if not (settings_data or keywords_data or json_keys_data or servicenow_data
            or any(project_data.get("holidays") or {})):
        return None

    # --- Build HCL ---
    resource_name = tf_resource_name(project_name)
    cfg: List[str] = []

    cfg.append(f'resource "insightfinder_project" "{resource_name}" {{')
    cfg.append(f'  project_name = "{project_name}"')
    cfg.append(f'  system_name  = var.system_name')
    cfg.append('')

    # project_creation_config
    # Title-case the data_type so the API/provider receives "Log", "Trace", "Deployment" etc.
    hcl_data_type = data_type.capitalize() if data_type else "Log"
    # Derive cloud/agent type from system framework API fields when available
    _pi = proj_info or {}
    cloud_type = (_pi.get("projectCloudType") or "OnPremise").strip()
    _class_type = _pi.get("projectClassType") or ""
    agent_type = _class_type.title() if _class_type else "Historical"
    cfg.append('  project_creation_config = {')
    if is_servicenow_project:
        cfg.append(f'    data_type          = "{hcl_data_type}"')
        cfg.append('    instance_type      = "ServiceNow"')
        cfg.append('    project_cloud_type = "ServiceNow"')
        cfg.append('    insight_agent_type = "Custom"')
        project_name_lower = project_name.lower()
        if "problem" in project_name_lower:
            sn_table = "problem"
        else:
            sn_table = (servicenow_data or {}).get("servicenow_table", "incident")
        cfg.append(f'    servicenow_table   = "{sn_table}"')
    else:
        cfg.append(f'    data_type          = "{hcl_data_type}"')
        cfg.append(f'    instance_type      = "{cloud_type}"')
        cfg.append(f'    project_cloud_type = "{cloud_type}"')
        cfg.append(f'    insight_agent_type = "{agent_type}"')
    cfg.append('  }')
    cfg.append('')

    # All mapped settings attributes
    attribute_mapping = {
        'projectDisplayName': 'project_display_name',
        'projectTimeZone': 'project_time_zone',
        'retentionTime': 'retention_time',
        'UBLRetentionTime': 'ubl_retention_time',
        'alertAverageTime': 'alert_average_time',
        'alertHourlyCost': 'alert_hourly_cost',
        'anomalyDetectionMode': 'anomaly_detection_mode',
        'anomalySamplingInterval': 'anomaly_sampling_interval',
        'avgPerIncidentDowntimeCost': 'avg_per_incident_downtime_cost',
        'baseValueSetting': 'base_value_setting',
        'cValue': 'c_value',
        'causalMinDelay': 'causal_min_delay',
        'causalPredictionSetting': 'causal_prediction_setting',
        'cdfSetting': 'cdf_setting',
        'coldEventThreshold': 'cold_event_threshold',
        'coldNumberLimit': 'cold_number_limit',
        'collectAllRareEventsFlag': 'collect_all_rare_events_flag',
        'componentNameAutoOverwrite': 'component_name_auto_overwrite',
        'dailyModelSpan': 'daily_model_span',
        'disableLogCompressEvent': 'disable_log_compress_event',
        'disableModelKeywordStatsCollection': 'disable_model_keyword_stats_collection',
        'emailSetting': 'email_setting',
        'enableAnomalyScoreEscalation': 'enable_anomaly_score_escalation',
        'enableHotEvent': 'enable_hot_event',
        'enableNewAlertEmail': 'enable_new_alert_email',
        'enableStreamDetection': 'enable_stream_detection',
        'escalationAnomalyScoreThreshold': 'escalation_anomaly_score_threshold',
        'featureOutlierSensitivity': 'feature_outlier_sensitivity',
        'featureOutlierThreshold': 'feature_outlier_threshold',
        'hotEventCalmDownPeriod': 'hot_event_calm_down_period',
        'hotEventDetectionMode': 'hot_event_detection_mode',
        'hotEventThreshold': 'hot_event_threshold',
        'hotNumberLimit': 'hot_number_limit',
        'ignoreAnomalyScoreThreshold': 'ignore_anomaly_score_threshold',
        'ignoreInstanceForKB': 'ignore_instance_for_kb',
        'incidentPredictionEventLimit': 'incident_prediction_event_limit',
        'incidentPredictionWindow': 'incident_prediction_window',
        'incidentRelationSearchWindow': 'incident_relation_search_window',
        'instanceConvertFlag': 'instance_convert_flag',
        'instanceDownEnable': 'instance_down_enable',
        'instanceGroupingUpdate': 'instance_grouping_update',
        'isEdgeBrain': 'is_edge_brain',
        'isGroupingByInstance': 'is_grouping_by_instance',
        'isTracePrompt': 'is_trace_prompt',
        'keywordFeatureNumber': 'keyword_feature_number',
        'keywordSetting': 'keyword_setting',
        'largeProject': 'large_project',
        'llmEvaluationSetting': 'llm_evaluation_setting',
        'logAnomalyEventBaseScore': 'log_anomaly_event_base_score',
        'logDetectionMinCount': 'log_detection_min_count',
        'logDetectionSize': 'log_detection_size',
        'logPatternLimitLevel': 'log_pattern_limit_level',
        'logToLogSettingList': 'log_to_log_setting_list',
        'maxLogModelSize': 'max_log_model_size',
        'maxWebHookRequestSize': 'max_web_hook_request_size',
        'maximumDetectionWaitTime': 'maximum_detection_wait_time',
        'maximumRootCauseResultSize': 'maximum_root_cause_result_size',
        'maximumThreads': 'maximum_threads',
        'minIncidentPredictionWindow': 'min_incident_prediction_window',
        'minValidModelSpan': 'min_valid_model_span',
        'modelKeywordSetting': 'model_keyword_setting',
        'multiHopSearchLevel': 'multi_hop_search_level',
        'multiHopSearchLimit': 'multi_hop_search_limit',
        'multiLineFlag': 'multi_line_flag',
        'newAlertFlag': 'new_alert_flag',
        'newPatternNumberLimit': 'new_pattern_number_limit',
        'newPatternRange': 'new_pattern_range',
        'nlpFlag': 'nlp_flag',
        'normalEventCausalFlag': 'normal_event_causal_flag',
        'pValue': 'p_value',
        'predictionCountThreshold': 'prediction_count_threshold',
        'predictionProbabilityThreshold': 'prediction_probability_threshold',
        'predictionRuleActiveCondition': 'prediction_rule_active_condition',
        'predictionRuleActiveThreshold': 'prediction_rule_active_threshold',
        'predictionRuleFalsePositiveThreshold': 'prediction_rule_false_positive_threshold',
        'predictionRuleInactiveThreshold': 'prediction_rule_inactive_threshold',
        'prettyJsonConvertorFlag': 'pretty_json_convertor_flag',
        'projectModelFlag': 'project_model_flag',
        'proxy': 'proxy',
        'rareAnomalyType': 'rare_anomaly_type',
        'rareEventAlertThresholds': 'rare_event_alert_thresholds',
        'rareNumberLimit': 'rare_number_limit',
        'rootCauseCountThreshold': 'root_cause_count_threshold',
        'rootCauseLogMessageSearchRange': 'root_cause_log_message_search_range',
        'rootCauseProbabilityThreshold': 'root_cause_probability_threshold',
        'rootCauseRankSetting': 'root_cause_rank_setting',
        'samplingInterval': 'sampling_interval',
        'sharedUsernames': 'shared_usernames',
        'showInstanceDown': 'show_instance_down',
        'similaritySensitivity': 'similarity_sensitivity',
        'trainingFilter': 'training_filter',
        'webhookAlertDampening': 'webhook_alert_dampening',
        'webhookBlackListSetStr': 'webhook_black_list_set_str',
        'webhookCriticalKeywordSetStr': 'webhook_critical_keyword_set_str',
        'webhookHeaderList': 'webhook_header_list',
        'webhookTypeSetStr': 'webhook_type_set_str',
        'webhookUrl': 'webhook_url',
        'whitelistNumberLimit': 'whitelist_number_limit',
        'zoneNameKey': 'zone_name_key',
    }

    for api_key, tf_key in attribute_mapping.items():
        if api_key in settings_data:
            value = settings_data[api_key]
            if api_key == 'emailSetting' and isinstance(value, dict):
                if 'awSeverityLevel' not in value:
                    value = dict(value)
                    value['awSeverityLevel'] = 'Major'
            cfg.append(f'  {tf_key} = {format_terraform_value(value)}')

    if 'componentNameAutoOverwrite' not in settings_data:
        cfg.append('  component_name_auto_overwrite = true')

    # Process mode (from /api/v1/logdedicatedmode)
    mode = project_data.get("mode")
    if mode is not None and mode != 0:
        cfg.append(f'  mode = {mode}')

    # ServiceNow block using var references for credentials
    if is_servicenow_project:
        cfg.append('')
        cfg.append('  # ServiceNow third-party settings')
        cfg.append('  project_servicenow_settings = {')
        sn = servicenow_data or {}
        cfg.append(f'    host                 = var.servicenow_host')
        cfg.append(f'    servicenow_user      = var.servicenow_username')
        cfg.append(f'    servicenow_password  = var.servicenow_password')
        cfg.append(f'    client_id            = var.servicenow_clientid')
        cfg.append(f'    client_secret        = var.servicenow_clientsecret')
        cfg.append(f'    instance_field       = "{sn.get("instanceField", "")}"')
        cfg.append(f'    instance_field_regex = "{sn.get("instanceFieldRegex", "")}"')
        cfg.append(f'    timestamp_format     = "{sn.get("timestampFormat", "")}"')
        cfg.append(f'    sysparm_query        = "{sn.get("sysparmQuery", "")}"')
        cfg.append(f'    proxy                = "{sn.get("proxy", "")}"')
        fields_json = json.dumps(sn.get('additionalFields', []))
        cfg.append(f'    additional_fields       = {fields_json}')
        cfg.append(f'    component_name_rule     = "{sn.get("componentNameRule", "")}"')
        sn_import_flag = str(sn.get("serviceNowImportFlag", False)).lower()
        cfg.append(f'    service_now_import_flag = {sn_import_flag}')
        cfg.append('  }')

    # log_label_settings
    log_labels = convert_keywords_to_log_labels(keywords_data)
    if log_labels:
        cfg.append('')
        cfg.append('  log_label_settings = [')
        for i, label in enumerate(log_labels):
            cfg.append('    {')
            cfg.append(f'      label_type       = "{label["label_type"]}",')
            cfg.append(f'      log_label_string = jsonencode({json.dumps(label["log_label_string"])})')
            if i < len(log_labels) - 1:
                cfg.append('    },')
            else:
                cfg.append('    }')
        cfg.append('  ]')

    # json_key_settings
    json_key_settings = convert_json_keys_to_terraform(
        json_keys_data,
        summary_settings=summary_settings,
        metafield_settings=metafield_settings,
        dampening_field_settings=dampening_field_settings,
    )
    if json_key_settings:
        cfg.append('')
        cfg.append('  json_key_settings = [')
        for i, ks in enumerate(json_key_settings):
            cfg.append('    {')
            cfg.append(f'      json_key                = "{ks["json_key"]}"')
            cfg.append(f'      type                    = "{ks["type"]}"')
            cfg.append(f'      summary_setting         = {format_terraform_value(ks["summary_setting"])}')
            cfg.append(f'      metafield_setting       = {format_terraform_value(ks["metafield_setting"])}')
            cfg.append(f'      dampening_field_setting = {format_terraform_value(ks["dampening_field_setting"])}')
            if i < len(json_key_settings) - 1:
                cfg.append('    },')
            else:
                cfg.append('    }')
        cfg.append('  ]')

    # holiday_settings
    cfg.extend(_generate_holiday_settings_hcl(project_data.get("holidays") or {}))

    cfg.append('}')
    return '\n'.join(cfg)


def _metric_projects_tf() -> str:
    lines = [
        'module "metric_projects" {',
        '  source = "./metric-projects"',
        '',
        '  system_name = var.system_name',
        '',
        '  providers = {',
        '    insightfinder = insightfinder',
        '  }',
        '}',
        '',
    ]
    return '\n'.join(lines)


def _metric_projects_variables_tf() -> str:
    return '''\
variable "system_name" {
  description = "System name passed from parent module"
  type        = string
}
'''


def _l2m_projects_tf() -> str:
    lines = [
        'module "l2m_projects" {',
        '  source = "./l2m-projects"',
        '',
        '  system_name = var.system_name',
        '',
        '  providers = {',
        '    insightfinder = insightfinder',
        '  }',
        '}',
        '',
    ]
    return '\n'.join(lines)


def _l2m_projects_variables_tf() -> str:
    return '''\
variable "system_name" {
  description = "System name passed from parent module"
  type        = string
}
'''


def _trace_projects_tf() -> str:
    lines = [
        'module "trace_projects" {',
        '  source = "./trace-projects"',
        '',
        '  system_name = var.system_name',
        '',
        '  providers = {',
        '    insightfinder = insightfinder',
        '  }',
        '}',
        '',
    ]
    return '\n'.join(lines)


def _trace_projects_variables_tf() -> str:
    return '''\
variable "system_name" {
  description = "System name passed from parent module"
  type        = string
}
'''


def _change_events_projects_tf(has_servicenow: bool = False) -> str:
    lines = [
        'module "change_events_projects" {',
        '  source = "./change-events-projects"',
        "",
        "  system_name = var.system_name",
    ]
    if has_servicenow:
        lines += [
            "",
            "  # ServiceNow credentials",
            "  servicenow_host         = var.servicenow_host",
            "  servicenow_username     = var.servicenow_username",
            "  servicenow_password     = var.servicenow_password",
            "  servicenow_clientid     = var.servicenow_clientid",
            "  servicenow_clientsecret = var.servicenow_clientsecret",
        ]
    lines += [
        "",
        "  providers = {",
        "    insightfinder = insightfinder",
        "  }",
        "}",
        "",
    ]
    return "\n".join(lines)


def _change_events_projects_variables_tf(has_servicenow: bool = False) -> str:
    lines = [
        'variable "system_name" {',
        '  description = "System name passed from parent module"',
        "  type        = string",
        "}",
    ]
    if has_servicenow:
        lines += [
            "",
            'variable "servicenow_host" {',
            '  description = "ServiceNow host url"',
            "  type        = string",
            '  default     = ""',
            "}",
            "",
            'variable "servicenow_username" {',
            '  description = "ServiceNow service account username"',
            "  type        = string",
            '  default     = ""',
            "}",
            "",
            'variable "servicenow_password" {',
            '  description = "ServiceNow service account password"',
            "  type        = string",
            "  sensitive   = true",
            '  default     = ""',
            "}",
            "",
            'variable "servicenow_clientid" {',
            '  description = "ServiceNow service account clientId"',
            "  type        = string",
            "  sensitive   = true",
            '  default     = ""',
            "}",
            "",
            'variable "servicenow_clientsecret" {',
            '  description = "ServiceNow service account clientSecret"',
            "  type        = string",
            "  sensitive   = true",
            '  default     = ""',
            "}",
        ]
    return "\n".join(lines) + "\n"


def _incident_projects_tf() -> str:
    lines = [
        'module "incident_projects" {',
        '  source = "./incident-projects"',
        '',
        '  system_name = var.system_name',
        '',
        '  providers = {',
        '    insightfinder = insightfinder',
        '  }',
        '}',
        '',
    ]
    return '\n'.join(lines)


def _incident_projects_variables_tf() -> str:
    return '''\
variable "system_name" {
  description = "System name passed from parent module"
  type        = string
}
'''


_ALERT_SETTING_FIELD_MAP: List[Tuple[str, str, str]] = [
    # (api_key, tf_attr, type)
    ("componentName",                      "component_name",                          "string"),
    ("thresholdAlertLowerBound",           "threshold_alert_lower_bound",             "string"),
    ("thresholdAlertUpperBound",           "threshold_alert_upper_bound",             "string"),
    ("thresholdAlertLowerBoundNegative",   "threshold_alert_lower_bound_negative",    "string"),
    ("thresholdAlertUpperBoundNegative",   "threshold_alert_upper_bound_negative",    "string"),
    ("thresholdNoAlertLowerBound",         "threshold_no_alert_lower_bound",          "string"),
    ("thresholdNoAlertUpperBound",         "threshold_no_alert_upper_bound",          "string"),
    ("thresholdNoAlertLowerBoundNegative", "threshold_no_alert_lower_bound_negative", "string"),
    ("thresholdNoAlertUpperBoundNegative", "threshold_no_alert_upper_bound_negative", "string"),
    ("incidentAlertLowerBound",            "incident_alert_lower_bound",              "string"),
    ("incidentAlertUpperBound",            "incident_alert_upper_bound",              "string"),
    ("incidentAlertLowerBoundNegative",    "incident_alert_lower_bound_negative",     "string"),
    ("incidentAlertUpperBoundNegative",    "incident_alert_upper_bound_negative",     "string"),
    ("incidentNoAlertLowerBound",          "incident_no_alert_lower_bound",           "string"),
    ("incidentNoAlertUpperBound",          "incident_no_alert_upper_bound",           "string"),
    ("incidentNoAlertLowerBoundNegative",  "incident_no_alert_lower_bound_negative",  "string"),
    ("incidentNoAlertUpperBoundNegative",  "incident_no_alert_upper_bound_negative",  "string"),
    ("isKPI",                              "is_kpi",                                  "bool"),
    ("isFlappingResultOnly",               "is_flapping_result_only",                 "bool"),
    ("incidentDurationThreshold",          "incident_duration_threshold",             "int"),
    ("detectionType",                      "detection_type",                          "string"),
    ("cValueOverride",                     "c_value_override",                        "nullable_int"),
    ("highCValueOverride",                 "high_c_value_override",                   "nullable_int"),
    ("patternNameHigher",                  "pattern_name_higher",                     "string"),
    ("patternNameLower",                   "pattern_name_lower",                      "string"),
    ("metricType",                         "metric_type",                             "string"),
    ("fillZero",                           "fill_zero",                               "bool"),
    # rougeValue handled separately
    ("enableBaselineNearConstance",        "enable_baseline_near_constance",          "bool"),
    ("computeDifference",                  "compute_difference",                      "bool"),
    ("anomalyGapToleranceDuration",        "anomaly_gap_tolerance_duration",          "int"),
]


def _format_alert_setting_value(value: Any, field_type: str) -> str:
    """Format a single alert setting field value for HCL output."""
    if field_type == "bool":
        return "true" if value else "false"
    elif field_type == "int":
        return str(int(value))
    elif field_type == "nullable_int":
        return "null" if value is None else str(int(value))
    else:  # string
        escaped = str(value).replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'


def _format_rouge_value(raw: Any) -> str:
    """Format rougeValue from the API GET response for HCL.

    The GET API returns rougeValue as a JSON string like '{"l":NaN,"s":NaN}' or "null".
    In Terraform HCL we emit it as a string attribute or null.
    """
    if raw is None:
        return "null"
    s = str(raw).strip()
    if s == "" or s == "null":
        return "null"
    # It's a non-null string like {"l":NaN,"s":NaN} — emit as a quoted HCL string
    escaped = s.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def _generate_metric_configurations_hcl(metric_configs: Dict[str, Any]) -> List[str]:
    """Build the metric_configurations = [...] HCL lines for a metric project resource.

    Each entry in metric_configs is:
      metric_name -> {
        "escalate_incident_components": [...],
        "ignored_components": [...],
        "alert_settings": [{ <API fields> }, ...],
      }
    """
    if not metric_configs:
        return []

    lines: List[str] = []
    lines.append("")
    lines.append("  metric_configurations = [")

    metrics = [m for m in sorted(metric_configs.keys())
               if metric_configs[m].get("alert_settings")]
    for metric_idx, metric_name in enumerate(metrics):
        cfg = metric_configs[metric_name]
        is_last_metric = metric_idx == len(metrics) - 1

        lines.append("    {")
        lines.append(f'      metric_name = "{metric_name}"')

        # escalate_incident_components
        escalate = cfg.get("escalate_incident_components") or []
        comps = ", ".join(f'"{c}"' for c in escalate)
        lines.append(f"      escalate_incident_components = [{comps}]")

        # ignored_components
        ignored = cfg.get("ignored_components") or []
        comps = ", ".join(f'"{c}"' for c in ignored)
        lines.append(f"      ignored_components = [{comps}]")

        # metric_alert_settings
        alert_settings = cfg.get("alert_settings") or []
        lines.append("")
        lines.append("      metric_alert_settings = [")
        for s_idx, setting in enumerate(alert_settings):
            is_last_setting = s_idx == len(alert_settings) - 1
            lines.append("        {")
            for api_key, tf_attr, field_type in _ALERT_SETTING_FIELD_MAP:
                # nullable_int fields are always emitted (null when absent)
                if field_type == "nullable_int":
                    val_hcl = _format_alert_setting_value(setting.get(api_key), field_type)
                elif api_key in setting:
                    val_hcl = _format_alert_setting_value(setting[api_key], field_type)
                else:
                    continue
                lines.append(f"          {tf_attr} = {val_hcl}")
            # rougeValue — special handling
            rouge_hcl = _format_rouge_value(setting.get("rougeValue"))
            lines.append(f"          rouge_value = {rouge_hcl}")
            lines.append("        }" + ("" if is_last_setting else ","))
        lines.append("      ]")

        lines.append("    }" + ("" if is_last_metric else ","))

    lines.append("  ]")
    return lines


def generate_metric_project_tf(project_name: str, project_data: Dict,
                                system_name: str, proj_info: Dict) -> str:
    """Generate a single metric project's .tf content for insightfinder_metric_project."""

    # Parse settings from watch-tower-setting response (same format as regular projects)
    settings_raw = project_data.get("settings") or {}
    settings_data: Dict[str, Any] = {}
    if "settingList" in settings_raw:
        for _key, settings_str in settings_raw["settingList"].items():
            try:
                settings_data = parse_project_settings(settings_str)
            except Exception:
                pass
            break

    resource_name = tf_resource_name(project_name)
    cloud_type = (proj_info.get("projectCloudType") or proj_info.get("cloudType") or "OnPremise").strip()
    _class_type = proj_info.get("projectClassType") or ""
    agent_type = _class_type.title() if _class_type else "Custom"
    cfg: List[str] = []

    cfg.append(f'resource "insightfinder_metric_project" "{resource_name}" {{')
    cfg.append(f'  project_name = "{project_name}"')
    cfg.append(f'  system_name  = var.system_name')
    cfg.append('')

    cfg.append('  project_creation_config = {')
    cfg.append('    data_type          = "Metric"')
    cfg.append(f'    instance_type      = "{cloud_type}"')
    cfg.append(f'    project_cloud_type = "{cloud_type}"')
    cfg.append(f'    insight_agent_type = "{agent_type}"')
    cfg.append('  }')
    cfg.append('')

    metric_attribute_mapping = {
        'projectDisplayName': 'project_display_name',
        'projectTimeZone': 'project_time_zone',
        'retentionTime': 'retention_time',
        'UBLRetentionTime': 'ubl_retention_time',
        'samplingInterval': 'sampling_interval',
        'cValue': 'c_value',
        'pValue': 'p_value',
        'highRatioCValue': 'high_ratio_c_value',
        'maximumHint': 'maximum_hint',
        'dynamicBaselineDetectionFlag': 'dynamic_baseline_detection_flag',
        'positiveBaselineViolationFactor': 'positive_baseline_violation_factor',
        'negativeBaselineViolationFactor': 'negative_baseline_violation_factor',
        'enablePeriodAnomalyFilter': 'enable_period_anomaly_filter',
        'enableUBLDetect': 'enable_ubl_detect',
        'enableCumulativeDetect': 'enable_cumulative_detect',
        'modelSpan': 'model_span',
        'enableMetricDataPrediction': 'enable_metric_data_prediction',
        'enableBaselineDetectionDoubleVerify': 'enable_baseline_detection_double_verify',
        'enableFillGap': 'enable_fill_gap',
        'enableStoreFilledGap': 'enable_store_filled_gap',
        'gapFillingTrainingDataLength': 'gap_filling_training_data_length',
        'patternIdGenerationRule': 'pattern_id_generation_rule',
        'anomalyGapToleranceCount': 'anomaly_gap_tolerance_count',
        'filterByAnomalyInBaselineGeneration': 'filter_by_anomaly_in_baseline_generation',
        'baselineDuration': 'baseline_duration',
        'anomalyDampening': 'anomaly_dampening',
        'instanceDownRatioThreshold': 'instance_down_ratio_threshold',
        'componentNameAutoOverwrite': 'component_name_auto_overwrite',
        'predictionTrainingDataLength': 'prediction_training_data_length',
        'predictionCorrelationSensitivity': 'prediction_correlation_sensitivity',
        'enableKPIPrediction': 'enable_kpi_prediction',
        'instanceDownThreshold': 'instance_down_threshold',
        'instanceDownReportNumber': 'instance_down_report_number',
        'instanceDownEnable': 'instance_down_enable',
        'trainingFilter': 'training_filter',
        'enableNewAlertEmail': 'enable_new_alert_email',
        'enableAnomalyScoreEscalation': 'enable_anomaly_score_escalation',
        'escalationAnomalyScoreThreshold': 'escalation_anomaly_score_threshold',
        'ignoreAnomalyScoreThreshold': 'ignore_anomaly_score_threshold',
        'enableStreamDetection': 'enable_stream_detection',
        'largeProject': 'large_project',
        'newPatternRange': 'new_pattern_range',
        'proxy': 'proxy',
        'ignoreInstanceForKB': 'ignore_instance_for_kb',
        'showInstanceDown': 'show_instance_down',
        'alertHourlyCost': 'alert_hourly_cost',
        'alertAverageTime': 'alert_average_time',
        'avgPerIncidentDowntimeCost': 'avg_per_incident_downtime_cost',
        'incidentPredictionWindow': 'incident_prediction_window',
        'minIncidentPredictionWindow': 'min_incident_prediction_window',
        'incidentRelationSearchWindow': 'incident_relation_search_window',
        'incidentPredictionEventLimit': 'incident_prediction_event_limit',
        'rootCauseCountThreshold': 'root_cause_count_threshold',
        'rootCauseProbabilityThreshold': 'root_cause_probability_threshold',
        'compositeRCALimit': 'composite_rca_limit',
        'rootCauseLogMessageSearchRange': 'root_cause_log_message_search_range',
        'causalPredictionSetting': 'causal_prediction_setting',
        'rootCauseRankSetting': 'root_cause_rank_setting',
        'maximumRootCauseResultSize': 'maximum_root_cause_result_size',
        'multiHopSearchLevel': 'multi_hop_search_level',
        'multiHopSearchLimit': 'multi_hop_search_limit',
        'predictionCountThreshold': 'prediction_count_threshold',
        'predictionProbabilityThreshold': 'prediction_probability_threshold',
        'predictionRuleActiveCondition': 'prediction_rule_active_condition',
        'predictionRuleFalsePositiveThreshold': 'prediction_rule_false_positive_threshold',
        'predictionRuleActiveThreshold': 'prediction_rule_active_threshold',
        'predictionRuleInactiveThreshold': 'prediction_rule_inactive_threshold',
        'minValidModelSpan': 'min_valid_model_span',
        'maxWebHookRequestSize': 'max_web_hook_request_size',
        'webhookUrl': 'webhook_url',
        'webhookTypeSetStr': 'webhook_type_set_str',
        'webhookBlackListSetStr': 'webhook_black_list_set_str',
        'webhookCriticalKeywordSetStr': 'webhook_critical_keyword_set_str',
        'webhookAlertDampening': 'webhook_alert_dampening',
        'linkedLogProjects': 'linked_log_projects',
        'sharedUsernames': 'shared_usernames',
        'webhookHeaderList': 'webhook_header_list',
        'instanceGroupingUpdate': 'instance_grouping_update',
        'emailSetting': 'email_setting',
    }

    for api_key_name, tf_key in metric_attribute_mapping.items():
        if api_key_name in settings_data:
            value = settings_data[api_key_name]
            if api_key_name == 'emailSetting' and isinstance(value, dict):
                if 'awSeverityLevel' not in value:
                    value = dict(value)
                    value['awSeverityLevel'] = 'Major'
            cfg.append(f'  {tf_key} = {format_terraform_value(value)}')

    # metric_configurations — populated from componentmetricupdate + metriccomponent APIs
    metric_configs = project_data.get("metric_configurations") or {}
    cfg.extend(_generate_metric_configurations_hcl(metric_configs))

    # holiday_settings
    cfg.extend(_generate_holiday_settings_hcl(project_data.get("holidays") or {}))

    cfg.append('}')
    return '\n'.join(cfg)


# ---------------------------------------------------------------------------
# File writing helpers
# ---------------------------------------------------------------------------

def write_file(path: str, content: str, dry_run: bool = False) -> None:
    if dry_run:
        print(f"  [dry-run] Would write: {path}")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Main generation logic
# ---------------------------------------------------------------------------

def process_system(session: requests.Session, env_name: str, env_cfg: Dict,
                   system: Dict, output_dir: str, delay: float,
                   dry_run: bool,
                   allowed_projects: Optional[set] = None) -> Dict[str, int]:
    """Generate all Terraform files for one system. Returns stats.

    allowed_projects: if set, only process projects whose names are in this set.
                      None means process all projects (subject to type filter).
    """
    system_name = get_system_display_name(system)
    system_id = get_system_id(system)
    base_url = env_cfg["base_url"].rstrip('/')
    username = env_cfg["username"]
    api_key = env_cfg["licensekey"]
    terraform_version = str(env_cfg.get("terraform_version", ">= 1.6.1"))
    project_types: List[str] = env_cfg.get("project_types", env_cfg.get("project_type", []))
    if isinstance(project_types, str):
        project_types = [project_types]

    all_projects_raw = system.get("projectDetailsList", system.get("projectDetailList", []))
    if isinstance(all_projects_raw, str):
        try:
            all_projects = json.loads(all_projects_raw)
        except (json.JSONDecodeError, ValueError):
            all_projects = []
    else:
        all_projects = all_projects_raw or []
    projects = filter_projects_by_type(all_projects, project_types)

    # Apply only_process.projects filter if provided
    if allowed_projects is not None:
        projects = [p for p in projects
                    if (p.get("projectName") or p.get("name") or "") in allowed_projects]

    filter_desc = "type+project filter" if allowed_projects is not None else "type filter"
    print(f"\n  System: {system_name!r}  ({len(projects)}/{len(all_projects)} projects after {filter_desc})")

    if not projects:
        print("    No matching projects — skipping system.")
        return {"projects": 0, "skipped": 0, "metric_projects": 0, "metric_skipped": 0,
                "l2m_projects": 0, "l2m_skipped": 0}

    # Split projects by data type into dedicated subfolders:
    #   metric-projects/        — Metric (excluding L2M)
    #   l2m-projects/           — Metric projects whose name ends in -L2M (case-insensitive)
    #   log-projects/           — Log, Alert, and any other non-separated types
    #   trace-projects/         — Trace
    #   change-events-projects/ — Deployment
    all_metric_projects = [p for p in projects if (p.get("dataType") or "").lower() == "metric"]
    l2m_projects_list = [
        p for p in all_metric_projects
        if (p.get("projectName") or p.get("name") or "").lower().endswith("-l2m")
    ]
    l2m_project_names = {p.get("projectName") or p.get("name") or "" for p in l2m_projects_list}
    metric_projects_list = [p for p in all_metric_projects if (p.get("projectName") or p.get("name") or "") not in l2m_project_names]
    trace_projects_list = [p for p in projects if (p.get("dataType") or "").lower() == "trace"]
    change_events_projects_list = [p for p in projects if (p.get("dataType") or "").lower() == "deployment"]
    incident_projects_list = [p for p in projects if (p.get("dataType") or "").lower() == "incident"]
    log_projects_list = [
        p for p in projects
        if (p.get("dataType") or "").lower() not in ("metric", "trace", "deployment", "incident")
    ]

    system_dir = os.path.join(output_dir, env_name, system_name)
    log_projects_dir = os.path.join(system_dir, "log-projects")
    metric_projects_dir = os.path.join(system_dir, "metric-projects")
    l2m_projects_dir = os.path.join(system_dir, "l2m-projects")
    trace_projects_dir = os.path.join(system_dir, "trace-projects")
    change_events_projects_dir = os.path.join(system_dir, "change-events-projects")
    incident_projects_dir = os.path.join(system_dir, "incident-projects")

    # --- Fetch system-level settings ---
    print(f"    Fetching system-level settings (KB, notifications, miscellaneous)...")
    kb_global, kb_incident, notifications = fetch_system_level_settings(
        session, base_url, username, api_key, username, system_id
    )
    system_down_data = fetch_system_down_setting(
        session, base_url, username, api_key, username, system_id
    )
    insights_report_data = fetch_insights_report_setting(
        session, base_url, username, api_key, username, system_id
    )
    miscellaneous_data = fetch_miscellaneous_settings(
        session, base_url, username, api_key, username, system_id
    )

    # --- Pre-fetch all project data so ServiceNow detection is based on actual API
    #     response, not just cloudType (which may be missing/incorrect in some envs) ---
    print(f"    Pre-fetching project data ({len(projects)} projects)...")
    prefetched: Dict[str, Any] = {}   # project_name -> project_data
    metric_project_names = {
        p.get("projectName") or p.get("name") or ""
        for p in metric_projects_list + l2m_projects_list
    }
    for proj in projects:
        project_name = proj.get("projectName") or proj.get("name") or ""
        if not project_name:
            continue
        is_metric = project_name in metric_project_names
        proj_data_type = (proj.get("dataType") or "log").lower()
        if is_metric:
            print(f"      {project_name} (metric — fetching configurations)")
        else:
            print(f"      {project_name} ({proj_data_type})")
        try:
            prefetched[project_name] = fetch_project_data(
                session, base_url, username, api_key, username, project_name,
                is_metric=is_metric,
            )
        except Exception as e:
            print(f"      Error pre-fetching {project_name!r}: {e}", file=sys.stderr)
        if delay > 0:
            time.sleep(delay)

    # --- Determine if any log project uses ServiceNow ---
    # ServiceNow projects are always Log type. A project is treated as ServiceNow
    # if cloudType says so OR if the API returned real ServiceNow settings.
    def _is_servicenow(proj: Dict) -> bool:
        name = proj.get("projectName") or proj.get("name") or ""
        if (proj.get("cloudType") or "").lower() == "servicenow":
            return True
        return bool((prefetched.get(name) or {}).get("servicenow"))

    servicenow_projects = {
        (p.get("projectName") or p.get("name") or "")
        for p in log_projects_list if _is_servicenow(p)
    }
    has_servicenow = len(servicenow_projects) > 0

    change_events_servicenow_projects = {
        (p.get("projectName") or p.get("name") or "")
        for p in change_events_projects_list if _is_servicenow(p)
    }
    has_change_events_servicenow = len(change_events_servicenow_projects) > 0

    # Collect a representative SN host for tfvars (log projects first, then change-events)
    sn_host_for_tfvars = ""
    for sn_name in list(servicenow_projects) + list(change_events_servicenow_projects):
        sn_data = (prefetched.get(sn_name) or {}).get("servicenow")
        if sn_data and sn_data.get("host"):
            sn_host_for_tfvars = sn_data["host"]
            break

    # --- Write system-level files ---
    write_file(os.path.join(system_dir, "versions.tf"),
               _versions_tf(env_name, system_name, terraform_version), dry_run)
    write_file(os.path.join(system_dir, "provider.tf"),
               _provider_tf(), dry_run)
    write_file(os.path.join(system_dir, "variables.tf"),
               _system_variables_tf(), dry_run)

    if log_projects_list:
        write_file(os.path.join(system_dir, "log_projects.tf"),
                   _log_projects_tf(has_servicenow), dry_run)
        write_file(os.path.join(log_projects_dir, "versions.tf"),
                   _projects_versions_tf(), dry_run)
        write_file(os.path.join(log_projects_dir, "variables.tf"),
                   _log_projects_variables_tf(has_servicenow), dry_run)

    if metric_projects_list:
        write_file(os.path.join(system_dir, "metric_projects.tf"),
                   _metric_projects_tf(), dry_run)
        write_file(os.path.join(metric_projects_dir, "versions.tf"),
                   _projects_versions_tf(), dry_run)
        write_file(os.path.join(metric_projects_dir, "variables.tf"),
                   _metric_projects_variables_tf(), dry_run)

    if l2m_projects_list:
        write_file(os.path.join(system_dir, "l2m_projects.tf"),
                   _l2m_projects_tf(), dry_run)
        write_file(os.path.join(l2m_projects_dir, "versions.tf"),
                   _projects_versions_tf(), dry_run)
        write_file(os.path.join(l2m_projects_dir, "variables.tf"),
                   _l2m_projects_variables_tf(), dry_run)

    if trace_projects_list:
        write_file(os.path.join(system_dir, "trace_projects.tf"),
                   _trace_projects_tf(), dry_run)
        write_file(os.path.join(trace_projects_dir, "versions.tf"),
                   _projects_versions_tf(), dry_run)
        write_file(os.path.join(trace_projects_dir, "variables.tf"),
                   _trace_projects_variables_tf(), dry_run)

    if change_events_projects_list:
        write_file(os.path.join(system_dir, "change_events_projects.tf"),
                   _change_events_projects_tf(has_change_events_servicenow), dry_run)
        write_file(os.path.join(change_events_projects_dir, "versions.tf"),
                   _projects_versions_tf(), dry_run)
        write_file(os.path.join(change_events_projects_dir, "variables.tf"),
                   _change_events_projects_variables_tf(has_change_events_servicenow), dry_run)

    if incident_projects_list:
        write_file(os.path.join(system_dir, "incident_projects.tf"),
                   _incident_projects_tf(), dry_run)
        write_file(os.path.join(incident_projects_dir, "versions.tf"),
                   _projects_versions_tf(), dry_run)
        write_file(os.path.join(incident_projects_dir, "variables.tf"),
                   _incident_projects_variables_tf(), dry_run)

    # --- Collect instance_down items from pre-fetched project data ---
    # Only include projects where instanceDownEnable = True
    instance_down_items: List[Dict] = []
    for proj in projects:
        project_name = proj.get("projectName") or proj.get("name") or ""
        if not project_name:
            continue
        id_setting = (prefetched.get(project_name) or {}).get("instance_down")
        if id_setting and id_setting.get("instanceDownEnable"):
            instance_down_items.append(id_setting)

    # --- Write system_settings.tf in system folder (not projects/) ---
    has_sys_settings = (kb_global or kb_incident or notifications
                        or system_down_data or insights_report_data or instance_down_items
                        or miscellaneous_data)
    if has_sys_settings:
        sys_settings_content = generate_system_settings_config(
            system_name=system_name,
            kb_global_data=kb_global,
            kb_incident_data=kb_incident,
            notifications_data=notifications,
            system_name_expr="var.system_name",
            system_down_data=system_down_data,
            insights_report_data=insights_report_data,
            instance_down_items=instance_down_items if instance_down_items else None,
            miscellaneous_data=miscellaneous_data,
        )
        write_file(os.path.join(system_dir, "system_settings.tf"),
                   sys_settings_content + "\n", dry_run)

    # --- Generate per-project files from pre-fetched data ---
    log_generated = 0
    log_skipped = 0
    metric_generated = 0
    metric_skipped = 0
    l2m_generated = 0
    l2m_skipped = 0
    trace_generated = 0
    trace_skipped = 0
    change_events_generated = 0
    change_events_skipped = 0
    incident_generated = 0
    incident_skipped = 0

    for proj in log_projects_list:
        project_name = proj.get("projectName") or proj.get("name") or ""
        if not project_name:
            log_skipped += 1
            continue

        project_data = prefetched.get(project_name)
        if project_data is None:
            log_skipped += 1
            continue

        is_sn = project_name in servicenow_projects
        print(f"    [log {log_generated + log_skipped + 1}/{len(log_projects_list)}] {project_name}"
              + (" (ServiceNow)" if is_sn else ""))

        try:
            tf_content = generate_project_tf(project_name, project_data,
                                             system_name, is_sn, data_type="Log",
                                             proj_info=proj)
        except Exception as e:
            print(f"      Error generating log TF: {e}", file=sys.stderr)
            log_skipped += 1
            continue

        if tf_content is None:
            print(f"      Skipped — no settings")
            log_skipped += 1
            continue

        tf_filename = tf_resource_name(project_name) + ".tf"
        write_file(os.path.join(log_projects_dir, tf_filename), tf_content + "\n", dry_run)
        log_generated += 1

    for proj in metric_projects_list:
        project_name = proj.get("projectName") or proj.get("name") or ""
        if not project_name:
            metric_skipped += 1
            continue

        project_data = prefetched.get(project_name)
        if project_data is None:
            metric_skipped += 1
            continue

        print(f"    [metric {metric_generated + metric_skipped + 1}/{len(metric_projects_list)}] {project_name}")

        try:
            tf_content = generate_metric_project_tf(project_name, project_data,
                                                    system_name, proj)
        except Exception as e:
            print(f"      Error generating metric TF: {e}", file=sys.stderr)
            metric_skipped += 1
            continue

        tf_filename = tf_resource_name(project_name) + ".tf"
        write_file(os.path.join(metric_projects_dir, tf_filename), tf_content + "\n", dry_run)
        metric_generated += 1

    for proj in l2m_projects_list:
        project_name = proj.get("projectName") or proj.get("name") or ""
        if not project_name:
            l2m_skipped += 1
            continue

        project_data = prefetched.get(project_name)
        if project_data is None:
            l2m_skipped += 1
            continue

        print(f"    [l2m {l2m_generated + l2m_skipped + 1}/{len(l2m_projects_list)}] {project_name}")

        try:
            tf_content = generate_metric_project_tf(project_name, project_data,
                                                    system_name, proj)
        except Exception as e:
            print(f"      Error generating l2m TF: {e}", file=sys.stderr)
            l2m_skipped += 1
            continue

        tf_filename = tf_resource_name(project_name) + ".tf"
        write_file(os.path.join(l2m_projects_dir, tf_filename), tf_content + "\n", dry_run)
        l2m_generated += 1

    for proj in trace_projects_list:
        project_name = proj.get("projectName") or proj.get("name") or ""
        if not project_name:
            trace_skipped += 1
            continue

        project_data = prefetched.get(project_name)
        if project_data is None:
            trace_skipped += 1
            continue

        print(f"    [trace {trace_generated + trace_skipped + 1}/{len(trace_projects_list)}] {project_name}")

        try:
            tf_content = generate_project_tf(project_name, project_data,
                                             system_name, is_servicenow_project=False,
                                             data_type="Trace", proj_info=proj)
        except Exception as e:
            print(f"      Error generating trace TF: {e}", file=sys.stderr)
            trace_skipped += 1
            continue

        if tf_content is None:
            print(f"      Skipped — no settings")
            trace_skipped += 1
            continue

        tf_filename = tf_resource_name(project_name) + ".tf"
        write_file(os.path.join(trace_projects_dir, tf_filename), tf_content + "\n", dry_run)
        trace_generated += 1

    for proj in change_events_projects_list:
        project_name = proj.get("projectName") or proj.get("name") or ""
        if not project_name:
            change_events_skipped += 1
            continue

        project_data = prefetched.get(project_name)
        if project_data is None:
            change_events_skipped += 1
            continue

        is_sn_ce = project_name in change_events_servicenow_projects
        print(f"    [deployment {change_events_generated + change_events_skipped + 1}/{len(change_events_projects_list)}] {project_name}"
              + (" (ServiceNow)" if is_sn_ce else ""))

        try:
            tf_content = generate_project_tf(project_name, project_data,
                                             system_name, is_servicenow_project=is_sn_ce,
                                             data_type="Deployment", proj_info=proj)
        except Exception as e:
            print(f"      Error generating change-events TF: {e}", file=sys.stderr)
            change_events_skipped += 1
            continue

        if tf_content is None:
            print(f"      Skipped — no settings")
            change_events_skipped += 1
            continue

        tf_filename = tf_resource_name(project_name) + ".tf"
        write_file(os.path.join(change_events_projects_dir, tf_filename), tf_content + "\n", dry_run)
        change_events_generated += 1

    for proj in incident_projects_list:
        project_name = proj.get("projectName") or proj.get("name") or ""
        if not project_name:
            incident_skipped += 1
            continue

        project_data = prefetched.get(project_name)
        if project_data is None:
            incident_skipped += 1
            continue

        print(f"    [incident {incident_generated + incident_skipped + 1}/{len(incident_projects_list)}] {project_name}")

        try:
            tf_content = generate_project_tf(project_name, project_data,
                                             system_name, is_servicenow_project=False,
                                             data_type="Incident", proj_info=proj)
        except Exception as e:
            print(f"      Error generating incident TF: {e}", file=sys.stderr)
            incident_skipped += 1
            continue

        if tf_content is None:
            print(f"      Skipped — no settings")
            incident_skipped += 1
            continue

        tf_filename = tf_resource_name(project_name) + ".tf"
        write_file(os.path.join(incident_projects_dir, tf_filename), tf_content + "\n", dry_run)
        incident_generated += 1

    # --- Write terraform.tfvars (after we have SN host if any) ---
    write_file(os.path.join(system_dir, "terraform.tfvars"),
               _tfvars(base_url, system_name, sn_host_for_tfvars), dry_run)

    print(f"    Log: {log_generated}/{len(log_projects_list)}  "
          f"Metric: {metric_generated}/{len(metric_projects_list)}  "
          f"L2M: {l2m_generated}/{len(l2m_projects_list)}  "
          f"Trace: {trace_generated}/{len(trace_projects_list)}  "
          f"Deployment: {change_events_generated}/{len(change_events_projects_list)}  "
          f"Incident: {incident_generated}/{len(incident_projects_list)}")
    return {
        "projects": log_generated, "skipped": log_skipped,
        "metric_projects": metric_generated, "metric_skipped": metric_skipped,
        "l2m_projects": l2m_generated, "l2m_skipped": l2m_skipped,
        "trace_projects": trace_generated, "trace_skipped": trace_skipped,
        "change_events_projects": change_events_generated, "change_events_skipped": change_events_skipped,
        "incident_projects": incident_generated, "incident_skipped": incident_skipped,
    }


def run(config_path: str, output_dir: str, env_filter: Optional[str],
        dry_run: bool, no_ssl_verify: bool) -> None:
    cfg = load_config(config_path)

    global _RETRY_DELAY, _MAX_RETRIES
    global_delay = float(cfg.get("Delay", cfg.get("delay", 0)))
    _RETRY_DELAY = global_delay  # reuse Delay for sleep between HTTP retries
    _MAX_RETRIES = int(cfg.get("Retries", cfg.get("retries", 3)))
    print(f"Config: Delay={global_delay}s, Retries={_MAX_RETRIES}")
    session = make_session(no_ssl_verify)

    total_projects = 0
    total_skipped = 0
    total_metric_projects = 0
    total_l2m_projects = 0
    total_trace_projects = 0
    total_systems = 0

    # Iterate environments (skip non-dict top-level keys like Delay)
    for env_name, env_cfg in cfg.items():
        if not isinstance(env_cfg, dict):
            continue
        if env_filter and env_name.upper() != env_filter.upper():
            continue

        print(f"\n{'='*60}")
        print(f"Environment: {env_name}  ({env_cfg.get('base_url', '')})")
        print(f"{'='*60}")

        username = env_cfg.get("username", "")
        api_key = env_cfg.get("licensekey", "")
        base_url = env_cfg.get("base_url", "").rstrip('/')

        if not username or not api_key or not base_url:
            print(f"  Skipping {env_name}: missing username/licensekey/base_url", file=sys.stderr)
            continue

        # Parse only_process filter
        only_process = env_cfg.get("only_process") or {}
        allowed_systems: set = set(only_process.get("systems") or [])
        extra_projects: set = set(only_process.get("projects") or [])
        has_filter = bool(allowed_systems or extra_projects)

        if has_filter:
            parts = []
            if allowed_systems:
                parts.append(f"systems={sorted(allowed_systems)}")
            if extra_projects:
                parts.append(f"projects={sorted(extra_projects)}")
            print(f"  only_process filter: {', '.join(parts)}")

        print(f"  Fetching owned systems for {username}...")
        systems = get_own_systems(session, base_url, username, api_key, username)
        print(f"  Found {len(systems)} owned system(s).")

        # Generate environment-level ServiceNow root module (ENV/servicenow/)
        process_env_servicenow(session, env_name, env_cfg, systems, output_dir, dry_run)

        for system in systems:
            system_display = get_system_display_name(system)

            if has_filter:
                system_in_allowed = system_display in allowed_systems

                if system_in_allowed:
                    # Process all projects in this system (type filter still applies)
                    project_filter = None
                else:
                    # Check if any explicitly listed projects belong to this system
                    if not extra_projects:
                        print(f"\n  System: {system_display!r} — skipped (not in only_process.systems)")
                        continue
                    _raw_projects = (system.get("projectDetailsList")
                                     or system.get("projectDetailList") or [])
                    if isinstance(_raw_projects, str):
                        try:
                            _raw_projects = json.loads(_raw_projects)
                        except (json.JSONDecodeError, ValueError):
                            _raw_projects = []
                    system_project_names = {
                        (p.get("projectName") or p.get("name") or "")
                        for p in _raw_projects
                        if isinstance(p, dict)
                    }
                    matching = extra_projects & system_project_names
                    if not matching:
                        print(f"\n  System: {system_display!r} — skipped (no matching projects)")
                        continue
                    project_filter = matching
            else:
                project_filter = None

            total_systems += 1
            stats = process_system(session, env_name, env_cfg, system,
                                   output_dir, global_delay, dry_run,
                                   allowed_projects=project_filter)
            total_projects += stats["projects"]
            total_skipped += stats["skipped"]
            total_metric_projects += stats.get("metric_projects", 0)
            total_l2m_projects += stats.get("l2m_projects", 0)
            total_trace_projects += stats.get("trace_projects", 0)

    print(f"\n{'='*60}")
    print(f"Done!  Environments: {env_filter or 'all'}  "
          f"Systems: {total_systems}  "
          f"Projects generated: {total_projects}  "
          f"Metric projects generated: {total_metric_projects}  "
          f"L2M projects generated: {total_l2m_projects}  "
          f"Deployment projects generated: {total_trace_projects}  "
          f"Skipped: {total_skipped}")
    print(f"Output directory: {output_dir}")

    if not dry_run and total_projects > 0:
        print(f"\nRunning: terraform fmt -recursive {output_dir}")
        result = subprocess.run(["terraform", "fmt", "-recursive", output_dir])
        if result.returncode != 0:
            print("Warning: terraform fmt exited with non-zero status", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-generate Terraform files from InsightFinder API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--config", "-c", default="config.yaml",
                        help="Path to config.yaml (default: config.yaml)")
    parser.add_argument("--output-dir", "-o", default="TerraformFiles",
                        help="Root output directory (default: TerraformFiles)")
    parser.add_argument("--env", help="Only process this environment (e.g. NBC)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be written without creating files")
    parser.add_argument("--no-ssl-verify", action="store_true",
                        help="Disable SSL certificate verification")

    args = parser.parse_args()

    if not os.path.exists(args.config):
        print(f"Error: config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    run(
        config_path=args.config,
        output_dir=args.output_dir,
        env_filter=args.env,
        dry_run=args.dry_run,
        no_ssl_verify=args.no_ssl_verify,
    )


if __name__ == "__main__":
    main()

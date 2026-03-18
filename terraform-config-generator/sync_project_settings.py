#!/usr/bin/env python3
"""
Sync InsightFinder project settings from one system's projects to another by generating
Terraform (.tf) files for the destination projects using the source projects' settings.

The destination project's identity is preserved:
    - project_name, project_display_name, system_name, resource key stay unchanged.
Only the settings values (anomaly thresholds, alerts, keywords, etc.) come from the source.

Output mirrors the TerraformFiles structure produced by auto_generate_terraform.py:
    TerraformFiles/<env>/<dst_system>/log-projects/<project>.tf
    TerraformFiles/<env>/<dst_system>/metric-projects/<project>.tf
    TerraformFiles/<env>/<dst_system>/trace-projects/<project>.tf
    TerraformFiles/<env>/<dst_system>/change-events-projects/<project>.tf
    TerraformFiles/<env>/<dst_system>/incident-projects/<project>.tf

Only project-level .tf files are written — system-level files (versions.tf, provider.tf,
variables.tf, terraform.tfvars, system_settings.tf) are left untouched.

Usage:
    python sync_project_settings.py --config config.yaml --sync-config sync_config.yaml
    python sync_project_settings.py --config config.yaml --sync-config sync_config.yaml --dry-run
    python sync_project_settings.py --config config.yaml --sync-config sync_config.yaml --output-dir TerraformFiles

sync_config.yaml format:
    sync_rules:
      # Rule 1: system-level sync using suffix matching
      - env: NBC                        # which env block from config.yaml
        from_system: "NBC Stage"        # source system display name
        to_system: "NBC UAT"            # destination system display name
        suffix: "-uat"                  # strip this suffix (case-insensitive) from destination
                                        # project names to find the matching source project
                                        # e.g. "akamai-UAT" -> source "akamai"
        sync:
          watch_tower: true             # main project settings (anomaly, alerts, etc.)
          keywords: true                # log label / keyword settings
          summary: true                 # summary and metafield settings
          json_keys: true               # JSON key type settings
          holidays: true                # holiday schedules
          metric: true                  # metric component & alert settings (metric projects only)
        exclude_projects:               # destination project names to skip
          - "some-project-uat"

      # Rule 2: explicit project-to-project mapping
      - env: NBC
        project_mappings:
          - from_project: "akamai"
            to_project: "akamai-uat"
          - from_project: "conviva"
            to_project: "conviva-uat"
        sync:
          watch_tower: true
          keywords: true
          summary: true
          json_keys: true
          holidays: true
          metric: true
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
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

# Reuse generators and helpers from the existing auto-generate script
from auto_generate_terraform import (
    get_own_systems,
    get_system_display_name,
    fetch_project_data,
    make_session,
    api_headers,
    fetch_json,
    tf_resource_name,
    write_file,
    generate_project_tf,
    generate_metric_project_tf,
)


def get_projects_in_system(system: Dict) -> List[Dict]:
    raw = system.get("projectDetailsList", system.get("projectDetailList", []))
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []
    return raw or []


# ---------------------------------------------------------------------------
# Identity fields — never copied from source; destination keeps its own
# ---------------------------------------------------------------------------
IDENTITY_FIELDS = {
    "projectName",
    "projectDisplayName",
    "systemName",
    "systemKey",
    "resourceKey",
    "customerName",
    "userName",
}

# Map dataType -> subdirectory name (same as auto_generate_terraform.py)
DATATYPE_SUBDIR = {
    "log":        "log-projects",
    "alert":      "log-projects",
    "metric":     "metric-projects",
    "trace":      "trace-projects",
    "deployment": "change-events-projects",
    "incident":   "incident-projects",
}


# ---------------------------------------------------------------------------
# Settings patching — strip identity fields so destination keeps its own
# ---------------------------------------------------------------------------

def _strip_identity_from_settings(project_data: Dict) -> Dict:
    """
    Return a deep copy of project_data with identity fields removed from the
    watch-tower settingList payload.  This ensures the generated TF file
    does not overwrite the destination project's display name etc.
    """
    patched = copy.deepcopy(project_data)
    settings_raw = patched.get("settings") or {}
    setting_list = settings_raw.get("settingList") or {}

    new_setting_list = {}
    for key, settings_str in setting_list.items():
        try:
            parsed = json.loads(settings_str)
            data = parsed.get("DATA") if isinstance(parsed, dict) and "DATA" in parsed else parsed
            if isinstance(data, dict):
                for field in IDENTITY_FIELDS:
                    data.pop(field, None)
            if isinstance(parsed, dict) and "DATA" in parsed:
                parsed["DATA"] = data
            else:
                parsed = data
            new_setting_list[key] = json.dumps(parsed)
        except (json.JSONDecodeError, TypeError):
            new_setting_list[key] = settings_str

    patched["settings"] = {"settingList": new_setting_list}
    return patched


def _filter_project_data(project_data: Dict, sync_flags: Dict[str, bool]) -> Dict:
    """
    Zero-out categories the user opted out of so generate_project_tf skips them.
    """
    patched = copy.deepcopy(project_data)

    if not sync_flags.get("watch_tower", True):
        patched["settings"] = {}
    if not sync_flags.get("keywords", True):
        patched["keywords"] = {}
    if not sync_flags.get("summary", True):
        patched["summary"] = {}
    if not sync_flags.get("json_keys", True):
        patched["jsonkeys"] = {}
    if not sync_flags.get("holidays", True):
        patched["holidays"] = {}
    if not sync_flags.get("metric", True):
        patched["metric_configurations"] = {}

    return patched


# ---------------------------------------------------------------------------
# Project matching
# ---------------------------------------------------------------------------

def build_project_name_map(projects: List[Dict]) -> Dict[str, Dict]:
    return {
        (p.get("projectName") or p.get("name") or ""): p
        for p in projects
        if (p.get("projectName") or p.get("name"))
    }


def match_projects_by_suffix(
        src_projects: Dict[str, Dict],
        dst_projects: Dict[str, Dict],
        suffix: str,
        exclude: Optional[List[str]] = None,
) -> List[Tuple[str, str]]:
    """
    Match destination projects to source by stripping suffix (case-insensitive).
    Returns list of (src_project_name, dst_project_name) pairs.
    """
    exclude_set = set(exclude or [])
    suffix_lower = suffix.lower() if suffix else ""
    pairs = []
    for dst_name in sorted(dst_projects.keys()):
        if dst_name in exclude_set:
            continue
        if suffix_lower and dst_name.lower().endswith(suffix_lower):
            src_name = dst_name[: -len(suffix_lower)]
        else:
            src_name = dst_name
        if src_name in src_projects:
            pairs.append((src_name, dst_name))
        else:
            print(f"      [no match] '{dst_name}' -> source '{src_name}' not found (skipping)")
    return pairs


# ---------------------------------------------------------------------------
# TF generation per project pair
# ---------------------------------------------------------------------------

def generate_tf_for_pair(
        session: requests.Session,
        base: str,
        username: str,
        api_key: str,
        src_project: str,
        dst_project: str,
        dst_system_name: str,
        src_proj_info: Dict,
        dst_proj_info: Dict,
        sync_flags: Dict[str, bool],
        output_dir: str,
        env_name: str,
        delay: float,
        dry_run: bool,
        verbose: bool,
) -> bool:
    """Fetch source settings and write a .tf file for the destination project."""

    data_type = (
        src_proj_info.get("dataType")
        or dst_proj_info.get("dataType")
        or "log"
    ).lower()
    is_metric = data_type == "metric"

    type_label = {
        "log": "Log", "metric": "Metric", "trace": "Trace",
        "deployment": "Deployment", "incident": "Incident",
    }.get(data_type, data_type.capitalize())

    subdir = DATATYPE_SUBDIR.get(data_type, "log-projects")

    print(f"      [{type_label}] '{src_project}' -> '{dst_project}'")

    # Fetch source project data (read-only API calls)
    if verbose:
        print(f"        Fetching source settings...")
    try:
        project_data = fetch_project_data(
            session, base, username, api_key, username,
            src_project, is_metric=is_metric,
        )
    except Exception as e:
        print(f"        Error fetching source settings: {e}", file=sys.stderr)
        return False

    if delay > 0:
        time.sleep(delay)

    # Strip identity fields so destination keeps its own, then apply sync_flags filter
    project_data = _strip_identity_from_settings(project_data)
    project_data = _filter_project_data(project_data, sync_flags)

    # Determine if this is a ServiceNow project (check source cloudType or fetched SN data)
    is_servicenow = (
        (src_proj_info.get("cloudType") or "").lower() == "servicenow"
        or bool(project_data.get("servicenow"))
    )

    # Use destination proj_info for cloud/agent type (identity of the dst project)
    proj_info_for_tf = dst_proj_info if dst_proj_info else src_proj_info

    # Generate TF content
    try:
        if is_metric:
            tf_content = generate_metric_project_tf(
                dst_project, project_data, dst_system_name, proj_info_for_tf,
            )
        else:
            tf_content = generate_project_tf(
                dst_project, project_data, dst_system_name,
                is_servicenow, data_type=data_type, proj_info=proj_info_for_tf,
            )
    except Exception as e:
        print(f"        Error generating TF: {e}", file=sys.stderr)
        return False

    # Write the .tf file
    tf_filename = tf_resource_name(dst_project) + ".tf"
    tf_path = os.path.join(output_dir, env_name, dst_system_name, subdir, tf_filename)
    write_file(tf_path, tf_content + "\n", dry_run)

    if verbose or dry_run:
        print(f"        -> {tf_path}")

    return True


# ---------------------------------------------------------------------------
# Rule processing
# ---------------------------------------------------------------------------

def process_rule(session: requests.Session, env_cfg: Dict, rule: Dict,
                 output_dir: str, delay: float, dry_run: bool, verbose: bool) -> Dict[str, int]:
    base = env_cfg["base_url"].rstrip("/")
    username = env_cfg["username"]
    api_key = env_cfg["licensekey"]

    sync_flags: Dict[str, bool] = {
        "watch_tower": True,
        "keywords": True,
        "summary": True,
        "json_keys": True,
        "holidays": True,
        "metric": True,
    }
    sync_flags.update(rule.get("sync") or {})

    stats = {"written": 0, "failed": 0, "skipped": 0}

    print(f"  Fetching system list...")
    all_systems = get_own_systems(session, base, username, api_key, username)

    pairs: List[Tuple[str, str]] = []
    src_projects_map: Dict[str, Dict] = {}
    dst_projects_map: Dict[str, Dict] = {}
    dst_system_name = ""

    if "project_mappings" in rule:
        # Build a global project map across all systems for dataType lookup
        global_map: Dict[str, Dict] = {}
        for system in all_systems:
            for p in get_projects_in_system(system):
                pname = p.get("projectName") or p.get("name") or ""
                if pname:
                    global_map[pname] = p
        src_projects_map = global_map
        dst_projects_map = global_map

        for mapping in rule["project_mappings"]:
            src = mapping.get("from_project", "").strip()
            dst = mapping.get("to_project", "").strip()
            if src and dst:
                pairs.append((src, dst))
            else:
                print(f"  Warning: incomplete project_mapping entry: {mapping}", file=sys.stderr)

        # Determine destination system name from the first destination project
        if pairs:
            first_dst = pairs[0][1]
            for system in all_systems:
                proj_names = {
                    p.get("projectName") or p.get("name") or ""
                    for p in get_projects_in_system(system)
                }
                if first_dst in proj_names:
                    dst_system_name = get_system_display_name(system)
                    break

    else:
        from_system_name = rule.get("from_system", "").strip()
        to_system_name = rule.get("to_system", "").strip()
        suffix = rule.get("suffix", "")
        exclude = rule.get("exclude_projects") or []

        if not from_system_name or not to_system_name:
            print("  Error: rule missing from_system or to_system", file=sys.stderr)
            return stats

        src_system = next(
            (s for s in all_systems if get_system_display_name(s) == from_system_name), None
        )
        dst_system = next(
            (s for s in all_systems if get_system_display_name(s) == to_system_name), None
        )

        if not src_system:
            print(f"  Error: source system '{from_system_name}' not found", file=sys.stderr)
            return stats
        if not dst_system:
            print(f"  Error: destination system '{to_system_name}' not found", file=sys.stderr)
            return stats

        dst_system_name = to_system_name
        src_projects_map = build_project_name_map(get_projects_in_system(src_system))
        dst_projects_map = build_project_name_map(get_projects_in_system(dst_system))

        # Log per-type breakdown
        type_counts: Dict[str, int] = {}
        for p in src_projects_map.values():
            dt = (p.get("dataType") or "log").lower()
            type_counts[dt] = type_counts.get(dt, 0) + 1
        type_summary = ", ".join(f"{c} {t}" for t, c in sorted(type_counts.items()))
        print(f"  Source '{from_system_name}': {len(src_projects_map)} projects ({type_summary})")
        print(f"  Destination '{to_system_name}': {len(dst_projects_map)} projects")
        if suffix:
            print(f"  Suffix matching (case-insensitive): '{suffix}'")

        pairs = match_projects_by_suffix(src_projects_map, dst_projects_map, suffix, exclude)
        stats["skipped"] = len(dst_projects_map) - len(pairs) - len(exclude or [])

    if not pairs:
        print("  No project pairs to process.")
        return stats

    # Per-type summary of what will be written
    type_pair_counts: Dict[str, int] = {}
    for src_name, dst_name in pairs:
        dt = (
            (src_projects_map.get(src_name) or {}).get("dataType")
            or (dst_projects_map.get(dst_name) or {}).get("dataType")
            or "log"
        ).lower()
        type_pair_counts[dt] = type_pair_counts.get(dt, 0) + 1
    type_pair_summary = ", ".join(f"{c} {t}" for t, c in sorted(type_pair_counts.items()))

    categories = [k for k, v in sync_flags.items() if v]
    print(f"  Writing {len(pairs)} .tf file(s): {type_pair_summary}")
    print(f"  Categories: {categories}")
    print(f"  Output: {os.path.join(output_dir, rule.get('env', ''), dst_system_name)}/")
    print(f"  Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    print()

    env_name = rule.get("env", "")
    for src_name, dst_name in pairs:
        src_info = src_projects_map.get(src_name) or {}
        dst_info = dst_projects_map.get(dst_name) or {}
        ok = generate_tf_for_pair(
            session, base, username, api_key,
            src_name, dst_name, dst_system_name,
            src_info, dst_info,
            sync_flags, output_dir, env_name,
            delay, dry_run, verbose,
        )
        if ok:
            stats["written"] += 1
        else:
            stats["failed"] += 1

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_yaml(path: str) -> Dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate Terraform files for destination projects using source project settings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--config", default="config.yaml",
                        help="Main config.yaml with env credentials (default: config.yaml)")
    parser.add_argument("--sync-config", default="sync_config.yaml", dest="sync_config",
                        help="Sync rules config file (default: sync_config.yaml)")
    parser.add_argument("--output-dir", default="TerraformFiles", dest="output_dir",
                        help="Root output directory for .tf files (default: TerraformFiles)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be written without creating any files")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed per-project logging")
    parser.add_argument("--delay", type=float, default=None,
                        help="Seconds to wait between project API calls (overrides config.yaml Delay)")
    parser.add_argument("--no-ssl-verify", action="store_true",
                        help="Disable SSL certificate verification")

    args = parser.parse_args(argv)

    try:
        main_cfg = load_yaml(args.config)
    except FileNotFoundError:
        parser.error(f"Config file not found: {args.config}")

    try:
        sync_cfg = load_yaml(args.sync_config)
    except FileNotFoundError:
        parser.error(f"Sync config file not found: {args.sync_config}")

    delay = args.delay if args.delay is not None else float(main_cfg.get("Delay", 1))
    session = make_session(args.no_ssl_verify)

    sync_rules = sync_cfg.get("sync_rules", [])
    if not sync_rules:
        print("No sync_rules defined in sync config. Nothing to do.")
        sys.exit(0)

    if args.dry_run:
        print("=" * 60)
        print("DRY-RUN MODE — no files will be written")
        print("=" * 60)
        print()

    total = {"written": 0, "failed": 0, "skipped": 0}

    for idx, rule in enumerate(sync_rules):
        env_name = rule.get("env", "")
        if not env_name:
            print(f"Rule #{idx + 1}: missing 'env' — skipping", file=sys.stderr)
            continue

        env_cfg = main_cfg.get(env_name)
        if not env_cfg:
            print(f"Rule #{idx + 1}: env '{env_name}' not found in {args.config} — skipping",
                  file=sys.stderr)
            continue

        mappings = rule.get("project_mappings")
        if mappings:
            rule_desc = f"{len(mappings)} explicit project mapping(s)"
        else:
            rule_desc = f"'{rule.get('from_system')}' -> '{rule.get('to_system')}'"

        print(f"Rule #{idx + 1}: [{env_name}] {rule_desc}")

        stats = process_rule(session, env_cfg, rule, args.output_dir, delay, args.dry_run, args.verbose)
        for k, v in stats.items():
            total[k] += v
        print()

    print("=" * 60)
    print(f"Done. Written: {total['written']} | Failed: {total['failed']} | Skipped: {total['skipped']}")
    if total["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

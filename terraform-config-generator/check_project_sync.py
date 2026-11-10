#!/usr/bin/env python3
"""
NBC project sync checker and fixer.

Commands:
  check                  - Check missing projects and show field-level diffs
  sync-json-keys         - Propagate missing json_key entries across matched projects
  apply-master           - Apply master plan settings (flat fields, log_label_settings,
                            l2m_settings, json_key_settings) to matched projects
  generate-l2m-projects  - Generate L2M metric project .tf files from log-projects
  create-missing         - Create missing log/l2m project .tf files, per environment,
                            for every name in a --project-list not yet present

Flags:
  --frequency     Process only LogFrequency projects (default: skip them, process regular projects)
  --project-list  Scope check/sync-json-keys/apply-master to only the base names in a
                  {"log_projects": [...]} file (e.g. NBC/BIC-Templates/project_name.json)
                  instead of every project group discovered in the folder. Required for
                  create-missing.

Usage:
  python3 check_project_sync.py check [--folder FOLDER] [--repo-root PATH] [--frequency] [--project-list PATH]
  python3 check_project_sync.py sync-json-keys [--folder FOLDER] [--repo-root PATH] [--dry-run] [--frequency] [--project-list PATH]
  python3 check_project_sync.py apply-master --master PATH [--folder FOLDER] [--repo-root PATH] [--dry-run] [--frequency] [--project-list PATH]
  python3 check_project_sync.py generate-l2m-projects --master-settings PATH [--repo-root PATH] [--dry-run]
  python3 check_project_sync.py create-missing --project-list PATH --master LOG_TEMPLATE --master-settings L2M_TEMPLATE [--repo-root PATH] [--dry-run]

Frequency detection projects (instance_type = LogFrequency) follow a different naming convention:
  Stage : {base}_frequency_detection          (e.g. akamai_frequency_detection)
          {base}_stage_frequency_detection     (e.g. conviva_alerts_stage_frequency_detection)
  UAT   : {base}_uat_frequency_detection       (e.g. akamai_uat_frequency_detection)
  Prod  : {base}_prod_frequency_detection      (e.g. akamai_prod_frequency_detection)

The --frequency flag enables correct cross-env matching for this naming scheme.

generate-l2m-projects:
  Walks each environment's log-projects/ folder, reads project_name from every .tf file,
  and creates a corresponding l2m-projects/{stem}_l2m.tf using --master-settings as the
  template. Only project_name, project_display_name, and the resource label are substituted;
  all other settings are copied verbatim from the master file. WARNING: this overwrites any
  existing l2m file for every log project found — use create-missing instead if you only
  want to fill in gaps for a specific project list.
  Example:
    log-projects/adobe_uat.tf  (project_name = "adobe-uat")
    → l2m-projects/adobe_uat_l2m.tf  (project_name = "adobe-uat-L2M")

create-missing:
  Reads a {"log_projects": [base names]} file and, per environment (stage: no suffix,
  uat: "-uat"/"_uat", prod: "-prod"/"_prod"), creates any log-projects/{stem}.tf or
  l2m-projects/{stem}_l2m.tf that doesn't already exist yet — never overwrites an existing
  file. The log template is rendered in full (including its json_key_settings and
  l2m_settings, with metric_project_name rewritten to the new project). The l2m template is
  rendered WITHOUT metric_configurations, since a brand-new metric project has no real
  backend component id yet — that gets filled in later by the existing
  sync_environments.py / poll_new_l2m_projects.py pipeline once the project has ingested
  data and been assigned a real Global_ id.
"""

import json
import re
import sys
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENVS = {
    "stage": {
        "dir": "NBC Stage/Stage Infra",
        "strip_suffixes": ["_stage"],
        "strip_prefixes": ["nbc_stage_"],
        "env_tag": "_stage",
    },
    "uat": {
        "dir": "NBC UAT/Stage Infra",
        "strip_suffixes": ["_uat"],
        "strip_prefixes": ["nbc_uat_"],
        "env_tag": "_uat",
    },
    "prod": {
        "dir": "NBC Prod",
        "strip_suffixes": ["_prod"],
        "strip_prefixes": ["nbc_prod_"],
        "env_tag": "_prod",
    },
}

# Inverse of ENVS' strip rules — given a base name, how to construct this
# env's filename stem and project_name. Used by create-missing.
ENV_SUFFIX = {
    "stage": {"file": "", "name": ""},
    "uat": {"file": "_uat", "name": "-uat"},
    "prod": {"file": "_prod", "name": "-prod"},
}

# Suffix shared by all LogFrequency project filenames
FREQUENCY_SUFFIX = "_frequency_detection"
# Suffix shared by all l2m-projects filenames
L2M_SUFFIX = "_l2m"
ENV_ORDER = ["stage", "uat", "prod"]

SKIP_FILES = {"variables.tf", "versions.tf"}

# Fields never propagated (env-specific by design)
SKIP_FIELDS = {"project_name", "project_display_name", "system_name"}

# Multi-line block field names
BLOCK_FIELDS = {"project_creation_config", "json_key_settings", "log_label_settings"}

# Flat fields that sit AFTER log_label_settings/l2m_settings/json_key_settings/
# metric_configurations in the master file (i.e. at the very end of the
# resource, right before the closing brace) rather than in the normal
# contiguous flat-field zone. Only these fields' insertion point should skip
# past those blocks — see _skip_trailing_blocks. Everything else (e.g. "mode",
# which sits right before those blocks) must NOT skip past them: doing so
# would insert/reposition it at the end instead of its correct spot.
FIELDS_AFTER_TRAILING_BLOCKS = {"service_now_short_description_format", "service_now_description_format"}
TRAILING_SKIPPABLE_BLOCKS = ("log_label_settings", "l2m_settings", "json_key_settings", "metric_configurations")

# Column at which '=' is aligned in TF files (0-indexed from line start)
EQ_COLUMN = 43

# Order of fields within a json_key_settings entry. The base fields are always
# emitted; the notification fields are only emitted for entries that actually
# have them (most entries don't) — see format_json_key_entry.
JSON_KEY_BASE_FIELDS = [
    "json_key",
    "type",
    "summary_setting",
    "metafield_setting",
    "dampening_field_setting",
]
JSON_KEY_NOTIFICATION_FIELDS = [
    "notification_setting",
    "notification_setting_display_name",
]
JSON_KEY_ENTRY_FIELDS = JSON_KEY_BASE_FIELDS + JSON_KEY_NOTIFICATION_FIELDS
JSON_KEY_STRING_FIELDS = {"json_key", "type", "notification_setting_display_name"}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TFProject:
    path: Path
    env: str
    normalized_name: str
    project_name: str
    instance_type: str
    is_servicenow: bool
    is_frequency: bool         # True when instance_type == "LogFrequency"
    flat_fields: dict          # field_name -> raw_value (single-line string as in file)
    json_key_entries: list     # list of dicts: {json_key, type, summary_setting, ...}
    raw_text: str


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def normalize_name(stem: str, env: str) -> str:
    """Strip environment suffix or prefix from a filename stem.

    For frequency detection projects the env tag is embedded before the
    '_frequency_detection' suffix, e.g.:
        akamai_uat_frequency_detection  ->  akamai_frequency_detection
        conviva_alerts_stage_frequency_detection  ->  conviva_alerts_frequency_detection
    Likewise for l2m-projects filenames, the env tag is embedded before the
    '_l2m' suffix, e.g.:
        baldur_uat_l2m  ->  baldur_l2m
        baldur_prod_l2m  ->  baldur_l2m
    Files that already lack the env tag (common in stage) are returned as-is.
    The nbc_{env}_ prefix variant (e.g. nbc_prod_servicenow_...) is handled by
    the regular prefix rule below.
    """
    cfg = ENVS[env]

    # Frequency detection: strip _{env} embedded before _frequency_detection
    freq_env_suffix = cfg["env_tag"] + FREQUENCY_SUFFIX
    if stem.endswith(freq_env_suffix):
        return stem[: -len(freq_env_suffix)] + FREQUENCY_SUFFIX

    # l2m-projects: strip _l2m, strip the env suffix from what remains, then
    # reattach _l2m — the env suffix sits before _l2m, not at the very end.
    if stem.endswith(L2M_SUFFIX):
        base = stem[: -len(L2M_SUFFIX)]
        for suffix in cfg["strip_suffixes"]:
            if base.endswith(suffix):
                return base[: -len(suffix)] + L2M_SUFFIX
        return stem

    for suffix in cfg["strip_suffixes"]:
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    for prefix in cfg["strip_prefixes"]:
        if stem.startswith(prefix):
            return stem[len(prefix):]
    return stem


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def count_net_brackets(s: str) -> int:
    """
    Count unmatched open brackets/parens in s, ignoring content inside strings.
    Returns > 0 if more opens than closes (multi-line block follows).
    """
    count = 0
    in_str = False
    i = 0
    while i < len(s):
        c = s[i]
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c in '{[(':
            count += 1
        elif c in '}])':
            count -= 1
        i += 1
    return count


def find_block_end(text: str, open_pos: int) -> int:
    """
    Given position of an opening bracket/brace in text, return position
    immediately after the matching closing bracket.
    """
    open_char = text[open_pos]
    close_char = {'{': '}', '[': ']', '(': ')'}[open_char]
    depth = 0
    in_str = False
    i = open_pos
    while i < len(text):
        c = text[i]
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == open_char:
            depth += 1
        elif c == close_char:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(text)


def get_resource_body(text: str) -> str:
    """Return the text inside the outermost resource { ... } block."""
    m = re.search(r'resource\s+"[^"]+"\s+"[^"]+"\s*\{', text)
    if not m:
        return text
    brace_pos = text.index('{', m.start())
    end = find_block_end(text, brace_pos)
    return text[brace_pos + 1 : end - 1]


def parse_flat_fields(text: str) -> dict:
    """
    Extract top-level (2-space indented) single-line key=value fields.
    Skips multi-line blocks and fields in SKIP_FIELDS / BLOCK_FIELDS.
    """
    fields = {}
    depth = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        if depth == 0:
            m = re.match(r'^(\w+)(\s*=\s*)(.+)$', stripped)
            if m:
                key = m.group(1)
                val = m.group(3).strip()
                net = count_net_brackets(val)
                if net > 0:
                    depth += net  # opens a multi-line block
                elif key not in SKIP_FIELDS and key not in BLOCK_FIELDS:
                    fields[key] = val
            else:
                depth += count_net_brackets(stripped)
        else:
            depth += count_net_brackets(stripped)
            if depth < 0:
                depth = 0

    return fields


def get_instance_type(text: str) -> str:
    """Extract instance_type value from anywhere in the file."""
    m = re.search(r'instance_type\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else ""


def parse_json_key_settings(text: str) -> list:
    """Parse json_key_settings entries. Returns list of dicts."""
    m = re.search(r'json_key_settings\s*=\s*\[', text)
    if not m:
        return []

    open_pos = text.index('[', m.start())
    end_pos = find_block_end(text, open_pos)
    block = text[open_pos + 1 : end_pos - 1]

    entries = []
    i = 0
    while i < len(block):
        if block[i] == '{':
            close = find_block_end(block, i)
            inner = block[i + 1 : close - 1]
            entry = {}
            for kv in re.finditer(
                r'(\w+)\s*=\s*(?:"([^"]*)"|(true|false|[\d.]+))',
                inner
            ):
                k = kv.group(1)
                v = kv.group(2) if kv.group(2) is not None else kv.group(3)
                entry[k] = v
            if 'json_key' in entry:
                entries.append(entry)
            i = close
        else:
            i += 1

    return entries


# ---------------------------------------------------------------------------
# Project loader
# ---------------------------------------------------------------------------

def load_tf_project(path: Path, env: str) -> Optional[TFProject]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  WARNING: cannot read {path}: {e}", file=sys.stderr)
        return None

    normalized = normalize_name(path.stem, env)
    instance_type = get_instance_type(text)
    is_servicenow = instance_type == "ServiceNow"
    is_frequency  = instance_type == "LogFrequency"

    m = re.search(r'project_name\s*=\s*"([^"]+)"', text)
    project_name = m.group(1) if m else ""

    body = get_resource_body(text)
    flat_fields = parse_flat_fields(body)

    json_key_entries = parse_json_key_settings(text)

    return TFProject(
        path=path,
        env=env,
        normalized_name=normalized,
        project_name=project_name,
        instance_type=instance_type,
        is_servicenow=is_servicenow,
        is_frequency=is_frequency,
        flat_fields=flat_fields,
        json_key_entries=json_key_entries,
        raw_text=text,
    )


def collect_projects(nbc_root: Path, folder_name: str, dir_overrides: Optional[dict] = None) -> dict:
    """
    Returns dict: normalized_name -> { env: TFProject }
    Only includes groups that have at least one env present.

    dir_overrides: optional {env: Path} — for an "infra-duplicate" folder that
    isn't one of the three ENVS dirs (e.g. NBC UAT/Prod Infra). Pair with
    --env so only that one env is actually processed.
    """
    groups: dict = defaultdict(dict)
    for env, cfg in ENVS.items():
        base_dir = (dir_overrides or {}).get(env, nbc_root / cfg["dir"])
        folder = base_dir / folder_name
        if not folder.exists():
            continue
        for tf_path in sorted(folder.glob("*.tf")):
            if tf_path.name in SKIP_FILES:
                continue
            proj = load_tf_project(tf_path, env)
            if proj:
                groups[proj.normalized_name][env] = proj

    return dict(groups)


def collect_l2m_projects_for_names(nbc_root: Path, project_names: list,
                                    dir_overrides: Optional[dict] = None) -> dict:
    """Build {base_name: {env: TFProject}} for l2m-projects, using the exact
    per-env filename convention (base + ENV_SUFFIX['file'] + '_l2m.tf') instead
    of collect_projects' generic normalize_name suffix-stripping — that doesn't
    work for l2m filenames, since the env suffix sits before "_l2m", not at the
    very end of the stem (e.g. "baldur_uat_l2m" ends with "_l2m", not "_uat",
    so normalize_name never strips anything and cross-env matching silently
    produces zero matches).

    dir_overrides: optional {env: Path} — for an "infra-duplicate" folder that
    isn't one of the three ENVS dirs (e.g. NBC UAT/Prod Infra, a second UAT
    deployment on a different host that happens to share the "-uat" naming
    convention). Pair with --env so only that one env is actually processed."""
    groups: dict = defaultdict(dict)
    for env in ENV_ORDER:
        cfg = ENVS[env]
        suf = ENV_SUFFIX[env]
        base_dir = (dir_overrides or {}).get(env, nbc_root / cfg["dir"])
        l2m_dir = base_dir / "l2m-projects"
        if not l2m_dir.exists():
            continue
        for base in project_names:
            path = l2m_dir / f"{base}{suf['file']}_l2m.tf"
            if not path.exists():
                continue
            proj = load_tf_project(path, env)
            if proj:
                groups[base][env] = proj
    return dict(groups)


def discover_folders(nbc_root: Path) -> list:
    found = set()
    for cfg in ENVS.values():
        env_path = nbc_root / cfg["dir"]
        if env_path.exists():
            for d in env_path.iterdir():
                if d.is_dir() and not d.name.startswith("."):
                    found.add(d.name)
    return sorted(found)


def load_project_list(path: Path) -> list:
    """Read a {"log_projects": [...]} file (e.g. BIC-Templates/project_name.json)
    and return the base project names."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("log_projects", [])


def filter_groups_by_names(groups: dict, names: Optional[list]) -> dict:
    """Restrict a project-group dict to only the given base names. Used to scope
    apply-master / sync-json-keys / check to a specific project list (e.g. only
    BIC projects) instead of every project group in the folder."""
    if not names:
        return groups
    name_set = set(names)
    return {k: v for k, v in groups.items() if k in name_set}


# ---------------------------------------------------------------------------
# Command: check
# ---------------------------------------------------------------------------

def _filter_groups(groups: dict, frequency: bool) -> dict:
    """
    Filter project groups by type.

    frequency=True  → keep only LogFrequency projects
    frequency=False → keep only non-frequency, non-ServiceNow projects
    """
    filtered = {}
    for name, envs in groups.items():
        kept = {}
        for env, proj in envs.items():
            if frequency:
                if proj.is_frequency:
                    kept[env] = proj
            else:
                if not proj.is_frequency and not proj.is_servicenow:
                    kept[env] = proj
        if kept:
            filtered[name] = kept
    return filtered


def cmd_check(groups: dict, folder_name: str, frequency: bool = False) -> None:
    mode_label = " [frequency]" if frequency else ""
    groups = _filter_groups(groups, frequency)
    print(f"\n{'='*72}")
    print(f"  Folder: {folder_name}{mode_label}")
    print(f"{'='*72}")

    all_names = sorted(groups.keys())

    # --- Missing ---
    missing_any = [n for n in all_names if len(groups[n]) < len(ENVS)]
    if missing_any:
        print("\n[MISSING PROJECTS]")
        for name in missing_any:
            present = sorted(groups[name].keys())
            absent = [e for e in ENV_ORDER if e not in groups[name]]
            print(f"  {name}")
            print(f"    present : {', '.join(present)}")
            print(f"    missing : {', '.join(absent)}")
    else:
        print("\n[MISSING PROJECTS] None.")

    # --- Field diffs ---
    diffs_found = False
    diff_lines = []
    for name in all_names:
        envs_present = {e: groups[name][e] for e in ENV_ORDER if e in groups[name]}
        if len(envs_present) < 2:
            continue

        all_keys = set()
        for proj in envs_present.values():
            all_keys.update(proj.flat_fields.keys())

        proj_diffs = []
        for key in sorted(all_keys):
            vals = {
                env: proj.flat_fields.get(key, "<missing>")
                for env, proj in envs_present.items()
            }
            unique_vals = set(vals.values())
            if len(unique_vals) > 1:
                proj_diffs.append((key, vals))

        if proj_diffs:
            diffs_found = True
            diff_lines.append(f"\n  Project: {name}")
            for key, vals in proj_diffs:
                diff_lines.append(f"    [{key}]")
                for env in ENV_ORDER:
                    if env in vals:
                        diff_lines.append(f"      {env:<6}: {vals[env]}")

    if diffs_found:
        print(f"\n[FIELD DIFFS]")
        for line in diff_lines:
            print(line)
    else:
        print("\n[FIELD DIFFS] None — all shared projects have matching field values.")

    # --- Summary table ---
    col_w = max((len(n) for n in all_names), default=10) + 2
    print(f"\n[SUMMARY] {folder_name}")
    print(f"  {'Project':<{col_w}} {'stage':^8} {'uat':^8} {'prod':^8}")
    print("  " + "-" * (col_w + 28))
    for name in all_names:
        row = f"  {name:<{col_w}}"
        for env in ENV_ORDER:
            mark = "✓" if env in groups[name] else "✗"
            row += f" {mark:^8}"
        print(row)


# ---------------------------------------------------------------------------
# Command: sync-json-keys
# ---------------------------------------------------------------------------

def format_json_key_entry(entry: dict, is_last: bool = False) -> str:
    """Format a single json_key_settings entry block.

    Base fields are always emitted. The notification_setting /
    notification_setting_display_name pair is only emitted when the entry
    actually carries it, so plain entries don't get padded out with
    notification_setting = false on every single key.
    """
    has_notification = any(k in entry for k in JSON_KEY_NOTIFICATION_FIELDS)
    keys = JSON_KEY_BASE_FIELDS + (JSON_KEY_NOTIFICATION_FIELDS if has_notification else [])
    pad = max(len(k) for k in keys) + 1

    lines = ["    {"]
    for key in keys:
        raw_val = entry.get(key, "false" if key not in JSON_KEY_STRING_FIELDS else "")
        if key in JSON_KEY_STRING_FIELDS:
            val_str = f'"{raw_val}"'
        else:
            val_str = raw_val  # true/false
        lines.append(f"      {key:<{pad}}= {val_str}")
    lines.append("    }" + ("" if is_last else ","))
    return "\n".join(lines)


def build_json_key_settings_block(entries: list) -> str:
    """Reconstruct the full json_key_settings = [...] block."""
    lines = ["  json_key_settings = ["]
    for i, entry in enumerate(entries):
        lines.append(format_json_key_entry(entry, is_last=(i == len(entries) - 1)))
    lines.append("  ]")
    return "\n".join(lines)


def replace_json_key_settings_in_text(text: str, entries: list) -> str:
    """Replace the json_key_settings block in file text with rebuilt block."""
    m = re.search(r'[ \t]*json_key_settings\s*=\s*\[', text)
    if not m:
        # No existing block — insert before closing }
        new_block = "\n" + build_json_key_settings_block(entries) + "\n"
        last_brace = text.rfind("\n}")
        if last_brace >= 0:
            return text[:last_brace + 1] + new_block + text[last_brace + 1:]
        return text + new_block

    open_pos = text.index('[', m.start())
    end_pos = find_block_end(text, open_pos)

    new_block = build_json_key_settings_block(entries)
    return text[: m.start()] + new_block + text[end_pos:]


def cmd_sync_json_keys(groups: dict, folder_name: str, dry_run: bool, frequency: bool = False) -> None:
    mode_label = " [frequency]" if frequency else ""
    groups = _filter_groups(groups, frequency)
    print(f"\n{'='*72}")
    print(f"  Folder: {folder_name}  [sync-json-keys{' DRY-RUN' if dry_run else ''}{mode_label}]")
    print(f"{'='*72}")

    for name in sorted(groups.keys()):
        envs_present = {e: groups[name][e] for e in ENV_ORDER if e in groups[name]}
        if len(envs_present) < 2:
            continue

        # Collect all unique json_key entries across envs, keyed by json_key value.
        # Preserve per-entry settings (e.g. summary_setting may differ).
        master_entries: dict = {}  # json_key -> entry dict
        for proj in envs_present.values():
            for entry in proj.json_key_entries:
                jk = entry["json_key"]
                if jk not in master_entries:
                    master_entries[jk] = entry

        if not master_entries:
            continue

        # Sort by json_key for deterministic output
        sorted_master = sorted(master_entries.values(), key=lambda e: e["json_key"])

        for env, proj in envs_present.items():
            existing_keys = {e["json_key"] for e in proj.json_key_entries}
            missing_keys = [e for e in sorted_master if e["json_key"] not in existing_keys]

            if not missing_keys:
                continue

            print(f"\n  {name} [{env}] — adding {len(missing_keys)} missing json_key(s):")
            for e in missing_keys:
                print(f"    + {e['json_key']}")

            if not dry_run:
                new_entries = proj.json_key_entries + missing_keys
                # Sort combined list by json_key
                new_entries.sort(key=lambda e: e["json_key"])
                new_text = replace_json_key_settings_in_text(proj.raw_text, new_entries)
                proj.path.write_text(new_text, encoding="utf-8")
                print(f"    => written: {proj.path}")

    print()


# ---------------------------------------------------------------------------
# Block-level helpers (for log_label_settings and similar blocks)
# ---------------------------------------------------------------------------

def extract_raw_block(text: str, block_name: str) -> str:
    """
    Return the full raw text of a top-level block assignment, e.g.:
        '  log_label_settings = [\n    ...\n  ]'
    Returns empty string if the block is not present.
    """
    m = re.search(r'^  ' + re.escape(block_name) + r'[ \t]*=[ \t]*([\[{])',
                  text, re.MULTILINE)
    if not m:
        return ""
    open_pos = m.start(1)
    end_pos  = find_block_end(text, open_pos)
    # Include the trailing newline if present
    if end_pos < len(text) and text[end_pos] == '\n':
        end_pos += 1
    return text[m.start() : end_pos]


def replace_block_in_text(text: str, block_name: str, new_block: str) -> tuple:
    """
    Replace an existing top-level block with new_block.
    If the block does not exist, insert it before json_key_settings or
    before the closing brace.
    Returns (new_text, action) where action is 'replaced', 'added', or 'unchanged'.
    """
    m = re.search(r'^  ' + re.escape(block_name) + r'[ \t]*=[ \t]*([\[{])',
                  text, re.MULTILINE)
    if m:
        open_pos = m.start(1)
        end_pos  = find_block_end(text, open_pos)
        if end_pos < len(text) and text[end_pos] == '\n':
            end_pos += 1
        old_block = text[m.start() : end_pos]
        if old_block.rstrip('\n') == new_block.rstrip('\n'):
            return text, 'unchanged'
        replacement = new_block if new_block.endswith('\n') else new_block + '\n'
        return text[:m.start()] + replacement + text[end_pos:], 'replaced'

    # Block not present — insert before json_key_settings or closing brace
    anchor = re.search(r'^  json_key_settings[ \t]*=', text, re.MULTILINE)
    if anchor:
        ins = anchor.start()
        leading = ''
    else:
        idx = text.rfind("\n}")
        ins = idx + 1 if idx >= 0 else len(text)
        # No json_key_settings anchor (e.g. l2m-projects files) — the closing-brace
        # fallback lands right after the last flat field, so add a separating
        # blank line ourselves instead of jamming the new block onto that line.
        leading = '' if ins == 0 or text[ins - 2:ins] == '\n\n' else '\n'

    block_text = new_block if new_block.endswith('\n') else new_block + '\n'
    return text[:ins] + leading + block_text + '\n' + text[ins:], 'added'


# ---------------------------------------------------------------------------
# Command: apply-master
# ---------------------------------------------------------------------------

def replace_flat_field(text: str, field_name: str, new_value: str) -> tuple:
    """
    Replace a top-level (2-space indented) field's value in TF file text.
    Returns (new_text, was_replaced).
    """
    # Match exactly the top-level assignment line (2-space indent)
    pattern = re.compile(
        r'^([ ]{2}' + re.escape(field_name) + r'[ \t]*=[ \t]*)(.+)$',
        re.MULTILINE
    )
    found = [False]

    def replacer(m):
        found[0] = True
        return m.group(1) + new_value

    new_text = pattern.sub(replacer, text, count=1)
    return new_text, found[0]


def find_insertion_point(
    text: str,
    field_name: str,
    master_order: list = None,
) -> int:
    """
    Return the character position at which to insert a new top-level flat field.

    Strategy (in priority order):
    1. If master_order is given: find the nearest predecessor of field_name in
       master_order that already exists in the target file, and insert after it.
       If no predecessor exists, find the nearest successor and insert before it.
    2. Alphabetical predecessor search: find the flat field with the LARGEST
       name that is still LESS THAN field_name (this avoids the header-field
       trap — e.g. project_time_zone sorts after causal_* but lives in the
       header, not the alphabetical section).
    3. Fall back to just before the first block or the closing brace.
    """

    def _line_end(pos: int) -> int:
        """Character position right after the newline on the line at pos."""
        nl = text.find('\n', pos)
        return nl + 1 if nl >= 0 else len(text)

    def _skip_trailing_blocks(pos: int) -> int:
        """Advance pos past any contiguous run of TRAILING_SKIPPABLE_BLOCKS
        assignments that starts right at pos (tolerating blank lines between
        them). Without this, inserting a field right after its nearest
        flat-field predecessor (e.g. "mode") would jam it in BEFORE
        log_label_settings/l2m_settings/json_key_settings whenever the target
        already has those blocks — wrong for fields like
        service_now_short_description_format, which in the master sits AFTER
        all of them, at the very end of the resource."""
        i = pos
        while True:
            j = i
            while j < len(text) and text[j] == '\n':
                j += 1
            m = re.match(r'  (\w+)[ \t]*=[ \t]*([\[{])', text[j:])
            if not m or m.group(1) not in TRAILING_SKIPPABLE_BLOCKS:
                break
            open_pos = j + m.end(2) - 1
            end_pos = find_block_end(text, open_pos)
            if end_pos < len(text) and text[end_pos] == '\n':
                end_pos += 1
            i = end_pos
        return i

    # --- Strategy 1: master-order ---
    if master_order and field_name in master_order:
        idx = master_order.index(field_name)

        # Walk backwards to find nearest predecessor that exists in target
        for i in range(idx - 1, -1, -1):
            pred = master_order[i]
            m = re.search(
                r'^  ' + re.escape(pred) + r'[ \t]*=[ \t]*.+$',
                text, re.MULTILINE,
            )
            if m:
                end = _line_end(m.start())
                return _skip_trailing_blocks(end) if field_name in FIELDS_AFTER_TRAILING_BLOCKS else end

        # Walk forwards to find nearest successor that exists in target
        for i in range(idx + 1, len(master_order)):
            succ = master_order[i]
            m = re.search(
                r'^  ' + re.escape(succ) + r'[ \t]*=',
                text, re.MULTILINE,
            )
            if m:
                return m.start()

    # --- Strategy 2: alphabetical predecessor ---
    best_pos = None
    best_name = None
    for m in re.finditer(r'^  (\w+)([ \t]*=[ \t]*)(.+)$', text, re.MULTILINE):
        fname = m.group(1)
        val   = m.group(3).strip()
        if fname in SKIP_FIELDS or fname in BLOCK_FIELDS or count_net_brackets(val) > 0:
            continue
        # Keep track of the largest name that is still less than field_name
        if fname < field_name:
            if best_name is None or fname > best_name:
                best_name = fname
                best_pos = _line_end(m.start())

    if best_pos is not None:
        return best_pos

    # --- Strategy 3: fallback ---
    for marker in ["log_label_settings", "json_key_settings"]:
        m = re.search(r'^  ' + marker + r'[ \t]*=', text, re.MULTILINE)
        if m:
            return m.start()

    idx = text.rfind("\n}")
    return idx + 1 if idx >= 0 else len(text)


def insert_flat_field(
    text: str,
    field_name: str,
    new_value: str,
    master_order: list = None,
) -> str:
    """Insert a new top-level field at the correct position."""
    key_width = EQ_COLUMN - 2  # 41 chars → '=' lands at EQ_COLUMN
    line = f"  {field_name:<{key_width}}= {new_value}\n"
    pos = find_insertion_point(text, field_name, master_order)
    return text[:pos] + line + text[pos:]


def reorder_field(
    text: str,
    field_name: str,
    master_order: list = None,
) -> str:
    """
    If field_name exists but is not at its correct position, move it.
    Uses master_order if provided, otherwise falls back to alphabetical.
    """
    pattern = re.compile(
        r'^  ' + re.escape(field_name) + r'[ \t]*=[ \t]*.+\n?',
        re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        return text

    field_line = m.group(0)
    if not field_line.endswith('\n'):
        field_line += '\n'

    # Remove from current position
    text_without = text[:m.start()] + text[m.end():]

    correct_pos = find_insertion_point(text_without, field_name, master_order)

    # If the field is already at the right position, nothing to do
    if m.start() == correct_pos:
        return text

    return text_without[:correct_pos] + field_line + text_without[correct_pos:]


def merge_json_key_entries(target_entries: list, master_entries: list) -> list:
    """Replace-if-exists-else-add: every key the master defines is pushed onto
    the target verbatim (in master order), including any notification_setting
    fields. Keys the target has that the master doesn't define are kept,
    appended after — this never deletes a project-specific key."""
    master_keys = {e["json_key"] for e in master_entries}
    extra = [e for e in target_entries if e["json_key"] not in master_keys]
    return list(master_entries) + extra


def render_l2m_settings_block(master_block: str, target_project_name: str) -> str:
    """Substitute metric_project_name inside an l2m_settings block for the
    target project's own "{name}-L2M", leaving json_parsers etc. verbatim."""
    return re.sub(
        r'(metric_project_name\s*=\s*")[^"]+(")',
        rf'\g<1>{target_project_name}-L2M\2',
        master_block,
        count=1,
    )


# ---------------------------------------------------------------------------
# L2M metric_alert_settings sync (apply-l2m-master)
# ---------------------------------------------------------------------------

def load_metric_overrides(path: Optional[Path]) -> tuple:
    """Read BIC-Templates/metric_config_l2m.json:
        {"exclude_metric_configurations": [...],
         "metric_alert_setting_overrides": {name: {field: raw_hcl_value}}}
    Returns (exclude_set, overrides_by_name). Override values are raw HCL
    literal text (quotes included for strings, e.g. '"25.0"'), same
    convention as flat_fields values elsewhere in this script. path=None
    (no --metric-overrides given) means no exclusions/overrides at all."""
    if path is None or not path.exists():
        return set(), {}
    data = json.loads(path.read_text(encoding="utf-8"))
    exclude = set(data.get("exclude_metric_configurations", []))
    overrides = data.get("metric_alert_setting_overrides", {})
    return exclude, overrides


def extract_metric_alert_settings_block(text: str) -> str:
    """Return the full `metric_alert_settings = [ { ... } ]` text, or "" if absent."""
    m = re.search(r'metric_alert_settings\s*=\s*\[', text)
    if not m:
        return ""
    open_pos = text.index('[', m.start())
    end_pos = find_block_end(text, open_pos)
    return text[m.start():end_pos]


def parse_metric_alert_fields(block_text: str) -> dict:
    """Parse scalar `field = value` lines out of a metric_alert_settings block
    (single object entry). Values are kept as raw HCL text (quotes included)."""
    fields = {}
    for m in re.finditer(r'^\s*(\w+)\s*=\s*(.+?)\s*$', block_text, re.MULTILINE):
        key, val = m.group(1), m.group(2)
        if key == "metric_alert_settings":  # the opening "metric_alert_settings = [" line itself
            continue
        fields[key] = val
    return fields


def sync_metric_alert_settings(
    text: str,
    master_fields: dict,
    overrides_for_project: dict,
) -> tuple:
    """Replace scalar field values inside an EXISTING metric_alert_settings
    entry with master's canonical values, with per-project overrides applied
    on top. Never touches component_name (that's the project's own
    var.<label>_id reference) and never adds/removes the block itself — a
    project with no metric_alert_settings yet is left alone (it has no real
    backend component id to attach one to).
    Returns (new_text, changes) where changes is [(field, old, new), ...].
    """
    block = extract_metric_alert_settings_block(text)
    if not block:
        return text, []

    current_fields = parse_metric_alert_fields(block)
    new_block = block
    changes = []
    for field, master_val in master_fields.items():
        if field == "component_name":
            continue
        target_val = overrides_for_project.get(field, master_val)
        current_val = current_fields.get(field)
        if current_val is None or current_val == target_val:
            continue
        pat = re.compile(r'(^\s*' + re.escape(field) + r'\s*=\s*).+$', re.MULTILINE)
        new_block, n = pat.subn(lambda mo: mo.group(1) + target_val, new_block, count=1)
        if n:
            changes.append((field, current_val, target_val))

    if not changes:
        return text, []

    start = text.index(block)
    return text[:start] + new_block + text[start + len(block):], changes


def cmd_apply_l2m_master(
    groups: dict,
    master_path: Path,
    overrides_path: Optional[Path],
    dry_run: bool,
    env_filter: Optional[str] = None,
) -> None:
    envs_to_process = [env_filter] if env_filter else ENV_ORDER
    env_label = f" [env={env_filter}]" if env_filter else ""
    print(f"\n{'='*72}")
    print(f"  Folder: l2m-projects  [apply-l2m-master{' DRY-RUN' if dry_run else ''}{env_label}]")
    print(f"  Master : {master_path}")
    print(f"  Overrides : {overrides_path if overrides_path else '(none given)'}")
    print(f"{'='*72}")

    master = load_tf_project(master_path, "stage")
    if not master:
        print("  ERROR: could not load master file.", file=sys.stderr)
        return

    master_fields = master.flat_fields
    master_order = list(master_fields.keys())
    master_metric_fields = parse_metric_alert_fields(
        extract_metric_alert_settings_block(master.raw_text)
    )
    exclude_set, overrides_by_name = load_metric_overrides(overrides_path)

    print(f"\n  Master has {len(master_fields)} flat field(s) to propagate.")
    print(f"  Master has {len(master_metric_fields)} metric_alert_settings field(s) to propagate.")
    if exclude_set:
        print(f"  Excluded from metric_configurations sync: {', '.join(sorted(exclude_set))}")
    if overrides_by_name:
        print(f"  Per-project field overrides: {', '.join(sorted(overrides_by_name))}")
    print()

    for name in sorted(groups.keys()):
        for env in envs_to_process:
            if env not in groups[name]:
                continue
            proj = groups[name][env]

            changes = []
            new_text = proj.raw_text
            fields_to_reorder = []

            for field_name in master_order:
                if field_name in SKIP_FIELDS:
                    continue
                master_val = master_fields[field_name]
                current_val = proj.flat_fields.get(field_name)
                if current_val is None:
                    changes.append(("ADD", field_name, None, master_val))
                    if not dry_run:
                        new_text = insert_flat_field(new_text, field_name, master_val, master_order)
                elif current_val != master_val:
                    changes.append(("UPDATE", field_name, current_val, master_val))
                    if not dry_run:
                        new_text, _ = replace_flat_field(new_text, field_name, master_val)
                        fields_to_reorder.append(field_name)

            if not dry_run:
                for field_name in fields_to_reorder:
                    new_text = reorder_field(new_text, field_name, master_order)

            metric_changes = []
            if name in exclude_set:
                pass  # never touch metric_configurations for excluded projects
            else:
                overrides_for_project = overrides_by_name.get(name, {})
                if dry_run:
                    _, metric_changes = sync_metric_alert_settings(
                        proj.raw_text, master_metric_fields, overrides_for_project
                    )
                else:
                    new_text, metric_changes = sync_metric_alert_settings(
                        new_text, master_metric_fields, overrides_for_project
                    )

            if changes or metric_changes:
                print(f"  {name} [{env}] — {len(changes)} field change(s)"
                      + (f" + {len(metric_changes)} metric_alert_settings field(s)" if metric_changes else "") + ":")
                for op, fname, old, new in changes:
                    if op == "ADD":
                        print(f"    + ADD    {fname} = {new}")
                    else:
                        print(f"    ~ UPDATE {fname}")
                        print(f"             was : {old}")
                        print(f"             now : {new}")
                for fname, old, new in metric_changes:
                    print(f"    ~ UPDATE metric_alert_settings.{fname}")
                    print(f"             was : {old}")
                    print(f"             now : {new}")

                if not dry_run:
                    proj.path.write_text(new_text, encoding="utf-8")
                    print(f"    => written: {proj.path}")
            else:
                print(f"  {name} [{env}] — no changes.")

    print()


def cmd_apply_master(
    groups: dict,
    folder_name: str,
    master_path: Path,
    dry_run: bool,
    frequency: bool = False,
    env_filter: Optional[str] = None,
) -> None:
    mode_label = " [frequency]" if frequency else ""
    env_label = f" [env={env_filter}]" if env_filter else ""
    groups = _filter_groups(groups, frequency)
    envs_to_process = [env_filter] if env_filter else ENV_ORDER
    print(f"\n{'='*72}")
    print(f"  Folder: {folder_name}  [apply-master{' DRY-RUN' if dry_run else ''}{mode_label}{env_label}]")
    print(f"  Master : {master_path}")
    print(f"{'='*72}")

    # Load master
    master = load_tf_project(master_path, "stage")  # env doesn't matter for master
    if not master:
        print("  ERROR: could not load master file.", file=sys.stderr)
        return

    master_fields = master.flat_fields
    # Preserve master field order for positional insertion
    master_order = list(master_fields.keys())
    master_log_label_block = extract_raw_block(master.raw_text, "log_label_settings")
    master_l2m_settings_block = extract_raw_block(master.raw_text, "l2m_settings")
    master_json_keys = master.json_key_entries
    print(f"\n  Master has {len(master_fields)} flat field(s) to propagate.")
    if master_log_label_block:
        print(f"  Master has log_label_settings block — will propagate.")
    if master_l2m_settings_block:
        print(f"  Master has l2m_settings block — will propagate (metric_project_name rewritten per target).")
    if master_json_keys:
        print(f"  Master has {len(master_json_keys)} json_key_settings entr(y/ies) — will replace-if-exists-else-add.")
    print()

    for name in sorted(groups.keys()):
        for env in envs_to_process:
            if env not in groups[name]:
                continue
            proj = groups[name][env]

            changes = []
            new_text = proj.raw_text
            fields_to_reorder = []

            # Iterate in master order so inserts land in correct relative order
            for field_name in master_order:
                if field_name in SKIP_FIELDS:
                    continue

                master_val  = master_fields[field_name]
                current_val = proj.flat_fields.get(field_name)

                if current_val is None:
                    # Field missing in target — insert at master-order position
                    changes.append(("ADD", field_name, None, master_val))
                    if not dry_run:
                        new_text = insert_flat_field(
                            new_text, field_name, master_val, master_order
                        )
                elif current_val != master_val:
                    changes.append(("UPDATE", field_name, current_val, master_val))
                    if not dry_run:
                        new_text, _ = replace_flat_field(new_text, field_name, master_val)
                        # Value updated in-place; fix position if it was misplaced
                        fields_to_reorder.append(field_name)

            if not dry_run:
                # Fix position of any updated field that was already in the file
                # but sitting at the wrong line (e.g. from a previous bad run)
                for field_name in fields_to_reorder:
                    new_text = reorder_field(new_text, field_name, master_order)

            # --- Apply log_label_settings block ---
            block_action = None
            if master_log_label_block:
                if dry_run:
                    target_block = extract_raw_block(proj.raw_text, "log_label_settings")
                    if target_block.rstrip('\n') != master_log_label_block.rstrip('\n'):
                        block_action = 'added' if not target_block else 'replaced'
                else:
                    new_text, block_action = replace_block_in_text(
                        new_text, "log_label_settings", master_log_label_block
                    )
                    if block_action == 'unchanged':
                        block_action = None

            # --- Apply l2m_settings block (metric_project_name rewritten to this target) ---
            l2m_action = None
            if master_l2m_settings_block and proj.project_name:
                rendered_l2m_block = render_l2m_settings_block(master_l2m_settings_block, proj.project_name)
                if dry_run:
                    target_block = extract_raw_block(proj.raw_text, "l2m_settings")
                    if target_block.rstrip('\n') != rendered_l2m_block.rstrip('\n'):
                        l2m_action = 'added' if not target_block else 'replaced'
                else:
                    new_text, l2m_action = replace_block_in_text(
                        new_text, "l2m_settings", rendered_l2m_block
                    )
                    if l2m_action == 'unchanged':
                        l2m_action = None

            # --- Apply json_key_settings: replace-if-exists-else-add from master ---
            json_key_action = None
            json_keys_added = json_keys_updated = 0
            if master_json_keys:
                current_entries = parse_json_key_settings(new_text) if not dry_run else proj.json_key_entries
                current_by_key = {e["json_key"]: e for e in current_entries}
                for e in master_json_keys:
                    if e["json_key"] not in current_by_key:
                        json_keys_added += 1
                    elif current_by_key[e["json_key"]] != e:
                        json_keys_updated += 1
                if json_keys_added or json_keys_updated:
                    merged = merge_json_key_entries(current_entries, master_json_keys)
                    json_key_action = f"{json_keys_added} added, {json_keys_updated} updated"
                    if not dry_run:
                        new_text = replace_json_key_settings_in_text(new_text, merged)

            block_summary = ", ".join(
                filter(None, [
                    f"log_label_settings {block_action}" if block_action else None,
                    f"l2m_settings {l2m_action}" if l2m_action else None,
                    f"json_key_settings ({json_key_action})" if json_key_action else None,
                ])
            )

            if changes or block_summary:
                print(f"  {name} [{env}] — {len(changes)} field change(s)"
                      + (f" + {block_summary}" if block_summary else "") + ":")
                for op, fname, old, new in changes:
                    if op == "ADD":
                        print(f"    + ADD    {fname} = {new}")
                    else:
                        print(f"    ~ UPDATE {fname}")
                        print(f"             was : {old}")
                        print(f"             now : {new}")
                if block_action:
                    print(f"    ~ {block_action.upper()} log_label_settings")
                if l2m_action:
                    print(f"    ~ {l2m_action.upper()} l2m_settings")
                if json_key_action:
                    print(f"    ~ json_key_settings: {json_key_action}")

                if not dry_run:
                    proj.path.write_text(new_text, encoding="utf-8")
                    print(f"    => written: {proj.path}")
            else:
                print(f"  {name} [{env}] — no changes.")

    print()


# ---------------------------------------------------------------------------
# Command: generate-l2m-projects
# ---------------------------------------------------------------------------

def generate_l2m_content(master_text: str, log_project_name: str, resource_label: str) -> str:
    """
    Produce a new L2M metric project .tf by substituting into the master template:
      - resource label       → resource_label  (e.g. "adobe_uat_l2m")
      - project_name         → "{log_project_name}-L2M"
      - project_display_name → "{log_project_name}-L2M"
    Everything else is copied verbatim from master_text.
    """
    l2m_name = f"{log_project_name}-L2M"

    # Replace the resource block label
    new_text = re.sub(
        r'(resource\s+"insightfinder_metric_project"\s+")[^"]+(")',
        rf'\g<1>{resource_label}\2',
        master_text,
        count=1,
    )

    # Replace project_name (first match, top-level field)
    new_text = re.sub(
        r'^([ \t]*project_name[ \t]*=[ \t]*")[^"]+(")',
        rf'\g<1>{l2m_name}\2',
        new_text,
        flags=re.MULTILINE,
        count=1,
    )

    # Replace project_display_name
    new_text = re.sub(
        r'^([ \t]*project_display_name[ \t]*=[ \t]*")[^"]+(")',
        rf'\g<1>{l2m_name}\2',
        new_text,
        flags=re.MULTILINE,
        count=1,
    )

    return new_text


def cmd_generate_l2m_projects(
    nbc_root: Path,
    master_path: Path,
    dry_run: bool,
) -> None:
    print(f"\n{'='*72}")
    print(f"  Command : generate-l2m-projects{' [DRY-RUN]' if dry_run else ''}")
    print(f"  Master  : {master_path}")
    print(f"{'='*72}")

    try:
        master_text = master_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"ERROR: cannot read master settings file: {e}", file=sys.stderr)
        return

    total_written = 0

    for env in ENV_ORDER:
        cfg = ENVS[env]
        env_dir = nbc_root / cfg["dir"]
        log_dir = env_dir / "log-projects"
        l2m_dir = env_dir / "l2m-projects"

        if not log_dir.exists():
            print(f"\n  [{env}] log-projects not found at {log_dir} — skipping.")
            continue

        tf_files = sorted(f for f in log_dir.glob("*.tf") if f.name not in SKIP_FILES)
        if not tf_files:
            print(f"\n  [{env}] No .tf files in {log_dir} — skipping.")
            continue

        print(f"\n  [{env}] {log_dir}")
        print(f"         → {l2m_dir}")
        print(f"         {len(tf_files)} log project(s) to process\n")

        for tf_path in tf_files:
            try:
                log_text = tf_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"    WARNING: cannot read {tf_path.name}: {e}", file=sys.stderr)
                continue

            m = re.search(r'project_name\s*=\s*"([^"]+)"', log_text)
            if not m:
                print(f"    WARNING: no project_name in {tf_path.name} — skipping.")
                continue

            log_project_name = m.group(1)          # e.g. "adobe-uat"
            stem = tf_path.stem                     # e.g. "adobe_uat"
            resource_label = f"{stem}_l2m"          # e.g. "adobe_uat_l2m"
            out_filename = f"{stem}_l2m.tf"         # e.g. "adobe_uat_l2m.tf"
            out_path = l2m_dir / out_filename

            action = "OVERWRITE" if out_path.exists() else "CREATE "
            l2m_project_name = f"{log_project_name}-L2M"
            print(f"    {action}  {out_filename}  (project_name: \"{l2m_project_name}\")")

            if not dry_run:
                new_content = generate_l2m_content(master_text, log_project_name, resource_label)
                l2m_dir.mkdir(exist_ok=True)
                out_path.write_text(new_content, encoding="utf-8")
                total_written += 1

    if dry_run:
        print(f"\n  [DRY-RUN] No files written.")
    else:
        print(f"\n  Done — {total_written} file(s) written.")


# ---------------------------------------------------------------------------
# Command: create-missing
# ---------------------------------------------------------------------------

def render_log_project_from_master(master_text: str, resource_label: str, project_name: str) -> str:
    """Render a new log-project .tf from a master template: substitute the
    resource label, project_name, project_display_name, and (if present) the
    l2m_settings metric_project_name. Everything else — including the full
    json_key_settings list — is copied verbatim from the master."""
    new_text = re.sub(
        r'(resource\s+"insightfinder_project"\s+")[^"]+(")',
        rf'\g<1>{resource_label}\2', master_text, count=1,
    )
    new_text = re.sub(
        r'^([ \t]*project_name[ \t]*=[ \t]*")[^"]+(")',
        rf'\g<1>{project_name}\2', new_text, flags=re.MULTILINE, count=1,
    )
    new_text = re.sub(
        r'^([ \t]*project_display_name[ \t]*=[ \t]*")[^"]+(")',
        rf'\g<1>{project_name}\2', new_text, flags=re.MULTILINE, count=1,
    )

    l2m_block = extract_raw_block(new_text, "l2m_settings")
    if l2m_block:
        rendered = render_l2m_settings_block(l2m_block, project_name)
        if rendered != l2m_block:
            new_text, _ = replace_block_in_text(new_text, "l2m_settings", rendered)

    return new_text


def strip_metric_configurations(text: str) -> str:
    """Remove the metric_configurations block. A brand-new L2M project has no
    real backend component id yet (that only exists once the platform has
    ingested data through it), so metric_configurations — which references
    var.<label>_id — can't be populated at scaffold time. The existing
    sync_environments.py / poll_new_l2m_projects.py pipeline fills this in
    later once a real Global_ id is known."""
    m = re.search(r'\n(\s*)metric_configurations\s*=\s*\{', text)
    if not m:
        return text
    open_pos = text.index('{', m.start())
    end_pos = find_block_end(text, open_pos)
    start = m.start() + 1
    if end_pos < len(text) and text[end_pos] == '\n':
        end_pos += 1
    return text[:start] + text[end_pos:]


def render_l2m_project_from_master(master_text: str, resource_label: str, project_name: str) -> str:
    """Render a new l2m-project .tf from a master template: substitute the
    resource label, project_name, project_display_name, then strip
    metric_configurations (see strip_metric_configurations)."""
    new_text = re.sub(
        r'(resource\s+"insightfinder_metric_project"\s+")[^"]+(")',
        rf'\g<1>{resource_label}\2', master_text, count=1,
    )
    new_text = re.sub(
        r'^([ \t]*project_name[ \t]*=[ \t]*")[^"]+(")',
        rf'\g<1>{project_name}\2', new_text, flags=re.MULTILINE, count=1,
    )
    new_text = re.sub(
        r'^([ \t]*project_display_name[ \t]*=[ \t]*")[^"]+(")',
        rf'\g<1>{project_name}\2', new_text, flags=re.MULTILINE, count=1,
    )
    return strip_metric_configurations(new_text)


def cmd_create_missing(
    nbc_root: Path,
    project_names: list,
    log_master_path: Path,
    l2m_master_path: Path,
    dry_run: bool,
    env_filter: Optional[str] = None,
    dir_override: Optional[Path] = None,
) -> None:
    envs_to_process = [env_filter] if env_filter else ENV_ORDER
    print(f"\n{'='*72}")
    print(f"  Command      : create-missing{' [DRY-RUN]' if dry_run else ''}{f' [env={env_filter}]' if env_filter else ''}")
    print(f"  Project list : {len(project_names)} name(s)")
    print(f"  Log master   : {log_master_path}")
    print(f"  L2M master   : {l2m_master_path}")
    if dir_override:
        print(f"  Target dir   : {dir_override} (overrides the default {env_filter!r} dir)")
    print(f"{'='*72}")

    log_master_text = log_master_path.read_text(encoding="utf-8")
    l2m_master_text = l2m_master_path.read_text(encoding="utf-8")

    created_log = created_l2m = 0

    for env in envs_to_process:
        cfg = ENVS[env]
        suf = ENV_SUFFIX[env]
        env_dir = dir_override if dir_override else nbc_root / cfg["dir"]
        log_dir = env_dir / "log-projects"
        l2m_dir = env_dir / "l2m-projects"

        if not log_dir.exists():
            print(f"\n  [{env}] {log_dir} not found — skipping.")
            continue

        print(f"\n  [{env}]")

        for base in sorted(project_names):
            stem = f"{base}{suf['file']}"
            project_name = f"{base}{suf['name']}"

            log_path = log_dir / f"{stem}.tf"
            if not log_path.exists():
                print(f"    CREATE log-projects/{stem}.tf  (project_name: \"{project_name}\")")
                if not dry_run:
                    content = render_log_project_from_master(log_master_text, stem, project_name)
                    log_path.write_text(content, encoding="utf-8")
                created_log += 1

            l2m_path = l2m_dir / f"{stem}_l2m.tf"
            if not l2m_path.exists():
                l2m_project_name = f"{project_name}-L2M"
                l2m_label = f"{stem}_l2m"
                print(f"    CREATE l2m-projects/{stem}_l2m.tf  (project_name: \"{l2m_project_name}\", "
                      f"no metric_configurations yet)")
                if not dry_run:
                    content = render_l2m_project_from_master(l2m_master_text, l2m_label, l2m_project_name)
                    l2m_dir.mkdir(exist_ok=True)
                    l2m_path.write_text(content, encoding="utf-8")
                created_l2m += 1

    print()
    if dry_run:
        print(f"  [DRY-RUN] Would create {created_log} log project file(s), {created_l2m} l2m project file(s).")
    else:
        print(f"  Done — created {created_log} log project file(s), {created_l2m} l2m project file(s).")
        print(f"  Run `terraform fmt -recursive` over the affected directories next.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NBC project sync checker and fixer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "command",
        choices=["check", "sync-json-keys", "apply-master", "apply-l2m-master", "generate-l2m-projects", "create-missing"],
        help="Action to perform.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repo root path (default: directory of this script).",
    )
    parser.add_argument(
        "--folder",
        default=None,
        help="Project-type folder to process (e.g. log-projects). Default: all.",
    )
    parser.add_argument(
        "--master",
        default=None,
        help="[apply-master / apply-l2m-master / create-missing] Path to the master log-project (or, for apply-l2m-master, l2m-project) .tf file.",
    )
    parser.add_argument(
        "--master-settings",
        default=None,
        metavar="PATH",
        help="[generate-l2m-projects / create-missing] Path to the master L2M metric project .tf file used as template.",
    )
    parser.add_argument(
        "--project-list",
        default=None,
        metavar="PATH",
        help=(
            "[check / sync-json-keys / apply-master / apply-l2m-master / create-missing] Path to a "
            '{"log_projects": [...]} file (e.g. NBC/BIC-Templates/project_name.json). '
            "For check/sync-json-keys/apply-master/apply-l2m-master this scopes processing to only "
            "those base names instead of every project group in the folder. "
            "Required for create-missing and apply-l2m-master."
        ),
    )
    parser.add_argument(
        "--metric-overrides",
        default=None,
        metavar="PATH",
        help=(
            "[apply-l2m-master] Path to a metric_config_l2m.json file with "
            '{"exclude_metric_configurations": [names...], '
            '"metric_alert_setting_overrides": {name: {field: raw_hcl_value}}}. '
            "Projects in the exclude list never get metric_configurations touched "
            "(e.g. e2e, which has none by design). Named overrides win over the "
            "master's value for that field only (e.g. a project with a different "
            "alert threshold). Optional — omit for no exclusions/overrides."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="[sync-json-keys / apply-master / apply-l2m-master / generate-l2m-projects / create-missing] Show changes without writing files.",
    )
    parser.add_argument(
        "--frequency",
        action="store_true",
        help=(
            "Process only LogFrequency (frequency detection) projects. "
            "Without this flag the default behaviour is to process regular "
            "projects and skip frequency detection ones."
        ),
    )
    parser.add_argument(
        "--env",
        choices=ENV_ORDER,
        default=None,
        help=(
            "[apply-master / apply-l2m-master / create-missing] Restrict writes to a single "
            "environment (stage / uat / prod) instead of all three. Ignored by check / "
            "sync-json-keys, which are inherently cross-environment comparisons. Required "
            "when --target-dir is given."
        ),
    )
    parser.add_argument(
        "--target-dir",
        default=None,
        metavar="PATH",
        help=(
            "[apply-master / apply-l2m-master / create-missing] Override the directory used "
            "for --env's environment, for an 'infra-duplicate' folder that shares that env's "
            "naming convention but isn't one of the three built-in ENVS dirs — e.g. "
            "'NBC/NBC UAT/Prod Infra', a second UAT deployment on a different host that still "
            "uses the '-uat' suffix. Path is relative to --repo-root. Requires --env."
        ),
    )
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).parent
    nbc_root = repo_root / "NBC"

    if not nbc_root.exists():
        print(f"ERROR: NBC directory not found at {nbc_root}", file=sys.stderr)
        sys.exit(1)

    if args.folder:
        folders = [args.folder]
    else:
        folders = discover_folders(nbc_root)

    project_names = None
    if args.project_list:
        project_list_path = Path(args.project_list)
        if not project_list_path.exists():
            print(f"ERROR: project-list file not found: {project_list_path}", file=sys.stderr)
            sys.exit(1)
        project_names = load_project_list(project_list_path)

    dir_overrides = None
    if args.target_dir:
        if not args.env:
            print("ERROR: --target-dir requires --env (it overrides that one environment's directory).",
                  file=sys.stderr)
            sys.exit(1)
        target_dir = repo_root / args.target_dir
        if not target_dir.is_dir():
            print(f"ERROR: --target-dir not found: {target_dir}", file=sys.stderr)
            sys.exit(1)
        dir_overrides = {args.env: target_dir}

    if args.command == "apply-master":
        if not args.master:
            print("ERROR: --master is required for apply-master.", file=sys.stderr)
            sys.exit(1)
        master_path = Path(args.master)
        if not master_path.exists():
            print(f"ERROR: master file not found: {master_path}", file=sys.stderr)
            sys.exit(1)

    if args.command == "generate-l2m-projects":
        if not args.master_settings:
            print("ERROR: --master-settings is required for generate-l2m-projects.", file=sys.stderr)
            sys.exit(1)
        master_settings_path = Path(args.master_settings)
        if not master_settings_path.exists():
            print(f"ERROR: master-settings file not found: {master_settings_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Repo root : {repo_root}")
        print(f"Command   : {args.command}")
        cmd_generate_l2m_projects(
            nbc_root=nbc_root,
            master_path=master_settings_path,
            dry_run=args.dry_run,
        )
        print()
        return

    if args.command == "create-missing":
        if not project_names:
            print("ERROR: --project-list is required for create-missing.", file=sys.stderr)
            sys.exit(1)
        if not args.master:
            print("ERROR: --master (log project template) is required for create-missing.", file=sys.stderr)
            sys.exit(1)
        if not args.master_settings:
            print("ERROR: --master-settings (l2m project template) is required for create-missing.", file=sys.stderr)
            sys.exit(1)
        log_master_path = Path(args.master)
        l2m_master_path = Path(args.master_settings)
        if not log_master_path.exists():
            print(f"ERROR: master file not found: {log_master_path}", file=sys.stderr)
            sys.exit(1)
        if not l2m_master_path.exists():
            print(f"ERROR: master-settings file not found: {l2m_master_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Repo root : {repo_root}")
        print(f"Command   : {args.command}")
        cmd_create_missing(
            nbc_root=nbc_root,
            project_names=project_names,
            log_master_path=log_master_path,
            l2m_master_path=l2m_master_path,
            dry_run=args.dry_run,
            env_filter=args.env,
            dir_override=dir_overrides[args.env] if dir_overrides else None,
        )
        print()
        return

    if args.command == "apply-l2m-master":
        if not project_names:
            print("ERROR: --project-list is required for apply-l2m-master.", file=sys.stderr)
            sys.exit(1)
        if not args.master:
            print("ERROR: --master (l2m project template) is required for apply-l2m-master.", file=sys.stderr)
            sys.exit(1)
        master_path = Path(args.master)
        if not master_path.exists():
            print(f"ERROR: master file not found: {master_path}", file=sys.stderr)
            sys.exit(1)
        overrides_path = Path(args.metric_overrides) if args.metric_overrides else None
        if overrides_path is not None and not overrides_path.exists():
            print(f"ERROR: metric-overrides file not found: {overrides_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Repo root : {repo_root}")
        print(f"Command   : {args.command}")
        groups = collect_l2m_projects_for_names(nbc_root, project_names, dir_overrides=dir_overrides)
        cmd_apply_l2m_master(
            groups,
            master_path=master_path,
            overrides_path=overrides_path,
            dry_run=args.dry_run,
            env_filter=args.env,
        )
        print()
        return

    print(f"Repo root : {repo_root}")
    print(f"Command   : {args.command}")
    print(f"Folders   : {', '.join(folders)}")
    print(f"Mode      : {'frequency' if args.frequency else 'regular'}")
    if project_names:
        print(f"Scoped to : {len(project_names)} project name(s) from --project-list")
    if args.env:
        print(f"Env       : {args.env} only")

    for folder_name in folders:
        groups = collect_projects(nbc_root, folder_name, dir_overrides=dir_overrides)
        groups = filter_groups_by_names(groups, project_names)

        if args.command == "check":
            cmd_check(groups, folder_name, frequency=args.frequency)
        elif args.command == "sync-json-keys":
            cmd_sync_json_keys(groups, folder_name, dry_run=args.dry_run, frequency=args.frequency)
        elif args.command == "apply-master":
            cmd_apply_master(
                groups,
                folder_name,
                master_path=Path(args.master),
                dry_run=args.dry_run,
                frequency=args.frequency,
                env_filter=args.env,
            )

    print()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
NBC project sync checker and fixer.

Commands:
  check                  - Check missing projects and show field-level diffs
  sync-json-keys         - Propagate missing json_key entries across matched projects
  apply-master           - Apply master plan settings to all non-ServiceNow projects
  generate-l2m-projects  - Generate L2M metric project .tf files from log-projects

Flags:
  --frequency    Process only LogFrequency projects (default: skip them, process regular projects)

Usage:
  python3 check_project_sync.py check [--folder FOLDER] [--repo-root PATH] [--frequency]
  python3 check_project_sync.py sync-json-keys [--folder FOLDER] [--repo-root PATH] [--dry-run] [--frequency]
  python3 check_project_sync.py apply-master --master PATH [--folder FOLDER] [--repo-root PATH] [--dry-run] [--frequency]
  python3 check_project_sync.py generate-l2m-projects --master-settings PATH [--repo-root PATH] [--dry-run]

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
  all other settings are copied verbatim from the master file.
  Example:
    log-projects/adobe_uat.tf  (project_name = "adobe-uat")
    → l2m-projects/adobe_uat_l2m.tf  (project_name = "adobe-uat-L2M")
"""

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
        "dir": "NBC Stage",
        "strip_suffixes": ["_stage"],
        "strip_prefixes": ["nbc_stage_"],
        "env_tag": "_stage",
    },
    "uat": {
        "dir": "NBC UAT",
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

# Suffix shared by all LogFrequency project filenames
FREQUENCY_SUFFIX = "_frequency_detection"
ENV_ORDER = ["stage", "uat", "prod"]

SKIP_FILES = {"variables.tf", "versions.tf"}

# Fields never propagated (env-specific by design)
SKIP_FIELDS = {"project_name", "project_display_name", "system_name"}

# Multi-line block field names
BLOCK_FIELDS = {"project_creation_config", "json_key_settings", "log_label_settings"}

# Column at which '=' is aligned in TF files (0-indexed from line start)
EQ_COLUMN = 43

# Order of fields within a json_key_settings entry
JSON_KEY_ENTRY_FIELDS = [
    "json_key",
    "type",
    "summary_setting",
    "metafield_setting",
    "dampening_field_setting",
]
JSON_KEY_STRING_FIELDS = {"json_key", "type"}


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
    Files that already lack the env tag (common in stage) are returned as-is.
    The nbc_{env}_ prefix variant (e.g. nbc_prod_servicenow_...) is handled by
    the regular prefix rule below.
    """
    cfg = ENVS[env]

    # Frequency detection: strip _{env} embedded before _frequency_detection
    freq_env_suffix = cfg["env_tag"] + FREQUENCY_SUFFIX
    if stem.endswith(freq_env_suffix):
        return stem[: -len(freq_env_suffix)] + FREQUENCY_SUFFIX

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


def collect_projects(nbc_root: Path, folder_name: str) -> dict:
    """
    Returns dict: normalized_name -> { env: TFProject }
    Only includes groups that have at least one env present.
    """
    groups: dict = defaultdict(dict)
    for env, cfg in ENVS.items():
        folder = nbc_root / cfg["dir"] / folder_name
        if not folder.exists():
            continue
        for tf_path in sorted(folder.glob("*.tf")):
            if tf_path.name in SKIP_FILES:
                continue
            proj = load_tf_project(tf_path, env)
            if proj:
                groups[proj.normalized_name][env] = proj

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
    """Format a single json_key_settings entry block."""
    pad = 24
    lines = ["    {"]
    for key in JSON_KEY_ENTRY_FIELDS:
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
    else:
        idx = text.rfind("\n}")
        ins = idx + 1 if idx >= 0 else len(text)

    block_text = new_block if new_block.endswith('\n') else new_block + '\n'
    return text[:ins] + block_text + '\n' + text[ins:], 'added'


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
                return _line_end(m.start())

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


def cmd_apply_master(
    groups: dict,
    folder_name: str,
    master_path: Path,
    dry_run: bool,
    frequency: bool = False,
) -> None:
    mode_label = " [frequency]" if frequency else ""
    groups = _filter_groups(groups, frequency)
    print(f"\n{'='*72}")
    print(f"  Folder: {folder_name}  [apply-master{' DRY-RUN' if dry_run else ''}{mode_label}]")
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
    print(f"\n  Master has {len(master_fields)} flat field(s) to propagate.")
    if master_log_label_block:
        print(f"  Master has log_label_settings block — will propagate.")
    print()

    for name in sorted(groups.keys()):
        for env in ENV_ORDER:
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

            if changes or block_action:
                print(f"  {name} [{env}] — {len(changes)} field change(s)"
                      + (f" + log_label_settings {block_action}" if block_action else "") + ":")
                for op, fname, old, new in changes:
                    if op == "ADD":
                        print(f"    + ADD    {fname} = {new}")
                    else:
                        print(f"    ~ UPDATE {fname}")
                        print(f"             was : {old}")
                        print(f"             now : {new}")
                if block_action:
                    print(f"    ~ {block_action.upper()} log_label_settings")

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
        choices=["check", "sync-json-keys", "apply-master", "generate-l2m-projects"],
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
        help="[apply-master] Path to the master .tf file.",
    )
    parser.add_argument(
        "--master-settings",
        default=None,
        metavar="PATH",
        help="[generate-l2m-projects] Path to the master L2M metric project .tf file used as template.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="[sync-json-keys / apply-master] Show changes without writing files.",
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

    print(f"Repo root : {repo_root}")
    print(f"Command   : {args.command}")
    print(f"Folders   : {', '.join(folders)}")
    print(f"Mode      : {'frequency' if args.frequency else 'regular'}")

    for folder_name in folders:
        groups = collect_projects(nbc_root, folder_name)

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
            )

    print()


if __name__ == "__main__":
    main()

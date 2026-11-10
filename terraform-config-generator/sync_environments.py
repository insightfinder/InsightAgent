#!/usr/bin/env python3
"""
In-place sync for NBC Terraform folders and their ServiceNow/Slack integrations.

Re-pulls live settings from the InsightFinder API for one already-existing folder
registered in sync_targets.yaml and overwrites ONLY its generated content — project
files, system_settings.tf, or (for servicenow/slack) the specific API-driven fields
inside one resource/locals block. Root files that hold hand-tuned backend state keys
and credentials (versions.tf, provider.tf, variables.tf, terraform.tfvars,
secret_mapping.json, CHANGELOG.md) are never touched.

See sync_targets.yaml for the registry format and generator-scripts/README.md for
background on why folders that look like duplicates are often different live hosts.

Usage:
  python3 sync_environments.py list
  python3 sync_environments.py sync-<alias> [--host <name>] [--dry-run] [--prune]
  python3 sync_environments.py sync-all [--dry-run] [--prune]
  python3 sync_environments.py copy <pair-name> [--dry-run] [--prune]
  python3 sync_environments.py fetch-l2m-ids-<alias> [--dry-run]

Examples:
  python3 sync_environments.py sync-nbcprod
  python3 sync_environments.py sync-servicenow-nbcuat-system --host stg
  python3 sync_environments.py copy nbcuat-prod-to-stage --dry-run
  python3 sync_environments.py sync-all
  python3 sync_environments.py fetch-l2m-ids-nbcuat-stageinfra
    Refreshes <output_dir>/l2m-component-ids.auto.tfvars for a `systems` alias —
    the per-project Global_ component ids used by l2m-projects/*.tf's
    metric_configurations — and, when NBC/BIC-Templates/l2m_project_template.tf
    exists, ALSO discovers any l2m-projects file with no metric_configurations at
    all yet (e.g. a project just scaffolded via check_project_sync.py
    create-missing), checks whether it's live now, and if so adds
    metric_configurations + the variable/module-passthrough wiring for it —
    the same thing "atom" and "gst_apps_sre" previously needed by hand.
    Projects listed in NBC/BIC-Templates/metric_config_l2m.json's
    exclude_metric_configurations (e.g. e2e) are always skipped, and its
    metric_alert_setting_overrides are applied per project.
    Always pulls live from that alias's own host (ids are not portable between
    environments). Touches only l2m-projects/*.tf, l2m-projects/variables.tf,
    l2m_component_id_variables.tf, l2m_projects.tf, and l2m-component-ids.auto.tfvars.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    print("Missing dependency: pyyaml. Install with: pip install pyyaml", file=sys.stderr)
    raise

sys.path.insert(0, str(Path(__file__).parent))

from auto_generate_terraform import (
    make_session,
    get_own_systems,
    get_system_display_name,
    process_system,
    fetch_servicenow_env_configs,
    fetch_slack_env_configs,
    _build_system_id_to_name,
)
from check_project_sync import (
    find_block_end,
    replace_flat_field,
    replace_block_in_text,
    extract_raw_block,
    load_metric_overrides,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files/dirs considered fully generated — safe to overwrite in place.
# Never touched: versions.tf, provider.tf, variables.tf, terraform.tfvars,
# secret_mapping.json, CHANGELOG.md, .terraform*
PROJECT_SUBDIRS = [
    "log-projects", "metric-projects", "l2m-projects",
    "trace-projects", "change-events-projects", "incident-projects",
]
WRAPPER_FILES = [
    "log_projects.tf", "metric_projects.tf", "l2m_projects.tf",
    "trace_projects.tf", "change_events_projects.tf", "incident_projects.tf",
]
EXTRA_SAFE_FILES = ["system_settings.tf"]


class SyncError(Exception):
    pass


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def load_registry(targets_path: Path) -> Dict[str, Any]:
    if not targets_path.exists():
        raise SyncError(
            f"targets file not found: {targets_path}\n"
            f"Copy generator-scripts/sync_targets.yaml (see README) and fill in credentials."
        )
    return yaml.safe_load(targets_path.read_text(encoding="utf-8")) or {}


def find_alias(registry: Dict[str, Any], alias: str) -> Tuple[Optional[str], Optional[Dict]]:
    for kind in ("systems", "servicenow", "slack"):
        entries = registry.get(kind) or {}
        if alias in entries:
            return kind, entries[alias]
    return None, None


def output_path(entry: Dict[str, Any]) -> Path:
    return REPO_ROOT / entry["output_dir"]


# ---------------------------------------------------------------------------
# `systems` sync — full project + system-settings regen via process_system()
# ---------------------------------------------------------------------------

def sync_system_target(alias: str, entry: Dict[str, Any], dry_run: bool,
                        prune: bool, no_ssl_verify: bool) -> Dict[str, int]:
    for field in ("base_url", "username", "licensekey", "system_name", "output_dir"):
        if not entry.get(field):
            raise SyncError(f"{alias}: missing/blank {field!r} in sync_targets.yaml")

    session = make_session(no_ssl_verify)
    env_cfg = {
        "base_url": entry["base_url"],
        "username": entry["username"],
        "licensekey": entry["licensekey"],
        "project_types": entry.get("project_types", []),
        "only_include_escalated_ignored": entry.get("only_include_escalated_ignored", True),
        "disable_metric_collection": entry.get("disable_metric_collection", False),
        "only_include_metrics": entry.get("only_include_metrics") or None,
        "terraform_version": entry.get("terraform_version", ">= 1.6.1"),
    }

    print(f"  Fetching owned systems from {env_cfg['base_url']}...")
    systems = get_own_systems(session, env_cfg["base_url"], env_cfg["username"],
                               env_cfg["licensekey"], env_cfg["username"])
    target_system = next(
        (s for s in systems if get_system_display_name(s) == entry["system_name"]), None
    )
    if target_system is None:
        raise SyncError(
            f"{alias}: system {entry['system_name']!r} not found among "
            f"{len(systems)} owned system(s) on {env_cfg['base_url']}"
        )

    tmp_root = tempfile.mkdtemp(prefix="sync_env_")
    try:
        tmp_env_name = "_sync"
        stats = process_system(
            session, tmp_env_name, env_cfg, target_system, tmp_root,
            delay=entry.get("delay", 0), dry_run=False,
        )
        tmp_system_dir = os.path.join(tmp_root, tmp_env_name, entry["system_name"])
        written, stale = copy_generated_subset(
            Path(tmp_system_dir), output_path(entry), dry_run=dry_run, prune=prune,
        )
        print(f"    {'Would write' if dry_run else 'Wrote'} {len(written)} file(s).")
        for path in stale:
            print(f"    [STALE] {path}" + ("" if prune else " (use --prune to remove)"))
        if not dry_run:
            apply_l2m_component_id_vars(output_path(entry))
        return stats
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


# ---------------------------------------------------------------------------
# `fetch-l2m-ids` — refresh just the per-project Global_ component id map
# ---------------------------------------------------------------------------

_L2M_LABEL_RE = re.compile(r'resource\s+"insightfinder_metric_project"\s+"([a-zA-Z0-9_]+)"')
_L2M_PROJECT_NAME_RE = re.compile(r'\bproject_name\s*=\s*"([^"]+)"')
_L2M_VARFILE_LINE_RE = re.compile(r'^([a-zA-Z0-9_]+)_id\s*=\s*"(Global_[0-9a-f]+)"\s*$')


def _get_projects_for_system(system: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Same shape as auto_generate_terraform.process_system's project list parsing:
    projectDetailsList/projectDetailList is sometimes a JSON-encoded string."""
    raw = system.get("projectDetailsList", system.get("projectDetailList", []))
    if isinstance(raw, str):
        try:
            return json.loads(raw) or []
        except (json.JSONDecodeError, ValueError):
            return []
    return raw or []


def _l2m_labels_needing_ids(l2m_projects_dir: Path) -> Dict[str, str]:
    """Scan l2m-projects/*.tf for resources that reference var.<label>_id, returning
    {label: insightfinder_project_name}. Files that don't reference such a var
    (e.g. the excluded adobe/akamai/fastly/relay/thanos/conviva/harmonic/newrelic/
    touchstream/centralized_expiry/atom/cats/gst_apps_sre/heimdall/mars/vidar projects,
    or any file with no metric_configurations at all) are skipped."""
    result: Dict[str, str] = {}
    for tf_file in sorted(l2m_projects_dir.glob("*.tf")):
        content = tf_file.read_text(encoding="utf-8")
        label_m = _L2M_LABEL_RE.search(content)
        name_m = _L2M_PROJECT_NAME_RE.search(content)
        if not label_m or not name_m:
            continue
        label = label_m.group(1)
        if f"var.{label}_id" not in content:
            continue
        result[label] = name_m.group(1)
    return result


_EXCLUDED_L2M_LABEL_SUBSTRINGS = (
    "adobe", "akamai", "fastly", "relay", "thanos",
    "conviva", "harmonic", "newrelic", "touchstream", "centralized_expiry", "cats", "heimdall", "mars", "vidar",
    "e2e",
)


def _l2m_labels_missing_wiring(l2m_projects_dir: Path) -> Dict[str, str]:
    """Scan l2m-projects/*.tf for resources that have NO metric_configurations at
    all yet (so _l2m_labels_needing_ids can't see them — there's no var.<label>_id
    reference to find). Returns {label: insightfinder_project_name}. These are
    candidates for sync_l2m_component_ids to wire up for the first time, once a
    real Global_ id is confirmed live."""
    result: Dict[str, str] = {}
    for tf_file in sorted(l2m_projects_dir.glob("*.tf")):
        if tf_file.name in ("variables.tf", "versions.tf"):
            continue
        if any(s in tf_file.stem for s in _EXCLUDED_L2M_LABEL_SUBSTRINGS):
            continue
        content = tf_file.read_text(encoding="utf-8")
        if "metric_configurations" in content:
            continue
        label_m = _L2M_LABEL_RE.search(content)
        name_m = _L2M_PROJECT_NAME_RE.search(content)
        if not label_m or not name_m:
            continue
        result[label_m.group(1)] = name_m.group(1)
    return result


def _render_new_metric_configurations(template_text: str, varname: str, overrides_for_project: Dict[str, str]) -> str:
    """Build a metric_configurations block for a project that doesn't have one
    yet, from the BIC l2m template: substitute component_name/
    escalate_incident_components to reference this project's own var.<label>_id,
    then apply any per-project field overrides from metric_config_l2m.json."""
    block = extract_raw_block(template_text, "metric_configurations")
    if not block:
        raise SyncError("BIC l2m template has no metric_configurations block")
    template_label_m = re.search(r'\[var\.(\w+)\]', block)
    if not template_label_m:
        raise SyncError("BIC l2m template's metric_configurations has no [var.<label>] reference")
    template_varname = template_label_m.group(1)
    block = block.replace(f"var.{template_varname}", f"var.{varname}")
    for field, value in overrides_for_project.items():
        block, _ = re.subn(
            r'(^\s*' + re.escape(field) + r'\s*=\s*).+$', lambda mo: mo.group(1) + value,
            block, count=1, flags=re.MULTILINE,
        )
    return block


def _l2m_project_state(l2m_projects_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Scan l2m-projects/*.tf and return, for every project whose metric_configurations
    block uses EXACTLY one distinct Global_ component id (whether that id currently
    appears as a literal string or has already been replaced with var.<label>_id):

        {label: {"project_name": str, "literal_id": Optional[str], "already_var": bool}}

    Projects with zero or multiple distinct ids (nothing to safely automate — e.g. the
    excluded catch-all alert-routing projects, or an anomalous multi-id project) are
    skipped. Detection does NOT depend on var.<label>_id already being present, since a
    fresh full regen (process_system) always writes literal ids — this must be able to
    re-detect and re-convert from that raw state every time.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for tf_file in sorted(l2m_projects_dir.glob("*.tf")):
        if any(s in tf_file.stem for s in _EXCLUDED_L2M_LABEL_SUBSTRINGS):
            continue
        content = tf_file.read_text(encoding="utf-8")
        if "metric_configurations" not in content:
            continue
        label_m = _L2M_LABEL_RE.search(content)
        name_m = _L2M_PROJECT_NAME_RE.search(content)
        if not label_m or not name_m:
            continue
        label = label_m.group(1)
        literal_ids = sorted(set(re.findall(r'"(Global_[0-9a-f]+)"', content)))
        already_var = f"var.{label}_id" in content
        if len(literal_ids) > 1:
            print(f"    WARNING: {tf_file.name} has {len(literal_ids)} distinct Global_ ids "
                  f"(expected 0 or 1) — skipping automatic id-var conversion for it.",
                  file=sys.stderr)
            continue
        if not literal_ids and not already_var:
            continue
        result[label] = {
            "project_name": name_m.group(1),
            "literal_id": literal_ids[0] if literal_ids else None,
            "already_var": already_var,
            "path": tf_file,
        }
    return result


def _ensure_variable_block(path: Path, varnames: List[str], description_fn) -> bool:
    """Idempotently append `variable "<name>" { ... }` blocks for any varnames not
    already declared in path. Returns True if the file was changed."""
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    missing = [v for v in varnames if f'variable "{v}"' not in content]
    if not missing:
        return False
    addition = []
    for v in missing:
        addition.append(f'variable "{v}" {{')
        addition.append(f'  description = "{description_fn(v)}"')
        addition.append('  type        = string')
        addition.append('}')
        addition.append('')
    new_content = content.rstrip("\n")
    new_content = (new_content + "\n\n" if new_content else "") + "\n".join(addition) + "\n"
    path.write_text(new_content, encoding="utf-8")
    return True


_PASSTHROUGH_LINE_RE = re.compile(r'^  (\w+)\s*=\s*var\.\1\s*$')


def _ensure_module_passthrough(l2m_projects_tf: Path, varnames: List[str]) -> bool:
    """Idempotently add `<var> = var.<var>` lines inside the l2m_projects module
    block for any varnames not already passed through, keeping the whole
    contiguous passthrough block alphabetically sorted with no blank lines
    between entries (matching the existing block's style; terraform fmt fixes
    column alignment afterward). Returns True if changed."""
    content = l2m_projects_tf.read_text(encoding="utf-8")
    missing = [v for v in varnames if f"{v} = var.{v}" not in content]
    if not missing:
        return False
    anchor = "  system_name = var.system_name\n"
    if anchor not in content:
        raise SyncError(f"{l2m_projects_tf}: could not find anchor line to insert component id passthroughs")

    start = content.index(anchor) + len(anchor)
    if content[start:start + 1] == "\n":
        start += 1

    # Consume the contiguous run of "  name = var.name" lines right after the
    # anchor (tolerating stray blank lines within it, so a previously
    # malformed insertion self-heals here too).
    end = start
    existing_names = []
    for line in content[start:].splitlines(keepends=True):
        if line.strip() == "":
            end += len(line)
            continue
        m = _PASSTHROUGH_LINE_RE.match(line.rstrip('\n'))
        if not m:
            break
        existing_names.append(m.group(1))
        end += len(line)

    all_names = sorted(set(existing_names) | set(missing))
    new_block = "".join(f"  {v} = var.{v}\n" for v in all_names) + "\n"
    new_content = content[:start] + new_block + content[end:]
    l2m_projects_tf.write_text(new_content, encoding="utf-8")
    return True


def apply_l2m_component_id_vars(output_dir: Path) -> None:
    """Make sure l2m-projects/*.tf reference var.<label>_id instead of a literal
    Global_ id, and that all the supporting wiring (module variable declarations,
    root variable declarations, module passthrough, and l2m-component-ids.auto.tfvars)
    exists — self-healing every time, since a fresh `sync-<alias>` regen always
    rewrites l2m-projects/*.tf with literal ids (the live API has no notion of our
    Terraform variables).
    """
    l2m_dir = output_dir / "l2m-projects"
    if not l2m_dir.is_dir():
        return
    state = _l2m_project_state(l2m_dir)
    if not state:
        return

    converted = []
    for label, info in sorted(state.items()):
        if info["literal_id"]:
            path: Path = info["path"]
            content = path.read_text(encoding="utf-8")
            new_content = content.replace(f'"{info["literal_id"]}"', f"var.{label}_id")
            if new_content != content:
                path.write_text(new_content, encoding="utf-8")
                converted.append(label)

    varnames = [f"{label}_id" for label in sorted(state)]

    def _desc(varname: str) -> str:
        label = varname[: -len("_id")]
        return f"Global_ component id for {label} (this environment only)"

    module_vars_path = l2m_dir / "variables.tf"
    changed_module_vars = _ensure_variable_block(module_vars_path, varnames, _desc)

    root_vars_path = output_dir / "l2m_component_id_variables.tf"
    changed_root_vars = _ensure_variable_block(root_vars_path, varnames, _desc)

    changed_passthrough = _ensure_module_passthrough(output_dir / "l2m_projects.tf", varnames)

    tfvars_path = output_dir / "l2m-component-ids.auto.tfvars"
    existing: Dict[str, str] = {}
    if tfvars_path.exists():
        for line in tfvars_path.read_text(encoding="utf-8").splitlines():
            m = _L2M_VARFILE_LINE_RE.match(line.strip())
            if m:
                existing[m.group(1)] = m.group(2)
    updated = dict(existing)
    tfvars_changed = []
    for label, info in state.items():
        if info["literal_id"] and existing.get(label) != info["literal_id"]:
            tfvars_changed.append((label, existing.get(label), info["literal_id"]))
            updated[label] = info["literal_id"]

    if tfvars_changed or set(updated) - set(existing):
        lines = [
            "# Global_ component ids, one per L2M project.",
            "# Regenerate per-environment via generator-scripts (never copy this file between environments).",
            "",
        ]
        for label in sorted(updated):
            lines.append(f'{label}_id = "{updated[label]}"')
        tfvars_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if converted or changed_module_vars or changed_root_vars or changed_passthrough or tfvars_changed:
        print(f"  Re-applied component-id-var wiring for {len(state)} project(s) "
              f"({len(converted)} file(s) had a literal id replaced).")
    for label, old, new in tfvars_changed:
        print(f"    {label}: {old!r} -> {new!r}")


def _l2m_base_name(label: str) -> str:
    """Strip "_l2m" and then a known env suffix ("_uat"/"_prod"/"_dev") from a label
    like "dpe_pipelining_and_tooling_uat_l2m" to get the BIC base name
    ("dpe_pipelining_and_tooling"), for metric_config_l2m.json override lookup."""
    base = label[:-len("_l2m")] if label.endswith("_l2m") else label
    for suf in ("_uat", "_prod", "_dev"):
        if base.endswith(suf):
            return base[: -len(suf)]
    return base


def sync_l2m_component_ids(alias: str, entry: Dict[str, Any], dry_run: bool,
                            no_ssl_verify: bool,
                            bic_template_path: Optional[Path] = None,
                            metric_overrides_path: Optional[Path] = None) -> None:
    """Refresh <output_dir>/l2m-component-ids.auto.tfvars for one environment, and
    (when bic_template_path is given) also discover + wire up component ids for
    l2m-projects that don't have ANY metric_configurations/id wiring yet but now
    exist live — the same thing that previously had to be done by hand for
    "atom" and "gst_apps_sre".

    Per-project Global_ component ids are NOT portable across environments/hosts
    (confirmed: same logical component gets a different hash on a different host,
    and can even change over time on the same host) — so this always re-derives
    ids from THIS target's own live systemframework API, never by copying another
    environment's tfvars file.

    id = "Global_" + projectKey, where projectKey comes from the system's
    projectDetailsList/projectDetailList entry whose projectName matches the
    L2M project (per user: "project is the id with prefix Global_").
    """
    for field in ("base_url", "username", "licensekey", "system_name", "output_dir"):
        if not entry.get(field):
            raise SyncError(f"{alias}: missing/blank {field!r} in sync_targets.yaml")

    out_dir = output_path(entry)
    l2m_dir = out_dir / "l2m-projects"
    if not l2m_dir.is_dir():
        raise SyncError(f"{alias}: no l2m-projects/ directory under {out_dir}")

    labels = _l2m_labels_needing_ids(l2m_dir)
    unwired = _l2m_labels_missing_wiring(l2m_dir) if bic_template_path else {}
    if not labels and not unwired:
        print("  No l2m-projects files reference a var.<label>_id, and none are "
              "missing wiring — nothing to do.")
        return
    if labels:
        print(f"  Found {len(labels)} project(s) expecting a component id: "
              f"{', '.join(sorted(labels))}")
    if unwired:
        print(f"  Found {len(unwired)} project(s) with no metric_configurations yet: "
              f"{', '.join(sorted(unwired))}")

    session = make_session(no_ssl_verify)
    print(f"  Fetching owned systems from {entry['base_url']}...")
    systems = get_own_systems(session, entry["base_url"], entry["username"],
                               entry["licensekey"], entry["username"])
    target_system = next(
        (s for s in systems if get_system_display_name(s) == entry["system_name"]), None
    )
    if target_system is None:
        raise SyncError(
            f"{alias}: system {entry['system_name']!r} not found among "
            f"{len(systems)} owned system(s) on {entry['base_url']}"
        )

    projects = _get_projects_for_system(target_system)
    project_key_by_name = {
        p.get("projectName"): p.get("projectKey")
        for p in projects if p.get("projectName") and p.get("projectKey")
    }
    print(f"  System {entry['system_name']!r} has {len(project_key_by_name)} project(s) "
          f"with a projectKey.")

    tfvars_path = out_dir / "l2m-component-ids.auto.tfvars"
    existing: Dict[str, str] = {}
    if tfvars_path.exists():
        for line in tfvars_path.read_text(encoding="utf-8").splitlines():
            m = _L2M_VARFILE_LINE_RE.match(line.strip())
            if m:
                existing[m.group(1)] = m.group(2)

    updated: Dict[str, str] = dict(existing)
    changed, missing = [], []
    for label, project_name in sorted(labels.items()):
        project_key = project_key_by_name.get(project_name)
        if not project_key:
            missing.append((label, project_name))
            continue
        new_id = f"Global_{project_key}"
        if updated.get(label) != new_id:
            changed.append((label, updated.get(label), new_id))
        updated[label] = new_id

    for label, old, new in changed:
        print(f"    {label}: {old!r} -> {new!r}")
    for label, project_name in missing:
        kept = f" (keeping existing value {existing[label]!r})" if label in existing else " (NO existing value — variable will be undefined!)"
        print(f"    WARNING: no projectKey found for {label} (project_name={project_name!r}){kept}", file=sys.stderr)

    # --- Discover + wire up ids for projects with no wiring at all yet ---
    newly_wired = []      # [(label, path, block_text)]
    newly_missing = []    # [(label, project_name)] — not live yet
    if unwired:
        template_text = bic_template_path.read_text(encoding="utf-8")
        exclude_set, overrides_by_name = load_metric_overrides(metric_overrides_path)
        for label, project_name in sorted(unwired.items()):
            base_name = _l2m_base_name(label)
            if base_name in exclude_set:
                continue
            project_key = project_key_by_name.get(project_name)
            if not project_key:
                newly_missing.append((label, project_name))
                continue
            new_id = f"Global_{project_key}"
            varname = f"{label}_id"
            block = _render_new_metric_configurations(template_text, varname, overrides_by_name.get(base_name, {}))
            newly_wired.append((label, l2m_dir / f"{label}.tf", block))
            updated[label] = new_id
            changed.append((label, None, new_id))
            print(f"    {label}: (new) -> {new_id}")
        for label, project_name in newly_missing:
            print(f"    Not live yet — skipping: {label} (project_name={project_name!r})")

    if not changed:
        print("  No id changes.")
        return

    if dry_run:
        print(f"  [dry-run] Would update {len(changed)} id(s) in {tfvars_path}"
              + (f", add metric_configurations to {len(newly_wired)} file(s)" if newly_wired else ""))
        return

    lines = [
        "# Global_ component ids, one per L2M project.",
        "# Regenerate per-environment via generator-scripts (never copy this file between environments).",
        "",
    ]
    for label in sorted(updated):
        lines.append(f'{label}_id = "{updated[label]}"')
    tfvars_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  Wrote {len(updated)} id(s) to {tfvars_path}")

    for label, path, block in newly_wired:
        text = path.read_text(encoding="utf-8")
        new_text, _ = replace_block_in_text(text, "metric_configurations", block)
        path.write_text(new_text, encoding="utf-8")
        varname = f"{label}_id"

        def _desc(v: str) -> str:
            return f"Global_ component id for {v[:-len('_id')]} (this environment only)"

        _ensure_variable_block(l2m_dir / "variables.tf", [varname], _desc)
        _ensure_variable_block(out_dir / "l2m_component_id_variables.tf", [varname], _desc)
        _ensure_module_passthrough(out_dir / "l2m_projects.tf", [varname])
        print(f"    Wired metric_configurations + variable for {label}")


def _remap_customer_names(text: str, from_customer: str, to_customer: str) -> str:
    """Rewrite source_customer/target_customer/customer values in system_settings.tf's
    project_level_dampening_windows and project_level_dampening_periods entries. These
    come straight from the API's `cs`/`ct`/`c` fields for whichever host generated the
    file — copying the file verbatim across two environments that use different
    InsightFinder usernames (e.g. two infra-duplicate folders on different hosts) would
    leave the wrong customer name in the destination."""
    if not from_customer or not to_customer or from_customer == to_customer:
        return text
    pattern = re.compile(r'(source_customer|target_customer|customer)(\s*=\s*)"' + re.escape(from_customer) + r'"')
    return pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}"{to_customer}"', text)


def copy_generated_subset(src_dir: Path, dst_dir: Path, dry_run: bool, prune: bool,
                           customer_remap: Optional[Tuple[str, str]] = None) -> Tuple[List[str], List[str]]:
    """Copy the generated-file subset from src_dir into dst_dir.

    Never touches anything outside WRAPPER_FILES / EXTRA_SAFE_FILES / PROJECT_SUBDIRS.
    Files present in dst_dir but missing from src_dir are reported as stale and only
    deleted when prune=True.

    customer_remap: (from_customer, to_customer) — when set, source_customer/
    target_customer values inside system_settings.tf are rewritten from the
    source environment's username to the destination's. Only meaningful for
    copies between two different `systems` entries (the `copy` command); a
    `sync-<alias>` run never needs this since source and destination are the
    same environment.
    """
    written: List[str] = []
    stale: List[str] = []

    if not dry_run:
        dst_dir.mkdir(parents=True, exist_ok=True)

    for fname in WRAPPER_FILES + EXTRA_SAFE_FILES:
        src_path = src_dir / fname
        dst_path = dst_dir / fname
        if src_path.is_file():
            written.append(str(dst_path))
            if not dry_run:
                if customer_remap and fname == "system_settings.tf":
                    text = _remap_customer_names(src_path.read_text(encoding="utf-8"), *customer_remap)
                    dst_path.write_text(text, encoding="utf-8")
                else:
                    shutil.copyfile(src_path, dst_path)
        elif dst_path.is_file():
            if prune:
                stale.append(f"{dst_path} (removed)")
                if not dry_run:
                    dst_path.unlink()
            else:
                stale.append(str(dst_path))

    for subdir in PROJECT_SUBDIRS:
        src_sub = src_dir / subdir
        dst_sub = dst_dir / subdir
        src_files = {f.name for f in src_sub.glob("*.tf")} if src_sub.is_dir() else set()

        if src_files:
            if not dry_run:
                dst_sub.mkdir(parents=True, exist_ok=True)
            for fname in sorted(src_files):
                dst_path = dst_sub / fname
                written.append(str(dst_path))
                if not dry_run:
                    shutil.copyfile(src_sub / fname, dst_path)

        if dst_sub.is_dir():
            dst_files = {f.name for f in dst_sub.glob("*.tf")}
            for fname in sorted(dst_files - src_files):
                dst_path = dst_sub / fname
                if prune:
                    stale.append(f"{dst_path} (removed)")
                    if not dry_run:
                        dst_path.unlink()
                else:
                    stale.append(str(dst_path))

    return written, stale


# ---------------------------------------------------------------------------
# Text-surgery helpers shared by servicenow/slack sync
# ---------------------------------------------------------------------------

def get_block_span(text: str, block_kind: str) -> Tuple[int, int]:
    """Return (start, end) offsets of the body between the braces of the
    target block, scoped so module blocks that reference local.* below a
    `locals {}` block are never touched."""
    if block_kind == "resource":
        m = re.search(r'resource\s+"[^"]+"\s+"[^"]+"\s*\{', text)
    elif block_kind == "locals":
        m = re.search(r'^locals\s*\{', text, re.MULTILINE)
    else:
        raise SyncError(f"unknown block kind: {block_kind!r}")
    if not m:
        raise SyncError(f"could not locate a {block_kind!r} block in the target file")
    brace_pos = text.index('{', m.start())
    end = find_block_end(text, brace_pos)
    return brace_pos + 1, end - 1


def sync_flat_field(body: str, field_name: str, new_value: str) -> str:
    """Replace field_name's value if the field already exists in body; a no-op
    otherwise. Deliberately never inserts a field that isn't already present —
    some fields (e.g. auth_type) only apply to certain block schemas (a plain
    `resource` block vs. a `locals` block feeding a module with its own
    defaults), and blindly inserting would add a field that doesn't belong."""
    new_body, found = replace_flat_field(body, field_name, new_value)
    return new_body if found else body


def _hcl_str(s: str) -> str:
    # ${ / %{ are escaped too so regex values (e.g. resolution_notes_skip_regex)
    # aren't read as HCL template interpolation.
    escaped = (str(s).replace('\\', '\\\\').replace('"', '\\"')
               .replace('${', '$${').replace('%{', '%%{'))
    return f'"{escaped}"'


# ---------------------------------------------------------------------------
# ServiceNow sync
# ---------------------------------------------------------------------------

def _format_servicenow_project_configs_block(project_configs: Dict[str, Any],
                                              block_name: str = "project_configs") -> str:
    lines = [f"  {block_name} = {{"]
    # The API doesn't guarantee stable ordering across fetches — sort alphabetically
    # (case-insensitively) so re-running a sync doesn't reorder-churn the whole block.
    for proj_name, pc in sorted(project_configs.items(), key=lambda kv: kv[0].lower()):
        lines.append(f'    {_hcl_str(proj_name)} = {{')
        lines.append(f'      enable_ticket_creation                    = {str(pc["enable_ticket_creation"]).lower()}')
        lines.append(f'      enable_ticket_update                      = {str(pc["enable_ticket_update"]).lower()}')
        lines.append(f'      enable_incident_consolidation_info_update = {str(pc["enable_incident_consolidation_info_update"]).lower()}')
        lines.append(f'      enable_incident_resolve_update            = {str(pc["enable_incident_resolve_update"]).lower()}')
        lines.append(f'      enable_incident_field_sync                = {str(pc.get("enable_incident_field_sync", False)).lower()}')
        lines.append(f'      enable_metric_value_update                = {str(pc.get("enable_metric_value_update", False)).lower()}')
        lines.append(f'      configuration_item                        = {_hcl_str(pc.get("configuration_item", ""))}')
        lines.append('    }')
    lines.append('  }')
    return "\n".join(lines)


def _load_bic_project_names(path: Path) -> set:
    """Union of log_projects + l2m_projects from a project_name.json(.tmp) file —
    the definitive list of which project_configs keys belong in project_configs_bic
    rather than project_configs_regular. See servicenow-nbcuat-system/main.tf and
    servicenow-nbcstage-system/main.tf, which merge the two back into project_configs."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data.get("log_projects", [])) | set(data.get("l2m_projects", []))


def _format_servicenow_table_mapping_block(table_mapping: Dict[str, str]) -> str:
    lines = ["  table_mapping = {"]
    # Same random-order-from-API risk as project_configs — sort for a stable diff.
    for project, table in sorted(table_mapping.items(), key=lambda kv: kv[0].lower()):
        lines.append(f'    {_hcl_str(project)} = {_hcl_str(table)}')
    lines.append("  }")
    return "\n".join(lines)


def _format_servicenow_resolution_code_rules_block(rules: List[Dict[str, Any]]) -> str:
    lines = ["  resolution_code_rules = ["]
    for rule in rules:
        lines.append('    {')
        lines.append(f'      pattern = {_hcl_str(rule.get("pattern", ""))}')
        lines.append(f'      outcome = {_hcl_str(rule.get("outcome", ""))}')
        lines.append('    },')
    lines.append("  ]")
    return "\n".join(lines)


def sync_servicenow_block(body: str, config: Dict[str, Any],
                           bic_names: Optional[set] = None) -> str:
    body = sync_flat_field(body, "account", _hcl_str(config["account"]))
    body = sync_flat_field(body, "service_host", _hcl_str(config["service_host"]))
    body = sync_flat_field(body, "auth_type", _hcl_str(config["auth_type"]))
    body = sync_flat_field(body, "system_names", json.dumps(config.get("system_names") or []))
    if config.get("options"):
        body = sync_flat_field(body, "options", json.dumps(config["options"]))
    if config.get("content_option"):
        body = sync_flat_field(body, "content_option", json.dumps(config["content_option"]))
    if config.get("service_now_field"):
        body = sync_flat_field(body, "service_now_field", _hcl_str(config["service_now_field"]))
    if config.get("content_source"):
        body = sync_flat_field(body, "content_source", _hcl_str(config["content_source"]))
    if config.get("trigger_window_in_mills"):
        body = sync_flat_field(body, "trigger_window_in_mills", str(int(config["trigger_window_in_mills"])))
    body = sync_flat_field(body, "enable_feedback_collect",
                            str(bool(config.get("enable_feedback_collect", False))).lower())
    if config.get("ticket_created_by_source_key"):
        body = sync_flat_field(body, "ticket_created_by_source_key",
                                _hcl_str(config["ticket_created_by_source_key"]))
    if config.get("ticket_created_by_source_value"):
        body = sync_flat_field(body, "ticket_created_by_source_value",
                                _hcl_str(config["ticket_created_by_source_value"]))
    body = sync_flat_field(body, "configuration_item", _hcl_str(config.get("configuration_item", "")))
    body = sync_flat_field(body, "enable_resolution_notes_learning",
                            str(bool(config.get("enable_resolution_notes_learning", False))).lower())
    if config.get("resolution_notes_skip_regex"):
        body = sync_flat_field(body, "resolution_notes_skip_regex",
                                _hcl_str(config["resolution_notes_skip_regex"]))
    if config.get("resolution_notes_pattern_strip_regex"):
        body = sync_flat_field(body, "resolution_notes_pattern_strip_regex",
                                _hcl_str(config["resolution_notes_pattern_strip_regex"]))
    if config.get("project_configs"):
        if bic_names is not None:
            # project_configs here is split across project_configs_bic /
            # project_configs_regular locals and merged back into project_configs —
            # sync each half separately and leave the merge(...) line alone.
            bic_configs = {k: v for k, v in config["project_configs"].items() if k in bic_names}
            regular_configs = {k: v for k, v in config["project_configs"].items() if k not in bic_names}
            bic_block = _format_servicenow_project_configs_block(bic_configs, "project_configs_bic")
            regular_block = _format_servicenow_project_configs_block(regular_configs, "project_configs_regular")
            body, _ = replace_block_in_text(body, "project_configs_bic", bic_block)
            body, _ = replace_block_in_text(body, "project_configs_regular", regular_block)
        else:
            block = _format_servicenow_project_configs_block(config["project_configs"])
            body, _ = replace_block_in_text(body, "project_configs", block)
    if config.get("table_mapping"):
        block = _format_servicenow_table_mapping_block(config["table_mapping"])
        body, _ = replace_block_in_text(body, "table_mapping", block)
    if config.get("resolution_code_rules"):
        block = _format_servicenow_resolution_code_rules_block(config["resolution_code_rules"])
        body, _ = replace_block_in_text(body, "resolution_code_rules", block)
    return body


def sync_servicenow_target(alias: str, entry: Dict[str, Any], host_override: Optional[str],
                            dry_run: bool, no_ssl_verify: bool) -> bool:
    host_name = host_override or entry.get("default_host")
    host_cfg = (entry.get("hosts") or {}).get(host_name)
    if host_cfg is None:
        raise SyncError(f"{alias}: unknown host {host_name!r} (available: {list((entry.get('hosts') or {}).keys())})")
    if not host_cfg.get("username") or not host_cfg.get("licensekey"):
        raise SyncError(f"{alias}: host {host_name!r} username/licensekey not filled in in sync_targets.yaml")

    session = make_session(no_ssl_verify)
    base_url = host_cfg["base_url"].rstrip("/")
    username = host_cfg["username"]
    licensekey = host_cfg["licensekey"]

    print(f"  Fetching ServiceNow configs + owned systems from {base_url} (host={host_name})...")
    sn_configs = fetch_servicenow_env_configs(session, base_url, username, licensekey)
    systems = get_own_systems(session, base_url, username, licensekey, username)
    system_id_to_name = _build_system_id_to_name(systems)
    for config in sn_configs:
        resolved = [system_id_to_name.get(sid, sid) for sid in config.get("system_ids", [])]
        if resolved:
            config["system_names"] = resolved

    matches = [c for c in sn_configs if entry["system_name"] in (c.get("system_names") or [])]
    if not matches:
        raise SyncError(f"{alias}: no ServiceNow config on {base_url} matched system {entry['system_name']!r}")
    if len(matches) > 1:
        raise SyncError(
            f"{alias}: {len(matches)} ServiceNow configs matched system {entry['system_name']!r} "
            f"on {base_url} — ambiguous, needs manual review"
        )
    config = matches[0]

    bic_names = None
    bic_projects_file = entry.get("bic_projects_file")
    if bic_projects_file:
        bic_names = _load_bic_project_names(REPO_ROOT / bic_projects_file)

    file_path = output_path(entry) / entry["file"]
    text = file_path.read_text(encoding="utf-8")
    start, end = get_block_span(text, entry["block"])
    new_body = sync_servicenow_block(text[start:end], config, bic_names=bic_names)
    new_text = text[:start] + new_body + text[end:]

    changed = new_text != text
    if changed and not dry_run:
        file_path.write_text(new_text, encoding="utf-8")
    print(f"    {file_path}: {'would change' if (changed and dry_run) else ('changed' if changed else 'no changes')}")
    return changed


# ---------------------------------------------------------------------------
# Slack sync (webhooks are inlined literals, not secrets — see slack-prod/terraform.tfvars)
# ---------------------------------------------------------------------------

def _format_slack_project_configs_block(project_configs: List[Dict[str, Any]],
                                        block_name: str = "project_configs") -> str:
    lines = [f"  {block_name} = ["]
    for i, pc in enumerate(project_configs):
        is_last = i == len(project_configs) - 1
        lines.append("    {")
        lines.append(f'      project_name                     = {_hcl_str(pc.get("project_name", ""))}')
        lines.append(f'      channel                          = {_hcl_str(pc.get("channel", ""))}')
        lines.append(f'      webhook                          = {_hcl_str(pc.get("webhook", ""))}')
        lines.append(f'      options                          = {json.dumps(pc.get("options") or [])}')
        lines.append(f'      enable_consolidation_info_update = {str(bool(pc.get("enable_consolidation_info_update", False))).lower()}')
        if pc.get("priority_levels"):
            lines.append(f'      priority_levels                  = {json.dumps(pc["priority_levels"])}')
        rule = pc.get("rule")
        if rule:
            lines.append("      rule = {")
            lines.append(f'        type    = {_hcl_str(rule.get("type", ""))}')
            lines.append(f'        keyword = {_hcl_str(rule.get("keyword", ""))}')
            lines.append("      }")
        lines.append("    }" + ("" if is_last else ","))
    lines.append("  ]")
    return "\n".join(lines)


def sync_slack_block(body: str, config: Dict[str, Any]) -> str:
    if "webhook" in config:
        body = sync_flat_field(body, "webhook", _hcl_str(config.get("webhook", "")))
    if "channel_name" in config:
        body = sync_flat_field(body, "channel_name", _hcl_str(config.get("channel_name", "")))
    if config.get("options"):
        body = sync_flat_field(body, "options", json.dumps(config["options"]))
    if config.get("priority_upgrade_channel"):
        body = sync_flat_field(body, "priority_upgrade_channel", _hcl_str(config["priority_upgrade_channel"]))
    if config.get("priority_upgrade_webhook"):
        body = sync_flat_field(body, "priority_upgrade_webhook", _hcl_str(config["priority_upgrade_webhook"]))
    body = sync_flat_field(body, "disable_slack_for_non_insightfinder_incidents",
                            str(bool(config.get("disable_slack_for_non_insightfinder_incidents", False))).lower())
    if config.get("project_configs"):
        dup = re.search(r'^  project_configs_duplicated[ \t]*=[ \t]*\[', body, re.MULTILINE)
        if dup:
            # Entries copied to the central aiops channel live in a separate
            # project_configs_duplicated list (concatenated back into the integration's
            # project_configs). Live entries already listed there stay there; everything
            # else goes to project_configs.
            dup_text = body[dup.start():find_block_end(body, dup.end() - 1)]
            dup_keys = set(re.findall(r'project_name\s*=\s*"([^"]+)"\s*\n\s*channel\s*=\s*"([^"]+)"', dup_text))
            is_dup = lambda pc: (pc.get("project_name", ""), pc.get("channel", "")) in dup_keys
            regular = [pc for pc in config["project_configs"] if not is_dup(pc)]
            duplicated = [pc for pc in config["project_configs"] if is_dup(pc)]
            body, _ = replace_block_in_text(body, "project_configs", _format_slack_project_configs_block(regular))
            body, _ = replace_block_in_text(body, "project_configs_duplicated",
                                            _format_slack_project_configs_block(duplicated, "project_configs_duplicated"))
        else:
            block = _format_slack_project_configs_block(config["project_configs"])
            body, _ = replace_block_in_text(body, "project_configs", block)
    return body


def sync_slack_target(alias: str, entry: Dict[str, Any], host_override: Optional[str],
                       dry_run: bool, no_ssl_verify: bool) -> bool:
    host_name = host_override or entry.get("default_host")
    host_cfg = (entry.get("hosts") or {}).get(host_name)
    if host_cfg is None:
        raise SyncError(f"{alias}: unknown host {host_name!r} (available: {list((entry.get('hosts') or {}).keys())})")
    if not host_cfg.get("username") or not host_cfg.get("licensekey"):
        raise SyncError(f"{alias}: host {host_name!r} username/licensekey not filled in in sync_targets.yaml")

    session = make_session(no_ssl_verify)
    base_url = host_cfg["base_url"].rstrip("/")
    username = host_cfg["username"]
    licensekey = host_cfg["licensekey"]

    print(f"  Fetching Slack configs + owned systems from {base_url} (host={host_name})...")
    slack_configs = fetch_slack_env_configs(session, base_url, username, licensekey)
    systems = get_own_systems(session, base_url, username, licensekey, username)
    system_id_to_name = _build_system_id_to_name(systems)
    for config in slack_configs:
        config["system_name"] = system_id_to_name.get(config.get("system_id", ""), config.get("system_id", ""))

    matches = [c for c in slack_configs if c.get("system_name") == entry["system_name"]]
    if not matches:
        raise SyncError(f"{alias}: no Slack config on {base_url} matched system {entry['system_name']!r}")
    if len(matches) > 1:
        raise SyncError(
            f"{alias}: {len(matches)} Slack configs matched system {entry['system_name']!r} "
            f"on {base_url} — ambiguous, needs manual review"
        )
    config = matches[0]

    file_path = output_path(entry) / entry["file"]
    text = file_path.read_text(encoding="utf-8")
    start, end = get_block_span(text, entry["block"])
    new_body = sync_slack_block(text[start:end], config)
    new_text = text[:start] + new_body + text[end:]

    changed = new_text != text
    if changed and not dry_run:
        file_path.write_text(new_text, encoding="utf-8")
    print(f"    {file_path}: {'would change' if (changed and dry_run) else ('changed' if changed else 'no changes')}")
    return changed


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(registry: Dict[str, Any]) -> None:
    for kind in ("systems", "servicenow", "slack"):
        entries = registry.get(kind) or {}
        if not entries:
            continue
        print(f"\n[{kind}]")
        for alias, entry in sorted(entries.items()):
            exists = "" if output_path(entry).exists() else "  (output_dir MISSING)"
            print(f"  {alias:<28} -> {entry['output_dir']}{exists}")
    pairs = registry.get("copy_pairs") or []
    if pairs:
        print("\n[copy_pairs]")
        for pair in pairs:
            print(f"  {pair['name']:<28} {pair['from']} -> {pair['to']}")


def cmd_sync_one(registry: Dict[str, Any], alias: str, host_override: Optional[str],
                  dry_run: bool, prune: bool, no_ssl_verify: bool) -> bool:
    kind, entry = find_alias(registry, alias)
    if entry is None:
        print(f"ERROR: unknown alias {alias!r}. Run `list` to see available aliases.", file=sys.stderr)
        sys.exit(1)

    print(f"=== sync-{alias} [{kind}]{' (dry-run)' if dry_run else ''} ===")
    try:
        if kind == "systems":
            sync_system_target(alias, entry, dry_run=dry_run, prune=prune, no_ssl_verify=no_ssl_verify)
        elif kind == "servicenow":
            sync_servicenow_target(alias, entry, host_override, dry_run, no_ssl_verify)
        elif kind == "slack":
            sync_slack_target(alias, entry, host_override, dry_run, no_ssl_verify)
        return True
    except SyncError as e:
        print(f"  FAILED: {e}", file=sys.stderr)
        return False


def cmd_sync_all(registry: Dict[str, Any], dry_run: bool, prune: bool, no_ssl_verify: bool) -> None:
    aliases = []
    for kind in ("systems", "servicenow", "slack"):
        aliases += sorted((registry.get(kind) or {}).keys())

    results = {}
    for alias in aliases:
        ok = cmd_sync_one(registry, alias, host_override=None, dry_run=dry_run,
                           prune=prune, no_ssl_verify=no_ssl_verify)
        results[alias] = ok

    print("\n=== sync-all summary ===")
    for alias, ok in results.items():
        print(f"  {'OK  ' if ok else 'FAIL'}  {alias}")
    if not all(results.values()):
        sys.exit(1)


def cmd_copy(registry: Dict[str, Any], pair_name: str, dry_run: bool, prune: bool) -> None:
    pairs = {p["name"]: p for p in (registry.get("copy_pairs") or [])}
    pair = pairs.get(pair_name)
    if pair is None:
        print(f"ERROR: unknown copy pair {pair_name!r}. Run `list` to see available pairs.", file=sys.stderr)
        sys.exit(1)

    _, from_entry = find_alias(registry, pair["from"])
    _, to_entry = find_alias(registry, pair["to"])
    if from_entry is None or to_entry is None:
        print(f"ERROR: copy pair {pair_name!r} references an unknown alias", file=sys.stderr)
        sys.exit(1)

    print(f"=== copy {pair_name}: {pair['from']} -> {pair['to']}{' (dry-run)' if dry_run else ''} ===")

    customer_remap = None
    from_user, to_user = from_entry.get("username"), to_entry.get("username")
    if from_user and to_user and from_user != to_user:
        customer_remap = (from_user, to_user)
        print(f"  Remapping system_settings.tf source_customer/target_customer: {from_user!r} -> {to_user!r}")

    written, stale = copy_generated_subset(
        output_path(from_entry), output_path(to_entry), dry_run=dry_run, prune=prune,
        customer_remap=customer_remap,
    )
    print(f"  {'Would write' if dry_run else 'Wrote'} {len(written)} file(s).")
    for path in stale:
        print(f"  [STALE] {path}" + ("" if prune else " (use --prune to remove)"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="In-place sync for NBC Terraform folders and ServiceNow/Slack integrations.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("command", help="list | sync-all | sync-<alias> | copy | fetch-l2m-ids-<alias>")
    parser.add_argument("pair_name", nargs="?", help="[copy] name of the copy_pairs entry")
    parser.add_argument("--host", help="[sync-<alias> on a servicenow/slack target] override which host to pull from")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing files")
    parser.add_argument("--prune", action="store_true",
                         help="Delete stale generated project files that no longer exist upstream (default: warn only)")
    parser.add_argument("--targets", default=None, help="Path to sync_targets.yaml (default: alongside this script)")
    parser.add_argument("--no-ssl-verify", action="store_true")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    targets_path = Path(args.targets) if args.targets else Path(__file__).parent / "sync_targets.yaml"

    try:
        registry = load_registry(targets_path)
    except SyncError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.command == "list":
        cmd_list(registry)
    elif args.command == "sync-all":
        cmd_sync_all(registry, dry_run=args.dry_run, prune=args.prune, no_ssl_verify=args.no_ssl_verify)
    elif args.command == "copy":
        if not args.pair_name:
            print("ERROR: copy requires a pair name, e.g. `copy nbcuat-prod-to-stage`. Run `list` to see pairs.",
                  file=sys.stderr)
            sys.exit(1)
        cmd_copy(registry, args.pair_name, dry_run=args.dry_run, prune=args.prune)
    elif args.command.startswith("fetch-l2m-ids-"):
        alias = args.command[len("fetch-l2m-ids-"):]
        kind, entry = find_alias(registry, alias)
        if entry is None or kind != "systems":
            print(f"ERROR: unknown `systems` alias {alias!r}. Run `list` to see available aliases.",
                  file=sys.stderr)
            sys.exit(1)
        print(f"=== fetch-l2m-ids-{alias}{' (dry-run)' if args.dry_run else ''} ===")
        bic_template_path = REPO_ROOT / "NBC/BIC-Templates/l2m_project_template.tf"
        metric_overrides_path = REPO_ROOT / "NBC/BIC-Templates/metric_config_l2m.json"
        if not bic_template_path.is_file():
            print("  (NBC/BIC-Templates/l2m_project_template.tf not found — will only refresh "
                  "already-wired ids, not discover new ones.)")
            bic_template_path = None
        try:
            sync_l2m_component_ids(alias, entry, dry_run=args.dry_run, no_ssl_verify=args.no_ssl_verify,
                                    bic_template_path=bic_template_path,
                                    metric_overrides_path=metric_overrides_path)
        except SyncError as e:
            print(f"  FAILED: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command.startswith("sync-"):
        alias = args.command[len("sync-"):]
        ok = cmd_sync_one(registry, alias, host_override=args.host, dry_run=args.dry_run,
                           prune=args.prune, no_ssl_verify=args.no_ssl_verify)
        if not ok:
            sys.exit(1)
    else:
        print(f"ERROR: unknown command {args.command!r}\n", file=sys.stderr)
        build_arg_parser().print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

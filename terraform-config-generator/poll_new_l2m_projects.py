#!/usr/bin/env python3
"""
Poll InsightFinder for new BIC log projects and open a PR per target that adds
their matching log-project + L2M metric-project Terraform files.

For each project found live but missing from a target's log-projects/*.tf:
  1. Render log-projects/<slug>.tf and l2m-projects/<slug>_l2m.tf from that
     target's master template pair (sync_targets.yaml: master_log_template /
     master_l2m_template) — same field-substitution style as
     check_project_sync.py's generate-l2m-projects.
  2. Wire up the new <slug>_l2m_id variable (module + root variables.tf,
     l2m_projects.tf passthrough) via sync_environments.py's existing helpers.
  3. Bootstrap-create the L2M metric project for real via a throwaway,
     local-backend `terraform apply` (no AWS/S3/DynamoDB credentials — state
     is discarded immediately after) purely to learn its real
     Global_<projectKey> id before opening the PR.
  4. Write that id into l2m-component-ids.auto.tfvars.
  5. Commit everything on a new branch and open a PR with `gh`.

This script never touches the real remote state — the existing
.github/workflows/terraform-plan.yml / terraform-apply.yml pipeline still owns
reviewing, planning, and applying the PR itself.

Usage:
  python3 poll_new_l2m_projects.py [--alias ALIAS ...] [--targets PATH]
                                    [--dry-run] [--force] [--no-ssl-verify]

Config (sync_targets.yaml `systems:` entries), in addition to the existing
base_url/username/licensekey/system_name/output_dir fields:
  poll_enabled: true
  poll_interval_minutes: 15
  master_log_template: "log-projects/atom.tf"      # relative to output_dir
  master_l2m_template: "l2m-projects/atom_l2m.tf"  # relative to output_dir
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    print("Missing dependency: pyyaml. Install with: pip install pyyaml", file=sys.stderr)
    raise

sys.path.insert(0, str(Path(__file__).parent))

from auto_generate_terraform import make_session, get_own_systems, get_system_display_name
from check_project_sync import generate_l2m_content, find_block_end
from sync_environments import (
    load_registry, find_alias, output_path, SyncError,
    _get_projects_for_system, _ensure_variable_block, _ensure_module_passthrough,
    _EXCLUDED_L2M_LABEL_SUBSTRINGS, _L2M_VARFILE_LINE_RE,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = Path(__file__).parent / ".poll_state.json"

_PROJECT_NAME_RE = re.compile(r'project_name\s*=\s*"([^"]+)"')


def tf_slug(name: str) -> str:
    return re.sub(r'[^a-z0-9_]', '_', name.lower()).strip('_')


# ---------------------------------------------------------------------------
# Poll-state — per-alias last-run timestamp, so one Jenkins cron tick can
# serve several aliases that each have their own poll_interval_minutes.
# ---------------------------------------------------------------------------

def load_state() -> Dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def due(alias: str, entry: Dict[str, Any], state: Dict[str, Any], now: float, force: bool) -> bool:
    if force:
        return True
    interval = entry.get("poll_interval_minutes")
    if not interval:
        return True
    last = state.get(alias, {}).get("last_run")
    if last is None:
        return True
    return (now - last) >= interval * 60


# ---------------------------------------------------------------------------
# Existing-project discovery — the git-tracked .tf files ARE the state, no
# separate database needed.
# ---------------------------------------------------------------------------

def existing_log_project_names(log_projects_dir: Path) -> set:
    names = set()
    if not log_projects_dir.is_dir():
        return names
    for tf_file in log_projects_dir.glob("*.tf"):
        if tf_file.name in ("variables.tf", "versions.tf"):
            continue
        m = _PROJECT_NAME_RE.search(tf_file.read_text(encoding="utf-8"))
        if m:
            names.add(m.group(1))
    return names


def branch_exists_on_remote(branch: str) -> bool:
    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", "origin", branch],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Rendering from master templates
# ---------------------------------------------------------------------------

def render_log_project(master_text: str, master_project_name: str,
                        new_project_name: str, new_label: str) -> str:
    """Substitute a log-project master .tf's resource label, project_name,
    project_display_name, and (if present) its l2m_settings
    metric_project_name (<old>-L2M -> <new>-L2M). Everything else is copied
    verbatim — same style as check_project_sync.generate_l2m_content."""
    old_l2m = f"{master_project_name}-L2M"
    new_l2m = f"{new_project_name}-L2M"
    text = master_text.replace(f'"{old_l2m}"', f'"{new_l2m}"')

    text = re.sub(
        r'(resource\s+"insightfinder_project"\s+")[^"]+(")',
        rf'\g<1>{new_label}\2', text, count=1,
    )
    text = re.sub(
        r'^([ \t]*project_name[ \t]*=[ \t]*")[^"]+(")',
        rf'\g<1>{new_project_name}\2', text, flags=re.MULTILINE, count=1,
    )
    text = re.sub(
        r'^([ \t]*project_display_name[ \t]*=[ \t]*")[^"]+(")',
        rf'\g<1>{new_project_name}\2', text, flags=re.MULTILINE, count=1,
    )
    return text


_L2M_RESOURCE_LABEL_RE = re.compile(r'resource\s+"insightfinder_metric_project"\s+"([a-zA-Z0-9_]+)"')


def render_l2m_project(master_l2m_text: str, master_project_name: str,
                        new_project_name: str, new_label: str) -> str:
    """generate_l2m_content() swaps the resource label + project_name(s) but
    leaves metric_configurations' self-referencing `var.<master_label>_id`
    untouched — fix that up here so the new file references its own id var,
    not the master's."""
    text = generate_l2m_content(master_l2m_text, new_project_name, new_label)
    m = _L2M_RESOURCE_LABEL_RE.search(master_l2m_text)
    if m:
        master_label = m.group(1)
        text = text.replace(f"var.{master_label}_id", f"var.{new_label}_id")
    return text


def strip_metric_configurations(l2m_text: str) -> str:
    """Remove the metric_configurations block — used only for the throwaway
    bootstrap apply, which just needs the project shell to be created."""
    m = re.search(r'\n(\s*)metric_configurations\s*=\s*\{', l2m_text)
    if not m:
        return l2m_text
    open_pos = l2m_text.index('{', m.start())
    end_pos = find_block_end(l2m_text, open_pos)
    start = m.start() + 1
    if end_pos < len(l2m_text) and l2m_text[end_pos] == '\n':
        end_pos += 1
    return l2m_text[:start] + l2m_text[end_pos:]


# ---------------------------------------------------------------------------
# Discardable bootstrap apply — create the L2M project for real, learn its
# id, never touch the real S3/DynamoDB state.
# ---------------------------------------------------------------------------

def bootstrap_l2m_project(entry: Dict[str, Any], l2m_resource_text: str) -> None:
    provider_text = (
        'provider "insightfinder" {\n'
        '  base_url    = var.base_url\n'
        '  username    = var.if_username\n'
        '  license_key = var.if_licensekey\n'
        '}\n'
    )
    versions_text = (
        'terraform {\n'
        '  required_providers {\n'
        '    insightfinder = {\n'
        '      source = "insightfinder/insightfinder"\n'
        '    }\n'
        '  }\n'
        '}\n'
        # No backend block => local backend (state lives only in this temp dir).
    )
    variables_text = (
        'variable "base_url" {\n  type = string\n}\n\n'
        'variable "if_username" {\n  type = string\n}\n\n'
        'variable "if_licensekey" {\n  type = string\n  sensitive = true\n}\n\n'
        'variable "system_name" {\n  type = string\n}\n'
    )
    tfvars_text = (
        f'base_url      = "{entry["base_url"]}"\n'
        f'system_name   = "{entry["system_name"]}"\n'
        f'if_username   = "{entry["username"]}"\n'
        f'if_licensekey = "{entry["licensekey"]}"\n'
    )

    tmp_dir = Path(tempfile.mkdtemp(prefix="l2m_bootstrap_"))
    try:
        (tmp_dir / "provider.tf").write_text(provider_text, encoding="utf-8")
        (tmp_dir / "versions.tf").write_text(versions_text, encoding="utf-8")
        (tmp_dir / "variables.tf").write_text(variables_text, encoding="utf-8")
        (tmp_dir / "terraform.tfvars").write_text(tfvars_text, encoding="utf-8")
        (tmp_dir / "main.tf").write_text(strip_metric_configurations(l2m_resource_text), encoding="utf-8")

        subprocess.run(["terraform", "init", "-input=false"], cwd=tmp_dir, check=True)
        subprocess.run(["terraform", "apply", "-auto-approve", "-input=false"], cwd=tmp_dir, check=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def fetch_l2m_global_id(session, entry: Dict[str, Any], l2m_project_name: str) -> Optional[str]:
    systems = get_own_systems(session, entry["base_url"], entry["username"],
                               entry["licensekey"], entry["username"])
    target = next((s for s in systems if get_system_display_name(s) == entry["system_name"]), None)
    if target is None:
        return None
    for p in _get_projects_for_system(target):
        name = p.get("projectName") or p.get("name")
        if name == l2m_project_name and p.get("projectKey"):
            return f"Global_{p['projectKey']}"
    return None


# ---------------------------------------------------------------------------
# l2m-component-ids.auto.tfvars — insert/update one entry, keep sorted.
# ---------------------------------------------------------------------------

def upsert_tfvars_id(tfvars_path: Path, label: str, value: str) -> None:
    existing: Dict[str, str] = {}
    if tfvars_path.exists():
        for line in tfvars_path.read_text(encoding="utf-8").splitlines():
            m = _L2M_VARFILE_LINE_RE.match(line.strip())
            if m:
                existing[m.group(1)] = m.group(2)
    existing[label] = value
    lines = [
        "# Global_ component ids, one per L2M project.",
        "# Regenerate per-environment via generator-scripts (never copy this file between environments).",
        "",
    ]
    for lbl in sorted(existing):
        lines.append(f'{lbl}_id = "{existing[lbl]}"')
    tfvars_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _desc(varname: str) -> str:
    label = varname[: -len("_id")]
    return f"Global_ component id for {label} (this environment only)"


# ---------------------------------------------------------------------------
# PR creation
# ---------------------------------------------------------------------------

def open_pr(entry: Dict[str, Any], branch: str, changed_files: List[Path], added_names: List[str]) -> None:
    rel_paths = [str(f.relative_to(REPO_ROOT)) for f in changed_files]
    subprocess.run(["git", "checkout", "-b", branch], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "add", *rel_paths], cwd=REPO_ROOT, check=True)
    title = f"{entry['system_name']}: add {len(added_names)} new BIC project(s) ({', '.join(added_names)})"
    subprocess.run(["git", "commit", "-m", title], cwd=REPO_ROOT, check=True)
    subprocess.run(["git", "push", "-u", "origin", branch], cwd=REPO_ROOT, check=True)
    body = (
        "Auto-detected new BIC log project(s) via poll_new_l2m_projects.py.\n"
        "The L2M metric project(s) were already bootstrap-created (real Global_ id "
        "already filled in below) — this PR's terraform plan should show a near-no-op "
        "for them and a normal create for the log project(s).\n\n"
        + "\n".join(f"- {n}" for n in added_names)
    )
    subprocess.run(
        ["gh", "pr", "create", "--title", title, "--body", body, "--base", "main", "--head", branch],
        cwd=REPO_ROOT, check=True,
    )
    subprocess.run(["git", "checkout", "main"], cwd=REPO_ROOT, check=True)


# ---------------------------------------------------------------------------
# Per-alias processing
# ---------------------------------------------------------------------------

def process_alias(alias: str, entry: Dict[str, Any], session, dry_run: bool) -> bool:
    for field in ("base_url", "username", "licensekey", "system_name", "output_dir"):
        if not entry.get(field):
            raise SyncError(f"{alias}: missing/blank {field!r} in sync_targets.yaml")
    if not entry.get("master_log_template") or not entry.get("master_l2m_template"):
        raise SyncError(f"{alias}: master_log_template/master_l2m_template not configured")

    out_dir = output_path(entry)
    log_dir = out_dir / "log-projects"
    l2m_dir = out_dir / "l2m-projects"
    master_log_path = out_dir / entry["master_log_template"]
    master_l2m_path = out_dir / entry["master_l2m_template"]
    if not master_log_path.is_file() or not master_l2m_path.is_file():
        raise SyncError(f"{alias}: master template file(s) not found under {out_dir}")

    print(f"  Fetching owned systems from {entry['base_url']}...")
    systems = get_own_systems(session, entry["base_url"], entry["username"],
                               entry["licensekey"], entry["username"])
    target = next((s for s in systems if get_system_display_name(s) == entry["system_name"]), None)
    if target is None:
        raise SyncError(f"{alias}: system {entry['system_name']!r} not found on {entry['base_url']}")

    live_projects = _get_projects_for_system(target)
    known_names = existing_log_project_names(log_dir)

    candidates = []
    for p in live_projects:
        name = p.get("projectName") or p.get("name")
        if not name or name in known_names:
            continue
        data_type = (p.get("dataType") or "log").lower()
        if data_type != "log":
            continue
        if any(sub in name.lower() for sub in _EXCLUDED_L2M_LABEL_SUBSTRINGS):
            continue
        candidates.append(name)

    if not candidates:
        print(f"  No new eligible projects for {alias}.")
        return False

    master_log_text = master_log_path.read_text(encoding="utf-8")
    m = _PROJECT_NAME_RE.search(master_log_text)
    master_log_name = m.group(1) if m else master_log_path.stem
    master_l2m_text = master_l2m_path.read_text(encoding="utf-8")

    changed_files: List[Path] = []
    added_names: List[str] = []

    for name in sorted(candidates):
        slug = tf_slug(name)
        branch = f"auto/l2m-{alias}-{slug}"
        if branch_exists_on_remote(branch):
            print(f"  Skipping {name!r} — branch {branch} already exists (PR likely open).")
            continue

        print(f"  New project: {name!r} -> slug {slug!r}")
        if dry_run:
            added_names.append(name)
            continue

        log_text = render_log_project(master_log_text, master_log_name, name, slug)
        l2m_label = f"{slug}_l2m"
        l2m_text = render_l2m_project(master_l2m_text, master_log_name, name, l2m_label)

        print(f"    Bootstrap-creating {name}-L2M on {entry['base_url']}...")
        bootstrap_l2m_project(entry, l2m_text)

        global_id = None
        for attempt in range(5):
            global_id = fetch_l2m_global_id(session, entry, f"{name}-L2M")
            if global_id:
                break
            time.sleep(5)
        if not global_id:
            print(f"    WARNING: could not resolve Global_ id for {name}-L2M after bootstrap "
                  f"apply — skipping this project.", file=sys.stderr)
            continue

        log_path = log_dir / f"{slug}.tf"
        l2m_path = l2m_dir / f"{slug}_l2m.tf"
        log_path.write_text(log_text, encoding="utf-8")
        l2m_path.write_text(l2m_text, encoding="utf-8")
        changed_files += [log_path, l2m_path]

        varname = f"{l2m_label}_id"
        if _ensure_variable_block(l2m_dir / "variables.tf", [varname], _desc):
            changed_files.append(l2m_dir / "variables.tf")
        if _ensure_variable_block(out_dir / "l2m_component_id_variables.tf", [varname], _desc):
            changed_files.append(out_dir / "l2m_component_id_variables.tf")
        if _ensure_module_passthrough(out_dir / "l2m_projects.tf", [varname]):
            changed_files.append(out_dir / "l2m_projects.tf")

        upsert_tfvars_id(out_dir / "l2m-component-ids.auto.tfvars", l2m_label, global_id)
        changed_files.append(out_dir / "l2m-component-ids.auto.tfvars")

        added_names.append(name)
        print(f"    Created {name}-L2M -> {global_id}")

    if not added_names:
        return False
    if dry_run:
        print(f"  [dry-run] Would add {len(added_names)} project(s): {', '.join(added_names)}")
        return True

    subprocess.run(["terraform", "fmt", "-recursive"], cwd=out_dir, check=False)

    branch = f"auto/l2m-{alias}-{'-'.join(tf_slug(n) for n in added_names)}"[:80]
    open_pr(entry, branch, sorted(set(changed_files)), added_names)
    print(f"  Opened PR on branch {branch} for {len(added_names)} project(s).")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Poll InsightFinder for new BIC log projects and open a PR adding their log+L2M Terraform.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--alias", action="append",
                         help="Only process this alias (repeatable). Default: all poll_enabled aliases.")
    parser.add_argument("--targets", default=None, help="Path to sync_targets.yaml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true",
                         help="Ignore poll_interval_minutes and process every selected alias now.")
    parser.add_argument("--no-ssl-verify", action="store_true")
    args = parser.parse_args()

    targets_path = Path(args.targets) if args.targets else Path(__file__).parent / "sync_targets.yaml"
    try:
        registry = load_registry(targets_path)
    except SyncError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    systems = registry.get("systems") or {}
    aliases = args.alias or [a for a, e in systems.items() if e.get("poll_enabled")]
    if not aliases:
        print("No poll_enabled aliases configured (and none given via --alias).")
        return

    state = load_state()
    now = time.time()
    session = make_session(args.no_ssl_verify)

    if not args.dry_run:
        subprocess.run(["git", "checkout", "main"], cwd=REPO_ROOT, check=True)
        subprocess.run(["git", "pull", "--ff-only"], cwd=REPO_ROOT, check=True)

    any_work = False
    for alias in aliases:
        entry = systems.get(alias)
        if entry is None:
            print(f"WARNING: unknown alias {alias!r} — skipping.", file=sys.stderr)
            continue
        if not due(alias, entry, state, now, args.force):
            continue

        print(f"=== poll {alias}{' (dry-run)' if args.dry_run else ''} ===")
        try:
            worked = process_alias(alias, entry, session, args.dry_run)
            any_work = any_work or worked
        except SyncError as e:
            print(f"  FAILED: {e}", file=sys.stderr)
        finally:
            state.setdefault(alias, {})["last_run"] = now

    if not args.dry_run:
        save_state(state)

    if not any_work:
        print("No new projects found this cycle.")


if __name__ == "__main__":
    main()

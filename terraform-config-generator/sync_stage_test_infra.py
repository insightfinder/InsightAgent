#!/usr/bin/env python3
"""
Keep json_key_settings in sync between NBC Stage's two duplicate
environments: "Stage Infra" and "Test Infra".

These two infras are meant to mirror each other project-for-project, using
identical file names (no env suffix/prefix stripping needed, unlike
stage/uat/prod). Over time, a project's json_key_settings can drift — e.g.
someone adds a new json_key while working in Stage Infra but the same
project in Test Infra never gets it. This script finds that drift and, for
`sync`, merges the union of json_key entries into both sides so neither
infra is missing a key the other has.

Only missing keys are added. If the same json_key exists on both sides with
different settings (type/summary_setting/metafield_setting/
dampening_field_setting), the conflict is reported but left untouched —
picking a winner automatically would silently discard someone's setting.

Commands:
  check   - Report json_key differences between matched project pairs
  sync    - Add missing json_key entries to whichever side lacks them

Usage:
  python3 sync_stage_test_infra.py check [--repo-root PATH] [--folder FOLDER]
  python3 sync_stage_test_infra.py sync  [--repo-root PATH] [--folder FOLDER] [--dry-run]
"""

import sys
import argparse
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from check_project_sync import (
    parse_json_key_settings,
    replace_json_key_settings_in_text,
)

INFRA_A = "Stage Infra"
INFRA_B = "Test Infra"
INFRAS = [INFRA_A, INFRA_B]

SKIP_FILES = {"variables.tf", "versions.tf", "provider.tf", "terraform.tfvars", "system_settings.tf"}


# ---------------------------------------------------------------------------
# Discovery / loading
# ---------------------------------------------------------------------------

def discover_folders(stage_root: Path) -> list:
    found = set()
    for infra in INFRAS:
        d = stage_root / infra
        if not d.exists():
            continue
        for sub in d.iterdir():
            if sub.is_dir() and not sub.name.startswith(".") and not sub.name.startswith("terraform"):
                found.add(sub.name)
    return sorted(found)


def collect_pairs(stage_root: Path, folder_name: str) -> dict:
    """Returns dict: filename -> {infra: (path, json_key_entries, raw_text)}"""
    groups = defaultdict(dict)
    for infra in INFRAS:
        folder = stage_root / infra / folder_name
        if not folder.exists():
            continue
        for tf_path in sorted(folder.glob("*.tf")):
            if tf_path.name in SKIP_FILES:
                continue
            text = tf_path.read_text(encoding="utf-8")
            entries = parse_json_key_settings(text)
            groups[tf_path.name][infra] = (tf_path, entries, text)
    return dict(groups)


# ---------------------------------------------------------------------------
# Command: check
# ---------------------------------------------------------------------------

def cmd_check(stage_root: Path, folders: list) -> None:
    any_output = False
    for folder_name in folders:
        groups = collect_pairs(stage_root, folder_name)
        if not groups:
            continue

        missing_side = []
        key_diffs = []
        conflicts = []

        for name in sorted(groups.keys()):
            infras_present = groups[name]

            if len(infras_present) < 2:
                present = next(iter(infras_present))
                absent = INFRA_B if present == INFRA_A else INFRA_A
                missing_side.append(f"  {name} — present in [{present}] only, missing in [{absent}]")
                continue

            a_path, a_entries, _ = infras_present[INFRA_A]
            b_path, b_entries, _ = infras_present[INFRA_B]
            a_by_key = {e["json_key"]: e for e in a_entries}
            b_by_key = {e["json_key"]: e for e in b_entries}

            only_a = sorted(set(a_by_key) - set(b_by_key))
            only_b = sorted(set(b_by_key) - set(a_by_key))
            if only_a or only_b:
                key_diffs.append((name, only_a, only_b))

            for jk in sorted(set(a_by_key) & set(b_by_key)):
                if a_by_key[jk] != b_by_key[jk]:
                    conflicts.append((name, jk, a_by_key[jk], b_by_key[jk]))

        if not (missing_side or key_diffs or conflicts):
            continue

        any_output = True
        print(f"\n{'='*72}")
        print(f"  Folder: {folder_name}")
        print(f"{'='*72}")

        if missing_side:
            print("\n[PROJECT MISSING ON ONE SIDE]")
            print("\n".join(missing_side))

        if key_diffs:
            print("\n[JSON_KEY DIFFERENCES]")
            for name, only_a, only_b in key_diffs:
                print(f"  {name}")
                if only_a:
                    print(f"    only in [{INFRA_A}] ({len(only_a)}):")
                    for jk in only_a:
                        print(f"      + {jk}")
                if only_b:
                    print(f"    only in [{INFRA_B}] ({len(only_b)}):")
                    for jk in only_b:
                        print(f"      + {jk}")

        if conflicts:
            print("\n[CONFLICTING SETTINGS FOR SAME json_key] (not auto-fixed)")
            for name, jk, a_entry, b_entry in conflicts:
                print(f"  {name} :: {jk}")
                print(f"    {INFRA_A:<12}: {a_entry}")
                print(f"    {INFRA_B:<12}: {b_entry}")

    if not any_output:
        print("\nNo differences found — Stage Infra and Test Infra json_key_settings are in sync.")


# ---------------------------------------------------------------------------
# Command: sync
# ---------------------------------------------------------------------------

def cmd_sync(stage_root: Path, folders: list, dry_run: bool) -> None:
    total_files_updated = 0

    for folder_name in folders:
        groups = collect_pairs(stage_root, folder_name)
        if not groups:
            continue

        printed_header = False
        for name in sorted(groups.keys()):
            infras_present = groups[name]
            if len(infras_present) < 2:
                continue  # nothing to merge if the project only exists on one side

            # Union of json_key entries, keyed by json_key. On conflicting
            # settings for the same key, prefer Stage Infra's version (first
            # processed) — existing entries on either side are never
            # overwritten, only genuinely missing keys are added.
            merged: dict = {}
            for infra in INFRAS:
                _, entries, _ = infras_present[infra]
                for entry in entries:
                    jk = entry["json_key"]
                    if jk not in merged:
                        merged[jk] = entry

            for infra in INFRAS:
                path, entries, text = infras_present[infra]
                existing_keys = {e["json_key"] for e in entries}
                missing = [merged[jk] for jk in sorted(merged) if jk not in existing_keys]
                if not missing:
                    continue

                if not printed_header:
                    print(f"\n{'='*72}")
                    print(f"  Folder: {folder_name}  [sync{' DRY-RUN' if dry_run else ''}]")
                    print(f"{'='*72}")
                    printed_header = True

                print(f"\n  {name} [{infra}] — adding {len(missing)} missing json_key(s):")
                for e in missing:
                    print(f"    + {e['json_key']}")

                if not dry_run:
                    new_entries = entries + missing
                    new_entries.sort(key=lambda e: e["json_key"])
                    new_text = replace_json_key_settings_in_text(text, new_entries)
                    path.write_text(new_text, encoding="utf-8")
                    print(f"    => written: {path}")
                    total_files_updated += 1

    print()
    if dry_run:
        print("[DRY-RUN] No files written.")
    else:
        print(f"Done — {total_files_updated} file(s) updated.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Sync json_key_settings between NBC Stage "Stage Infra" and "Test Infra".',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("command", choices=["check", "sync"], help="Action to perform.")
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repo root path (default: parent directory of this script).",
    )
    parser.add_argument(
        "--folder",
        default=None,
        help="Project-type folder to process (e.g. log-projects). Default: all.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="[sync] Show changes without writing files.",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root) if args.repo_root else Path(__file__).parent.parent
    stage_root = repo_root / "NBC" / "NBC Stage"

    if not stage_root.exists():
        print(f"ERROR: NBC Stage directory not found at {stage_root}", file=sys.stderr)
        sys.exit(1)
    for infra in INFRAS:
        if not (stage_root / infra).exists():
            print(f"ERROR: {infra} not found under {stage_root}", file=sys.stderr)
            sys.exit(1)

    folders = [args.folder] if args.folder else discover_folders(stage_root)

    print(f"Repo root : {repo_root}")
    print(f"Stage root: {stage_root}")
    print(f"Command   : {args.command}")
    print(f"Folders   : {', '.join(folders)}")

    if args.command == "check":
        cmd_check(stage_root, folders)
    elif args.command == "sync":
        cmd_sync(stage_root, folders, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

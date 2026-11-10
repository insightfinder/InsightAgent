#!/usr/bin/env python3
"""
Standalone lookup: find a project's projectKey (and Global_<key> component id,
the form used in metric_configurations id-var wiring — see sync_environments.py's
apply_l2m_component_id_vars) given the project's name.

Usage:
  python3 fetch_project_id.py --url <base_url> --username <user> \
      --licensekey <key> --project-name <name> [--no-ssl-verify]

Example:
  python3 fetch_project_id.py --url https://app.insightfinder.com \
      --username nbcuat --licensekey xxxxx --project-name my-metric-project-L2M
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from auto_generate_terraform import (
    make_session,
    get_own_systems,
    get_system_display_name,
)


def get_projects_for_system(system: Dict[str, Any]) -> List[Dict[str, Any]]:
    """projectDetailsList/projectDetailList is sometimes a JSON-encoded string."""
    raw = system.get("projectDetailsList", system.get("projectDetailList", []))
    if isinstance(raw, str):
        try:
            return json.loads(raw) or []
        except (json.JSONDecodeError, ValueError):
            return []
    return raw or []


def find_project(session, base_url: str, username: str, licensekey: str,
                  project_name: str) -> Optional[Dict[str, Any]]:
    systems = get_own_systems(session, base_url, username, licensekey, username)
    if not systems:
        print(f"No owned systems found for {username!r} on {base_url}", file=sys.stderr)
        return None

    for system in systems:
        for project in get_projects_for_system(system):
            if project.get("projectName") == project_name:
                project["_systemDisplayName"] = get_system_display_name(system)
                return project
    return None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="Base URL, e.g. https://app.insightfinder.com")
    parser.add_argument("--username", required=True)
    parser.add_argument("--licensekey", required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--no-ssl-verify", action="store_true")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    session = make_session(args.no_ssl_verify)
    base_url = args.url.rstrip("/")

    print(f"Fetching owned systems from {base_url} for user {args.username!r}...", file=sys.stderr)
    project = find_project(session, base_url, args.username, args.licensekey, args.project_name)

    if project is None:
        print(f"ERROR: project {args.project_name!r} not found among owned systems on {base_url}",
              file=sys.stderr)
        sys.exit(1)

    project_key = project.get("projectKey")
    print(f"project_name:   {project.get('projectName')}")
    print(f"system:         {project.get('_systemDisplayName')}")
    print(f"projectKey:     {project_key}")
    if project_key:
        print(f"component_id:   Global_{project_key}")
    print(f"dataType:       {project.get('dataType')}")


if __name__ == "__main__":
    main()

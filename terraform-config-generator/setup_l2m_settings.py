#!/usr/bin/env python3
"""
Setup Log-to-Metric (L2M) settings for InsightFinder projects.

Usage:
  # Process all projects in a folder:
  python setup_l2m_settings.py --folder "/path/to/l2m-projects"

  # Process a single project by its L2M name (e.g. adobe-uat-L2M):
  python setup_l2m_settings.py --project "adobe-uat-L2M"
"""

import argparse
import glob
import json
import re
import sys
import time
from datetime import datetime
import random
import requests

# ─── Credentials (fill in before running) ────────────────────────────────────
HOST       = ""   # e.g. https://app.insightfinder.com
USERNAME   = ""
PASSWORD   = ""
# ─────────────────────────────────────────────────────────────────────────────

API_ENDPOINT = "/api/v1/logtometricsetting?tzOffset=-14400000"
L2M_SUFFIX   = "-L2M"


def generate_user_agent():
    timestamp = datetime.now().strftime("%Y.%m.%d.%H.%M")
    random_suffix = random.randint(10000, 99999)
    return f"SetupL2MAgent/{timestamp}-{random_suffix} (Linux; x86_64)"


USER_AGENT = generate_user_agent()


def log_in(host, user_name, password):
    url = host + "/api/v1/login-check"
    headers = {"User-Agent": USER_AGENT}
    data = {"userName": user_name, "password": password}

    try:
        resp = requests.post(url, data=data, headers=headers, timeout=60)
        if resp.status_code == 200:
            token = json.loads(resp.text)["token"]
            headers = {"User-Agent": USER_AGENT, "X-CSRF-Token": token}
            print(f"[Login] Logged in as '{user_name}' successfully.")
        else:
            sys.exit(f"[Login] Failed — HTTP {resp.status_code}: {resp.text}")
    except requests.exceptions.RequestException as e:
        sys.exit(f"[Login] Request error: {e}")

    return resp.cookies, headers


def build_regex_info(metric_project_name):
    """Build the regexInfo payload for the given L2M project name."""
    return {
        "jsonFlag": True,
        "metricProjectName": metric_project_name,
        "jsonParsers": [
            {
                "operation": 2,
                "metricValueKey": "alert->core->summary",
                "aggregationMode": 0,
                "aggregationPeriod": 0,
                "groupingByComponent": False,
                "containerType": None,
            }
        ],
        "enableMapping": False,
    }


def strip_l2m_suffix(project_name):
    """Return the base project name without the -L2M suffix (case-insensitive)."""
    if project_name.upper().endswith(L2M_SUFFIX.upper()):
        return project_name[: -len(L2M_SUFFIX)]
    return project_name


def post_l2m_setting(host, cookies, headers, metric_project_name):
    """POST the L2M setting for a single project. Returns True on success."""
    base_name = strip_l2m_suffix(metric_project_name)
    regex_info = build_regex_info(metric_project_name)

    url = host + API_ENDPOINT
    payload = {
        "projectName": base_name,
        "regexInfo": json.dumps(regex_info, separators=(",", ":")),
    }

    print(f"[Request] projectName='{base_name}'  metricProjectName='{metric_project_name}'")
    try:
        resp = requests.post(url, data=payload, headers=headers, cookies=cookies, timeout=60)
        if resp.status_code == 200:
            print(f"[Success] {metric_project_name} → HTTP {resp.status_code}: {resp.text}")
            return True
        else:
            print(f"[Failed]  {metric_project_name} → HTTP {resp.status_code}: {resp.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"[Error]   {metric_project_name} → {e}")
        return False


def extract_project_names_from_folder(folder):
    """
    Scan all .tf files in `folder` and extract the `project_name` values.
    Returns a list of L2M project names (e.g. ['adobe-uat-L2M', ...]).
    """
    tf_files = glob.glob(f"{folder}/**/*.tf", recursive=True) + glob.glob(f"{folder}/*.tf")
    # deduplicate while preserving order
    tf_files = list(dict.fromkeys(tf_files))

    if not tf_files:
        sys.exit(f"[Error] No .tf files found in: {folder}")

    project_names = []
    for tf_file in sorted(tf_files):
        with open(tf_file, "r") as fh:
            content = fh.read()

        # Match:  project_name = "some-value"
        matches = re.findall(r'project_name\s*=\s*"([^"]+)"', content)
        for name in matches:
            if name not in project_names:
                project_names.append(name)
                print(f"[Scan] Found project: '{name}' in {tf_file}")

    if not project_names:
        sys.exit(f"[Error] No project_name entries found in .tf files under: {folder}")

    return project_names


def main():
    parser = argparse.ArgumentParser(
        description="Configure L2M settings on InsightFinder for projects defined in Terraform files."
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--folder",
        help="Path to a directory containing .tf files (processes all projects found).",
    )
    group.add_argument(
        "--project",
        help="Single L2M project name to configure (e.g. adobe-uat-L2M).",
    )

    args = parser.parse_args()

    # ── Login ──────────────────────────────────────────────────────────────
    cookies, headers = log_in(HOST, USERNAME, PASSWORD)

    # ── Collect project names ──────────────────────────────────────────────
    if args.folder:
        project_names = extract_project_names_from_folder(args.folder)
    else:
        project_names = [args.project]

    print(f"\n[Info] About to configure {len(project_names)} project(s).\n")

    # ── Send requests ──────────────────────────────────────────────────────
    success_count = 0
    fail_count = 0
    for name in project_names:
        ok = post_l2m_setting(HOST, cookies, headers, name)
        if ok:
            success_count += 1
        else:
            fail_count += 1

    print(f"\n[Done] {success_count} succeeded, {fail_count} failed.")


if __name__ == "__main__":
    main()

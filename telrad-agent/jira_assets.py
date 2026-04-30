#!/usr/bin/env python3
"""
Jira Assets API helpers — workspace discovery and eNB asset lookup.

Matching strategy (in priority order):
  1. DeviceName numeric suffix  — e.g. Jira DeviceName="eNodeB200" → device_id "200"
                                    Stable even if IP changes.
  2. management_ip              — falls back to IP for assets whose DeviceName has no
                                    embedded device ID (e.g. "eNB", "RoofeNodeB").
"""

import logging
import re

import requests

logger = logging.getLogger(__name__)

_WORKSPACE_ENDPOINT = "/rest/servicedeskapi/assets/workspace"
_AQL_ENDPOINT = "https://api.atlassian.com/jsm/assets/workspace/{workspace_id}/v1/aql/objects"

# objectTypeAttributeId constants for the "device" object type (schema 2)
_ATTR_MANAGEMENT_IP = "390"
_ATTR_DEVICE_NAME = "383"

_DIGITS_RE = re.compile(r"\d+$")
ENB_NAME_RE = re.compile(r"(eNodeB|eNB)", re.IGNORECASE)


def discover_workspace_id(jira_url: str, username: str, api_token: str) -> str:
    """Return the Jira Assets workspace ID for the given Jira instance."""
    url = jira_url.rstrip("/") + _WORKSPACE_ENDPOINT
    resp = requests.get(
        url,
        auth=(username, api_token),
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    values = resp.json().get("values", [])
    if not values:
        raise ValueError(f"No Jira Assets workspace found at {jira_url}")
    workspace_id = values[0]["workspaceId"]
    logger.info(f"Jira workspace ID: {workspace_id}")
    return workspace_id


def _get_attr(obj: dict, attr_id: str) -> str:
    for a in obj.get("attributes", []):
        if str(a.get("objectTypeAttributeId", "")) == attr_id:
            vals = a.get("objectAttributeValues", [])
            if vals:
                return vals[0].get("value") or vals[0].get("displayValue") or ""
    return ""


def fetch_assets_by_ips(
    workspace_id: str,
    username: str,
    api_token: str,
    ips: list[str],
) -> list[dict]:
    """Return a list of asset dicts for all Jira 'device' assets matching the given IPs.

    Each dict: {label, ip, device_id_hint}
      - label: Jira asset name (e.g. "Tus-TennisCourt-eNodeB200")
      - ip: management_ip value
      - device_id_hint: trailing digits from DeviceName (e.g. "200"), or "" if none
    """
    if not ips:
        return []

    ip_list = ",".join(f'"{ip}"' for ip in ips if ip)
    aql = f'objectType = "device" AND "management_ip" IN ({ip_list})'
    endpoint = _AQL_ENDPOINT.format(workspace_id=workspace_id)
    auth = (username, api_token)
    headers = {"Accept": "application/json"}
    per_page = 50
    page = 1
    results: list[dict] = []

    while True:
        params = {"qlQuery": aql, "page": page, "resultsPerPage": per_page}
        resp = requests.get(endpoint, params=params, auth=auth, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        entries = data.get("objectEntries", [])
        for obj in entries:
            label = obj.get("label", "")
            ip = _get_attr(obj, _ATTR_MANAGEMENT_IP)
            device_name = _get_attr(obj, _ATTR_DEVICE_NAME)
            m = _DIGITS_RE.search(device_name)
            device_id_hint = m.group() if m else ""
            results.append({"label": label, "ip": ip, "device_id_hint": device_id_hint})
        logger.debug(f"Page {page}: {len(entries)} assets fetched")
        if len(entries) < per_page:
            break
        page += 1

    logger.info(f"Fetched {len(results)} Jira asset(s) for the queried IPs")
    return results

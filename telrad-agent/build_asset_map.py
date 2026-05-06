#!/usr/bin/env python3
"""
Jira asset map helpers — resolve BreezeVIEW device IDs to Jira asset names.

No file I/O. resolve_subset() is the main entry point: given a subset of
{device_id: ip} and {device_id: display_name}, return {device_id: label}.

Matching strategy (in priority order):
  1. DeviceName numeric suffix  — Jira DeviceName="eNodeB200" → device_id "200"
  2. management_ip              — fallback for assets whose DeviceName has no embedded ID
  3. BreezeVIEW display name    — last resort when no Jira match exists
"""

import logging

from jira_assets import ENB_NAME_RE, fetch_assets_by_ips

logger = logging.getLogger(__name__)


def _resolve_map(device_ip_map: dict[str, str], assets: list[dict], device_name_map: dict[str, str]) -> dict[str, str]:
    """Return {device_id: label} using two-tier Jira matching with BreezeVIEW name fallback."""
    by_hint: dict[str, list[dict]] = {}
    by_ip: dict[str, list[dict]] = {}
    for a in assets:
        if a["device_id_hint"]:
            by_hint.setdefault(a["device_id_hint"], []).append(a)
        if a["ip"]:
            by_ip.setdefault(a["ip"], []).append(a)

    def pick_candidate(candidates: list[dict]) -> dict:
        if len(candidates) == 1:
            return candidates[0]
        enb_ones = [c for c in candidates if ENB_NAME_RE.search(c["label"])]
        chosen = enb_ones[0] if enb_ones else candidates[0]
        labels = [c["label"] for c in candidates]
        logger.warning(f"Multiple Jira assets matched (picking '{chosen['label']}'): {labels}")
        return chosen

    result: dict[str, str] = {}
    for device_id, ip in device_ip_map.items():
        if device_id in by_hint:
            candidates = by_hint[device_id]
            chosen = pick_candidate(candidates)
            label = chosen["label"]
            result[device_id] = label
            asset_ip = chosen["ip"]
            if ip and asset_ip and ip != asset_ip:
                logger.warning(f"  eNB {device_id} → {label}  [matched by DeviceName suffix '{device_id}'] IP MISMATCH: BreezeVIEW={ip}, Jira={asset_ip}")
            else:
                logger.info(f"  eNB {device_id} → {label}  [matched by DeviceName suffix '{device_id}', IP verified: {ip or 'N/A'}]")
        elif ip in by_ip:
            label = pick_candidate(by_ip[ip])["label"]
            result[device_id] = label
            logger.info(f"  eNB {device_id} ({ip}) → {label}  [matched by IP]")
        else:
            fallback = device_name_map.get(device_id) or device_id
            result[device_id] = fallback
            logger.warning(f"  eNB {device_id} ({ip}): no Jira match — using BreezeVIEW name '{fallback}' as instance name")

    return result


def resolve_subset(
    jira_user: str,
    jira_token: str,
    workspace_id: str,
    device_ip_map: dict[str, str],
    device_name_map: dict[str, str],
) -> dict[str, str]:
    """Return {device_id: label} for the given subset of devices.

    Queries Jira only for the IPs in device_ip_map. Falls back to BreezeVIEW
    display name (device_name_map) when no Jira asset matches.
    """
    ips = [ip for ip in device_ip_map.values() if ip]
    assets = fetch_assets_by_ips(workspace_id, jira_user, jira_token, ips)
    return _resolve_map(device_ip_map, assets, device_name_map)

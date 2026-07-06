#!/usr/bin/env python3
"""
Jira asset map helpers — resolve BreezeVIEW device IDs / CPE serials to Jira asset names.

No file I/O. resolve_subset() is the main entry point: given a subset of
{key: match_value} and {key: display_name}, return {key: label}.

Matching strategy depends on match_by:
  match_by="ip" (default, used for eNBs), in priority order:
    1. DeviceName numeric suffix  — Jira DeviceName="eNodeB200" → device_id "200"
    2. management_ip              — fallback for assets whose DeviceName has no embedded ID
    3. BreezeVIEW display name    — last resort when no Jira match exists
    A matched Jira label containing "?" (an unfilled naming-pattern placeholder, e.g.
    "DVR-?h-ue 6C:AD:EF:15:B1:B9") is treated as no match and falls through to tier 3 —
    Jira Assets renders "?" for empty attributes referenced by an object's naming pattern,
    so such labels are a Jira data-hygiene issue, never a usable device name.

  match_by="serial" (used for CPEs), in priority order:
    1. serial_number               — matched against the asset-cache device's
                                      serial_number field. A serial match is authoritative: the found label is
                                      used as-is, including "?"-containing labels, since
                                      the malformed-label heuristic exists only to guard
                                      the weaker IP-based tiers, not an exact serial match.
                                      "As-is" here means the first whitespace-delimited
                                      token of the asset name (jira_assets._to_asset()
                                      already trims any trailing note/MAC before this
                                      module ever sees the label).
                                      A completely blank label (no naming pattern computed
                                      at all) is still treated as no match, same as tier 1
                                      of the IP path — there's no name to use as-is there.
    2. WAN IP (ip_fallback_map)     — optional fallback tried only when serial doesn't
                                      match. Weaker than serial: WAN IPs are DHCP'd/NAT'd
                                      and can be shared or stale, so a match here can
                                      point at the wrong physical device. Logged as a
                                      WARNING (not debug) so a bad match is visible.
    3. CPE serial number            — final fallback (as the instance name) when nothing
                                      above matches.
"""

from __future__ import annotations

import logging

from jira_assets import ENB_NAME_RE, fetch_assets

logger = logging.getLogger(__name__)

_MATCH_BY_VALUES = ("ip", "serial")

# Jira Assets renders a literal "?" in an object's auto-generated label wherever a
# naming-pattern placeholder attribute is left empty (e.g. "DVR-?h-ue 6C:AD:EF:15:B1:B9").
# Such labels are Jira data-hygiene issues, not device names — never use them as an
# instance name.
def _is_malformed_label(label: str) -> bool:
    return not label or "?" in label


def _pick_candidate(candidates: list[dict], prefer=None) -> dict:
    """Return one candidate from a same-key multi-match, deterministically.

    Ties are broken by sorting on label first (so repeated resolutions of the same
    ambiguous data pick the same candidate every time, regardless of Jira's API
    response order — otherwise an instance name could flip between ticks). If
    `prefer` is given (a predicate over a candidate's label), a preferred match is
    chosen over the deterministic default when one exists.
    """
    if len(candidates) == 1:
        return candidates[0]
    ordered = sorted(candidates, key=lambda c: c["label"])
    chosen = ordered[0]
    if prefer:
        preferred = [c for c in ordered if prefer(c["label"])]
        if preferred:
            chosen = preferred[0]
    labels = [c["label"] for c in candidates]
    logger.warning(f"Multiple Jira assets matched (picking '{chosen['label']}'): {labels}")
    return chosen


def _log_label_collisions(result: dict[str, dict], entity_label: str) -> None:
    """Warn when two different keys resolved to the same instance name (metrics would collide)."""
    label_owners: dict[str, list[str]] = {}
    for key, entry in result.items():
        label_owners.setdefault(entry["label"], []).append(key)
    for label, owners in label_owners.items():
        if len(owners) > 1:
            logger.warning(f"  Multiple {entity_label}s resolved to the same instance name '{label}': {owners} — their metrics will collide")


def _log_resolution_summary(
    entity_label: str,
    matched_count: int,
    total: int,
    match_desc: str,
    fallback_desc: str,
    skipped_count: int = 0,
    skipped_desc: str = "",
) -> None:
    summary = f"Resolved {matched_count}/{total} {entity_label}(s) via Jira{match_desc}"
    if skipped_count:
        summary += f" ({skipped_count} {skipped_desc} skipped)"
    unresolved_count = total - matched_count
    if unresolved_count:
        summary += f", {unresolved_count} using {fallback_desc}"
    logger.info(summary)


def _fallback_entry(name: str) -> dict:
    """A {label, venue, component_name, ip, mac, object_key, serial} entry for an
    unmatched key — only label is set, everything else is left empty so callers know
    no device-inventory identifier is available."""
    return {
        "label": name, "venue": "", "component_name": "", "ip": "",
        "mac": "", "object_key": "", "serial": "",
    }


def _matched_entry(candidate: dict) -> dict:
    """A {label, venue, component_name, ip, mac, object_key, serial} entry for a
    successfully matched Jira asset (device-inventory record)."""
    return {
        "label": candidate["label"],
        "venue": candidate.get("venue") or "",
        "component_name": candidate.get("component_name") or "",
        "ip": candidate.get("ip") or "",
        "mac": candidate.get("mac") or "",
        "object_key": candidate.get("object_key") or "",
        "serial": candidate.get("serial") or "",
    }


def _resolve_map_by_serial(
    serial_map: dict[str, str],
    assets: list[dict],
    device_name_map: dict[str, str],
    entity_label: str,
    ip_fallback_map: dict[str, str] | None = None,
) -> dict[str, dict]:
    """Return {key: {label, venue, component_name, ip, mac, object_key, serial}} matching each key's serial number
    against Jira serial_number, with an optional WAN-IP fallback tier.

    Tier 1 — serial_number: a serial match is authoritative — the found label is used
    as-is (including "?"-containing placeholder labels), unlike the IP-based tiers in
    _resolve_map() which discard those as a data-hygiene guard against weaker (IP)
    matches. A completely blank label is still rejected as no match — there's no name
    to use as-is in that case, and treating it as a match would permanently cache an
    empty string and prevent ever re-resolving the CPE once Jira's data is fixed.

    Tier 2 — WAN IP (only if ip_fallback_map is given and serial found nothing): WAN
    IPs are DHCP'd/NAT'd and can be shared or stale, so this is weaker than a serial
    match and can point at the wrong physical device — every WAN-IP match is logged as
    a WARNING (not debug) so a bad match is visible rather than silently trusted.

    venue/component_name/ip/mac/object_key/serial are left empty ("") for fallback
    (fully unmatched) entries.
    """
    by_serial: dict[str, list[dict]] = {}
    by_ip: dict[str, list[dict]] = {}
    for a in assets:
        if a.get("serial"):
            by_serial.setdefault(a["serial"], []).append(a)
        if a.get("ip"):
            by_ip.setdefault(a["ip"], []).append(a)

    ip_fallback_map = ip_fallback_map or {}
    result: dict[str, dict] = {}
    matched_count = 0
    blank_count = 0
    ip_matched_count = 0
    for key, serial in serial_map.items():
        candidates = by_serial.get(serial)
        chosen = _pick_candidate(candidates) if candidates else None
        label = chosen["label"] if chosen else None
        if candidates and not label:
            logger.warning(f"  {entity_label} {key}: Jira label is blank for serial '{serial}' — ignoring match, falling back")
            blank_count += 1
            label = None
            chosen = None

        matched_by_ip = False
        if not label:
            wan_ip = ip_fallback_map.get(key)
            ip_candidates = by_ip.get(wan_ip) if wan_ip else None
            if ip_candidates:
                ip_candidate = _pick_candidate(ip_candidates)
                if ip_candidate["label"]:
                    label = ip_candidate["label"]
                    chosen = ip_candidate
                    matched_by_ip = True
                    ip_matched_count += 1
                    logger.warning(
                        f"  {entity_label} {key} → {label}  [matched by WAN IP fallback '{wan_ip}' — "
                        f"serial '{serial}' had no match; WAN IPs can be shared/stale, verify this is correct]"
                    )

        if label:
            result[key] = _matched_entry(chosen)
            matched_count += 1
            if not matched_by_ip:
                logger.debug(f"  {entity_label} {key} → {label}  [matched by serial_number '{serial}']")
        else:
            result[key] = _fallback_entry(device_name_map.get(key) or key)

    _log_label_collisions(result, entity_label)
    _log_resolution_summary(
        entity_label, matched_count, len(result),
        match_desc=" (serial/WAN-IP match)" if ip_fallback_map else " (serial match)",
        fallback_desc="serial number fallback",
        skipped_count=blank_count, skipped_desc="blank label(s)",
    )
    if ip_matched_count:
        logger.info(f"  {ip_matched_count} {entity_label}(s) matched via WAN-IP fallback (serial had no match)")
    return result


def _resolve_map(
    device_ip_map: dict[str, str],
    assets: list[dict],
    device_name_map: dict[str, str],
    entity_label: str = "eNB",
) -> dict[str, dict]:
    """Return {device_id: {label, venue, component_name, ip, mac, object_key, serial}} using two-tier Jira matching
    with BreezeVIEW name fallback. venue/component_name/ip are left empty ("") for
    fallback (unmatched or malformed-label) entries."""
    by_hint: dict[str, list[dict]] = {}
    by_ip: dict[str, list[dict]] = {}
    for a in assets:
        if a["device_id_hint"]:
            by_hint.setdefault(a["device_id_hint"], []).append(a)
        if a["ip"]:
            by_ip.setdefault(a["ip"], []).append(a)

    prefer_enb = lambda label: ENB_NAME_RE.search(label)

    result: dict[str, dict] = {}
    matched_count = 0
    malformed_count = 0
    for device_id, ip in device_ip_map.items():
        label = None
        chosen = None
        if device_id in by_hint:
            candidates = by_hint[device_id]
            candidate = _pick_candidate(candidates, prefer=prefer_enb)
            label = candidate["label"]
            asset_ip = candidate["ip"]
            if _is_malformed_label(label):
                logger.warning(f"  {entity_label} {device_id}: Jira label '{label}' looks incomplete (naming-pattern placeholder left empty) — ignoring match, falling back")
                label = None
                malformed_count += 1
            else:
                chosen = candidate
                if ip and asset_ip and ip != asset_ip:
                    logger.warning(f"  {entity_label} {device_id} → {label}  [matched by DeviceName suffix '{device_id}'] IP MISMATCH: BreezeVIEW={ip}, Jira={asset_ip}")
                else:
                    logger.debug(f"  {entity_label} {device_id} → {label}  [matched by DeviceName suffix '{device_id}', IP verified: {ip or 'N/A'}]")
        elif ip in by_ip:
            candidate = _pick_candidate(by_ip[ip], prefer=prefer_enb)
            candidate_label = candidate["label"]
            if _is_malformed_label(candidate_label):
                logger.warning(f"  {entity_label} {device_id} ({ip}): Jira label '{candidate_label}' looks incomplete (naming-pattern placeholder left empty) — ignoring match, falling back")
                malformed_count += 1
            else:
                label = candidate_label
                chosen = candidate
                logger.debug(f"  {entity_label} {device_id} ({ip}) → {label}  [matched by IP]")

        if label is not None:
            result[device_id] = _matched_entry(chosen)
            matched_count += 1
        else:
            result[device_id] = _fallback_entry(device_name_map.get(device_id) or device_id)

    _log_label_collisions(result, entity_label)
    _log_resolution_summary(
        entity_label, matched_count, len(result),
        match_desc="", fallback_desc="BreezeVIEW fallback name",
        skipped_count=malformed_count, skipped_desc="malformed label(s)",
    )
    return result


def resolve_with_assets(
    match_value_map: dict[str, str],
    assets: list[dict],
    device_name_map: dict[str, str],
    entity_label: str = "eNB",
    match_by: str = "ip",
    ip_fallback_map: dict[str, str] | None = None,
) -> dict[str, dict]:
    """Like resolve_subset(), but against an already-fetched asset list.

    Returns {key: {label, venue, component_name, ip, mac, object_key, serial}} — venue/component_name/ip are
    only populated for keys with a successfully matched Jira asset; unmatched/fallback
    entries leave them as "".

    Lets a caller fetch assets once (e.g. for a combined IP+serial set spanning
    multiple device types) and resolve several match_value_map subsets against
    the same result, instead of one Jira query per subset.

    match_by="ip" (default): eNB two-tier DeviceName-suffix/management_ip matching;
    match_value_map values are management IPs.
    match_by="serial": CPE serial-number-first matching; match_value_map values are
    serial numbers. ip_fallback_map (optional, {key: wan_ip}) is tried only when a
    key's serial doesn't match — see _resolve_map_by_serial()'s WAN-IP fallback tier.
    Ignored when match_by="ip".
    """
    if match_by not in _MATCH_BY_VALUES:
        raise ValueError(f"match_by must be one of {_MATCH_BY_VALUES!r}, got {match_by!r}")
    if match_by == "serial":
        return _resolve_map_by_serial(
            match_value_map, assets, device_name_map, entity_label=entity_label, ip_fallback_map=ip_fallback_map
        )
    return _resolve_map(match_value_map, assets, device_name_map, entity_label=entity_label)


def resolve_subset(
    base_url: str,
    api_key: str,
    match_value_map: dict[str, str],
    device_name_map: dict[str, str],
    entity_label: str = "eNB",
    match_by: str = "ip",
    ip_fallback_map: dict[str, str] | None = None,
) -> dict[str, dict]:
    """Return {device_id: {label, venue, component_name, ip, mac, object_key, serial}} for the given subset of devices.

    Queries the asset cache only for the IPs (match_by="ip") or serial numbers
    (match_by="serial") in match_value_map. Falls back to the BreezeVIEW display name /
    serial number (device_name_map) when no asset matches (venue/component_name/ip left "").

    ip_fallback_map (optional, match_by="serial" only): {key: wan_ip} tried as a second
    tier when a key's serial doesn't match — its values are queried alongside
    match_value_map's serials in the same asset-cache fetch. See
    _resolve_map_by_serial() for the matching/logging details.

    entity_label is used only for log messages (e.g. "CPE" instead of "eNB")
    when resolving a non-eNB device set such as CPEs.
    """
    if match_by not in _MATCH_BY_VALUES:
        raise ValueError(f"match_by must be one of {_MATCH_BY_VALUES!r}, got {match_by!r}")
    values = [v for v in match_value_map.values() if v]
    if match_by == "serial":
        ip_values = [v for v in (ip_fallback_map or {}).values() if v]
        assets = fetch_assets(base_url, api_key, serials=values, ips=ip_values)
    else:
        assets = fetch_assets(base_url, api_key, ips=values)
    return resolve_with_assets(
        match_value_map, assets, device_name_map, entity_label=entity_label, match_by=match_by,
        ip_fallback_map=ip_fallback_map,
    )

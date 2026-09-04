"""Reconciles one ControllerDevice against Jira Assets and Zabbix, and builds
the InsightFinder log record for it.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from jira_assets import JiraAssetIndex
from models import ControllerDevice
from models import ReconciledDevice
from zabbix import ZabbixIndex

logger = logging.getLogger(__name__)


def reconcile_device(
    device: ControllerDevice, jira_index: JiraAssetIndex, zabbix_index: ZabbixIndex | None
) -> ReconciledDevice:
    jira_match = jira_index.find_device(mac=device.mac, serial=device.serial, name=device.name)

    zabbix_match = None
    zabbix_error = False
    if zabbix_index is not None:
        zabbix_match, zabbix_error = zabbix_index.resolve(
            jira_object_key=jira_match.object_key if jira_match else "",
            jira_zabbix_host_id=jira_match.zabbix_host_id if jira_match else "",
            device_name=device.name,
            device_ip=device.ip,
        )

    return ReconciledDevice(
        controller_device=device,
        jira=jira_match,
        zabbix=zabbix_match,
        zabbix_error=zabbix_error,
    )


_WHITESPACE = re.compile(r"\s+")

# InsightFinder instance-name rule: no space, ",", "_", "@", "#", ":".
_SANITIZE_MAP = str.maketrans({" ": "-", ",": "-", "@": "-", "#": "-", "_": ".", ":": "-"})
_LEADING_NON_WORD = re.compile(r"^[^\w]+")


def sanitize_instance_name(name: str) -> str:
    cleaned = name.translate(_SANITIZE_MAP)
    cleaned = _LEADING_NON_WORD.sub("", cleaned)
    return cleaned or "unknown-device"


def build_instance_tags(devices: list[ControllerDevice]) -> list[str]:
    """Sanitizes each device's name into an InsightFinder instance tag,
    disambiguating collisions.

    Device *name* is not a unique key on any of these vendor controllers —
    e.g. UISP lets two distinct devices (different MAC/serial) share a
    display name across sites. Without disambiguation, two such devices
    sanitize to the same tag and silently collapse into one InsightFinder
    instance, permanently losing one device's data. A colliding tag gets a
    suffix from the device's own stable identifier (serial, then
    device_id, then MAC) so it stays the same across runs.
    """
    base_tags = [sanitize_instance_name(d.name) for d in devices]
    counts = Counter(base_tags)
    collisions = {tag: n for tag, n in counts.items() if n > 1}
    if collisions:
        logger.warning(
            "%d device name(s) collide into %d shared instance tag(s) — disambiguating with serial/device_id/MAC "
            "so distinct devices don't collapse into one InsightFinder instance (e.g. %s)",
            sum(collisions.values()),
            len(collisions),
            ", ".join(list(collisions)[:5]),
        )

    tags: list[str] = []
    fallback_seen: dict[str, int] = {}
    for device, tag in zip(devices, base_tags):
        if counts[tag] > 1:
            disambiguator = device.serial or device.device_id or device.mac
            if disambiguator:
                tag = f"{tag}-{sanitize_instance_name(disambiguator)}"
            else:
                fallback_seen[tag] = fallback_seen.get(tag, 0) + 1
                tag = f"{tag}-{fallback_seen[tag]}"
        tags.append(tag)
    return tags


def _strip_whitespace(value: str) -> str:
    """Every whitespace character removed. Used only to compare a controller
    value against a Jira one, never to rewrite what gets shipped."""
    return _WHITESPACE.sub("", value)


def ip_mismatch(reconciled: ReconciledDevice) -> bool:
    """True when the controller and Jira both report an IP and they differ.

    Whitespace-insensitive, for the same reason matching is (see
    jira_assets.JiraAssetIndex): stray spacing in a Jira field is a
    formatting defect, not a different address, and a device matched despite
    that whitespace must not then be reported as disagreeing with itself.
    """
    jira = reconciled.jira
    if not (jira and jira.ip and reconciled.controller_device.ip):
        return False
    return _strip_whitespace(jira.ip) != _strip_whitespace(reconciled.controller_device.ip)


def mac_mismatch(reconciled: ReconciledDevice) -> bool:
    """True when the controller and Jira both report a MAC and they differ.
    Case- and whitespace-insensitive — Jira holds MACs recorded as
    " 48:A9:8A:9B:EA:C9" and "48:A9:8A:B6: E7:8A", which are the same
    addresses their controllers report, not different ones."""
    jira = reconciled.jira
    if not (jira and jira.mac and reconciled.controller_device.mac):
        return False
    return (
        _strip_whitespace(jira.mac).lower()
        != _strip_whitespace(reconciled.controller_device.mac).lower()
    )


def build_log_data(reconciled: ReconciledDevice) -> dict:
    """The InsightFinder log record for one device.

    Every key is always present, with "" where a value is unknown or the
    device wasn't found at all — a field that disappears when a device is
    missing can't be queried or alerted on in InsightFinder, which is the
    whole point of this agent.

    Values are shipped exactly as each source reports them — whitespace
    included. InsightFinder's ingestion rules constrain the *instance name*,
    which build_instance_tags/sanitize_instance_name handles; the log record
    itself is free-form, so rewriting a source's own value here would only
    misrepresent what that source holds. Whitespace is ignored when finding
    and comparing devices (see jira_assets.JiraAssetIndex, ip_mismatch,
    mac_mismatch), not when reporting them.

    Both match_method fields name a field of this record, so every field one
    can name is present here — that's why controller.serial and
    jira.zabbix_host_id are emitted even though nothing else reads them.
    """
    d = reconciled.controller_device
    jira = reconciled.jira
    zabbix = reconciled.zabbix
    return {
        "controller": {
            "name": d.controller,
            "device_name": d.name,
            "ip": d.ip,
            "mac": d.mac,
            "serial": d.serial,
        },
        "jira": {
            "id": jira.object_key if jira else "",
            "device_name": jira.device_name if jira else "",
            "ip": jira.ip if jira else "",
            "mac": jira.mac if jira else "",
            "zabbix_host_id": jira.zabbix_host_id if jira else "",
            "match_method": jira.match_method if jira else "",
        },
        "zabbix": {
            "id": zabbix.hostid if zabbix else "",
            "device_name": zabbix.device_name if zabbix else "",
            "match_method": zabbix.match_method if zabbix else "",
        },
    }

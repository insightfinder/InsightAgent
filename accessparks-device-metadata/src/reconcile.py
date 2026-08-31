"""Reconciles one ControllerDevice against Jira Assets and Zabbix, and builds
the InsightFinder log record for it.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from jira_assets import JiraAssetClient
from models import ControllerDevice
from models import ReconciledDevice
from zabbix import ZabbixIndex

logger = logging.getLogger(__name__)


def reconcile_device(device: ControllerDevice, jira_client: JiraAssetClient, zabbix_index: ZabbixIndex | None) -> ReconciledDevice:
    jira_match, jira_error = jira_client.find_device(mac=device.mac, serial=device.serial, name=device.name)

    zabbix_match = None
    zabbix_error = False
    # A Jira-lookup error makes the caller discard this record entirely, so
    # skip the Zabbix RPC (which includes a live tag lookup) rather than
    # spending it on a result nobody will use.
    if zabbix_index is not None and not jira_error:
        zabbix_match, zabbix_error = zabbix_index.resolve(
            jira_object_key=jira_match.object_key if jira_match else "",
            jira_zabbix_host_id=jira_match.zabbix_host_id if jira_match else "",
            device_name=device.name,
            device_ip=device.ip,
        )

    return ReconciledDevice(
        controller_device=device,
        jira=jira_match,
        jira_error=jira_error,
        zabbix=zabbix_match,
        zabbix_error=zabbix_error,
    )


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


def build_log_data(reconciled: ReconciledDevice) -> dict:
    d = reconciled.controller_device
    jira = reconciled.jira
    zabbix = reconciled.zabbix
    return {
        "controller": {
            "name": d.controller,
            "device_name": d.name,
            "ip": d.ip or None,
            "mac": d.mac or None,
        },
        "jira": {
            "id": jira.object_key if jira else None,
            "ip": jira.ip if jira else None,
            "mac": jira.mac if jira else None,
        },
        "zabbix": {
            "id": zabbix.hostid if zabbix else None,
        },
    }

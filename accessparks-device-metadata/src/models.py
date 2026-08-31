from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class ControllerDevice:
    """A device as reported by a vendor controller.

    Sites/customers/networks a controller organizes devices under are
    deliberately not modeled here — only device identity matters for the
    reconciliation this agent performs.
    """

    controller: str
    name: str
    ip: str = ""
    mac: str = ""
    serial: str = ""
    device_id: str = ""


@dataclasses.dataclass
class JiraMatch:
    object_key: str
    ip: str = ""
    mac: str = ""
    zabbix_host_id: str = ""


@dataclasses.dataclass
class ZabbixMatch:
    hostid: str
    matched_by: str = ""


@dataclasses.dataclass
class ReconciledDevice:
    controller_device: ControllerDevice
    jira: JiraMatch | None
    jira_error: bool
    zabbix: ZabbixMatch | None
    zabbix_error: bool = False

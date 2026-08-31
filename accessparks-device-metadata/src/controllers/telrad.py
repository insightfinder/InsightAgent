"""Telrad controller — BreezeVIEW CLI (SSH), CPEs only.

Ported near-verbatim from InsightAgent/telrad-agent/get_cli_metrics.py, trimmed
to inventory fields (drops the RSRP/SINR/etc signal-quality parsing this repo
doesn't need). The eNB REST NBI path from that same reference agent is
deliberately not ported — CPEs are the only device class in scope here.

CPE-side data is only reachable via BreezeVIEW's interactive CLI over SSH: a
network-wide "kpi-snapshot" must be triggered and polled until it finishes,
then read back. This is a different service from the Telrad REST NBI, on a
different port on the same host (see README.md). Only online CPEs appear in
a snapshot — an offline CPE is simply absent from list_devices(), never
reported as a false Jira/Zabbix gap.

Command policy — METRICS ONLY, NEVER MODIFY: the only commands ever sent are
"show ..." commands and the exact "request cpe-view cpes kpi-snapshot start".
_run_cli() enforces this with a hard allowlist.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time

from models import ControllerDevice

logger = logging.getLogger(__name__)

STATUS_CMD = "show cpe-view cpes kpi-snapshot status"
START_CMD = "request cpe-view cpes kpi-snapshot start"
SHOW_KPI_CMD = "show cpe-view cpes kpi-snapshot cpe-kpi | nomore"
LIST_SIZE_CMD = "show cpe-view cpes kpi-snapshot list-size"

CLI_PARSE_RETRIES = 3
CLI_RETRY_BACKOFF = 3

_HEADER_RE = re.compile(r"cpe-view cpes kpi-snapshot cpe-kpi\s+(\S+)\s+(\S+)\s+(\S+)")
_STATUS_RE = re.compile(r"kpi-snapshot status\s+(\S+)")
_LIST_SIZE_RE = re.compile(r"kpi-snapshot list-size\s+(\d+)")
# Only inventory field this controller needs from a CPE record — a single targeted
# regex, since a generic multi-key field-registry isn't earning its keep at one key.
_IP_WAN_RE = re.compile(r"\bip-wan\b\s*(\S+)")

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[=>]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class SSHConnectionError(RuntimeError):
    """The ssh/sshpass process itself failed (bad exit code), not a flaky-output issue."""


def _allowed_cli_command(cmd: str) -> bool:
    cmd = cmd.strip()
    return cmd.startswith("show ") or cmd == START_CMD


def _run_cli(commands: list[str], host: str, port: str, user: str, password: str, timeout: int) -> str:
    for cmd in commands:
        if not _allowed_cli_command(cmd):
            raise ValueError(f"Refusing to send disallowed BreezeVIEW CLI command: {cmd!r}")

    stdin_payload = "\n".join(commands + ["exit"]) + "\n"
    env = os.environ.copy()
    env["SSHPASS"] = password
    argv = [
        "sshpass", "-e", "ssh", "-tt",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-p", str(port),
        f"{user}@{host}",
    ]
    proc = subprocess.run(argv, input=stdin_payload, env=env, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise SSHConnectionError(f"ssh/sshpass exited {proc.returncode}: {proc.stderr.strip() or '(no stderr)'}")
    return proc.stdout


def _strip_ansi(text: str) -> str:
    text = _ANSI_RE.sub("", text)
    return _CONTROL_RE.sub("", text)


def _strip_chrome(text: str, sent_commands: tuple = ()) -> str:
    text = _strip_ansi(text)
    skip_lines = set(sent_commands) | {"exit"}
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("Starting BreezeVIEW CLI") or line.startswith("Type 'exit'"):
            continue
        if "connected from" in line and "using console on" in line:
            continue
        if line.startswith("admin@BreezeVIEW>"):
            line = line[len("admin@BreezeVIEW>"):].strip()
            if not line:
                continue
        if line.startswith("[ok][") or line.startswith("[error]["):
            continue
        if line.startswith("Connection to ") and line.endswith("closed."):
            continue
        if line in skip_lines:
            continue
        lines.append(line)
    return "\n".join(lines)


def _run_cli_parsed(commands, host, port, user, password, timeout, parse_fn, what, is_success=None):
    is_success = is_success or (lambda result: bool(result))
    last_error = None
    for attempt in range(1, CLI_PARSE_RETRIES + 1):
        try:
            raw = _run_cli(commands, host, port, user, password, timeout)
        except subprocess.TimeoutExpired as e:
            last_error = TimeoutError(f"ssh command timed out after {timeout}s: {commands}")
            last_error.__cause__ = e
        except SSHConnectionError as e:
            last_error = e
        else:
            cleaned = _strip_chrome(raw, sent_commands=commands)
            try:
                result = parse_fn(cleaned)
            except Exception:
                result = None
            if result is not None and is_success(result):
                return result
            last_error = RuntimeError(f"Could not parse {what} from CLI output: {cleaned!r}")
        if attempt < CLI_PARSE_RETRIES:
            logger.warning("%s (attempt %d/%d) — retrying in %ds", last_error, attempt, CLI_PARSE_RETRIES, CLI_RETRY_BACKOFF)
            time.sleep(CLI_RETRY_BACKOFF)
    raise last_error


def _get_snapshot_status(host, port, user, password, timeout) -> str:
    return _run_cli_parsed(
        [STATUS_CMD], host, port, user, password, timeout,
        parse_fn=lambda text: (m.group(1) if (m := _STATUS_RE.search(text)) else None),
        what="kpi-snapshot status",
    )


def _start_snapshot(host, port, user, password, timeout) -> None:
    _run_cli([START_CMD], host, port, user, password, timeout)


def _parse_cpe_kpi(text: str) -> list[dict]:
    flat = re.sub(r"\s+", " ", text).strip()
    headers = list(_HEADER_RE.finditer(flat))
    cpes = []
    for i, header in enumerate(headers):
        oui, product_class, serial_number = header.groups()
        body_start = header.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(flat)
        body = flat[body_start:body_end]

        current = {
            "oui": oui,
            "product_class": product_class,
            "serial_number": serial_number.upper(),
        }
        m = _IP_WAN_RE.search(body)
        if m:
            value = m.group(1).strip()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            current["ip-wan"] = None if value in ("N/A", "", '""') else value
        cpes.append(current)
    return cpes


def _fetch_snapshot_list_size_and_kpis(host, port, user, password, timeout) -> tuple[int | None, list[dict]]:
    def parse_both(text):
        m = _LIST_SIZE_RE.search(text)
        list_size = int(m.group(1)) if m else None
        return list_size, _parse_cpe_kpi(text)

    def is_success(result):
        list_size, cpes = result
        if list_size is None:
            return bool(cpes)
        return bool(cpes) or list_size == 0

    return _run_cli_parsed(
        [LIST_SIZE_CMD, SHOW_KPI_CMD], host, port, user, password, timeout,
        parse_fn=parse_both,
        what="list-size + cpe-kpi records",
        is_success=is_success,
    )


class TelradController:
    name = "Telrad"

    def __init__(
        self,
        host: str,
        port: str,
        user: str,
        password: str,
        timeout: int = 15,
        snapshot_timeout: int = 240,
        poll_interval: int = 10,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self.snapshot_timeout = snapshot_timeout
        self.poll_interval = poll_interval

    def _collect_cpes(self) -> list[dict]:
        args = (self.host, self.port, self.user, self.password, self.timeout)

        status = _get_snapshot_status(*args)
        if status == "running":
            logger.info("Telrad: kpi-snapshot collection already running — polling for completion")
        else:
            logger.info("Telrad: starting BreezeVIEW kpi-snapshot collection")
            _start_snapshot(*args)

        deadline = time.monotonic() + self.snapshot_timeout
        status = "running"
        while status == "running":
            if time.monotonic() >= deadline:
                logger.warning(
                    "Telrad: kpi-snapshot did not finish within %ds — reading best-effort results",
                    self.snapshot_timeout,
                )
                break
            time.sleep(self.poll_interval)
            try:
                status = _get_snapshot_status(*args)
            except Exception as e:  # noqa: BLE001 - one bad poll must not abort the collection
                logger.warning("Telrad: kpi-snapshot status poll failed: %s — will retry next poll", e)

        if status == "finish-fail":
            logger.warning("Telrad: kpi-snapshot reported finish-fail — reading best-effort results")

        list_size, cpes = _fetch_snapshot_list_size_and_kpis(*args)
        if list_size is not None and list_size != len(cpes):
            logger.warning(
                "Telrad: parsed %d CPE record(s) but CLI reports list-size=%d — some may have been dropped",
                len(cpes), list_size,
            )
        return cpes

    def list_devices(self) -> list[ControllerDevice]:
        cpes = self._collect_cpes()
        devices: list[ControllerDevice] = []
        for cpe in cpes:
            serial = cpe.get("serial_number") or ""
            devices.append(
                ControllerDevice(
                    controller=self.name,
                    name=serial,
                    ip=cpe.get("ip-wan") or "",
                    mac="",
                    serial=serial,
                    device_id=serial,
                )
            )
        logger.info("Telrad: collected %d CPE(s) total", len(devices))
        return devices

#!/usr/bin/env python3
"""
Fetch CPE-side UE KPIs (RSRP, SINR, RSRQ, CINR, tx/rx rates) via the BreezeVIEW CLI.

These metrics are NOT available via the REST NBI (see get_metrics.py) — the CLI's
network-wide "kpi-snapshot" flow is the only source for CPE-side signal quality.

Command policy — METRICS ONLY, NEVER MODIFY:
  The only commands this module will ever send to the BreezeVIEW CLI are:
    - any command starting with "show "
    - the exact command "request cpe-view cpes kpi-snapshot start"
  "start" triggers a KPI collection snapshot; it does not change device configuration.
  No other "request", "set", "commit", or "kpi-snapshot {empty,cancel}" command is ever
  issued. _run_cli() enforces this with a hard allowlist — see CLAUDE.md for the policy.

Access path: this module runs on a host that can reach the BreezeVIEW CLI directly:
  ssh -tt -p <port> <user>@<host>
The CLI is an interactive REPL requiring a PTY (ssh -tt); commands are piped via stdin
and the session is closed with "exit". See:
  docs/BreezeVIEW - How to Get UE(s) KPIs via BreezeVIEW CLI.md

Usage:
  python3 get_cli_metrics.py
  python3 get_cli_metrics.py --all               # include offline CPEs in the summary
  python3 get_cli_metrics.py --json-only --output cpe_metrics.json
  python3 get_cli_metrics.py --skip-collection   # read last snapshot, don't trigger a new one
  python3 get_cli_metrics.py --no-jira           # skip Jira asset name resolution

Each online CPE's Jira asset name is resolved by matching its serial number against
the asset-cache server's 'serial_number' field, falling back to its current WAN IP
(ip-wan) only when serial doesn't match (via build_asset_map's match_by="serial" path),
and shown as its own "jira=" field in the summary (and a "jira_asset_name" key in JSON
output) alongside the serial number.
Best-effort: if ASSET_CACHE_* is not configured, the `requests` package (needed by
jira_assets.py) isn't installed, or no asset matches, that field is left empty,
with a WARNING log — this never blocks the KPI output.
build_asset_map/jira_assets are imported lazily inside resolve_cpe_asset_names() so this
script has no import-time dependency beyond get_metrics.py's (stdlib + sshpass/ssh on PATH).
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

from get_metrics import _cfg, load_env

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

STATUS_CMD = "show cpe-view cpes kpi-snapshot status"
START_CMD = "request cpe-view cpes kpi-snapshot start"
SHOW_KPI_CMD = "show cpe-view cpes kpi-snapshot cpe-kpi | nomore"
LIST_SIZE_CMD = "show cpe-view cpes kpi-snapshot list-size"

# The CLI runs over an interactive SSH/PTY session that occasionally returns empty or
# garbled stdout for an otherwise-valid command (a flaky read, not a real CLI error).
# Parse-critical commands are retried this many times, with this backoff, before giving
# up — see _run_cli_parsed().
CLI_PARSE_RETRIES = 3
CLI_RETRY_BACKOFF = 3

_HEADER_RE = re.compile(
    r"cpe-view cpes kpi-snapshot cpe-kpi\s+(\S+)\s+(\S+)\s+(\S+)"
)
_STATUS_RE = re.compile(r"kpi-snapshot status\s+(\S+)")
_LIST_SIZE_RE = re.compile(r"kpi-snapshot list-size\s+(\d+)")

# Fields that are plain numbers (float-castable) once N/A/"" is filtered out.
_NUMERIC_FIELDS = {
    "up-time", "physical-cell-id", "cell-id", "tx-power", "tx-power1",
    "RSRP0", "RSRP1", "RSRP2", "RSRP3",
    "SINR0", "SINR1", "SINR2", "SINR3",
    "MCC", "MNC",
    "RSRQ", "RSRQ1", "RSRQ2", "RSRQ3",
    "CINR0", "CINR1",
    "RSSI", "RSSI0", "RSSI1", "RSSI2", "RSSI3",
    "bandwidth",
    "DlBLER", "CaSecondaryDlBLER", "UlBLER", "CaSecondaryUlBLER",
    "DlMCS", "CaSecondaryDlMCS", "UlMCS", "CaSecondaryUlMCS",
    "UlRSSI", "CaSecondaryUlRSSI", "UlCINR", "CaSecondaryUlCINR",
    "Distance",
}
_RATE_FIELDS = {"tx-data-rate", "rx-data-rate"}

# Non-numeric per-CPE fields (in addition to _NUMERIC_FIELDS/_RATE_FIELDS above).
_META_FIELDS = {"collection-date", "collection-id", "model", "IMSI", "ip-wan", "ue-status", "serving-enb"}

# All known field names, longest first so e.g. "RSRQ1" is tried before "RSRQ".
_ALL_FIELD_KEYS = sorted(_NUMERIC_FIELDS | _RATE_FIELDS | _META_FIELDS, key=len, reverse=True)
_FIELD_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in _ALL_FIELD_KEYS) + r")\b")


def _allowed_cli_command(cmd: str) -> bool:
    """Metrics-only allowlist: any 'show ...' or the exact snapshot-start request."""
    cmd = cmd.strip()
    return cmd.startswith("show ") or cmd == START_CMD


class SSHConnectionError(RuntimeError):
    """The ssh/sshpass process itself failed (bad exit code) — not a flaky-output issue."""


def _run_cli(commands: list, host: str, port: str, user: str, password: str, timeout: int) -> str:
    """Send a sequence of commands to the BreezeVIEW CLI over SSH and return raw stdout.

    Uses a PTY (ssh -tt) since the CLI is an interactive REPL. The password is passed
    via the SSHPASS env var, never on argv or in a shell string, so it's safe even if
    it contains shell-special characters.

    Raises SSHConnectionError (with stderr attached) if ssh/sshpass itself exits
    non-zero — e.g. bad credentials, host unreachable, sshpass missing — so callers can
    tell that apart from a session that connected fine but returned flaky/garbled output.
    """
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
    proc = subprocess.run(
        argv, input=stdin_payload, env=env,
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise SSHConnectionError(
            f"ssh/sshpass exited {proc.returncode}: {proc.stderr.strip() or '(no stderr)'}"
        )
    return proc.stdout


_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[=>]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _strip_ansi(text: str) -> str:
    """Strip ANSI/VT100 escape sequences and other control chars.

    The remote pty (allocated via ssh -tt) may emit cursor/color control codes even
    though our local side is a subprocess pipe, not a real terminal. Left in place,
    these can glue two tokens together mid-stream (e.g. "...215\\x1b[Kcpe-view...")
    and silently break record-boundary matching downstream.
    """
    text = _ANSI_RE.sub("", text)
    return _CONTROL_RE.sub("", text)


def _strip_chrome(text: str, sent_commands: tuple = ()) -> str:
    """Remove CLI banner/prompt/status-line noise, keeping only command output lines.

    sent_commands: the exact command strings sent to this CLI session. The remote pty
    echoes back whatever we type, and that echoed command text can itself contain the
    literal phrase our response-parsing regexes search for (e.g. the command
    "show cpe-view cpes kpi-snapshot status" contains the same "kpi-snapshot status"
    substring as the real response line). Left in, the echo can be mistaken for — or
    corrupt the boundary of — the real output. Dropping any line that is an exact echo
    of a command we sent removes the ambiguity at the source instead of patching each
    downstream regex.
    """
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
            # Local echo of a command we sent (or the closing "exit"), not real output.
            continue
        lines.append(line)
    return "\n".join(lines)


def _run_cli_parsed(commands, host, port, user, password, timeout, parse_fn, what, is_success=None):
    """Run a CLI command and parse its output, retrying on transient failures.

    Two distinct failure modes are retried, and reported as what they actually are:
    - the ssh/sshpass process itself failing (SSHConnectionError, subprocess.TimeoutExpired)
    - a session that connected fine but returned empty/garbled output that parse_fn
      can't make sense of (a flaky PTY read, not a real CLI error)
    Conflating the two used to produce a misleading "could not parse" error even when the
    real cause was e.g. bad credentials or an unreachable host — retrying doesn't fix that,
    but the final error now says which one actually happened, so on-call debugs the right
    layer.

    Retries up to CLI_PARSE_RETRIES times with CLI_RETRY_BACKOFF between attempts before
    raising.

    parse_fn(cleaned_text) should return the parsed value, or raise/return None on a
    parse miss. is_success(result), if given, decides whether a non-exception result
    counts as success (default: truthy) — pass this when an empty-but-valid result (e.g.
    a network with zero online CPEs) must not be mistaken for a parse miss. Returns
    parse_fn's result on success; raises the last error (SSHConnectionError, a
    TimeoutError, or a RuntimeError naming the unparseable output) if every attempt fails.
    """
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
            logger.warning(
                f"{last_error} (attempt {attempt}/{CLI_PARSE_RETRIES}) — retrying in {CLI_RETRY_BACKOFF}s"
            )
            time.sleep(CLI_RETRY_BACKOFF)
    raise last_error


def get_snapshot_status(host, port, user, password, timeout) -> str:
    """Return the current kpi-snapshot status: empty|running|finish-ok|finish-fail|finish-cancel."""
    return _run_cli_parsed(
        [STATUS_CMD], host, port, user, password, timeout,
        parse_fn=lambda text: (m.group(1) if (m := _STATUS_RE.search(text)) else None),
        what="kpi-snapshot status",
    )


def start_snapshot(host, port, user, password, timeout) -> None:
    _run_cli([START_CMD], host, port, user, password, timeout)


def fetch_snapshot_list_size_and_kpis(host, port, user, password, timeout) -> tuple:
    """Fetch list-size and cpe-kpi records together in one SSH session, retrying as a unit.

    Sending both commands in a single _run_cli call (rather than two independent calls,
    each separately retried) halves the ssh/PTY connect-auth-teardown overhead per tick
    and avoids a flaky link paying for up to two separate 3-attempt retry sequences.

    Returns (list_size, cpes). If list-size fails to parse, list_size is None and the
    cpes-empty check below falls back to always expecting non-empty output.
    """
    def parse_both(text):
        m = _LIST_SIZE_RE.search(text)
        list_size = int(m.group(1)) if m else None
        return list_size, parse_cpe_kpi(text)

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


def _cast_value(key: str, value: str):
    value = value.strip()
    if value in ("N/A", "", '""'):
        return None
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if key in _RATE_FIELDS:
        # e.g. "27.000 kbps" / "0 bps" -> normalize to kbps float
        m = re.match(r"([\d.]+)\s*(kbps|bps)?", value)
        if not m:
            return None
        num = float(m.group(1))
        unit = m.group(2) or "bps"
        return num / 1000.0 if unit == "bps" else num
    if key in _NUMERIC_FIELDS:
        try:
            return float(value)
        except ValueError:
            return value
    return value


def parse_cpe_kpi(text: str) -> list:
    """Parse the output of 'show cpe-view cpes kpi-snapshot cpe-kpi' into per-CPE dicts.

    Tokenizes by known field name rather than by line: the CLI has no real interactive
    terminal attached over SSH, so a record's key-value pairs are not reliably one per
    line — a header or field landing mid-line would silently merge into the previous
    CPE's dict under line-anchored parsing. Flattening whitespace and splitting on known
    field names is immune to wherever the line breaks fall.
    """
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
            # Uppercased at the point of capture — the asset cache stores/matches
            # serial_number case-sensitively (uppercase), so this is the one place
            # every downstream consumer (send_metrics.py, get_cli_metrics.py) needs
            # to agree on the canonical form.
            "serial_number": serial_number.upper(),
        }
        field_matches = list(_FIELD_RE.finditer(body))
        for j, fm in enumerate(field_matches):
            key = fm.group(1)
            val_start = fm.end()
            val_end = field_matches[j + 1].start() if j + 1 < len(field_matches) else len(body)
            current[key] = _cast_value(key, body[val_start:val_end])
        cpes.append(current)
    return cpes


def collect_cpe_metrics(
    host: str, port: str, user: str, password: str,
    timeout: int = 15,
    snapshot_timeout: int = 240,
    poll_interval: int = 10,
    skip_collection: bool = False,
):
    """Run (or reuse) a BreezeVIEW-wide CPE KPI snapshot and return (ts_ms, list[cpe_dict]).

    If skip_collection is True, the last available snapshot is read without triggering
    a new collection (may be stale). Otherwise: check status, start a collection if not
    already running, poll until finish-ok/finish-fail/timeout, then read results.
    """
    if not skip_collection:
        status = get_snapshot_status(host, port, user, password, timeout)
        if status == "running":
            logger.info("kpi-snapshot collection already running — will poll for completion")
        else:
            logger.info("Starting BreezeVIEW kpi-snapshot collection...")
            start_snapshot(host, port, user, password, timeout)

        deadline = time.monotonic() + snapshot_timeout
        status = "running"
        while status == "running":
            if time.monotonic() >= deadline:
                logger.warning(
                    f"kpi-snapshot collection did not finish within {snapshot_timeout}s "
                    "— reading best-effort results"
                )
                break
            time.sleep(poll_interval)
            try:
                status = get_snapshot_status(host, port, user, password, timeout)
            except Exception as e:
                # Already retried CLI_PARSE_RETRIES times inside get_snapshot_status; treat
                # exhaustion as "still running" so one bad poll doesn't abort the whole
                # collection — the deadline check above still bounds total wait time.
                logger.warning(f"kpi-snapshot status poll failed: {e} — will retry next poll")

        if status == "finish-fail":
            logger.warning("kpi-snapshot collection reported finish-fail — reading best-effort results")
        elif status == "finish-ok":
            logger.info("kpi-snapshot collection completed")

    list_size, cpes = fetch_snapshot_list_size_and_kpis(host, port, user, password, timeout)

    if list_size is not None and list_size != len(cpes):
        logger.warning(
            f"Parsed {len(cpes)} CPE record(s) but CLI reports list-size={list_size} "
            "— some CPEs may have been dropped during parsing"
        )

    ts_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    logger.debug(f"Parsed {len(cpes)} CPE KPI record(s)")
    return ts_ms, cpes


def resolve_cpe_asset_names(cpes: list, asset_cache_url: str, asset_cache_key: str) -> None:
    """Best-effort: set cpe["jira_asset_name"] for each online CPE with a matched asset.

    Matches by the CPE's serial number against the asset cache's serial_number field,
    falling back to its current WAN IP (ip-wan) only when serial doesn't match — the
    same lookup used in send_metrics.py (see build_asset_map.resolve_subset,
    match_by="serial"). Never raises — a missing/unreachable asset-cache config, a
    missing `requests` package, or a failed lookup just means jira_asset_name stays
    unset and the diagnostic still prints KPIs.

    build_asset_map/jira_assets are imported here (not at module level) so this script
    has no import-time dependency on `requests` when asset resolution isn't needed.
    """
    candidates = [c for c in cpes if c.get("ue-status") == "online" and c.get("serial_number")]
    if not candidates:
        return

    try:
        from build_asset_map import resolve_subset

        serial_map = {c["serial_number"]: c["serial_number"] for c in candidates}
        ip_fallback_map = {c["serial_number"]: (c.get("ip-wan") or "") for c in candidates}
        resolved = resolve_subset(
            asset_cache_url, asset_cache_key, serial_map, serial_map,
            entity_label="CPE", match_by="serial", ip_fallback_map=ip_fallback_map,
        )
    except Exception as e:
        logger.warning(f"Asset cache lookup failed for CPE(s): {e} — showing serial numbers only")
        return

    for c in candidates:
        entry = resolved.get(c["serial_number"])
        label = entry.get("label") if entry else None
        if label and label != c["serial_number"]:
            c["jira_asset_name"] = label


def print_summary(cpes: list, show_all: bool = False) -> None:
    online_count = sum(1 for c in cpes if c.get("ue-status") == "online")
    for c in cpes:
        label = f"{c.get('serial_number', '?')} ({c.get('model', '')})"
        jira_name = c.get("jira_asset_name", "")
        status = c.get("ue-status", "unknown")
        if status != "online":
            if show_all:
                print(f"[CPE {label}]  jira={jira_name}  {status}")
            continue
        print(
            f"[CPE {label}]  jira={jira_name}  ip={c.get('ip-wan')}  serving-enb={c.get('serving-enb')}  "
            f"RSRP0={c.get('RSRP0')} RSRP1={c.get('RSRP1')}  "
            f"SINR0={c.get('SINR0')} SINR1={c.get('SINR1')}  "
            f"RSRQ={c.get('RSRQ')}"
        )
    print(f"\nTotal devices: {len(cpes)}  Online: {online_count}  Offline: {len(cpes) - online_count}")


def main():
    parser = argparse.ArgumentParser(description="Fetch CPE-side UE KPIs via BreezeVIEW CLI (SSH)")
    parser.add_argument("--output", metavar="FILE", help="Write JSON to file")
    parser.add_argument("--timeout", type=int, default=15, metavar="SEC", help="Per-command SSH timeout (default: 15)")
    parser.add_argument("--snapshot-timeout", type=int, default=240, metavar="SEC", help="Max time to wait for snapshot completion (default: 240)")
    parser.add_argument("--poll-interval", type=int, default=10, metavar="SEC", help="Snapshot status poll interval (default: 10)")
    parser.add_argument("--skip-collection", action="store_true", help="Read last snapshot without triggering a new collection")
    parser.add_argument("--no-jira", action="store_true", help="Skip Jira asset name resolution")
    parser.add_argument("--json-only", action="store_true", help="Print JSON to stdout instead of human-readable summary")
    parser.add_argument("-a", "--all", action="store_true", help="Include offline CPEs in the human-readable summary (default: online only)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    env = load_env()
    host = _cfg(env, "BREEZEVIEW_CLI_HOST")
    port = _cfg(env, "BREEZEVIEW_CLI_PORT") or "22"
    user = _cfg(env, "BREEZEVIEW_CLI_USER")
    password = _cfg(env, "BREEZEVIEW_CLI_PASSWORD")

    if not host or not user or not password:
        logger.error("set BREEZEVIEW_CLI_HOST, BREEZEVIEW_CLI_USER, BREEZEVIEW_CLI_PASSWORD in .env")
        sys.exit(1)

    try:
        ts_ms, cpes = collect_cpe_metrics(
            host, port, user, password,
            timeout=args.timeout,
            snapshot_timeout=args.snapshot_timeout,
            poll_interval=args.poll_interval,
            skip_collection=args.skip_collection,
        )
    except Exception as e:
        logger.error(str(e))
        sys.exit(1)

    if not args.no_jira:
        asset_cache_url = _cfg(env, "ASSET_CACHE_URL")
        asset_cache_key = _cfg(env, "ASSET_CACHE_API_KEY")
        if asset_cache_url and asset_cache_key:
            resolve_cpe_asset_names(cpes, asset_cache_url, asset_cache_key)
        else:
            logger.warning("Asset cache config incomplete — skipping CPE asset name resolution")

    online_count = sum(1 for c in cpes if c.get("ue-status") == "online")
    payload = {
        "timestamp": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_devices": len(cpes),
        "online_devices": online_count,
        "cpes": cpes,
    }
    json_str = json.dumps(payload, indent=2)

    if args.json_only:
        print(json_str)
    else:
        print_summary(cpes, show_all=args.all)
        if args.output:
            with open(args.output, "w") as f:
                f.write(json_str)
            print(f"\nJSON written to {args.output}")


if __name__ == "__main__":
    main()

"""Client for the AccessParks Asset Registry service — a local mirror of Jira
Assets (see InsightAgent/ap-jira-asset-server). This is what every existing
AccessParks agent talks to instead of Jira Assets/AQL directly.

Matching happens against a local index built from one `GET /devices/export`
call rather than per-device `GET /devices/{identifier}` requests. Two reasons:

- Whitespace. Jira Assets device labels contain stray whitespace that the
  controllers don't reproduce — 58 of the ~33k records have a doubled or
  edge space (e.g. "ALBU-Ped  6-AP" for the controller's "ALBU-Ped 6-AP").
  `/devices/{identifier}` matches exactly (case-insensitively), so no
  identifier we could send would ever match those; the registry cannot be
  asked to ignore whitespace. Matching locally can.
- Cost. The registry is reached over the public internet
  (JIRAASSET_BASE is an EC2 host), and this agent resolves ~10k devices with
  up to 3 identifiers each. That's up to 30k internet round trips replaced
  by a single ~3 MB gzipped fetch — which is exactly what the export
  endpoint documents itself as being for.

A failed export fetch aborts the run (same as Zabbix's bulk host fetch)
rather than degrading into per-device "not found", so a network problem is
never reported to InsightFinder as a fleet-wide Jira gap.
"""

from __future__ import annotations

import dataclasses
import gzip
import json
import logging
import re
import urllib.error
import urllib.request

from models import JiraMatch

logger = logging.getLogger(__name__)

_WHITESPACE = re.compile(r"\s+")

# Values reported as jira.match_method, ordered by how much we trust them.
# Each names the record field whose value was used as the lookup key, so a
# reader can see exactly what was matched on rather than inferring it. The
# key always comes from the controller here — it's the controller's device
# that's being looked up in Jira.
MATCH_MAC = "controller.mac"
MATCH_SERIAL = "controller.serial"
MATCH_NAME = "controller.device_name"


def _exact_key(value: str) -> str:
    return value.strip().lower()


def _loose_key(value: str) -> str:
    """Whitespace-insensitive form of an identifier: every whitespace run
    removed, lowercased. "ALBU-Ped  6-AP" and "albu-ped 6-ap" collapse to the
    same key."""
    return _WHITESPACE.sub("", value).lower()


class JiraAssetClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def health_ok(self) -> bool:
        try:
            req = urllib.request.Request(
                f"{self.base_url}/health",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read()).get("status") == "ok"
        except (urllib.error.URLError, ValueError, OSError) as e:
            logger.error("Asset Registry health check failed: %s", e)
            return False

    def export_devices(self, timeout: int = 180) -> list[dict]:
        """GET /devices/export — every device record in one call. Raises
        RuntimeError on any failure; the caller must abort the run.

        The payload's shape is checked, not assumed: a proxy or WAF in front
        of the registry can answer 200 with a JSON *object* error envelope,
        which would otherwise sail past this contract and fail later as an
        AttributeError inside build_index, past main()'s RuntimeError handler.
        """
        req = urllib.request.Request(
            f"{self.base_url}/devices/export",
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-API-Key": self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            records = json.loads(raw)
        except (urllib.error.URLError, ValueError, OSError) as e:
            raise RuntimeError(f"Jira Assets device export failed: {e}") from e
        if not isinstance(records, list):
            raise RuntimeError(
                f"Jira Assets device export returned {type(records).__name__}, not a list of devices"
            )
        return records


class JiraAssetIndex:
    """Local, whitespace-insensitive index over the Asset Registry export.

    Identifiers are tried strongest-first — MAC, then serial, then the device
    label — and each is looked up exactly (case-insensitively) before its
    whitespace-stripped form. IP is deliberately not a match key: it isn't
    stable enough to key identity on, and IP disagreement is one of the
    things this agent exists to report. Neither is Jira's short `device_name`
    ("AP", "GN", "GPONAP"): 29,697 of the 33k devices share one with another
    device, and across a 2,000-device sample the unique remainder matched
    nothing a stronger identifier hadn't already matched — so indexing it
    only risks binding a device to an unrelated venue's asset.

    Exact and whitespace-stripped keys live in separate tables so relaxing
    whitespace can only add matches, never redirect or destroy an exact one.
    Jira really does contain a device whose stripped label collides with a
    different device's exact label ("DLPC-Home315-HMR"), which in a shared
    table would take out the exact match too.

    A key claimed by two or more devices is disabled rather than resolved
    arbitrarily. Jira has 277 MACs and 180 serials sitting on more than one
    device — placeholders like "-" and "n/a", but also real duplicates left
    behind by device replacements. `GET /devices/{identifier}` settles those
    with an arbitrary `LIMIT 1`; refusing the identifier and falling through
    to the next one instead means a device is matched on a unique serial or
    its own name rather than a coin-flipped MAC, or is honestly reported as
    unmatched.
    """

    _METHODS = (MATCH_MAC, MATCH_SERIAL, MATCH_NAME)

    def __init__(self) -> None:
        # method -> key -> JiraMatch, or None once the key is known ambiguous.
        self._exact: dict[str, dict[str, JiraMatch | None]] = {m: {} for m in self._METHODS}
        self._loose: dict[str, dict[str, JiraMatch | None]] = {m: {} for m in self._METHODS}
        # Identifier values disabled for being shared, held as
        # (method, loose key). A set rather than a counter, and keyed on the
        # loose form rather than the table key: each value is inserted into
        # both the exact and the loose table, so an incrementing counter — or
        # a set keyed on the table key, whose two forms differ whenever the
        # value contains whitespace — would report each identifier twice.
        self._disabled: set[tuple[str, str]] = set()
        # One entry per device whose strongest identifier was ambiguous, so a
        # weaker one (or nothing) had to be used — a Jira data-quality signal
        # worth reporting per run. Appends are atomic, so no lock is needed
        # for the concurrent reconcile workers.
        self.ambiguous_hits: list[tuple[str, str]] = []

    @property
    def ambiguous_keys(self) -> int:
        """Distinct identifier values disabled for being shared by two or
        more Jira devices."""
        return len(self._disabled)

    def _put(self, table: dict[str, JiraMatch | None], key: str, match: JiraMatch) -> bool:
        """Indexes match under key. Returns True if this call disabled the key
        as ambiguous."""
        if key not in table:
            table[key] = match
            return False
        if table[key] is not None and table[key].object_key != match.object_key:
            table[key] = None
            return True
        return False

    def add(self, record: dict) -> None:
        object_key = record.get("object_key") or ""
        if not object_key:
            return
        match = JiraMatch(
            object_key=object_key,
            device_name=record.get("name") or record.get("device_name") or "",
            ip=record.get("ip_address") or "",
            mac=(record.get("mac_address") or "").upper(),
            zabbix_host_id=record.get("zabbix_host_id") or "",
        )
        for method, value in (
            (MATCH_MAC, record.get("mac_address") or ""),
            (MATCH_SERIAL, record.get("serial_number") or ""),
            (MATCH_NAME, record.get("name") or ""),
        ):
            if not value.strip():
                continue
            disabled = self._put(self._exact[method], _exact_key(value), match)
            disabled |= self._put(self._loose[method], _loose_key(value), match)
            if disabled:
                self._disabled.add((method, _loose_key(value)))

    def find_device(self, mac: str, serial: str, name: str) -> JiraMatch | None:
        """Returns the matched device with match_method filled in, or None for
        a confirmed miss.

        Records at most one ambiguous-identifier hit per call, so
        ambiguous_hits stays a count of affected *devices* — a device with
        both a shared MAC and a shared serial is one problem to fix, not two.
        The hit is recorded the moment an ambiguous identifier is skipped,
        not after the loop: a device that then matches on a weaker identifier
        returns from inside the loop, and it's exactly those devices (matched
        on their name because their MAC was shared) most worth reporting.
        """
        recorded = False
        for method, value in (
            (MATCH_MAC, mac),
            (MATCH_SERIAL, serial),
            (MATCH_NAME, name),
        ):
            if not value or not value.strip():
                continue
            ambiguous = False
            for table, keyfn in ((self._exact, _exact_key), (self._loose, _loose_key)):
                key = keyfn(value)
                match = table[method].get(key)
                if match is not None:
                    return dataclasses.replace(match, match_method=method)
                ambiguous = ambiguous or key in table[method]
            if ambiguous and not recorded:
                self.ambiguous_hits.append((method, value))
                recorded = True
        return None


def build_index(client: JiraAssetClient) -> JiraAssetIndex:
    logger.info("Fetching Jira Assets device export from %s...", client.base_url)
    records = client.export_devices()
    # An unsynced registry answers 200 with []. Building an empty index from
    # that would report the entire fleet as missing from Jira — precisely the
    # fleet-wide false gap this module's error handling exists to prevent, and
    # no longer caught per-device now that the jira_error tri-state is gone.
    if not records:
        raise RuntimeError(
            "Jira Assets device export returned 0 devices — the registry is empty or unsynced "
            "(check its /sync/status); every device would otherwise be reported as missing from Jira"
        )
    index = JiraAssetIndex()
    for record in records:
        index.add(record)
    logger.info(
        "Indexed %d Jira Asset device(s) (%d ambiguous identifier(s) disabled as match keys — "
        "values shared by two or more Jira devices, which cannot identify either)",
        len(records),
        index.ambiguous_keys,
    )
    return index

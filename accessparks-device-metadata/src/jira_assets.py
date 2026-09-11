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
_NON_HEX = re.compile(r"[^0-9a-f]")

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


def mac_key(value: str) -> str:
    """Separator-insensitive form of a MAC: every non-hex character removed,
    lowercased. Jira records the same address both ways — 21,522 with colons
    and 717 with dashes ("00-0e-d8-19-89-8c" for the controller's
    "00:0E:D8:19:89:8C") — so neither form can be the only one indexed.

    Returns "" unless the result is exactly 12 hex digits. Jira holds "-" as
    the MAC of 286 devices and other placeholders like "n/a"; without the
    length check those collapse into short keys that would collide devices
    with each other rather than identify any of them."""
    stripped = _NON_HEX.sub("", value.lower())
    return stripped if len(stripped) == 12 else ""


def _serial_core_key(value: str) -> str:
    """The real serial inside a Positron composite serial: field 3 of the
    4-field "ASY-2103-20,R14,01142017,24192" is "01142017", which is exactly
    what Jira stores for that device. Returns "" for anything that isn't a
    4-field comma composite — Positron's fleet has only those two shapes
    (2,376 composite, 174 plain), so there is no third case to guess at.

    Applied when indexing Jira too, not just when looking a device up: Jira
    itself holds a handful of records carrying the whole composite string, and
    normalizing both sides the same way is what lets those match."""
    parts = [p.strip() for p in value.split(",")]
    return parts[2].lower() if len(parts) == 4 else ""


def _serial_zero_key(value: str) -> str:
    """Leading-zero-insensitive serial. Positron reports "01126539" where Jira
    stores "1126539" for the same device (LVKS-Ped333-GN), and 1,855 Jira
    serials carry a leading zero while 737 are recorded without one. Only 6
    values exist in Jira in both forms; those disable themselves as ambiguous
    like any other shared identifier."""
    return _loose_key(value).lstrip("0")


def _serial_core_zero_key(value: str) -> str:
    """_serial_core_key then _serial_zero_key — the real serial inside a
    composite, with leading zeros removed. Positron's
    "ASY-2103-20,R12,01126539,23321" reaches Jira's "1126539"
    (LVKS-Ped333-GN) only through both reductions."""
    core = _serial_core_key(value)
    return _serial_zero_key(core) if core else ""


def _name_key(value: str) -> str:
    """Whitespace- and "+"-insensitive device label. Jira spells one venue's
    combo units "ILBI-Lot 8-ONT+HRAP" (123 records, all ILBI) where UISP — and
    every other venue's Jira records — spell the same hardware "ONTHRAP". The
    "+" is a data-entry convention, not part of the device's identity."""
    return _WHITESPACE.sub("", value).replace("+", "").lower()


def _keys(value: str, keyfns) -> list[str]:
    """The distinct, non-empty keys one tier's key functions produce for a
    value, in declared order.

    Ordered and de-duplicated rather than a set: a tier can hold several key
    functions (see JiraAssetIndex._KEYFNS), and two of them can in principle
    land on different Jira devices — a controller's composite serial whose
    whole string is one device's serial and whose 3rd field is another's.
    Iterating a set would resolve that by hash order, so the same device could
    match a different asset from run to run. Declared order makes the stricter
    key win, every time.
    """
    keys: list[str] = []
    for keyfn in keyfns:
        key = keyfn(value)
        if key and key not in keys:
            keys.append(key)
    return keys


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
    """Local, normalization-tolerant index over the Asset Registry export.

    Identifiers are tried strongest-first — MAC, then serial, then the device
    label — and each identifier is looked up through an ordered tuple of
    normalizations (_KEYFNS), strictest first: exact (case-insensitive), then
    whitespace-stripped, then a per-identifier form that absorbs how this Jira
    instance actually records that field. IP is deliberately not a match key:
    it isn't stable enough to key identity on, and IP disagreement is one of
    the things this agent exists to report. Neither is Jira's short
    `device_name` ("AP", "GN", "GPONAP"): 29,697 of the 33k devices share one
    with another device, and across a 2,000-device sample the unique remainder
    matched nothing a stronger identifier hadn't already matched — so indexing
    it only risks binding a device to an unrelated venue's asset.

    Each normalization gets its own table so relaxing one can only add
    matches, never redirect or destroy a stricter one. Jira really does
    contain a device whose whitespace-stripped label collides with a different
    device's exact label ("DLPC-Home315-HMR"), which in a shared table would
    take out the exact match too.

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

    # Per-identifier normalizations, strictest tier first. Each tier owns one
    # table and may list several key functions, all of which write into — and
    # read from — that one table, so they act as aliases of equal strictness
    # rather than as separate tiers.
    #
    # That distinction is what makes the serial tiers work. _serial_core_key
    # is not a normalization both sides share: it reduces a composite to the
    # real serial, and Jira stores that same serial *plain*. Given its own
    # table it would only ever meet other composites, so the controller's
    # extracted "01142017" would miss Jira's plain "01142017" entirely. Paired
    # with _loose_key in one tier, both forms land in the same table and match
    # from either direction — which also covers the handful of Jira records
    # that carry the whole composite string themselves.
    #
    # A key function returning "" means "doesn't apply to this value", and
    # that key is skipped — how _serial_core_key ignores non-composites and
    # mac_key ignores placeholder MACs.
    _KEYFNS = {
        MATCH_MAC: ((_exact_key,), (_loose_key,), (mac_key,)),
        MATCH_SERIAL: (
            (_exact_key,),
            (_loose_key, _serial_core_key),
            (_serial_zero_key, _serial_core_zero_key),
        ),
        MATCH_NAME: ((_exact_key,), (_loose_key,), (_name_key,)),
    }

    def __init__(self) -> None:
        # method -> tier index -> key -> JiraMatch, or None once the key is
        # known ambiguous.
        self._tables: dict[str, list[dict[str, JiraMatch | None]]] = {
            m: [{} for _ in self._KEYFNS[m]] for m in self._METHODS
        }
        # Identifier values disabled for being shared, held as
        # (method, whitespace-stripped key). A set rather than a counter, and
        # keyed on one fixed normalization rather than per tier: each value is
        # inserted into every tier's table, so an incrementing counter — or a
        # set keyed per tier, whose forms differ whenever the value contains
        # whitespace or separators — would report each identifier several
        # times. _loose_key is the one used because it is the only
        # normalization that never returns "" for a non-blank value; keying on
        # the most relaxed tier would collapse every placeholder MAC ("-",
        # "n/a") into a single empty key and undercount them.
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
            serial=record.get("serial_number") or "",
            zabbix_host_id=record.get("zabbix_host_id") or "",
        )
        for method, value in (
            (MATCH_MAC, record.get("mac_address") or ""),
            (MATCH_SERIAL, record.get("serial_number") or ""),
            (MATCH_NAME, record.get("name") or ""),
        ):
            if not value.strip():
                continue
            disabled = False
            for table, keyfns in zip(self._tables[method], self._KEYFNS[method]):
                for key in _keys(value, keyfns):
                    disabled |= self._put(table, key, match)
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
            for table, keyfns in zip(self._tables[method], self._KEYFNS[method]):
                for key in _keys(value, keyfns):
                    match = table.get(key)
                    if match is not None:
                        return dataclasses.replace(match, match_method=method)
                    ambiguous = ambiguous or key in table
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

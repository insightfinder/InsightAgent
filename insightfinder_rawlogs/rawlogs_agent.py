#!/usr/bin/env python3
"""
Copies raw log events from one InsightFinder instance to mapped projects on
another, via POST /api/external/v1/rawlogs. Each invocation is one collection
cycle (live window or replay range) and exits; see cron.py for scheduling.
"""
import argparse
import json
import logging
import math
import os
import re
import socket
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from logging.handlers import TimedRotatingFileHandler
from threading import Lock
from typing import Optional

import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.exceptions import InsecureRequestWarning
from urllib3.util.retry import Retry

HOSTNAME = socket.gethostname().partition('.')[0]
RAWLOGS_PATH = '/api/external/v1/rawlogs'
CHECK_PROJECT_PATH = '/api/v1/check-and-add-custom-project'
SEND_DATA_PATH = '/api/v1/customprojectrawdata'

UNDERSCORE = re.compile(r'_+')
COLONS = re.compile(r':+')
LEADING_JUNK = re.compile(r'^[-_\W]+')

logger = logging.getLogger('insightfinder_rawlogs')


class ConfigError(Exception):
    pass


class SourceError(Exception):
    pass


#############
# Config
#############

@dataclass
class SourceConfig:
    url: str
    user_name: str
    license_key: str
    data_user_name: str
    projects: dict  # source_project -> target_project
    verify_ssl: bool
    timeout_seconds: int
    proxies: dict


@dataclass
class DestinationConfig:
    url: str
    user_name: str
    license_key: str
    system_name: str
    project_type: str  # 'log' or 'logreplay'
    sampling_interval_seconds: int
    auto_create_projects: bool
    chunk_size_kb: int
    verify_ssl: bool
    timeout_seconds: int
    proxies: dict


@dataclass
class ReplayRange:
    start_ms: int
    end_ms: int


@dataclass
class CollectionConfig:
    interval_seconds: int
    offset_seconds: int
    slice_seconds: int
    replay: Optional[ReplayRange]
    workers: int
    align_to_interval: bool


@dataclass
class TransformConfig:
    include_metadata: bool
    instance_prefix: str
    instance_whitelist: Optional[re.Pattern]
    default_instance_name: str


@dataclass
class LoggingConfig:
    level: str
    file: Optional[str]
    rotate: bool
    backup_count: int


@dataclass
class AgentConfig:
    source: SourceConfig
    destination: DestinationConfig
    collection: CollectionConfig
    transform: TransformConfig
    logging: LoggingConfig


def _require(section: dict, key: str, section_name: str):
    value = section.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ConfigError(f"Missing required config value: {section_name}.{key}")
    return value


def _parse_timestamp(value, timezone_name: str) -> int:
    """Epoch-millis int/str, or 'YYYY-MM-DD HH:mm:ss' in timezone_name, -> epoch ms."""
    if isinstance(value, (int, float)):
        return int(value)
    value = str(value).strip()
    if value.isdigit():
        return int(value)
    import datetime
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(timezone_name or 'UTC')
    except Exception:
        tz = datetime.timezone.utc
    dt = datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=tz)
    return int(dt.timestamp() * 1000)


def load_config(path: str) -> AgentConfig:
    if not os.path.exists(path):
        raise ConfigError(f"Config file not found: {path}")
    with open(path) as fp:
        raw = yaml.safe_load(fp) or {}

    src = raw.get('source') or {}
    dst = raw.get('destination') or {}
    coll = raw.get('collection') or {}
    trans = raw.get('transform') or {}
    log_cfg = raw.get('logging') or {}

    src_url = _require(src, 'url', 'source')
    src_user = _require(src, 'user_name', 'source')
    src_key = os.environ.get('IF_SOURCE_LICENSE_KEY') or src.get('license_key')
    if not src_key:
        raise ConfigError("Missing required config value: source.license_key "
                          "(or IF_SOURCE_LICENSE_KEY env var)")

    projects = dict(src.get('projects') or {})
    if not projects:
        raise ConfigError("source.projects (a source-project -> destination-project "
                          "map) must have at least one entry")

    source = SourceConfig(
        url=src_url,
        user_name=src_user,
        license_key=src_key,
        data_user_name=src.get('data_user_name') or src_user,
        projects=projects,
        verify_ssl=bool(src.get('verify_ssl', True)),
        timeout_seconds=int(src.get('timeout_seconds', 300)),
        proxies=dict(src.get('proxies') or {}),
    )

    dst_url = _require(dst, 'url', 'destination')
    dst_user = _require(dst, 'user_name', 'destination')
    dst_key = os.environ.get('IF_DEST_LICENSE_KEY') or dst.get('license_key')
    if not dst_key:
        raise ConfigError("Missing required config value: destination.license_key "
                          "(or IF_DEST_LICENSE_KEY env var)")

    project_type = (dst.get('project_type') or 'log').lower()
    if project_type not in ('log', 'logreplay'):
        raise ConfigError("destination.project_type must be 'log' or 'logreplay'")

    destination = DestinationConfig(
        url=dst_url,
        user_name=dst_user,
        license_key=dst_key,
        system_name=dst.get('system_name') or '',
        project_type=project_type,
        sampling_interval_seconds=int(dst.get('sampling_interval_seconds', 60)),
        auto_create_projects=bool(dst.get('auto_create_projects', True)),
        chunk_size_kb=int(dst.get('chunk_size_kb', 2048)),
        verify_ssl=bool(dst.get('verify_ssl', True)),
        timeout_seconds=int(dst.get('timeout_seconds', 120)),
        proxies=dict(dst.get('proxies') or {}),
    )

    interval_seconds = int(coll.get('interval_seconds', 60))
    slice_seconds = int(coll.get('slice_seconds') or interval_seconds)

    replay = None
    replay_raw = coll.get('replay')
    if replay_raw:
        tz_name = replay_raw.get('timezone', 'UTC')
        replay = ReplayRange(
            start_ms=_parse_timestamp(replay_raw['start'], tz_name),
            end_ms=_parse_timestamp(replay_raw['end'], tz_name),
        )
        if replay.end_ms <= replay.start_ms:
            raise ConfigError("collection.replay.end must be after collection.replay.start")

    collection = CollectionConfig(
        interval_seconds=interval_seconds,
        offset_seconds=int(coll.get('offset_seconds', 0)),
        slice_seconds=slice_seconds,
        replay=replay,
        workers=int(coll.get('workers', 4)),
        align_to_interval=bool(coll.get('align_to_interval', True)),
    )

    whitelist_str = trans.get('instance_whitelist') or ''
    try:
        whitelist = re.compile(whitelist_str) if whitelist_str else None
    except re.error as e:
        raise ConfigError(f"Invalid transform.instance_whitelist regex: {e}")

    transform = TransformConfig(
        include_metadata=bool(trans.get('include_metadata', False)),
        instance_prefix=trans.get('instance_prefix') or '',
        instance_whitelist=whitelist,
        default_instance_name=trans.get('default_instance_name') or 'unknown',
    )

    logging_cfg = LoggingConfig(
        level=(log_cfg.get('level') or 'INFO').upper(),
        file=log_cfg.get('file') or None,
        rotate=bool(log_cfg.get('rotate', True)),
        backup_count=int(log_cfg.get('backup_count', 14)),
    )

    return AgentConfig(source=source, destination=destination, collection=collection,
                      transform=transform, logging=logging_cfg)


#############
# Windows
#############

def live_window(now_ms: int, interval_s: int, offset_s: int, align: bool = True) -> tuple:
    """Half-open [start, end) trailing window, interval_s long, ending offset_s
    before now. If align, end is snapped to the nearest interval_s boundary
    (clock-aligned, may close slightly before now); otherwise end is exactly
    now - offset_s (use when the caller's scheduler fires on a precise cadence)."""
    interval_ms = interval_s * 1000
    offset_ms = offset_s * 1000
    end = now_ms - offset_ms
    if align:
        end = math.floor(end / interval_ms) * interval_ms
    start = end - interval_ms
    return start, end


def slices(start_ms: int, end_ms: int, slice_s: int):
    """Half-open sub-ranges of [start_ms, end_ms), each at most slice_s seconds."""
    slice_ms = slice_s * 1000
    t = start_ms
    while t < end_ms:
        nxt = min(t + slice_ms, end_ms)
        yield t, nxt
        t = nxt


#############
# Source: RawLogsClient
#############

@dataclass
class ProjectExport:
    project_name: str
    events: list = field(default_factory=list)
    error: Optional[str] = None


def _session_with_retries(total=3, backoff=1.0) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset(['GET', 'POST']),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


class RawLogsClient:
    def __init__(self, cfg: SourceConfig):
        self.cfg = cfg
        self.session = _session_with_retries()

    def export(self, start_ms: int, end_ms: int) -> list:
        params = {
            'userName': self.cfg.data_user_name,
            'startTime': start_ms,
            'endTime': end_ms,
            'projectNameList': json.dumps(list(self.cfg.projects.keys())),
        }

        headers = {
            'X-User-Name': self.cfg.user_name,
            'X-License-Key': self.cfg.license_key,
        }
        url = urllib.parse.urljoin(self.cfg.url, RAWLOGS_PATH)

        try:
            response = self.session.post(
                url, data=params, headers=headers, verify=self.cfg.verify_ssl,
                proxies=self.cfg.proxies, timeout=self.cfg.timeout_seconds,
            )
        except requests.exceptions.RequestException as e:
            raise SourceError(f"Request to {url} failed: {e}")

        if response.status_code != 200:
            raise SourceError(
                f"Export request failed [{response.status_code}]: {response.text[:500]}")

        body = response.json()
        if not body.get('success'):
            raise SourceError(f"Export request reported failure: {body}")

        results = []
        for proj in body.get('projects', []):
            if proj.get('error'):
                logger.error("Source project '%s' failed to export: %s",
                            proj.get('projectName'), proj.get('error'))
                results.append(ProjectExport(project_name=proj.get('projectName'),
                                            error=proj.get('error')))
                continue
            results.append(ProjectExport(project_name=proj.get('projectName'),
                                        events=proj.get('events') or []))
        return results


#############
# Transform
#############

def safe_instance_name(instance: str) -> str:
    if not instance:
        return ''
    instance = UNDERSCORE.sub('.', instance)
    instance = COLONS.sub('-', instance)
    instance = LEADING_JUNK.sub('', instance)
    return instance


def to_entries(export: ProjectExport, cfg: TransformConfig) -> list:
    """Pure transform: export events -> InsightFinder log entries."""
    entries = []
    for event in export.events:
        raw_instance = event.get('instanceName') or cfg.default_instance_name
        if cfg.instance_whitelist and not cfg.instance_whitelist.search(raw_instance):
            continue
        instance = safe_instance_name(raw_instance) or cfg.default_instance_name
        if cfg.instance_prefix:
            instance = f"{cfg.instance_prefix}{instance}"

        timestamp = event.get('timestamp')
        if timestamp is None:
            continue

        if cfg.include_metadata:
            body = {
                'rawData': event.get('rawData', ''),
                'patternId': event.get('patternId'),
                'patternName': event.get('patternName'),
                'eventType': event.get('eventType'),
            }
        else:
            body = event.get('rawData', '')

        entries.append({
            'eventId': str(int(timestamp)),
            'tag': instance,
            'data': body,
        })
    return entries


#############
# Sink: InsightFinderSink
#############

class InsightFinderSink:
    def __init__(self, cfg: DestinationConfig):
        self.cfg = cfg
        self.session = _session_with_retries()
        self._checked_projects = set()
        self._project_lock = Lock()
        self._send_locks = {}

    def _send_lock(self, project: str) -> Lock:
        with self._project_lock:
            if project not in self._send_locks:
                self._send_locks[project] = Lock()
            return self._send_locks[project]

    def _agent_type(self) -> str:
        return 'LogFileReplay' if self.cfg.project_type == 'logreplay' else 'LogStreaming'

    def _insight_agent_type(self) -> str:
        return 'LogFile' if self.cfg.project_type == 'logreplay' else 'Custom'

    def ensure_project(self, project: str) -> bool:
        with self._project_lock:
            if project in self._checked_projects:
                return True

        if self._check_project(project):
            with self._project_lock:
                self._checked_projects.add(project)
            return True

        if not self.cfg.auto_create_projects:
            return False

        if not self._create_project(project):
            return False

        time.sleep(10)
        if self._check_project(project):
            with self._project_lock:
                self._checked_projects.add(project)
            return True

        logger.error("Project '%s' still not found after create.", project)
        return False

    def _post(self, path: str, data: dict):
        url = urllib.parse.urljoin(self.cfg.url, path)
        return self.session.post(
            url, data=data, verify=self.cfg.verify_ssl, proxies=self.cfg.proxies,
            timeout=self.cfg.timeout_seconds,
        )

    def _check_project(self, project: str) -> bool:
        try:
            resp = self._post(CHECK_PROJECT_PATH, {
                'operation': 'check',
                'userName': self.cfg.user_name,
                'licenseKey': self.cfg.license_key,
                'projectName': project,
            })
            result = resp.json()
            return bool(result.get('success') and result.get('isProjectExist'))
        except Exception as e:
            logger.error("Check project '%s' failed: %s", project, e)
            return False

    def _create_project(self, project: str) -> bool:
        try:
            resp = self._post(CHECK_PROJECT_PATH, {
                'operation': 'create',
                'userName': self.cfg.user_name,
                'licenseKey': self.cfg.license_key,
                'projectName': project,
                'systemName': self.cfg.system_name or project,
                'instanceType': 'PrivateCloud',
                'projectCloudType': 'PrivateCloud',
                'dataType': 'Log',
                'insightAgentType': self._insight_agent_type(),
                'samplingInterval': max(1, int(self.cfg.sampling_interval_seconds / 60)),
                'samplingIntervalInSeconds': self.cfg.sampling_interval_seconds,
            })
            result = resp.json()
            if not result.get('success'):
                logger.error("Create project '%s' failed: %s", project, result)
                return False
            logger.info("Created destination project '%s'.", project)
            return True
        except Exception as e:
            logger.error("Create project '%s' failed: %s", project, e)
            return False

    def _chunked(self, entries: list):
        """Yield lists of entries whose serialized size stays under chunk_size_kb."""
        limit_bytes = self.cfg.chunk_size_kb * 1024
        chunk, chunk_bytes = [], 0
        for entry in entries:
            entry_bytes = len(json.dumps(entry))
            if chunk and chunk_bytes + entry_bytes > limit_bytes:
                yield chunk
                chunk, chunk_bytes = [], 0
            chunk.append(entry)
            chunk_bytes += entry_bytes
        if chunk:
            yield chunk

    def send(self, project: str, entries: list, dry_run: bool = False) -> tuple:
        """Send entries to `project`, chunked by size. Returns (sent_count, request_count)."""
        if not entries:
            return 0, 0

        with self._send_lock(project):
            if not dry_run and not self.ensure_project(project):
                logger.error("Skipping send for project '%s': project not available.", project)
                return 0, 0

            sent, requests_made = 0, 0
            for chunk in self._chunked(entries):
                if dry_run:
                    sent += len(chunk)
                    requests_made += 1
                    continue

                payload = {
                    'userName': self.cfg.user_name,
                    'licenseKey': self.cfg.license_key,
                    'projectName': project,
                    'instanceName': HOSTNAME,
                    'agentType': self._agent_type(),
                    'metricData': json.dumps(chunk),
                }
                try:
                    resp = self._post(SEND_DATA_PATH, payload)
                    if resp.status_code != 200:
                        logger.error("Send to '%s' failed [%s]: %s", project,
                                    resp.status_code, resp.text[:500])
                        continue
                    result = resp.json()
                    if not result.get('success', True):
                        logger.error("Send to '%s' reported failure: %s", project, result)
                        continue
                    sent += len(chunk)
                    requests_made += 1
                except Exception as e:
                    logger.error("Send to '%s' failed: %s", project, e)

            return sent, requests_made


#############
# Orchestration
#############

@dataclass
class RunSummary:
    start_ms: int
    end_ms: int
    fetched: int = 0
    sent: int = 0
    skipped_projects: set = field(default_factory=set)
    failed_slices: list = field(default_factory=list)
    duration_s: float = 0.0

    def had_failures(self) -> bool:
        return bool(self.failed_slices)


def _process_slice(source: RawLogsClient, sink: InsightFinderSink, cfg: AgentConfig,
                   start_ms: int, end_ms: int, dry_run: bool) -> dict:
    """Fetch + transform + send one time slice. Returns per-project stats."""
    stats = {'fetched': 0, 'sent': 0, 'skipped': set()}
    exports = source.export(start_ms, end_ms)
    for export in exports:
        stats['fetched'] += len(export.events)
        if export.error:
            continue

        target = cfg.source.projects.get(export.project_name)
        if not target:
            logger.warning("Source project '%s' has no destination mapping; skipping "
                          "%d event(s).", export.project_name, len(export.events))
            stats['skipped'].add(export.project_name)
            continue

        entries = to_entries(export, cfg.transform)
        sent, _ = sink.send(target, entries, dry_run=dry_run)
        stats['sent'] += sent
    return stats


def run_once(cfg: AgentConfig, dry_run: bool = False) -> RunSummary:
    if cfg.collection.replay:
        start_ms, end_ms = cfg.collection.replay.start_ms, cfg.collection.replay.end_ms
        logger.info("Replaying range %d - %d", start_ms, end_ms)
    else:
        now_ms = int(time.time() * 1000)
        start_ms, end_ms = live_window(now_ms, cfg.collection.interval_seconds,
                                       cfg.collection.offset_seconds,
                                       align=cfg.collection.align_to_interval)
        logger.info("Live window %d - %d", start_ms, end_ms)

    summary = RunSummary(start_ms=start_ms, end_ms=end_ms)
    run_started = time.time()

    source = RawLogsClient(cfg.source)
    sink = InsightFinderSink(cfg.destination)

    slice_list = list(slices(start_ms, end_ms, cfg.collection.slice_seconds))
    if not slice_list:
        logger.info("Empty time range; nothing to do.")
        return summary

    with ThreadPoolExecutor(max_workers=cfg.collection.workers) as pool:
        future_to_slice = {
            pool.submit(_process_slice, source, sink, cfg, s, e, dry_run): (s, e)
            for s, e in slice_list
        }
        for future in as_completed(future_to_slice):
            slice_bounds = future_to_slice[future]
            try:
                stats = future.result()
                summary.fetched += stats['fetched']
                summary.sent += stats['sent']
                summary.skipped_projects |= stats['skipped']
            except SourceError as e:
                logger.error("Slice %s failed: %s", slice_bounds, e)
                summary.failed_slices.append(slice_bounds)
            except Exception as e:
                logger.error("Slice %s failed unexpectedly: %s", slice_bounds, e)
                summary.failed_slices.append(slice_bounds)

    summary.duration_s = round(time.time() - run_started, 2)
    return summary


#############
# Logging / CLI
#############

def configure_logging(cfg: LoggingConfig, verbose: bool, quiet: bool):
    level = logging.DEBUG if verbose else (logging.WARNING if quiet else
                                           getattr(logging, cfg.level, logging.INFO))
    logger.setLevel(level)
    logger.handlers.clear()

    fmt = logging.Formatter(
        '%(asctime)s [pid %(process)d] %(levelname)-8s %(name)s | %(message)s')

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    if cfg.file:
        os.makedirs(os.path.dirname(cfg.file) or '.', exist_ok=True)
        if cfg.rotate:
            file_handler = TimedRotatingFileHandler(
                cfg.file, when='midnight', backupCount=cfg.backup_count)
        else:
            file_handler = logging.FileHandler(cfg.file)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-c', '--config', default='./config.yaml',
                       help='Path to config.yaml (default: ./config.yaml)')
    parser.add_argument('--replay-start', help='Override collection.replay.start '
                       '(epoch millis or "YYYY-MM-DD HH:mm:ss")')
    parser.add_argument('--replay-end', help='Override collection.replay.end '
                       '(epoch millis or "YYYY-MM-DD HH:mm:ss")')
    parser.add_argument('--dry-run', action='store_true',
                       help='Fetch and transform but never send to the destination')
    parser.add_argument('-v', '--verbose', action='store_true', help='Debug logging')
    parser.add_argument('-q', '--quiet', action='store_true',
                       help='Only warning/error logging')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
    args = parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        # logging isn't configured yet on a config error, so print directly
        print(f"Config error: {e}", file=sys.stderr)
        return 1

    configure_logging(cfg.logging, args.verbose, args.quiet)

    if args.replay_start or args.replay_end:
        if not (args.replay_start and args.replay_end):
            logger.error("--replay-start and --replay-end must be given together")
            return 1
        # accepts epoch millis or "YYYY-MM-DD HH:mm:ss" (UTC)
        cfg.collection.replay = ReplayRange(
            start_ms=_parse_timestamp(args.replay_start, 'UTC'),
            end_ms=_parse_timestamp(args.replay_end, 'UTC'),
        )

    logger.info("Starting insightfinder_rawlogs run (dry_run=%s)", args.dry_run)
    try:
        summary = run_once(cfg, dry_run=args.dry_run)
    except Exception as e:
        logger.exception("Run failed: %s", e)
        return 1

    logger.info(
        "Run complete: window=[%d, %d) fetched=%d sent=%d skipped_projects=%s "
        "failed_slices=%s duration=%.2fs",
        summary.start_ms, summary.end_ms, summary.fetched, summary.sent,
        sorted(summary.skipped_projects), summary.failed_slices, summary.duration_s,
    )

    if summary.had_failures():
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

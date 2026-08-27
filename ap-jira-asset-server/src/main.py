import asyncio
import gzip
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.responses import JSONResponse, Response
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.gzip import GZipMiddleware

load_dotenv()

from .database import SessionLocal, get_session, init_db
from .jira_sync import run_sync, run_venue_sync
from .repository import DeviceRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = structlog.get_logger()

# ── auth ──────────────────────────────────────────────────────────────────────

_API_KEY = os.getenv("API_KEY")
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str = Security(_api_key_header)):
    if not _API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured on server.")
    if key != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")

# ── sync state ───────────────────────────────────────────────────────────────

_sync_state: Dict[str, Any] = {
    "running": False,
    "last_started": None,
    "last_finished": None,
    "last_result": None,
    "last_error": None,
}
_sync_lock = asyncio.Lock()


async def _do_sync():
    async with _sync_lock:
        if _sync_state["running"]:
            return
        _sync_state["running"] = True
        _sync_state["last_started"] = datetime.now(timezone.utc).isoformat()
        _sync_state["last_error"] = None

    try:
        result = await run_sync()
        _sync_state["last_result"] = result
        _sync_state["last_finished"] = datetime.now(timezone.utc).isoformat()
        logger.info("sync_complete", **result)
        _invalidate_bulk_cache("devices", "edges", "venues")
    except Exception as exc:
        _sync_state["last_error"] = str(exc)
        _sync_state["last_finished"] = datetime.now(timezone.utc).isoformat()
        logger.error("sync_failed", error=str(exc))
    finally:
        _sync_state["running"] = False


_venue_sync_state: Dict[str, Any] = {
    "running": False,
    "last_started": None,
    "last_finished": None,
    "last_result": None,
    "last_error": None,
}
_venue_sync_lock = asyncio.Lock()


async def _do_venue_sync():
    async with _venue_sync_lock:
        if _venue_sync_state["running"]:
            return
        _venue_sync_state["running"] = True
        _venue_sync_state["last_started"] = datetime.now(timezone.utc).isoformat()
        _venue_sync_state["last_error"] = None

    try:
        result = await run_venue_sync()
        _venue_sync_state["last_result"] = result
        _venue_sync_state["last_finished"] = datetime.now(timezone.utc).isoformat()
        logger.info("venue_sync_complete", **result)
        _invalidate_bulk_cache("venues")
    except Exception as exc:
        _venue_sync_state["last_error"] = str(exc)
        _venue_sync_state["last_finished"] = datetime.now(timezone.utc).isoformat()
        logger.error("venue_sync_failed", error=str(exc))
    finally:
        _venue_sync_state["running"] = False


# ── bulk export cache ────────────────────────────────────────────────────────
# Building these lists means walking every device/edge/venue row through the
# ORM and re-serializing it — tens of thousands of rows, 10+ seconds for
# devices. Multiple clients (jira-metadata, ap-dependency-upload) each fetch
# these once per run, so the blob is cached in-process until the sync that
# changed the underlying data invalidates it — no TTL, since /sync and
# /sync/support-engineers are the only two things that ever mutate this data.
#
# The cache stores the fully-encoded response bytes (both plain and gzipped),
# not the Python list — encoding ~32k nested dicts to JSON and gzip-compressing
# the result (tens of MB) is itself multiple seconds of work, and would
# otherwise repeat on every request even with the DB query skipped.

_CacheEntry = Tuple[bytes, bytes]  # (raw_json_bytes, gzip_compressed_bytes)


def _encode_cache_entry(data: Any) -> _CacheEntry:
    raw = json.dumps(data).encode("utf-8")
    return raw, gzip.compress(raw)


async def _build_devices_cache() -> _CacheEntry:
    async with SessionLocal() as session:
        repo = DeviceRepository(session)
        devices = await repo.list_all_devices()
        return _encode_cache_entry([_device_to_dict(d) for d in devices])


async def _build_edges_cache() -> _CacheEntry:
    async with SessionLocal() as session:
        repo = DeviceRepository(session)
        edges = await repo.list_all_edges()
        return _encode_cache_entry([
            {"source_id": e.source_id, "target_id": e.target_id, "relationship_type": e.relationship_type}
            for e in edges
        ])


async def _build_venues_cache() -> _CacheEntry:
    async with SessionLocal() as session:
        repo = DeviceRepository(session)
        venues = await repo.list_venue_abbreviations()
        return _encode_cache_entry([
            {
                "abbreviation": v.abbreviation,
                "venue_name": v.venue_name,
                "venue_key": v.venue_key,
                "venue_id": v.venue_id,
            }
            for v in venues
        ])


_BULK_CACHE_BUILDERS = {
    "devices": _build_devices_cache,
    "edges": _build_edges_cache,
    "venues": _build_venues_cache,
}
_bulk_cache: Dict[str, Optional[_CacheEntry]] = {key: None for key in _BULK_CACHE_BUILDERS}
_bulk_cache_locks: Dict[str, asyncio.Lock] = {key: asyncio.Lock() for key in _BULK_CACHE_BUILDERS}


async def _get_bulk_cached(key: str) -> _CacheEntry:
    if _bulk_cache[key] is not None:
        return _bulk_cache[key]
    async with _bulk_cache_locks[key]:
        if _bulk_cache[key] is None:  # still None after acquiring the lock — build it
            _bulk_cache[key] = await _BULK_CACHE_BUILDERS[key]()
        return _bulk_cache[key]


def _invalidate_bulk_cache(*keys: str) -> None:
    """Drop the given cache entries and immediately kick off a background
    rebuild, so the first real request after a sync doesn't pay for it."""
    for key in keys:
        _bulk_cache[key] = None
        asyncio.create_task(_get_bulk_cached(key))


async def _serve_bulk_cached(key: str, request: Request) -> Response:
    """Serve a cached bulk blob as-is — gzipped if the client accepts it,
    otherwise plain — with zero re-serialization or re-compression per request.
    """
    raw, compressed = await _get_bulk_cached(key)
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(content=compressed, media_type="application/json", headers={"Content-Encoding": "gzip"})
    return Response(content=raw, media_type="application/json")


# ── scheduler ────────────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler()

SYNC_CRON = os.getenv("SYNC_CRON", "0 2 * * *")  # 2am daily default


def _parse_cron(expr: str) -> Dict[str, str]:
    minute, hour, day, month, day_of_week = expr.split()
    return dict(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)


# ── lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    cron_kwargs = _parse_cron(SYNC_CRON)
    scheduler.add_job(_do_sync, "cron", **cron_kwargs, id="nightly_sync", replace_existing=True)
    scheduler.start()
    logger.info("scheduler_started", cron=SYNC_CRON)

    for key in _BULK_CACHE_BUILDERS:
        asyncio.create_task(_get_bulk_cached(key))
    logger.info("bulk_cache_prewarm_started")

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(title="Asset Registry", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ── helpers ───────────────────────────────────────────────────────────────────

def _device_to_dict(device) -> Dict[str, Any]:
    meta = device.meta or {}
    d = {
        "id": device.id,
        "object_key": device.object_key,
        "name": device.name,
        "device_name": device.device_name,
        "ip_address": device.ip_address,
        "mac_address": device.mac_address,
        "serial_number": device.serial_number,
        "zabbix_host_id": device.zabbix_host_id,
        "model_id": device.model_id,
        "updated_at": device.updated_at.isoformat() if device.updated_at else None,
        "meta": meta,
        "jira_device_key": device.object_key,
        "jira_location_key": meta.get("location_key"),
        "jira_subvenue_key": meta.get("subvenue_key"),
        "jira_venue_key": meta.get("venue_key"),
        "jira_model_key": (device.model.meta or {}).get("object_key") if device.model else None,
        "jira_device_name": device.name,
        "jira_location_name": meta.get("location"),
        "jira_subvenue_name": meta.get("subvenue"),
        "jira_venue_name": meta.get("venue"),
        "jira_model_name": device.model.name if device.model else None,
        "jira_modelclass_name": (
            f"{device.model.name} ({device.model.device_class})"
            if device.model and device.model.device_class
            else (device.model.name if device.model else None)
        ),
    }
    if device.model:
        d["model"] = {
            "id": device.model.id,
            "name": device.model.name,
            "manufacturer": device.model.manufacturer,
            "device_class": device.model.device_class,
            "classtype": device.model.classtype,
            "zabbix_model_monitoring_mode": device.model.zabbix_model_monitoring_mode,
            "zabbix_model_snmp_template_id": device.model.zabbix_model_snmp_template_id,
            "meta": device.model.meta or {},
        }
    return d


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/devices/export", dependencies=[Depends(require_api_key)])
async def export_devices(request: Request):
    """
    Bulk dump of every device, same shape as GET /devices/{identifier}.

    For clients resolving thousands of identifiers per run (e.g. jira-metadata,
    ap-dependency-upload) — fetch this once and build a local index instead of
    one request per identifier. Served from an in-memory cache invalidated by
    /sync; registered ahead of /devices/{identifier} so the literal path
    "export" isn't swallowed by that route's path parameter.
    """
    return await _serve_bulk_cached("devices", request)


@app.get("/devices/edges/export", dependencies=[Depends(require_api_key)])
async def export_device_edges(request: Request):
    """
    Bulk dump of every dependency edge, for local upstream/downstream traversal.
    Served from an in-memory cache invalidated by /sync.
    """
    return await _serve_bulk_cached("edges", request)


@app.get("/devices/{identifier}", dependencies=[Depends(require_api_key)])
async def get_device(identifier: str, session: AsyncSession = Depends(get_session)):
    """
    Look up a device by any identifier: Jira ID, name, IP, MAC, serial, object key.
    """
    repo = DeviceRepository(session)
    device = await repo.find_device(identifier)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device not found: {identifier}")
    return _device_to_dict(device)


@app.get("/devices/by-zabbix-host-id/{host_id}", dependencies=[Depends(require_api_key)])
async def get_device_by_zabbix_host_id(host_id: str, session: AsyncSession = Depends(get_session)):
    """
    Look up a device strictly by zabbix_host_id — no fallback to id/name/ip/etc.
    Use this instead of /devices/{identifier} when the identifier is a Zabbix host id,
    since that endpoint can match a different device's internal id/object_key first.
    """
    repo = DeviceRepository(session)
    device = await repo.find_by_zabbix_host_id(host_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device not found for zabbix_host_id: {host_id}")
    return _device_to_dict(device)


@app.get("/devices", dependencies=[Depends(require_api_key)])
async def search_devices(
    ip: Optional[str] = None,
    mac: Optional[str] = None,
    serial: Optional[str] = None,
    name: Optional[str] = None,
    device_name: Optional[str] = None,
    object_key: Optional[str] = None,
    zabbix_host_id: Optional[str] = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    """
    Search devices. All provided params are AND-combined.
    Fields: ip, mac, serial, name (partial), device_name (partial), object_key, zabbix_host_id.
    """
    if not any([ip, mac, serial, name, device_name, object_key, zabbix_host_id]):
        raise HTTPException(status_code=400, detail="Provide at least one search parameter.")
    repo = DeviceRepository(session)
    devices = await repo.search_devices(
        ip=ip, mac=mac, serial=serial, name=name,
        device_name=device_name, object_key=object_key,
        zabbix_host_id=zabbix_host_id, limit=limit,
    )
    return [_device_to_dict(d) for d in devices]


@app.get("/devices/{identifier}/upstream", dependencies=[Depends(require_api_key)])
async def get_upstream(
    identifier: str,
    max_depth: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """All nodes that feed into this device (ancestors / upstream path)."""
    repo = DeviceRepository(session)
    device = await repo.find_device(identifier)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device not found: {identifier}")
    return await repo.get_upstream(device.id, max_depth=max_depth)


@app.get("/devices/{identifier}/downstream", dependencies=[Depends(require_api_key)])
async def get_downstream(
    identifier: str,
    max_depth: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """All nodes that depend on this device (descendants / downstream path)."""
    repo = DeviceRepository(session)
    device = await repo.find_device(identifier)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device not found: {identifier}")
    return await repo.get_downstream(device.id, max_depth=max_depth)


@app.get("/devices/by-zabbix-host-id/{host_id}/upstream", dependencies=[Depends(require_api_key)])
async def get_upstream_by_zabbix_host_id(
    host_id: str,
    max_depth: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """All nodes that feed into this device (ancestors / upstream path), looked up strictly by zabbix_host_id."""
    repo = DeviceRepository(session)
    device = await repo.find_by_zabbix_host_id(host_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device not found for zabbix_host_id: {host_id}")
    return await repo.get_upstream(device.id, max_depth=max_depth)


@app.get("/devices/by-zabbix-host-id/{host_id}/downstream", dependencies=[Depends(require_api_key)])
async def get_downstream_by_zabbix_host_id(
    host_id: str,
    max_depth: int = 10,
    session: AsyncSession = Depends(get_session),
):
    """All nodes that depend on this device (descendants / downstream path), looked up strictly by zabbix_host_id."""
    repo = DeviceRepository(session)
    device = await repo.find_by_zabbix_host_id(host_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device not found for zabbix_host_id: {host_id}")
    return await repo.get_downstream(device.id, max_depth=max_depth)


@app.get("/devices/{identifier}/dependency-map", dependencies=[Depends(require_api_key)])
async def get_dependency_map(
    identifier: str,
    max_depth: int = 5,
    session: AsyncSession = Depends(get_session),
):
    """Full dependency map: the device itself + all upstream and downstream nodes."""
    repo = DeviceRepository(session)
    device = await repo.find_device(identifier)
    if not device:
        raise HTTPException(status_code=404, detail=f"Device not found: {identifier}")

    upstream, downstream = await asyncio.gather(
        repo.get_upstream(device.id, max_depth=max_depth),
        repo.get_downstream(device.id, max_depth=max_depth),
    )
    return {
        "device": _device_to_dict(device),
        "upstream": upstream,
        "downstream": downstream,
    }


@app.get("/support-engineers", dependencies=[Depends(require_api_key)])
async def get_support_engineers(session: AsyncSession = Depends(get_session)):
    """
    Venue → Support Engineer mapping, sourced from the Venue object's
    "Support Engineer" field in Jira Assets.
    """
    repo = DeviceRepository(session)
    venues = await repo.list_venues()
    return [
        {
            "venue_name": v.name,
            "venue_key": v.key,
            "support_engineer_name": v.support_engineer_name,
            "support_engineer_id": v.support_engineer_id,
            "support_engineer_key": v.support_engineer_key,
        }
        for v in venues
    ]


@app.get("/venues/abbreviations", dependencies=[Depends(require_api_key)])
async def list_venue_abbreviations(request: Request):
    """
    Abbreviation → Venue mapping, sourced from the Venue's own linked
    Abbreviation plus every one of its Subvenues' linked Abbreviation in Jira
    Assets (the common case — see jira_sync.build_venue_abbreviation_records).
    Served from an in-memory cache invalidated by /sync and
    /sync/support-engineers.
    """
    return await _serve_bulk_cached("venues", request)


@app.get("/venues/abbreviations/{abbreviation}", dependencies=[Depends(require_api_key)])
async def get_venue_by_abbreviation(abbreviation: str, session: AsyncSession = Depends(get_session)):
    """Look up the venue linked to a given abbreviation code."""
    repo = DeviceRepository(session)
    venue = await repo.find_venue_by_abbreviation(abbreviation)
    if not venue:
        raise HTTPException(status_code=404, detail=f"No venue found for abbreviation: {abbreviation}")
    return {
        "abbreviation": venue.abbreviation,
        "venue_name": venue.venue_name,
        "venue_key": venue.venue_key,
        "venue_id": venue.venue_id,
    }


@app.post("/sync", dependencies=[Depends(require_api_key)])
async def trigger_sync():
    """Trigger a full sync from Jira Assets. Returns immediately; sync runs in background."""
    if _sync_state["running"]:
        return JSONResponse(status_code=202, content={"status": "already_running"})
    asyncio.create_task(_do_sync())
    return JSONResponse(status_code=202, content={"status": "started"})


@app.get("/sync/status", dependencies=[Depends(require_api_key)])
async def sync_status(session: AsyncSession = Depends(get_session)):
    """Last sync info plus current DB counts."""
    repo = DeviceRepository(session)
    counts = await repo.counts()
    return {**_sync_state, "db": counts}


@app.post("/sync/support-engineers", dependencies=[Depends(require_api_key)])
async def trigger_venue_sync():
    """
    Trigger a Venue-only sync (name + Support Engineer). Much faster than the
    full /sync since it skips Model/Device/Subvenue/edges. Returns immediately;
    sync runs in background.
    """
    if _venue_sync_state["running"]:
        return JSONResponse(status_code=202, content={"status": "already_running"})
    asyncio.create_task(_do_venue_sync())
    return JSONResponse(status_code=202, content={"status": "started"})


@app.get("/sync/support-engineers/status", dependencies=[Depends(require_api_key)])
async def venue_sync_status():
    """Last venue-sync info."""
    return _venue_sync_state

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

load_dotenv()

from .database import SessionLocal, get_session, init_db
from .jira_sync import run_sync
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
    except Exception as exc:
        _sync_state["last_error"] = str(exc)
        _sync_state["last_finished"] = datetime.now(timezone.utc).isoformat()
        logger.error("sync_failed", error=str(exc))
    finally:
        _sync_state["running"] = False


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

    yield

    scheduler.shutdown(wait=False)


app = FastAPI(title="Asset Registry", lifespan=lifespan)


# ── helpers ───────────────────────────────────────────────────────────────────

def _device_to_dict(device) -> Dict[str, Any]:
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
        "meta": device.meta or {},
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

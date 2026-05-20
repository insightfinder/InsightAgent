from typing import Any, Dict, List, Optional
from sqlalchemy import select, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import selectinload

from .models import Device, DeviceEdge, DeviceModel


class DeviceRepository:
    def __init__(self, session):
        self.session = session

    # ── bulk writes ──────────────────────────────────────────────────────────

    async def upsert_models(self, records: List[Dict[str, Any]]) -> int:
        if not records:
            return 0
        stmt = insert(DeviceModel).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={c: stmt.excluded[c] for c in records[0] if c != "id"},
        )
        await self.session.execute(stmt)
        return len(records)

    async def upsert_devices(self, records: List[Dict[str, Any]]) -> int:
        if not records:
            return 0
        stmt = insert(Device).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={c: stmt.excluded[c] for c in records[0] if c != "id"},
        )
        await self.session.execute(stmt)
        return len(records)

    async def upsert_edges(self, records: List[Dict[str, Any]]) -> int:
        if not records:
            return 0
        stmt = insert(DeviceEdge).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={c: stmt.excluded[c] for c in records[0] if c != "id"},
        )
        await self.session.execute(stmt)
        return len(records)

    # ── single-device lookups ────────────────────────────────────────────────

    async def find_device(self, identifier: str) -> Optional[Device]:
        """Smart lookup by: Jira ID, object_key (IHS-xxxxx), name, device_name,
        ip_address, mac_address, serial_number, or zabbix_host_id."""
        stmt = (
            select(Device)
            .where(
                (Device.id == identifier)
                | (Device.object_key == identifier)
                | (Device.name == identifier)
                | (Device.device_name == identifier)
                | (Device.ip_address == identifier)
                | (Device.mac_address == identifier)
                | (Device.serial_number == identifier)
                | (Device.zabbix_host_id == identifier)
            )
            .options(selectinload(Device.model))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ── multi-field search ───────────────────────────────────────────────────

    async def search_devices(
        self,
        ip: Optional[str] = None,
        mac: Optional[str] = None,
        serial: Optional[str] = None,
        name: Optional[str] = None,
        device_name: Optional[str] = None,
        object_key: Optional[str] = None,
        zabbix_host_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Device]:
        stmt = select(Device).options(selectinload(Device.model))
        if ip:
            stmt = stmt.where(Device.ip_address == ip)
        if mac:
            stmt = stmt.where(Device.mac_address == mac)
        if serial:
            stmt = stmt.where(Device.serial_number == serial)
        if name:
            stmt = stmt.where(Device.name.ilike(f"%{name}%"))
        if device_name:
            stmt = stmt.where(Device.device_name.ilike(f"%{device_name}%"))
        if object_key:
            stmt = stmt.where(Device.object_key == object_key)
        if zabbix_host_id:
            stmt = stmt.where(Device.zabbix_host_id == zabbix_host_id)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ── graph traversal (recursive CTEs) ────────────────────────────────────

    async def get_upstream(self, device_id: str, max_depth: int = 10) -> List[Dict[str, Any]]:
        """
        All nodes that feed into device_id (ancestors in the dependency graph).
        Edge direction: source → target means source is upstream of target.
        """
        sql = text("""
            WITH RECURSIVE upstream(node_id, depth) AS (
                SELECT source_id, 1
                FROM device_edges
                WHERE target_id = :device_id
                UNION ALL
                SELECT e.source_id, u.depth + 1
                FROM device_edges e
                JOIN upstream u ON e.target_id = u.node_id
                WHERE u.depth < :max_depth
            )
            SELECT
                d.id, d.name, d.ip_address, d.mac_address, d.serial_number,
                d.object_key, d.meta, d.model_id,
                MIN(u.depth) AS depth,
                dm.name AS model_name, dm.manufacturer
            FROM devices d
            JOIN upstream u ON d.id = u.node_id
            LEFT JOIN device_models dm ON d.model_id = dm.id
            GROUP BY d.id
            ORDER BY MIN(u.depth)
        """)
        result = await self.session.execute(sql, {"device_id": device_id, "max_depth": max_depth})
        return [dict(row._mapping) for row in result]

    async def get_downstream(self, device_id: str, max_depth: int = 10) -> List[Dict[str, Any]]:
        """All nodes that depend on device_id (descendants in the dependency graph)."""
        sql = text("""
            WITH RECURSIVE downstream(node_id, depth) AS (
                SELECT target_id, 1
                FROM device_edges
                WHERE source_id = :device_id
                UNION ALL
                SELECT e.target_id, dw.depth + 1
                FROM device_edges e
                JOIN downstream dw ON e.source_id = dw.node_id
                WHERE dw.depth < :max_depth
            )
            SELECT
                d.id, d.name, d.ip_address, d.mac_address, d.serial_number,
                d.object_key, d.meta, d.model_id,
                MIN(dw.depth) AS depth,
                dm.name AS model_name, dm.manufacturer
            FROM devices d
            JOIN downstream dw ON d.id = dw.node_id
            LEFT JOIN device_models dm ON d.model_id = dm.id
            GROUP BY d.id
            ORDER BY MIN(dw.depth)
        """)
        result = await self.session.execute(sql, {"device_id": device_id, "max_depth": max_depth})
        return [dict(row._mapping) for row in result]

    # ── counts ───────────────────────────────────────────────────────────────

    async def counts(self) -> Dict[str, int]:
        r = await self.session.execute(text(
            "SELECT "
            "(SELECT COUNT(*) FROM devices) AS devices,"
            "(SELECT COUNT(*) FROM device_models) AS models,"
            "(SELECT COUNT(*) FROM device_edges) AS edges"
        ))
        row = r.mappings().one()
        return dict(row)

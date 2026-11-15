"""node availability diagnostics: explicit dependencies and invocation data."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class NodeAvailabilityDiagnosticsPorts:
    zone_nodes_diag_sql: Callable[..., Any]
    classify_zone_nodes: Callable[..., Any]
    node_persistent_dead_sec: Callable[..., Any]


class NodeAvailabilityDiagnostics:
    def __init__(self, ports: NodeAvailabilityDiagnosticsPorts) -> None:
        self._ports = ports

    def node_persistent_dead_sec(self) -> int:
        return max(60, int(os.getenv("AE3_NODE_PERSISTENT_DEAD_SEC", "600")))

    def classify_zone_nodes(self, *, zone_id: int, diag_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Классифицирует ноды зоны по transient/persistent offline (как snapshot read-model)."""
        persistent_threshold = self._ports.node_persistent_dead_sec()
        zone_nodes: list[dict[str, Any]] = []
        persistently_offline_uids: list[str] = []
        transiently_offline_uids: list[str] = []

        for row in diag_rows:
            uid = str(row.get("node_uid") or "").strip()
            if not uid:
                continue
            node_type = str(row.get("node_type") or "").strip().lower() or None
            status = str(row.get("status") or "").strip().lower() or None
            try:
                last_seen_age_sec = (
                    int(row.get("last_seen_age_sec")) if row.get("last_seen_age_sec") is not None else None
                )
            except (TypeError, ValueError):
                last_seen_age_sec = None
            try:
                active_actuator_count = int(row.get("active_actuator_count") or 0)
            except (TypeError, ValueError):
                active_actuator_count = 0

            zone_nodes.append(
                {
                    "uid": uid,
                    "type": node_type,
                    "status": status,
                    "last_seen_age_sec": last_seen_age_sec,
                    "active_actuator_count": active_actuator_count,
                }
            )

            if status == "online":
                continue
            if last_seen_age_sec is not None and last_seen_age_sec >= persistent_threshold:
                persistently_offline_uids.append(uid)
            else:
                transiently_offline_uids.append(uid)

        return {
            "zone_id": int(zone_id),
            "zone_nodes": zone_nodes,
            "persistently_offline_uids": persistently_offline_uids,
            "transiently_offline_uids": transiently_offline_uids,
            "persistent_dead_threshold_sec": persistent_threshold,
        }

    async def fetch_zone_nodes_diagnostics(self, *, zone_id: int, conn: Any | None) -> dict[str, Any]:
        if conn is not None:
            rows = await conn.fetch(self._ports.zone_nodes_diag_sql(), zone_id)
            return self._ports.classify_zone_nodes(zone_id=zone_id, diag_rows=rows)

        from common.db import get_pool

        pool = await get_pool()
        async with pool.acquire() as acquired:
            rows = await acquired.fetch(self._ports.zone_nodes_diag_sql(), zone_id)
        return self._ports.classify_zone_nodes(zone_id=zone_id, diag_rows=rows)

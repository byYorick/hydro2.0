"""GetZoneAutomationStateUseCase queries: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Optional

from ae3lite.application.level_monitor import (
    load_zone_level_monitor_config,
    summarize_zone_telemetry_rows,
)
from ae3lite.application.services.zone_state_shared import _TIMELINE_NODE_EVENT_TYPES, logger
from ae3lite.domain.services.zone_node_availability import ZONE_NODES_DIAG_SQL


@dataclass(frozen=True)
class ZoneStateQueriesPorts:
    build_node_runtime_timeline_event: Callable[..., Any]
    fetch_fn: Callable[..., Any]
    task_repository: Callable[[], Any]


class ZoneStateQueries:
    def __init__(self, ports: ZoneStateQueriesPorts) -> None:
        self._ports = ports

    async def fetch_zone_telemetry(self, *, zone_id: int) -> tuple[dict[str, Any], bool]:
        """Читает ``telemetry_last`` для pH, EC и датчиков уровня этой зоны.

        Возвращает ``(levels_dict, ok)``, где ``ok`` равно ``False``, если SQL-чтение не удалось.
        """
        try:
            level_cfg = await load_zone_level_monitor_config(zone_id=zone_id, fetch_fn=self._ports.fetch_fn)
            rows = await self._ports.fetch_fn(
                """
                SELECT s.label, s.type, tl.last_value, tl.last_ts, tl.last_quality
                FROM sensors s
                JOIN telemetry_last tl ON tl.sensor_id = s.id
                WHERE s.zone_id = $1
                  AND s.is_active = TRUE
                  AND s.type IN ('PH', 'EC', 'WATER_LEVEL', 'WATER_LEVEL_SWITCH')
                ORDER BY s.type, s.label
                """,
                zone_id,
            )
        except Exception:
            logger.warning(
                "AE3 automation state: telemetry fetch failed for zone_id=%s",
                zone_id,
                exc_info=True,
            )
            return {}, False

        return summarize_zone_telemetry_rows(rows, config=level_cfg), True

    async def fetch_zone_nodes_diag(self, *, zone_id: int) -> list[dict[str, Any]]:
        if self._ports.fetch_fn is None:
            return []
        try:
            rows = await self._ports.fetch_fn(ZONE_NODES_DIAG_SQL, zone_id)
        except Exception:
            logger.warning(
                "AE3 automation state: node diag fetch failed for zone_id=%s",
                zone_id,
                exc_info=True,
            )
            return []
        return [dict(row) if isinstance(row, Mapping) else row for row in rows]

    async def fetch_recent_node_runtime_events(
        self, *, zone_id: int, since_ts: datetime | None
    ) -> list[dict[str, Any]]:
        if self._ports.fetch_fn is None:
            return []
        try:
            rows = await self._ports.fetch_fn(
                """
                SELECT type, created_at, COALESCE(details, payload_json) AS payload
                FROM zone_events
                WHERE zone_id = $1
                  AND type = ANY($2::text[])
                  AND ($3::timestamp IS NULL OR created_at >= $3)
                ORDER BY created_at ASC, id ASC
                LIMIT 32
                """,
                zone_id,
                list(_TIMELINE_NODE_EVENT_TYPES),
                since_ts,
            )
        except Exception:
            logger.warning(
                "AE3 automation state: node runtime events fetch failed for zone_id=%s",
                zone_id,
                exc_info=True,
            )
            return []

        events: list[dict[str, Any]] = []
        for row in rows:
            event = self._ports.build_node_runtime_timeline_event(row)
            if event is not None:
                events.append(event)
        return events

    async def latest_irrigation_task(self, *, zone_id: int, task: Optional[Any]) -> Any | None:
        if task is not None and str(getattr(task, "task_type", "") or "").strip().lower() == "irrigation_start":
            return task
        getter = getattr(self._ports.task_repository(), "get_last_irrigation_for_zone", None)
        if getter is None:
            return None
        try:
            return await getter(zone_id=zone_id)
        except Exception:
            logger.warning(
                "AE3 automation state: last irrigation task read failed for zone_id=%s",
                zone_id,
                exc_info=True,
            )
            return None

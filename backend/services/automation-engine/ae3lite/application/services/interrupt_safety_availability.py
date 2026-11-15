"""interrupt safety availability: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence


@dataclass(frozen=True)
class InterruptSafetyAvailabilityPorts:
    node_is_fresh_online: Callable[..., Any]
    fetch: Callable[..., Any]


class InterruptSafetyAvailability:
    def __init__(self, ports: InterruptSafetyAvailabilityPorts) -> None:
        self._ports = ports

    async def zone_has_active_ae_task(self, *, zone_id: int) -> bool:
        rows = await self._ports.fetch(
            """
            SELECT 1
            FROM ae_tasks
            WHERE zone_id = $1
              AND status = ANY(ARRAY['pending','claimed','running','waiting_command']::text[])
            LIMIT 1
            """,
            zone_id,
        )
        return bool(rows)

    async def required_nodes_online(
        self, *, zone_id: int, required_types: Sequence[str], max_age_sec: int
    ) -> tuple[bool, tuple[str, ...]]:
        """Все assigned-ноды каждого required type должны быть fresh-online.

        Не берём «первую попавшуюся» ноду типа: если у зоны два irrig, оба должны
        быть online со свежим last_seen/last_heartbeat. Отсутствие нод типа —
        missing (fail-closed).
        """
        rows = await self._ports.fetch(
            """
            SELECT LOWER(COALESCE(type, '')) AS node_type,
                   LOWER(TRIM(COALESCE(status, ''))) AS status,
                   EXTRACT(
                       EPOCH FROM (
                           NOW() - COALESCE(
                               last_seen_at,
                               last_heartbeat_at,
                               updated_at
                           )
                       )
                   )::BIGINT AS last_seen_age_sec
            FROM nodes
            WHERE zone_id = $1
            """,
            zone_id,
        )
        by_type: dict[str, list[tuple[str, int | None]]] = {}
        for row in rows:
            node_type = str(row.get("node_type") or "").strip().lower()
            if not node_type:
                continue
            status = str(row.get("status") or "").strip().lower()
            age_raw = row.get("last_seen_age_sec")
            try:
                age = int(age_raw) if age_raw is not None else None
            except (TypeError, ValueError):
                age = None
            by_type.setdefault(node_type, []).append((status, age))

        freshness_limit = max(1, int(max_age_sec))
        missing: list[str] = []
        for node_type in required_types:
            nodes = by_type.get(str(node_type).strip().lower()) or []
            if not nodes:
                missing.append(str(node_type))
                continue
            if not all(
                self._ports.node_is_fresh_online(
                    status=status,
                    last_seen_age_sec=age,
                    max_age_sec=freshness_limit,
                )
                for status, age in nodes
            ):
                missing.append(str(node_type))
        return (not missing, tuple(missing))

    async def read_workflow_phase(self, *, zone_id: int) -> str | None:
        rows = await self._ports.fetch(
            """
            SELECT workflow_phase
            FROM zone_workflow_state
            WHERE zone_id = $1
            LIMIT 1
            """,
            zone_id,
        )
        if not rows:
            return None
        return str(rows[0].get("workflow_phase") or "").strip().lower() or None

"""climate tick state queries: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class ClimateTickStateQueriesPorts:
    execute: Callable[..., Any]
    fetch: Callable[..., Any]


class ClimateTickStateQueries:
    def __init__(self, ports: ClimateTickStateQueriesPorts) -> None:
        self._ports = ports

    async def ensure_state_row(self, greenhouse_id: int) -> None:
        await self._ports.execute(
            """
            INSERT INTO greenhouse_automation_state (greenhouse_id, climate_enabled, control_mode, created_at, updated_at)
            VALUES ($1, false, 'auto', now(), now())
            ON CONFLICT (greenhouse_id) DO NOTHING
            """,
            greenhouse_id,
        )

    async def load_manual_override(self, greenhouse_id: int) -> dict[str, Any] | None:
        rows = await self._ports.fetch(
            """
            SELECT id, left_position_pct, right_position_pct, ttl_sec, return_mode, reason, expires_at
            FROM greenhouse_manual_overrides
            WHERE greenhouse_id = $1 AND expires_at > now()
            ORDER BY id DESC
            LIMIT 1
            """,
            greenhouse_id,
        )
        if not rows:
            return None
        r = dict(rows[0])
        return {
            "id": int(r.get("id") or 0),
            "left_position_pct": int(r.get("left_position_pct") or 0),
            "right_position_pct": int(r.get("right_position_pct") or 0),
            "ttl_sec": int(r.get("ttl_sec") or 0),
            "return_mode": str(r.get("return_mode") or "auto"),
            "reason": r.get("reason"),
            "expires_at": r.get("expires_at"),
        }

    async def expired_manual_override_return_mode(self, greenhouse_id: int, state: Mapping[str, Any]) -> str | None:
        override_id = state.get("active_manual_override_id")
        if override_id is None:
            return None
        rows = await self._ports.fetch(
            """
            SELECT return_mode
            FROM greenhouse_manual_overrides
            WHERE id = $1 AND greenhouse_id = $2 AND expires_at <= now()
            LIMIT 1
            """,
            int(override_id),
            greenhouse_id,
        )
        if not rows:
            return None
        return_mode = str(rows[0].get("return_mode") or "auto").strip().lower()
        if return_mode not in {"auto", "semi", "manual"}:
            return_mode = "auto"
        return return_mode

    async def load_vents(self, greenhouse_id: int) -> dict[str, dict[str, Any]]:
        rows = await self._ports.fetch(
            """
            SELECT nc.channel AS channel,
                   n.uid AS node_uid,
                   n.zone_id AS zone_id,
                   z.uid AS zone_uid,
                   g.uid AS greenhouse_uid
            FROM channel_bindings cb
            JOIN infrastructure_instances ii ON ii.id = cb.infrastructure_instance_id
            JOIN node_channels nc ON nc.id = cb.node_channel_id
            JOIN nodes n ON n.id = nc.node_id
            JOIN zones z ON z.id = n.zone_id
            JOIN greenhouses g ON g.id = ii.owner_id
            WHERE ii.owner_type = 'greenhouse'
              AND ii.owner_id = $1
              AND z.greenhouse_id = ii.owner_id
              AND cb.direction = 'actuator'
              AND cb.role = 'vent_actuator'
              AND nc.is_active IS TRUE
              AND nc.channel IN ('roof_vent_left', 'roof_vent_right')
            """,
            greenhouse_id,
        )
        out: dict[str, dict[str, Any]] = {}
        for row in rows or []:
            ch = str(row.get("channel") or "")
            if ch:
                out[ch] = {
                    "node_uid": str(row.get("node_uid") or ""),
                    "zone_id": int(row.get("zone_id") or 0),
                    "greenhouse_uid": str(row.get("greenhouse_uid") or ""),
                }
        return out

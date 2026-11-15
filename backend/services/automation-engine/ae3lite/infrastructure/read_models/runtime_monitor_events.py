"""PgZoneRuntimeMonitor events: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class RuntimeMonitorEventsPorts:
    age_sec: Callable[..., Any]
    normalize_timestamp: Callable[..., Any]
    resolve_zone_event_payload: Callable[..., Any]
    global_get_pool: Callable[..., Any]


class RuntimeMonitorEvents:
    def __init__(self, ports: RuntimeMonitorEventsPorts) -> None:
        self._ports = ports

    async def read_latest_irr_state(
        self,
        *,
        zone_id: int,
        max_age_sec: int,
        expected_cmd_id: str | None = None,
    ) -> Mapping[str, Any]:
        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id,
                    payload_json,
                    details,
                    created_at,
                    COALESCE(details->>'cmd_id', payload_json->>'cmd_id') AS snapshot_cmd_id
                FROM zone_events
                WHERE zone_id = $1
                  AND type = 'IRR_STATE_SNAPSHOT'
                  AND ($2::text IS NULL OR COALESCE(details->>'cmd_id', payload_json->>'cmd_id') = $2)
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                zone_id,
                expected_cmd_id,
            )
        if row is None:
            return {
                "has_snapshot": False,
                "is_stale": False,
                "snapshot": None,
                "cmd_id": expected_cmd_id,
            }

        payload = self._ports.resolve_zone_event_payload(row)
        snapshot = payload.get("snapshot") if isinstance(payload.get("snapshot"), Mapping) else None
        age_sec = self._ports.age_sec(row.get("created_at"))
        is_stale = bool((age_sec or 0.0) > max(0, int(max_age_sec)))
        return {
            "event_id": row.get("id"),
            "has_snapshot": isinstance(snapshot, Mapping),
            "is_stale": is_stale,
            "snapshot": dict(snapshot) if isinstance(snapshot, Mapping) else None,
            "sample_age_sec": age_sec,
            "created_at": row.get("created_at"),
            "cmd_id": str(row.get("snapshot_cmd_id") or "").strip() or None,
        }

    async def read_node_liveness(self, *, node_uid: str) -> Mapping[str, Any]:
        """Возвращает актуальность heartbeat/LWT узла для pre-probe backoff.

        Используется handler'ами чтобы пропустить `_probe_irr_state` когда нода
        в reboot/disconnect — probe всё равно упадёт по timeout, а мы сэкономим
        HL roundtrip и storage_state публикацию.
        """
        normalized_uid = str(node_uid or "").strip()
        if not normalized_uid:
            return {"found": False, "status": None, "heartbeat_age_sec": None}

        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT status, last_heartbeat_at, last_seen_at
                FROM nodes
                WHERE uid = $1
                """,
                normalized_uid,
            )
        if row is None:
            return {"found": False, "status": None, "heartbeat_age_sec": None}

        status = str(row.get("status") or "").strip().lower() or None
        heartbeat_age_sec = self._ports.age_sec(row.get("last_heartbeat_at"))
        last_seen_age_sec = self._ports.age_sec(row.get("last_seen_at"))
        return {
            "found": True,
            "status": status,
            "heartbeat_age_sec": heartbeat_age_sec,
            "last_seen_age_sec": last_seen_age_sec,
        }

    async def read_latest_zone_event(
        self,
        *,
        zone_id: int,
        event_types: Sequence[str],
        max_age_sec: int,
        since_ts: datetime | None = None,
        channel: str | None = None,
    ) -> Mapping[str, Any] | None:
        normalized_event_types = [str(item or "").strip().upper() for item in event_types if str(item or "").strip()]
        if not normalized_event_types:
            return None
        normalized_since_ts = self._ports.normalize_timestamp(since_ts)
        normalized_channel = str(channel or "").strip().lower() or None

        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, type, payload_json, details, created_at
                FROM zone_events
                WHERE zone_id = $1
                  AND type = ANY($2::text[])
                  AND created_at >= NOW() - ($3::int * INTERVAL '1 second')
                  AND ($4::timestamp IS NULL OR created_at >= $4)
                  AND (
                    $5::text IS NULL
                    OR LOWER(TRIM(COALESCE(details->>'channel', payload_json->>'channel', ''))) = $5
                  )
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                zone_id,
                normalized_event_types,
                max(1, int(max_age_sec)),
                normalized_since_ts,
                normalized_channel,
            )
        if row is None:
            return None

        payload = self._ports.resolve_zone_event_payload(row)
        age_sec = self._ports.age_sec(row.get("created_at"))
        return {
            "event_id": row.get("id"),
            "event_type": str(row.get("type") or "").strip().upper(),
            "payload": dict(payload) if isinstance(payload, Mapping) else {},
            "created_at": row.get("created_at"),
            "sample_age_sec": age_sec,
            "is_stale": bool((age_sec or 0.0) > max(0, int(max_age_sec))),
        }

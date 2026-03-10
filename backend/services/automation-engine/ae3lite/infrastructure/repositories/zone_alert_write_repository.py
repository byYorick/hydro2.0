"""Write access to alerts / zone_events for AE3 runtime business failures."""

from __future__ import annotations

from datetime import timezone
from datetime import datetime
from typing import Any, Mapping

from common.db import get_pool


class PgZoneAlertWriteRepository:
    """Minimal ACTIVE alert upsert compatible with Laravel alert lifecycle."""

    def _normalize_timestamp(self, value: datetime) -> datetime:
        normalized = value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo is not None else value
        return normalized.replace(microsecond=0)

    def _build_event_payload(
        self,
        *,
        alert_id: int,
        zone_id: int,
        code: str,
        source: str,
        alert_type: str,
        status: str,
        category: str,
        severity: str,
        error_count: int,
        details: Mapping[str, Any],
        action: str,
        now: datetime,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "alert_id": alert_id,
            "action": action,
            "code": code,
            "type": alert_type,
            "source": source,
            "status": status,
            "severity": severity,
            "category": category,
            "zone_id": zone_id,
            "node_uid": details.get("node_uid"),
            "hardware_id": details.get("hardware_id"),
            "error_count": error_count,
            "message": details.get("message") or details.get("description"),
            "recommendation": details.get("recommendation"),
            "details": dict(details),
        }
        if extra:
            payload.update(dict(extra))
        payload["server_ts"] = int(now.timestamp() * 1000)
        return payload

    async def create_or_update_active(
        self,
        *,
        zone_id: int,
        code: str,
        details: Mapping[str, Any],
        now: datetime,
        source: str = "biz",
        alert_type: str = "automation_engine",
        category: str = "agronomy",
        severity: str = "error",
    ) -> int:
        pool = await get_pool()
        normalized_now = self._normalize_timestamp(now)
        normalized_code = str(code or "").strip()
        normalized_details = dict(details)
        now_iso = normalized_now.isoformat()

        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT id, details, error_count
                    FROM alerts
                    WHERE zone_id = $1
                      AND code = $2
                      AND status = 'ACTIVE'
                    ORDER BY id DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    zone_id,
                    normalized_code,
                )
                if row is None:
                    created_details = dict(normalized_details)
                    created_details["count"] = 1
                    created_details["first_seen_at"] = now_iso
                    created_details["last_seen_at"] = now_iso
                    alert_id = await conn.fetchval(
                        """
                        INSERT INTO alerts (
                            zone_id,
                            source,
                            code,
                            type,
                            details,
                            status,
                            category,
                            severity,
                            error_count,
                            first_seen_at,
                            last_seen_at,
                            created_at
                        )
                        VALUES (
                            $1, $2, $3, $4, $5::jsonb, 'ACTIVE', $6, $7, 1, $8, $8, $8
                        )
                        RETURNING id
                        """,
                        zone_id,
                        source,
                        normalized_code,
                        alert_type,
                        created_details,
                        category,
                        severity,
                        normalized_now,
                    )
                    created_payload = self._build_event_payload(
                        alert_id=int(alert_id),
                        zone_id=zone_id,
                        code=normalized_code,
                        source=source,
                        alert_type=alert_type,
                        status="ACTIVE",
                        category=category,
                        severity=severity,
                        error_count=1,
                        details=created_details,
                        action="created",
                        now=normalized_now,
                        extra={"created_at": now_iso},
                    )
                    await conn.execute(
                        """
                        INSERT INTO zone_events (
                            zone_id,
                            type,
                            entity_type,
                            entity_id,
                            server_ts,
                            payload_json,
                            created_at
                        )
                        VALUES ($1, 'ALERT_CREATED', 'alert', $2, $3, $4::jsonb, $5)
                        """,
                        zone_id,
                        str(alert_id),
                        created_payload["server_ts"],
                        created_payload,
                        normalized_now,
                    )
                    return int(alert_id)

                merged_details = dict(row["details"] or {})
                merged_details.update(normalized_details)
                error_count = int(row["error_count"] or 1) + 1
                merged_details["count"] = error_count
                merged_details["last_seen_at"] = now_iso
                await conn.execute(
                    """
                    UPDATE alerts
                    SET details = $2::jsonb,
                        source = $3,
                        type = $4,
                        category = $5,
                        severity = $6,
                        error_count = $7,
                        last_seen_at = $8
                    WHERE id = $1
                    """,
                    int(row["id"]),
                    merged_details,
                    source,
                    alert_type,
                    category,
                    severity,
                    error_count,
                    normalized_now,
                )
                updated_payload = self._build_event_payload(
                    alert_id=int(row["id"]),
                    zone_id=zone_id,
                    code=normalized_code,
                    source=source,
                    alert_type=alert_type,
                    status="ACTIVE",
                    category=category,
                    severity=severity,
                    error_count=error_count,
                    details=merged_details,
                    action="updated",
                    now=normalized_now,
                    extra={
                        "updated_at": now_iso,
                        "error_count": error_count,
                    },
                )
                await conn.execute(
                    """
                    INSERT INTO zone_events (
                        zone_id,
                        type,
                        entity_type,
                        entity_id,
                        server_ts,
                        payload_json,
                        created_at
                    )
                    VALUES ($1, 'ALERT_UPDATED', 'alert', $2, $3, $4::jsonb, $5)
                    """,
                    zone_id,
                    str(row["id"]),
                    updated_payload["server_ts"],
                    updated_payload,
                    normalized_now,
                )
                return int(row["id"])

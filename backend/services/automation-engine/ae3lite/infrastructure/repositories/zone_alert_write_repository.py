"""AE3 business alert adapter over canonical Laravel ingest path."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from common.biz_alerts import send_biz_alert


class PgZoneAlertWriteRepository:
    """Compatibility adapter kept only for AE3 handler interface stability."""

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
        payload = dict(details)
        payload.setdefault("category", category)
        payload.setdefault("severity", severity)
        payload.setdefault("source", source)
        payload.setdefault("observed_at", now.isoformat())
        await send_biz_alert(
            code=str(code or "").strip(),
            message=str(payload.get("message") or payload.get("description") or code or "business alert"),
            zone_id=zone_id,
            alert_type=alert_type,
            severity=severity,
            details=payload,
        )
        return 0

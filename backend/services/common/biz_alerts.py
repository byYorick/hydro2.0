"""
Helper functions for canonical business alert publishing.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional, Sequence

from .alert_publisher import AlertPublisher

logger = logging.getLogger(__name__)
_publisher = AlertPublisher(default_source="biz")
_DEFAULT_SCOPE_KEYS = (
    "task_id",
    "stage",
    "workflow_phase",
    "pid_type",
    "error_code",
    "corr_step",
    "pump_channel",
    "node_uid",
    "hardware_id",
    "channel",
    "component",
)


def _build_dedupe_key(
    *,
    code: str,
    zone_id: Optional[int],
    details: Optional[Mapping[str, Any]] = None,
    scope_parts: Sequence[Any] | None = None,
) -> str:
    resolved_parts = [f"code_scope:{code}"]
    for key in _DEFAULT_SCOPE_KEYS:
        value = details.get(key) if isinstance(details, Mapping) else None
        if value is None:
            continue
        normalized = str(value).strip()
        if normalized == "":
            continue
        resolved_parts.append(f"{key}:{normalized}")

    if scope_parts:
        for item in scope_parts:
            normalized = str(item).strip()
            if normalized:
                resolved_parts.append(normalized)

    return _publisher.build_dedupe_key(code=code, zone_id=zone_id, parts=resolved_parts)


async def send_biz_alert(
    *,
    code: str,
    message: str,
    zone_id: Optional[int] = None,
    alert_type: str = "Business Alert",
    severity: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    dedupe_key: Optional[str] = None,
    scope_parts: Sequence[Any] | None = None,
    node_uid: Optional[str] = None,
    hardware_id: Optional[str] = None,
    ts_device: Optional[str] = None,
) -> bool:
    payload_details = dict(details) if isinstance(details, dict) else {}
    payload_details.setdefault("message", message)
    resolved_dedupe_key = str(dedupe_key or payload_details.get("dedupe_key") or "").strip()
    if resolved_dedupe_key == "":
        resolved_dedupe_key = _build_dedupe_key(
            code=code,
            zone_id=zone_id,
            details=payload_details,
            scope_parts=scope_parts,
        )
    payload_details["dedupe_key"] = resolved_dedupe_key

    try:
        return await _publisher.raise_active(
            zone_id=zone_id,
            source="biz",
            code=code,
            alert_type=alert_type,
            details=payload_details,
            dedupe_key=resolved_dedupe_key,
            scoped=True,
            node_uid=node_uid or payload_details.get("node_uid"),
            hardware_id=hardware_id or payload_details.get("hardware_id"),
            severity=severity,
            ts_device=ts_device,
        )
    except Exception as exc:
        logger.error(
            "[BIZ_ALERT] Failed to publish business alert: %s",
            exc,
            exc_info=True,
            extra={"code": code, "zone_id": zone_id},
        )
        return False


class BizAlertPublisher:
    """Small object adapter for callers that need dependency injection."""

    async def raise_active(
        self,
        *,
        zone_id: int,
        code: str,
        details: Mapping[str, Any],
        now: Any | None = None,
        alert_type: str = "automation_engine",
        category: str = "operations",
        severity: str = "error",
    ) -> bool:
        payload = dict(details)
        payload.setdefault("category", category)
        payload.setdefault("severity", severity)
        if now is not None:
            try:
                payload.setdefault("observed_at", now.isoformat())
            except Exception:
                payload.setdefault("observed_at", str(now))
        return await send_biz_alert(
            code=code,
            message=str(payload.get("message") or payload.get("description") or code),
            zone_id=zone_id,
            alert_type=alert_type,
            severity=severity,
            details=payload,
        )

"""Helpers for throttled correction-skip events in zone automation."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List


CreateZoneEventFn = Callable[[int, str, Dict[str, Any]], Awaitable[Any]]
UtcNowFn = Callable[[], datetime]


def normalize_flag_signature_values(raw_values: Any) -> List[str]:
    if not isinstance(raw_values, list):
        return []
    return sorted(str(item).strip().lower() for item in raw_values if str(item).strip())


def build_correction_skip_signature(
    *,
    event_type: str,
    event_payload: Dict[str, Any],
    reason_code: str,
) -> str:
    payload = event_payload if isinstance(event_payload, dict) else {}
    missing_flags = normalize_flag_signature_values(payload.get("missing_flags"))
    stale_flags = normalize_flag_signature_values(payload.get("stale_flags"))
    return "|".join(
        [
            str(event_type or "").strip().upper(),
            str(reason_code or "").strip().lower(),
            ",".join(missing_flags),
            ",".join(stale_flags),
        ]
    )


async def emit_correction_skip_event_throttled(
    *,
    zone_id: int,
    event_type: str,
    event_payload: Dict[str, Any],
    reason_code: str,
    zone_state: Dict[str, Any],
    correction_skip_event_throttle_seconds: int,
    utcnow_fn: UtcNowFn,
    create_zone_event_fn: CreateZoneEventFn,
    logger: logging.Logger,
) -> None:
    now = utcnow_fn()
    last_reported = zone_state.get("last_correction_skip_event_at")
    signature = build_correction_skip_signature(
        event_type=event_type,
        event_payload=event_payload,
        reason_code=reason_code,
    )
    last_signature = str(zone_state.get("last_correction_skip_signature") or "")
    same_signature = last_signature == signature
    within_throttle = (
        isinstance(last_reported, datetime)
        and (now - last_reported).total_seconds() < correction_skip_event_throttle_seconds
    )

    if same_signature and within_throttle:
        zone_state["suppressed_correction_skip_events"] = int(zone_state.get("suppressed_correction_skip_events") or 0) + 1
        logger.debug(
            "Zone %s: correction skip event suppressed by throttle",
            zone_id,
            extra={
                "zone_id": zone_id,
                "event_type": event_type,
                "reason_code": reason_code,
                "signature": signature,
                "suppressed_correction_skip_events": zone_state["suppressed_correction_skip_events"],
                "throttle_seconds": correction_skip_event_throttle_seconds,
            },
        )
        return

    suppressed_count = int(zone_state.get("suppressed_correction_skip_events") or 0)
    payload = dict(event_payload)
    if suppressed_count > 0:
        payload["suppressed_events_since_last_emit"] = suppressed_count

    logger.info(
        "Zone %s: emitting correction skip event",
        zone_id,
        extra={
            "zone_id": zone_id,
            "event_type": event_type,
            "reason_code": reason_code,
            "signature": signature,
            "suppressed_events_since_last_emit": suppressed_count,
            "payload": payload,
        },
    )
    await create_zone_event_fn(zone_id, event_type, payload)
    zone_state["last_correction_skip_event_at"] = now
    zone_state["last_correction_skip_reason"] = str(reason_code or "")
    zone_state["last_correction_skip_signature"] = signature
    zone_state["suppressed_correction_skip_events"] = 0


__all__ = [
    "build_correction_skip_signature",
    "emit_correction_skip_event_throttled",
    "normalize_flag_signature_values",
]

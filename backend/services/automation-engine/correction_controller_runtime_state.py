"""Runtime-state helpers extracted from CorrectionController."""

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def log_skip_decision(
    controller: Any,
    *,
    zone_id: int,
    reason_code: str,
    level: str = "warning",
    **extra_data: Any,
) -> None:
    payload = {
        "component": "correction_controller",
        "zone_id": zone_id,
        "metric": controller.metric_name,
        "decision": "skip",
        "reason_code": reason_code,
    }
    payload.update(extra_data)
    log_fn = logger.info if level == "info" else logger.warning
    log_fn(
        "Zone %s: %s correction skipped (%s)",
        zone_id,
        controller.metric_name,
        reason_code,
        extra=payload,
    )


def is_anomaly_guard_enabled(controller: Any, settings: Any) -> bool:
    return bool(getattr(settings, "AE_EQUIPMENT_ANOMALY_GUARD_ENABLED", True))


def resolve_anomaly_min_delta(controller: Any, settings: Any) -> float:
    if controller.correction_type.value == "ph":
        return max(0.0, float(getattr(settings, "AE_EQUIPMENT_ANOMALY_PH_MIN_DELTA", 0.03)))
    return max(0.0, float(getattr(settings, "AE_EQUIPMENT_ANOMALY_EC_MIN_DELTA", 0.03)))


def resolve_anomaly_block_until(controller: Any, zone_id: int) -> Optional[float]:
    blocked_until = controller._anomaly_blocked_until_by_zone.get(zone_id)
    if blocked_until is None:
        return None
    now_mono = time.monotonic()
    if blocked_until <= now_mono:
        controller._anomaly_blocked_until_by_zone.pop(zone_id, None)
        controller._no_effect_streak_by_zone.pop(zone_id, None)
        return None
    return blocked_until


def register_pending_effect_window(
    controller: Any,
    *,
    zone_id: int,
    baseline_value: float,
    target_value: float,
    correction_type: str,
    settings: Any,
    correlation_id: str,
) -> None:
    if not controller._is_anomaly_guard_enabled(settings):
        return
    expected_direction = -1 if correction_type in {"add_acid", "dilute"} else 1
    window_sec = max(30, int(getattr(settings, "AE_EQUIPMENT_ANOMALY_NO_EFFECT_WINDOW_SEC", 180)))
    now_mono = time.monotonic()
    controller._pending_effect_window_by_zone[zone_id] = {
        "baseline_value": float(baseline_value),
        "target_value": float(target_value),
        "expected_direction": expected_direction,
        "correction_type": correction_type,
        "window_started_at": now_mono,
        "window_deadline_at": now_mono + float(window_sec),
        "window_sec": window_sec,
        "correlation_id": correlation_id,
    }


def evaluate_pending_effect_window(
    controller: Any,
    *,
    zone_id: int,
    current_value: float,
    settings: Any,
) -> Optional[Dict[str, Any]]:
    if not controller._is_anomaly_guard_enabled(settings):
        controller._pending_effect_window_by_zone.pop(zone_id, None)
        return None

    pending = controller._pending_effect_window_by_zone.get(zone_id)
    if not pending:
        return None

    now_mono = time.monotonic()
    deadline_at = float(pending.get("window_deadline_at") or 0.0)
    if now_mono < deadline_at:
        return None

    baseline_value = float(pending.get("baseline_value") or 0.0)
    expected_direction = int(pending.get("expected_direction") or 1)
    min_delta = controller._resolve_anomaly_min_delta(settings)
    observed_delta = float(current_value) - baseline_value
    effect_ok = observed_delta >= min_delta if expected_direction > 0 else observed_delta <= -min_delta
    controller._pending_effect_window_by_zone.pop(zone_id, None)

    if effect_ok:
        previous_streak = int(controller._no_effect_streak_by_zone.get(zone_id, 0))
        controller._no_effect_streak_by_zone[zone_id] = 0
        return {
            "state": "effect_confirmed",
            "observed_delta": observed_delta,
            "min_delta": min_delta,
            "previous_streak": previous_streak,
            "pending": pending,
        }

    next_streak = int(controller._no_effect_streak_by_zone.get(zone_id, 0)) + 1
    controller._no_effect_streak_by_zone[zone_id] = next_streak
    streak_threshold = max(1, int(getattr(settings, "AE_EQUIPMENT_ANOMALY_STREAK_THRESHOLD", 3)))
    block_minutes = max(1, int(getattr(settings, "AE_EQUIPMENT_ANOMALY_BLOCK_MINUTES", 30)))
    block_activated = next_streak >= streak_threshold
    block_until = None
    if block_activated:
        block_until = now_mono + block_minutes * 60.0
        controller._anomaly_blocked_until_by_zone[zone_id] = block_until

    return {
        "state": "no_effect_detected",
        "observed_delta": observed_delta,
        "min_delta": min_delta,
        "streak": next_streak,
        "streak_threshold": streak_threshold,
        "block_activated": block_activated,
        "block_until_monotonic": block_until,
        "pending": pending,
    }


def normalize_int_key_map(raw: Any, *, value_cast) -> Dict[int, Any]:
    if not isinstance(raw, dict):
        return {}
    result: Dict[int, Any] = {}
    for key, value in raw.items():
        try:
            zone_id = int(key)
            result[zone_id] = value_cast(value)
        except (TypeError, ValueError):
            continue
    return result


def export_runtime_state_payload(controller: Any) -> Dict[str, Any]:
    now_mono = time.monotonic()
    pending_effect: Dict[str, Any] = {}
    for zone_id, payload in (controller._pending_effect_window_by_zone or {}).items():
        if not isinstance(payload, dict):
            continue
        deadline = float(payload.get("window_deadline_at") or 0.0)
        remaining = max(0.0, deadline - now_mono)
        pending_effect[str(zone_id)] = {
            "baseline_value": payload.get("baseline_value"),
            "target_value": payload.get("target_value"),
            "expected_direction": payload.get("expected_direction"),
            "correction_type": payload.get("correction_type"),
            "correlation_id": payload.get("correlation_id"),
            "window_sec": payload.get("window_sec"),
            "remaining_sec": remaining,
        }

    anomaly_block: Dict[str, Any] = {}
    for zone_id, blocked_until in (controller._anomaly_blocked_until_by_zone or {}).items():
        remaining = max(0.0, float(blocked_until) - now_mono)
        anomaly_block[str(zone_id)] = {"remaining_sec": remaining}

    return {
        "last_target_by_zone": {str(k): float(v) for k, v in controller._last_target_by_zone.items()},
        "freshness_check_failure_count": {str(k): int(v) for k, v in controller._freshness_check_failure_count.items()},
        "no_effect_streak_by_zone": {str(k): int(v) for k, v in controller._no_effect_streak_by_zone.items()},
        "pending_effect_window_by_zone": pending_effect,
        "anomaly_blocked_by_zone": anomaly_block,
    }


def restore_runtime_state_payload(controller: Any, raw_state: Optional[Dict[str, Any]]) -> None:
    state = raw_state or {}
    now_mono = time.monotonic()

    controller._last_target_by_zone = controller._normalize_int_key_map(
        state.get("last_target_by_zone"),
        value_cast=lambda value: float(value),
    )
    controller._last_target_ts_by_zone = {zone_id: now_mono for zone_id in controller._last_target_by_zone}
    controller._freshness_check_failure_count = controller._normalize_int_key_map(
        state.get("freshness_check_failure_count"),
        value_cast=lambda value: int(value),
    )
    controller._no_effect_streak_by_zone = controller._normalize_int_key_map(
        state.get("no_effect_streak_by_zone"),
        value_cast=lambda value: int(value),
    )

    pending_effect: Dict[int, Dict[str, Any]] = {}
    pending_raw = state.get("pending_effect_window_by_zone")
    if isinstance(pending_raw, dict):
        for key, payload in pending_raw.items():
            if not isinstance(payload, dict):
                continue
            try:
                zone_id = int(key)
                remaining_sec = max(0.0, float(payload.get("remaining_sec") or 0.0))
                window_sec = max(30, int(payload.get("window_sec") or 180))
                pending_effect[zone_id] = {
                    "baseline_value": float(payload.get("baseline_value") or 0.0),
                    "target_value": float(payload.get("target_value") or 0.0),
                    "expected_direction": int(payload.get("expected_direction") or 1),
                    "correction_type": str(payload.get("correction_type") or ""),
                    "correlation_id": str(payload.get("correlation_id") or ""),
                    "window_started_at": now_mono,
                    "window_deadline_at": now_mono + remaining_sec,
                    "window_sec": window_sec,
                }
            except (TypeError, ValueError):
                continue
    controller._pending_effect_window_by_zone = pending_effect

    anomaly_blocks: Dict[int, float] = {}
    blocks_raw = state.get("anomaly_blocked_by_zone")
    if isinstance(blocks_raw, dict):
        for key, payload in blocks_raw.items():
            try:
                zone_id = int(key)
                if isinstance(payload, dict):
                    remaining_sec = max(0.0, float(payload.get("remaining_sec") or 0.0))
                else:
                    remaining_sec = max(0.0, float(payload))
                anomaly_blocks[zone_id] = now_mono + remaining_sec
            except (TypeError, ValueError):
                continue
    controller._anomaly_blocked_until_by_zone = anomaly_blocks


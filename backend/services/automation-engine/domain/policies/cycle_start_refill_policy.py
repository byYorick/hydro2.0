"""Cycle-start refill helper policy extracted from scheduler coordinator."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Sequence

from common.node_types import normalize_node_type


def normalize_text_list(*, raw: Any, default: Sequence[str]) -> List[str]:
    if isinstance(raw, str):
        values = [item.strip().lower() for item in raw.split(",") if item.strip()]
        return values or [str(item).strip().lower() for item in default if str(item).strip()]
    if isinstance(raw, Sequence):
        values = [str(item).strip().lower() for item in raw if str(item).strip()]
        return values or [str(item).strip().lower() for item in default if str(item).strip()]
    return [str(item).strip().lower() for item in default if str(item).strip()]


def normalize_node_type_list(*, raw: Any, default: Sequence[str]) -> List[str]:
    raw_values = normalize_text_list(raw=raw, default=default)
    canonical: List[str] = []
    for value in raw_values:
        normalized = normalize_node_type(value)
        if normalized == "unknown":
            continue
        if normalized not in canonical:
            canonical.append(normalized)
    if canonical:
        return canonical

    fallback: List[str] = []
    for value in default:
        normalized = normalize_node_type(str(value))
        if normalized == "unknown":
            continue
        if normalized not in fallback:
            fallback.append(normalized)
    return fallback


def resolve_required_node_types(
    *,
    override: Any,
    default: Sequence[str],
) -> List[str]:
    return normalize_node_type_list(raw=override, default=default)


def resolve_clean_tank_threshold(
    *,
    execution_config: Dict[str, Any],
    refill_config: Dict[str, Any],
    default_threshold: float,
) -> float:
    threshold_raw = refill_config.get("clean_tank_full_threshold")
    if threshold_raw is None:
        threshold_raw = execution_config.get("clean_tank_full_threshold")
    try:
        threshold = float(threshold_raw) if threshold_raw is not None else default_threshold
    except (TypeError, ValueError):
        threshold = default_threshold
    return max(0.0, min(1.0, threshold))


def resolve_refill_duration_ms(
    *,
    execution_config: Dict[str, Any],
    refill_config: Dict[str, Any],
    default_duration_sec: int,
) -> int:
    duration_raw = refill_config.get("duration_sec")
    if duration_raw is None:
        duration_raw = execution_config.get("refill_duration_sec")
    try:
        duration_sec = float(duration_raw) if duration_raw is not None else float(default_duration_sec)
    except (TypeError, ValueError):
        duration_sec = float(default_duration_sec)
    duration_sec = max(0.1, duration_sec)
    return max(100, int(duration_sec * 1000))


def resolve_refill_attempt(*, payload: Dict[str, Any]) -> int:
    raw_attempt = payload.get("refill_attempt")
    try:
        attempt = int(raw_attempt) if raw_attempt is not None else 0
    except (TypeError, ValueError):
        attempt = 0
    return max(0, attempt)


def resolve_refill_started_at(
    *,
    payload: Dict[str, Any],
    now: datetime,
    parse_iso_datetime: Callable[[str], datetime | None],
) -> datetime:
    raw_started_at = payload.get("refill_started_at")
    parsed = parse_iso_datetime(str(raw_started_at)) if raw_started_at else None
    return parsed or now


def resolve_refill_timeout_at(
    *,
    payload: Dict[str, Any],
    started_at: datetime,
    execution_config: Dict[str, Any],
    refill_config: Dict[str, Any],
    parse_iso_datetime: Callable[[str], datetime | None],
    default_timeout_sec: int,
) -> datetime:
    raw_timeout = payload.get("refill_timeout_at")
    if raw_timeout is None:
        raw_timeout = refill_config.get("timeout_at")
    if raw_timeout is None:
        raw_timeout = execution_config.get("refill_timeout_at")

    parsed_timeout = parse_iso_datetime(str(raw_timeout)) if raw_timeout else None
    if parsed_timeout is not None:
        return parsed_timeout

    timeout_sec_raw = refill_config.get("timeout_sec")
    if timeout_sec_raw is None:
        timeout_sec_raw = execution_config.get("refill_timeout_sec")
    try:
        timeout_sec = int(timeout_sec_raw) if timeout_sec_raw is not None else default_timeout_sec
    except (TypeError, ValueError):
        timeout_sec = default_timeout_sec
    timeout_sec = max(30, timeout_sec)
    return started_at + timedelta(seconds=timeout_sec)


def build_refill_check_payload(
    *,
    payload: Dict[str, Any],
    refill_started_at: datetime,
    refill_timeout_at: datetime,
    next_attempt: int,
) -> Dict[str, Any]:
    next_payload = dict(payload)
    next_payload["workflow"] = "refill_check"
    next_payload["refill_started_at"] = refill_started_at.isoformat()
    next_payload["refill_timeout_at"] = refill_timeout_at.isoformat()
    next_payload["refill_attempt"] = next_attempt
    return next_payload


__all__ = [
    "build_refill_check_payload",
    "normalize_node_type_list",
    "normalize_text_list",
    "resolve_clean_tank_threshold",
    "resolve_refill_attempt",
    "resolve_refill_duration_ms",
    "resolve_refill_started_at",
    "resolve_refill_timeout_at",
    "resolve_required_node_types",
]

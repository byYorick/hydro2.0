"""Shared payload/primitive parsing helpers for API layer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def to_optional_int(raw_value: Any) -> Optional[int]:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return None
    return value


def to_optional_float(raw_value: Any) -> Optional[float]:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    return value


def coerce_datetime(raw_value: Any) -> Optional[datetime]:
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is not None:
            return raw_value.astimezone(timezone.utc).replace(tzinfo=None)
        return raw_value

    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        if normalized == "":
            return None
        if normalized.endswith("Z"):
            normalized = f"{normalized[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    return None


def extract_workflow(payload: Dict[str, Any]) -> str:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    raw_workflow = payload.get("workflow") or payload.get("diagnostics_workflow") or execution.get("workflow") or ""
    return str(raw_workflow).strip().lower()


def extract_topology(payload: Dict[str, Any]) -> str:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    raw_topology = payload.get("topology") or execution.get("topology") or ""
    return str(raw_topology).strip().lower()


__all__ = [
    "coerce_datetime",
    "extract_topology",
    "extract_workflow",
    "to_optional_float",
    "to_optional_int",
]

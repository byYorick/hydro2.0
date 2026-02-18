"""Shared normalization and coercion helpers for scheduler workflows."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


def resolve_int(*, raw: Any, default: int, minimum: int) -> int:
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


def resolve_float(*, raw: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def normalize_labels(*, raw: Any, default: Sequence[str]) -> List[str]:
    if isinstance(raw, str):
        labels = [item.strip().lower() for item in raw.split(",") if item.strip()]
        return labels or [str(item).strip().lower() for item in default if str(item).strip()]
    if isinstance(raw, Sequence):
        labels = [str(item).strip().lower() for item in raw if str(item).strip()]
        return labels or [str(item).strip().lower() for item in default if str(item).strip()]
    return [str(item).strip().lower() for item in default if str(item).strip()]


def canonical_sensor_label(raw: Any) -> str:
    label = str(raw or "").strip().lower()
    if not label:
        return ""
    normalized = "".join(ch if ch.isalnum() else "_" for ch in label)
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_")


def merge_dict_recursive(*, base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dict_recursive(
                base=merged.get(key) if isinstance(merged.get(key), dict) else {},
                patch=value,
            )
        else:
            merged[key] = value
    return merged


__all__ = [
    "canonical_sensor_label",
    "merge_dict_recursive",
    "normalize_labels",
    "resolve_float",
    "resolve_int",
]

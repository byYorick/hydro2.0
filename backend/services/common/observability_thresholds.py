"""Authority defaults for automation observability hang-hint thresholds."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

STAGE_KEYS: tuple[str, ...] = (
    "startup",
    "clean_fill_check",
    "solution_fill_check",
    "prepare_recirculation_check",
    "irrigation_check",
    "irrigation_recovery_check",
    "await_ready",
    "decision_gate",
)

_DEFAULTS_PATH = Path(__file__).with_name("observability_thresholds_defaults.json")


def load_builtin_defaults() -> dict[str, int]:
    with _DEFAULTS_PATH.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, Mapping):
        raise ValueError("observability_thresholds_defaults.json must be an object")
    return {str(key): int(value) for key, value in raw.items()}


def resolved_thresholds(override: Mapping[str, Any] | None) -> dict[str, int]:
    merged = load_builtin_defaults()
    if override is None:
        return merged
    for key, value in override.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            merged[str(key)] = int(value)
    return merged


def stage_threshold_pair(cfg: Mapping[str, int], stage: str) -> tuple[int, int] | None:
    normalized = str(stage or "").strip().lower()
    if normalized not in STAGE_KEYS:
        return None
    warn = int(cfg.get(f"stage_{normalized}_warn_sec", 0))
    critical = int(cfg.get(f"stage_{normalized}_critical_sec", 0))
    if warn <= 0 or critical <= 0:
        return None
    return warn, critical


async def load_system_observability_thresholds(fetch_fn: Any | None) -> dict[str, int]:
    if fetch_fn is None:
        return resolved_thresholds(None)
    try:
        rows = await fetch_fn(
            """
            SELECT config
            FROM automation_effective_bundles
            WHERE scope_type = 'system'
              AND scope_id = 0
            LIMIT 1
            """
        )
        if not rows:
            return resolved_thresholds(None)
        first = rows[0]
        config = first.get("config") if isinstance(first, Mapping) else None
        if not isinstance(config, Mapping):
            return resolved_thresholds(None)
        system = config.get("system")
        if not isinstance(system, Mapping):
            return resolved_thresholds(None)
        payload = system.get("observability_thresholds")
        if not isinstance(payload, Mapping):
            return resolved_thresholds(None)
        return resolved_thresholds(payload)
    except Exception:
        return resolved_thresholds(None)


__all__ = [
    "STAGE_KEYS",
    "load_builtin_defaults",
    "load_system_observability_thresholds",
    "resolved_thresholds",
    "stage_threshold_pair",
]

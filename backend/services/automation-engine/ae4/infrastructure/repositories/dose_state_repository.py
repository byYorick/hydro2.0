"""Состояние импульса дозы в pid_state. Не импортирует ae3lite."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ae4.domain.dose_policy import DoseReagentState, ObservationOutcome
from common.db import fetch, execute

_PID_BY_REAGENT = {
    "nutrition": "ec",
    "ph_up": "ph",
    "ph_down": "ph",
}


def _as_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0) if value.microsecond else value


def _parse_stats(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if isinstance(loaded, Mapping):
            return dict(loaded)
    return {}


async def load_reagent_state(*, zone_id: int, reagent: str) -> DoseReagentState | None:
    pid_type = _PID_BY_REAGENT.get(reagent)
    if pid_type is None:
        return None
    rows = await fetch(
        """
        SELECT last_dose_at, no_effect_count, last_correction_kind, last_measured_value, stats
        FROM pid_state
        WHERE zone_id = $1 AND pid_type = $2
        LIMIT 1
        """,
        zone_id,
        pid_type,
    )
    if not rows:
        return None
    row = rows[0]
    kind = str(row.get("last_correction_kind") or "").strip()
    # Для ph в одной строке два реагента — смотрим last_correction_kind и stats.by_reagent.
    stats = _parse_stats(row.get("stats"))
    by_reagent = stats.get("ae4_reagents")
    entry: Mapping[str, Any] = {}
    if isinstance(by_reagent, Mapping):
        raw_entry = by_reagent.get(reagent)
        if isinstance(raw_entry, Mapping):
            entry = raw_entry
    if reagent in {"ph_up", "ph_down"} and kind and kind != reagent and not entry:
        return DoseReagentState(
            reagent=reagent,
            last_dose_at=None,
            no_effect_count=0,
            baseline_value=None,
            last_dose_ml=None,
            observation="effect",
        )
    last_dose_at = _as_naive(row.get("last_dose_at"))
    if entry.get("last_dose_at"):
        try:
            last_dose_at = _as_naive(datetime.fromisoformat(str(entry["last_dose_at"])))
        except ValueError:
            pass
    observation_raw = str(entry.get("observation") or "").strip()
    observation: ObservationOutcome
    if observation_raw in {"effect", "no_effect", "sensor_stale", "pending"}:
        observation = observation_raw  # type: ignore[assignment]
    elif last_dose_at is None:
        observation = "effect"
    else:
        observation = "pending"
    no_effect = int(entry.get("no_effect_count") or row.get("no_effect_count") or 0)
    baseline = entry.get("baseline_value")
    if baseline is None:
        baseline = row.get("last_measured_value")
    dose_ml = entry.get("last_dose_ml")
    return DoseReagentState(
        reagent=reagent,
        last_dose_at=last_dose_at if (kind == reagent or reagent == "nutrition" or entry) else None,
        no_effect_count=max(0, no_effect),
        baseline_value=float(baseline) if baseline is not None else None,
        last_dose_ml=float(dose_ml) if dose_ml is not None else None,
        observation=observation,
    )


async def mark_dose_done(
    *,
    zone_id: int,
    reagent: str,
    dose_ml: float,
    baseline_value: float,
    now: datetime,
) -> None:
    """last_dose_at только после terminal DONE."""
    pid_type = _PID_BY_REAGENT[reagent]
    now_naive = _as_naive(now)
    assert now_naive is not None
    rows = await fetch(
        """
        SELECT stats, no_effect_count
        FROM pid_state
        WHERE zone_id = $1 AND pid_type = $2
        LIMIT 1
        """,
        zone_id,
        pid_type,
    )
    stats = _parse_stats(rows[0].get("stats") if rows else None)
    reagents = stats.get("ae4_reagents")
    if not isinstance(reagents, dict):
        reagents = {}
    reagents[reagent] = {
        "last_dose_at": now_naive.isoformat(),
        "last_dose_ml": float(dose_ml),
        "baseline_value": float(baseline_value),
        "observation": "pending",
        "no_effect_count": int(
            reagents.get(reagent, {}).get("no_effect_count")
            if isinstance(reagents.get(reagent), Mapping)
            else (rows[0].get("no_effect_count") if rows else 0) or 0
        ),
    }
    stats["ae4_reagents"] = reagents
    await execute(
        """
        INSERT INTO pid_state (
            zone_id, pid_type, last_dose_at, last_measured_value,
            last_correction_kind, no_effect_count, stats, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, COALESCE($6, 0), $7::jsonb, $3, $3)
        ON CONFLICT (zone_id, pid_type) DO UPDATE SET
            last_dose_at = EXCLUDED.last_dose_at,
            last_measured_value = EXCLUDED.last_measured_value,
            last_correction_kind = EXCLUDED.last_correction_kind,
            stats = EXCLUDED.stats,
            updated_at = EXCLUDED.updated_at
        """,
        zone_id,
        pid_type,
        now_naive,
        float(baseline_value),
        reagent,
        int(reagents[reagent]["no_effect_count"]),
        json.dumps(stats),
    )


async def save_observation_state(*, zone_id: int, state: DoseReagentState) -> None:
    pid_type = _PID_BY_REAGENT[state.reagent]
    rows = await fetch(
        """
        SELECT stats
        FROM pid_state
        WHERE zone_id = $1 AND pid_type = $2
        LIMIT 1
        """,
        zone_id,
        pid_type,
    )
    stats = _parse_stats(rows[0].get("stats") if rows else None)
    reagents = stats.get("ae4_reagents")
    if not isinstance(reagents, dict):
        reagents = {}
    reagents[state.reagent] = {
        "last_dose_at": state.last_dose_at.isoformat() if state.last_dose_at else None,
        "last_dose_ml": state.last_dose_ml,
        "baseline_value": state.baseline_value,
        "observation": state.observation,
        "no_effect_count": int(state.no_effect_count),
    }
    stats["ae4_reagents"] = reagents
    now_naive = _as_naive(datetime.now(timezone.utc))
    await execute(
        """
        INSERT INTO pid_state (
            zone_id, pid_type, no_effect_count, last_correction_kind, stats, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $6)
        ON CONFLICT (zone_id, pid_type) DO UPDATE SET
            no_effect_count = EXCLUDED.no_effect_count,
            last_correction_kind = COALESCE(EXCLUDED.last_correction_kind, pid_state.last_correction_kind),
            stats = EXCLUDED.stats,
            updated_at = EXCLUDED.updated_at
        """,
        zone_id,
        pid_type,
        int(state.no_effect_count),
        state.reagent,
        json.dumps(stats),
        now_naive,
    )


__all__ = [
    "load_reagent_state",
    "mark_dose_done",
    "save_observation_state",
]

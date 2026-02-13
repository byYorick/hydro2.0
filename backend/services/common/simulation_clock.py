"""
Simulation clock utilities for accelerated simulations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .db import fetch
from .utils.time import utcnow


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return _to_utc(parsed)


@dataclass(frozen=True)
class SimulationClock:
    real_start: datetime
    sim_start: datetime
    time_scale: float
    mode: Optional[str] = None

    def now(self) -> datetime:
        real_now = utcnow()
        elapsed = (real_now - self.real_start).total_seconds()
        return self.sim_start + timedelta(seconds=elapsed * self.time_scale)

    def to_sim_time(self, real_ts: datetime) -> datetime:
        real_ts = _to_utc(real_ts)
        elapsed = (real_ts - self.real_start).total_seconds()
        return self.sim_start + timedelta(seconds=elapsed * self.time_scale)

    def to_real_time(self, sim_ts: datetime) -> datetime:
        sim_ts = _to_utc(sim_ts)
        elapsed = (sim_ts - self.sim_start).total_seconds()
        return self.real_start + timedelta(seconds=elapsed / self.time_scale)

    def scale_duration_seconds(self, duration_seconds: float, min_seconds: float = 0.1) -> float:
        if self.time_scale <= 0:
            return duration_seconds
        return max(min_seconds, duration_seconds / self.time_scale)


def _extract_simulation_clock(row: Dict[str, Any]) -> Optional[SimulationClock]:
    scenario = row.get("scenario") or {}
    sim_meta = scenario.get("simulation") or {}
    mode = sim_meta.get("mode")

    real_start = _parse_iso_datetime(sim_meta.get("real_started_at") or sim_meta.get("started_at"))
    sim_start = _parse_iso_datetime(sim_meta.get("sim_started_at") or sim_meta.get("sim_start_at"))

    if not real_start:
        created_at = row.get("created_at")
        if not created_at:
            return None
        real_start = _to_utc(created_at)

    if not sim_start:
        sim_start = real_start

    time_scale = sim_meta.get("time_scale")
    if time_scale is None:
        duration_hours = row.get("duration_hours")
        real_minutes = sim_meta.get("real_duration_minutes")
        real_seconds = sim_meta.get("real_duration_seconds")
        if duration_hours and real_minutes:
            time_scale = (duration_hours * 60) / float(real_minutes)
        elif duration_hours and real_seconds:
            time_scale = (duration_hours * 3600) / float(real_seconds)

    try:
        time_scale_value = float(time_scale)
    except (TypeError, ValueError):
        return None

    if time_scale_value <= 0:
        return None

    return SimulationClock(
        real_start=real_start,
        sim_start=sim_start,
        time_scale=time_scale_value,
        mode=mode if isinstance(mode, str) else None,
    )


async def get_simulation_clocks(zone_ids: List[int]) -> Dict[int, SimulationClock]:
    if not zone_ids:
        return {}
    try:
        rows = await fetch(
            """
            SELECT DISTINCT ON (zone_id)
                zone_id,
                scenario,
                duration_hours,
                created_at
            FROM zone_simulations
            WHERE zone_id = ANY($1::int[]) AND status = 'running'
            ORDER BY zone_id, created_at DESC
            """,
            zone_ids,
        )
    except Exception:
        return {}

    clocks: Dict[int, SimulationClock] = {}
    for row in rows:
        clock = _extract_simulation_clock(row)
        if clock:
            clocks[row["zone_id"]] = clock
    return clocks

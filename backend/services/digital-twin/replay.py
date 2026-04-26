"""Replay-режим Digital Twin (Phase B / B7).

Читает реальную историю зоны из БД (`commands` в статусе DONE +
`telemetry_samples` для initial state) и прогоняет её через ZoneWorld в
command-driven режиме. Опционально считает MAE между предсказанием DT и
фактической телеметрией за тот же период (sim2real validation).

Контракт:
    POST /v1/simulate/replay
    {
        "zone_id": <int>,
        "from_ts": "<ISO8601>",
        "to_ts":   "<ISO8601>",
        "step_minutes": 5,
        "include_actual": false
    }

Возвращает:
    {
        "status": "ok",
        "data": {
            "zone_id": ...,
            "from_ts": ...,
            "to_ts": ...,
            "step_minutes": ...,
            "points": [{"t", "ph", "ec", ...}, ...],
            "commands_replayed": <int>,
            "initial_state": {...},
            "actual": {...} | null,
            "mae": {"ph": ..., "ec": ...} | null
        }
    }
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from common.db import fetch
from common.utils.time import to_naive_utc
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dt_params import get_zone_dt_params
from world import CommandRouter, ZoneWorld

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Schema ---------------------------------------------------------------


class ReplayRequest(BaseModel):
    zone_id: int = Field(..., ge=1)
    from_ts: datetime
    to_ts: datetime
    step_minutes: int = Field(5, ge=1, le=60)
    include_actual: bool = False


# --- DB readers ----------------------------------------------------------


_INITIAL_METRIC_KEYS = {
    "PH": "ph",
    "EC": "ec",
    "TEMPERATURE": "temp_air",
    "HUMIDITY": "humidity_air",
    "WATER_TEMPERATURE": "temp_water",
    "WATER_CONTENT": "water_content",
}


async def _load_initial_state(zone_id: int, ts: datetime) -> Dict[str, float]:
    """Считать последние известные значения метрик до `ts` для зоны."""
    rows = await fetch(
        """
        SELECT DISTINCT ON (UPPER(s.type))
               UPPER(s.type) AS metric_type, ts.value
        FROM telemetry_samples ts
        JOIN sensors s ON s.id = ts.sensor_id
        WHERE ts.zone_id = $1 AND ts.ts <= $2
        ORDER BY UPPER(s.type), ts.ts DESC
        """,
        zone_id,
        to_naive_utc(ts),
    )
    initial: Dict[str, float] = {}
    for row in rows or []:
        metric = str(row.get("metric_type") or "").strip()
        key = _INITIAL_METRIC_KEYS.get(metric)
        if not key:
            continue
        try:
            initial[key] = float(row["value"])
        except (TypeError, ValueError):
            continue
    return initial


async def _load_commands(
    zone_id: int,
    from_ts: datetime,
    to_ts: datetime,
) -> List[Dict[str, Any]]:
    """Считать DONE-команды за период, отсортированные по created_at."""
    from_naive = to_naive_utc(from_ts)
    to_naive = to_naive_utc(to_ts)
    rows = await fetch(
        """
        SELECT created_at, cmd, channel, params
        FROM commands
        WHERE zone_id = $1
          AND status = 'DONE'
          AND created_at >= $2
          AND created_at <  $3
        ORDER BY created_at ASC
        """,
        zone_id,
        from_naive,
        to_naive,
    )
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        ts = row.get("created_at")
        if not ts:
            continue
        delta = (to_naive_utc(ts) - from_naive).total_seconds() / 60.0
        if delta < 0:
            continue
        params = row.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        out.append({
            "t_min": delta,
            "cmd": str(row.get("cmd") or "").strip(),
            "channel": str(row.get("channel") or "").strip(),
            "params": params,
        })
    return out


async def _load_actual_telemetry(
    zone_id: int,
    from_ts: datetime,
    to_ts: datetime,
) -> Dict[str, List[Dict[str, Any]]]:
    """Считать актуальные ph/ec samples за период для compare."""
    from_naive = to_naive_utc(from_ts)
    to_naive = to_naive_utc(to_ts)
    rows = await fetch(
        """
        SELECT ts.ts, UPPER(s.type) AS metric_type, ts.value
        FROM telemetry_samples ts
        JOIN sensors s ON s.id = ts.sensor_id
        WHERE ts.zone_id = $1
          AND ts.ts >= $2 AND ts.ts < $3
          AND UPPER(s.type) IN ('PH','EC','TEMPERATURE','HUMIDITY')
          AND ts.value IS NOT NULL
        ORDER BY ts.ts ASC
        """,
        zone_id,
        from_naive,
        to_naive,
    )
    by_metric: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows or []:
        metric = str(row.get("metric_type") or "").strip()
        try:
            value = float(row["value"])
        except (TypeError, ValueError):
            continue
        delta = (to_naive_utc(row["ts"]) - from_naive).total_seconds() / 3600.0
        by_metric.setdefault(metric, []).append({"t": delta, "value": value})
    return by_metric


# --- Replay logic --------------------------------------------------------


def _interpolate_actual(samples: List[Dict[str, Any]], t_hours: float) -> Optional[float]:
    """Линейная интерполяция фактической телеметрии в момент t_hours."""
    if not samples:
        return None
    # binary search не нужен — данных мало; линейный поиск приемлем.
    prev = None
    for sample in samples:
        if sample["t"] >= t_hours:
            if prev is None:
                return float(sample["value"])
            t0, t1 = prev["t"], sample["t"]
            v0, v1 = prev["value"], sample["value"]
            if t1 == t0:
                return float(v1)
            ratio = (t_hours - t0) / (t1 - t0)
            return float(v0 + ratio * (v1 - v0))
        prev = sample
    return float(samples[-1]["value"]) if samples else None


def _compute_mae(
    points: List[Dict[str, Any]],
    actual: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, float]:
    """MAE между predicted и interpolated actual по полям ph/ec/temp_air/humidity_air."""
    field_to_metric = {
        "ph": "PH",
        "ec": "EC",
        "temp_air": "TEMPERATURE",
        "humidity_air": "HUMIDITY",
    }
    mae: Dict[str, float] = {}
    for field, metric in field_to_metric.items():
        samples = actual.get(metric, [])
        if not samples:
            continue
        diffs: List[float] = []
        for point in points:
            actual_value = _interpolate_actual(samples, float(point["t"]))
            if actual_value is None:
                continue
            try:
                predicted = float(point[field])
            except (KeyError, TypeError, ValueError):
                continue
            diffs.append(abs(predicted - actual_value))
        if diffs:
            mae[field] = sum(diffs) / len(diffs)
    return mae


async def replay_zone(request: ReplayRequest) -> Dict[str, Any]:
    if request.to_ts <= request.from_ts:
        raise HTTPException(status_code=400, detail="to_ts must be > from_ts")

    duration_seconds = (request.to_ts - request.from_ts).total_seconds()
    if duration_seconds <= 0:
        raise HTTPException(status_code=400, detail="empty interval")
    if duration_seconds > 30 * 24 * 3600:
        raise HTTPException(status_code=400, detail="interval > 30 days not supported")

    initial_state = await _load_initial_state(request.zone_id, request.from_ts)
    params_by_group = await get_zone_dt_params(request.zone_id)
    commands = await _load_commands(request.zone_id, request.from_ts, request.to_ts)

    world = ZoneWorld(params_by_group=params_by_group)
    state = world.initial_state(initial_state)
    router_cmd = CommandRouter(world.actuator_solver, commands)

    step_minutes = request.step_minutes
    step_hours = step_minutes / 60.0
    total_minutes = duration_seconds / 60.0

    points: List[Dict[str, Any]] = []
    elapsed_minutes = 0.0
    while elapsed_minutes < total_minutes:
        router_cmd.advance_to(elapsed_minutes + step_minutes)
        state = world.step_with_commands(state, targets={}, dt_hours=step_hours)
        points.append({
            "t": round(elapsed_minutes / 60.0, 4),
            "ph": round(state.chem.ph, 3),
            "ec": round(state.chem.ec, 3),
            "temp_air": round(state.climate.temp_air_c, 2),
            "temp_water": round(state.tank.water_temp_c, 2),
            "humidity_air": round(state.climate.humidity_air_pct, 2),
            "solution_volume_l": round(state.tank.solution_volume_l, 2),
            "clean_volume_l": round(state.tank.clean_volume_l, 2),
            "level_solution_min": state.tank.level_solution_min,
        })
        elapsed_minutes += step_minutes

    response: Dict[str, Any] = {
        "zone_id": request.zone_id,
        "from_ts": request.from_ts.isoformat(),
        "to_ts": request.to_ts.isoformat(),
        "step_minutes": step_minutes,
        "points": points,
        "commands_replayed": len(commands),
        "initial_state": initial_state,
        "actual": None,
        "mae": None,
    }

    if request.include_actual:
        actual = await _load_actual_telemetry(
            request.zone_id, request.from_ts, request.to_ts
        )
        response["actual"] = actual
        response["mae"] = _compute_mae(points, actual)

    return response


# --- Endpoint -------------------------------------------------------------


@router.post("/v1/simulate/replay")
async def simulate_replay_endpoint(request: ReplayRequest):
    try:
        result = await replay_zone(request)
        return JSONResponse(content={"status": "ok", "data": result})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Digital Twin replay failed", exc_info=exc)
        raise HTTPException(status_code=500, detail=str(exc))

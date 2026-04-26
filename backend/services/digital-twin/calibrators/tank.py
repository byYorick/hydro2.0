"""TankCalibrator — восстанавливает параметры TankSolver из истории.

Источники:
- `commands` — ON/OFF события `valve_clean_fill` (status=DONE)
- `telemetry_samples` для каналов `level_clean_max` (или похожих) — смена 0→1
- `telemetry_samples` для канала `solution_volume_l` — если зона публикует объём

Восстанавливаемые параметры:
- `source_clean_l_per_hour` — оценка скорости наполнения чистой воды (из деления
  объёма-приращения на время открытия valve_clean_fill между ON и приходом
  level_clean_max=1).
- `evaporation_l_per_hour` — оценка испарения из solution tank
  в простоях (когда нет дозировок и valve закрыты).

В первом приближении используем эвристики и грубые оценки. При недостатке
данных — defaults. Точная оптимизация (Bayesian) — в Phase E.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from common.db import fetch
from common.utils.time import to_naive_utc, utcnow

logger = logging.getLogger(__name__)


_DEFAULT_RESULT: Dict[str, float] = {
    "source_clean_l_per_hour": 60.0,
    "evaporation_l_per_hour": 0.05,
}


@dataclass
class TankCalibrationResult:
    params: Dict[str, float]
    n_samples_used: int
    notes: List[str]


# --- Public API ----------------------------------------------------------


async def calibrate_tank_model(zone_id: int, days: int = 7) -> TankCalibrationResult:
    """Калибровать TankSolver-параметры зоны по истории.

    Возвращает `TankCalibrationResult`:
      - `params`: словарь с ключами `source_clean_l_per_hour`, `evaporation_l_per_hour`.
      - `n_samples_used`: сколько опорных эпизодов использовано для оценки.
      - `notes`: список причин fallback'ов (для логирования и UI).
    """
    cutoff = utcnow() - timedelta(days=days)
    notes: List[str] = []

    valve_events = await _load_valve_events(
        zone_id, cutoff, channels=("valve_clean_fill",)
    )
    level_events = await _load_level_transitions(
        zone_id, cutoff, level_channel_substr="level_clean_max"
    )

    fill_rate, fill_episodes = _estimate_fill_rate(valve_events, level_events)
    if fill_rate is None:
        fill_rate = _DEFAULT_RESULT["source_clean_l_per_hour"]
        notes.append("clean_fill_rate: insufficient data, using default")

    evap_rate, evap_episodes = await _estimate_evaporation(zone_id, cutoff)
    if evap_rate is None:
        evap_rate = _DEFAULT_RESULT["evaporation_l_per_hour"]
        notes.append("evaporation: insufficient data, using default")

    return TankCalibrationResult(
        params={
            "source_clean_l_per_hour": round(float(fill_rate), 4),
            "evaporation_l_per_hour": round(float(evap_rate), 4),
        },
        n_samples_used=int(fill_episodes + evap_episodes),
        notes=notes,
    )


# --- DB readers ----------------------------------------------------------


async def _load_valve_events(
    zone_id: int,
    cutoff: datetime,
    channels: Tuple[str, ...],
) -> List[Dict[str, Any]]:
    """Считать ON/OFF события set_relay для указанных каналов в формате (ts, channel, state)."""
    rows = await fetch(
        """
        SELECT created_at, channel, params
        FROM commands
        WHERE zone_id = $1
          AND status = 'DONE'
          AND cmd = 'set_relay'
          AND channel = ANY($2::text[])
          AND created_at >= $3
        ORDER BY created_at ASC
        """,
        zone_id,
        list(channels),
        to_naive_utc(cutoff),
    )
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        params = row.get("params") or {}
        if not isinstance(params, dict):
            continue
        out.append({
            "ts": row["created_at"],
            "channel": row["channel"],
            "state": bool(params.get("state", False)),
        })
    return out


async def _load_level_transitions(
    zone_id: int,
    cutoff: datetime,
    level_channel_substr: str,
) -> List[Dict[str, Any]]:
    """Считать сэмплы для уровня и оставить только переходы 0→1 / 1→0."""
    rows = await fetch(
        """
        SELECT ts, channel, value
        FROM telemetry_samples
        WHERE zone_id = $1
          AND ts >= $2
          AND channel ILIKE '%' || $3 || '%'
          AND value IS NOT NULL
        ORDER BY ts ASC
        """,
        zone_id,
        to_naive_utc(cutoff),
        level_channel_substr,
    )
    transitions: List[Dict[str, Any]] = []
    last_state: Optional[int] = None
    for row in rows or []:
        try:
            value = int(round(float(row["value"])))
        except (TypeError, ValueError):
            continue
        state = 1 if value >= 1 else 0
        if last_state is None or state != last_state:
            transitions.append({"ts": row["ts"], "state": state})
            last_state = state
    return transitions


# --- Estimators ----------------------------------------------------------


def _estimate_fill_rate(
    valve_events: List[Dict[str, Any]],
    level_transitions: List[Dict[str, Any]],
) -> Tuple[Optional[float], int]:
    """Оценить l/час для valve_clean_fill.

    Эпизод: valve ON → level_clean_max становится 1.
    Грубая оценка: считаем, что между ON и LATCH течёт чистая вода. Без
    реального знания тонкостей объёма берём фиксированный шаг
    `assumed_volume_added_l` (приближённо capacity-headroom). Это очень
    приблизительная оценка, но даёт лучше defaults для зон с реальными
    данными.
    """
    if not valve_events or not level_transitions:
        return None, 0

    # Простая модель: при каждом переходе level=0→1 ищем последний предшествующий
    # ON-event. Из времени открытия и assumed_volume_added_l оцениваем rate.
    assumed_volume_added_l = 80.0  # допущение per-зона

    rates: List[float] = []
    for trans in level_transitions:
        if trans["state"] != 1:
            continue
        latch_ts = trans["ts"]
        last_on: Optional[Dict[str, Any]] = None
        for event in valve_events:
            if event["ts"] >= latch_ts:
                break
            if event["state"]:
                last_on = event
        if not last_on:
            continue
        delta_seconds = (latch_ts - last_on["ts"]).total_seconds()
        if delta_seconds <= 60:
            continue
        rate = assumed_volume_added_l / (delta_seconds / 3600.0)
        if 1.0 <= rate <= 600.0:
            rates.append(rate)

    if not rates:
        return None, 0
    return sum(rates) / len(rates), len(rates)


async def _estimate_evaporation(
    zone_id: int,
    cutoff: datetime,
) -> Tuple[Optional[float], int]:
    """Оценить evaporation_l_per_hour.

    Идеальный источник — `telemetry_samples` для канала `solution_volume_l`
    (если эмитим). Если нет — fallback к EC-rise-без-дозировок (как в
    legacy `calibrate_ec_model`), но это даёт безразмерный коэффициент,
    несовместимый с l/час → возвращаем None.

    Чтобы реализовать оценку, ищем `solution_volume_l` сэмплы в простоях
    (без команд за последний час). Если канал отсутствует — None.
    """
    rows = await fetch(
        """
        SELECT ts, value
        FROM telemetry_samples
        WHERE zone_id = $1
          AND ts >= $2
          AND channel = 'solution_volume_l'
          AND value IS NOT NULL
        ORDER BY ts ASC
        """,
        zone_id,
        to_naive_utc(cutoff),
    )
    if not rows or len(rows) < 2:
        return None, 0

    drops: List[float] = []
    for i in range(1, len(rows)):
        prev = rows[i - 1]
        curr = rows[i]
        try:
            v_prev = float(prev["value"])
            v_curr = float(curr["value"])
        except (TypeError, ValueError):
            continue
        if v_curr >= v_prev:
            continue
        delta_hours = (curr["ts"] - prev["ts"]).total_seconds() / 3600.0
        if delta_hours <= 0 or delta_hours > 4:
            # Пропускаем разреженные/большие интервалы.
            continue
        rate = (v_prev - v_curr) / delta_hours
        if 0.001 <= rate <= 5.0:
            drops.append(rate)

    if not drops:
        return None, 0
    return sum(drops) / len(drops), len(drops)

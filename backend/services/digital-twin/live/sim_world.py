"""SimWorld — обёртка ZoneWorld + nodes/channels mapping для live-режима.

Один SimWorld соответствует одной активной live-симуляции (`zone_simulations.id`).
Хранит карту `node_uid → channels` (sensors + actuators), чтобы:
- знать, на какие топики подписываться (channel-level cmd для actuators);
- знать, какие telemetry-сэмплы публиковать (channel-level metrics для sensors).

`metric_type` для каналов берётся из БД (`node_channels.metric_type`), но если
metric_type не задан — резолвим эвристикой по имени канала.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from solvers import ZoneState
from world import CommandRouter, ZoneWorld

logger = logging.getLogger(__name__)


# --- Spec / events --------------------------------------------------------


@dataclass
class NodeChannelSpec:
    """Описание одного канала узла в симулированной зоне."""

    node_uid: str
    channel: str
    type: str           # 'SENSOR' | 'ACTUATOR'
    metric_type: Optional[str] = None  # для SENSOR


@dataclass
class SensorSample:
    """Один telemetry-сэмпл для публикации."""

    node_uid: str
    channel: str
    metric_type: str
    value: float
    ts_seconds: float


@dataclass
class LevelSwitchEvent:
    """Событие изменения level switch для публикации."""

    node_uid: str
    channel: str
    state: int           # 0/1
    initial: bool
    ts_seconds: float


# --- Эвристика метрики по имени канала ------------------------------------


_CHANNEL_METRIC_HEURISTIC: Tuple[Tuple[str, str], ...] = (
    ("ph_sensor", "PH"),
    ("ec_sensor", "EC"),
    ("temp_air", "TEMPERATURE"),
    ("air_temp", "TEMPERATURE"),
    ("temperature", "TEMPERATURE"),
    ("solution_temp", "WATER_TEMPERATURE"),
    ("water_temp", "WATER_TEMPERATURE"),
    ("humidity", "HUMIDITY"),
    ("rh", "HUMIDITY"),
    ("co2", "CO2"),
    ("level_clean_max", "WATER_LEVEL"),
    ("level_clean_min", "WATER_LEVEL"),
    ("level_solution_max", "WATER_LEVEL"),
    ("level_solution_min", "WATER_LEVEL"),
    ("water_content", "WATER_CONTENT"),
)


def resolve_metric_type(channel: str, hint: Optional[str] = None) -> Optional[str]:
    """Резолвить metric_type канала.

    `hint` — значение из БД (`node_channels.metric_type`), приоритет.
    """
    if hint:
        return hint.upper().strip() or None
    name = (channel or "").lower()
    for substr, metric in _CHANNEL_METRIC_HEURISTIC:
        if substr in name:
            return metric
    return None


# --- SimWorld -------------------------------------------------------------


@dataclass
class _PrevLevelLatches:
    """Последнее опубликованное состояние level switches (для diff-эмиссии)."""

    levels: Dict[Tuple[str, str], int] = field(default_factory=dict)


class SimWorld:
    """ZoneWorld + nodes/channels + tick orchestration для одной live-сессии."""

    def __init__(
        self,
        simulation_id: int,
        zone_id: int,
        gh_uid: str,
        zone_uid: str,
        channels: List[NodeChannelSpec],
        params_by_group: Optional[Dict[str, Dict[str, float]]] = None,
        initial_state: Optional[Dict[str, Any]] = None,
        time_scale: float = 1.0,
    ) -> None:
        self.simulation_id = simulation_id
        self.zone_id = zone_id
        self.gh_uid = gh_uid
        self.zone_uid = zone_uid
        self.channels = channels
        self.time_scale = max(0.1, float(time_scale or 1.0))

        self.world = ZoneWorld(params_by_group=params_by_group)
        self.state: ZoneState = self.world.initial_state(initial_state)
        # Router здесь без расписания — команды поступают онлайн через apply_command.
        self.command_router = CommandRouter(self.world.actuator_solver, [])
        self._latches = _PrevLevelLatches()

        # Сразу инициализируем latch state (initial=True эмитим в первом emit).
        self._actuator_channels: Dict[Tuple[str, str], NodeChannelSpec] = {}
        self._sensor_channels: List[NodeChannelSpec] = []
        for ch in channels:
            if ch.type.upper() == "ACTUATOR":
                self._actuator_channels[(ch.node_uid, ch.channel)] = ch
            else:
                self._sensor_channels.append(ch)

    # ---- public API --------------------------------------------------------

    def apply_command(
        self,
        node_uid: str,
        channel: str,
        cmd: str,
        params: Dict[str, Any],
    ) -> str:
        """Принять онлайн-команду (от subscriber). Вернуть резолвленную role."""
        spec = self._actuator_channels.get((node_uid, channel))
        if not spec:
            logger.debug(
                "Command for unknown actuator (%s/%s) — applying anyway by name",
                node_uid,
                channel,
            )
        return self.world.actuator_solver.apply_command(
            cmd=cmd,
            channel=channel,
            params=params,
        )

    def step(self, dt_real_seconds: float) -> Tuple[List[SensorSample], List[LevelSwitchEvent]]:
        """Прошагать мир на `dt_real_seconds` реального времени.

        Возвращает:
            samples — telemetry-сэмплы для публикации (по одному на каждый sensor channel).
            level_events — diff-события `level_switch_changed`.
        """
        sim_seconds = max(0.0, dt_real_seconds * self.time_scale)
        sim_hours = sim_seconds / 3600.0
        if sim_hours <= 0:
            return [], []

        # Phase B шаг — actuator_solver формирует flows и dose effects.
        self.state = self.world.step_with_commands(
            self.state, targets={}, dt_hours=sim_hours
        )

        ts_now = _now_seconds()
        samples = self._sample_sensors(ts_now)
        level_events = self._emit_level_events(ts_now, initial=False)
        return samples, level_events

    def emit_initial_levels(self) -> List[LevelSwitchEvent]:
        """Эмитить начальные level latches (с initial=True)."""
        return self._emit_level_events(_now_seconds(), initial=True)

    # ---- internal ----------------------------------------------------------

    def _sample_sensors(self, ts_seconds: float) -> List[SensorSample]:
        """Из текущего ZoneState сделать sensor samples per channel."""
        samples: List[SensorSample] = []
        for spec in self._sensor_channels:
            metric = resolve_metric_type(spec.channel, spec.metric_type)
            if not metric:
                continue
            value = self._value_for_metric(spec.channel, metric)
            if value is None:
                continue
            samples.append(SensorSample(
                node_uid=spec.node_uid,
                channel=spec.channel,
                metric_type=metric,
                value=float(value),
                ts_seconds=ts_seconds,
            ))
        return samples

    def _value_for_metric(self, channel: str, metric: str) -> Optional[float]:
        chan_lower = (channel or "").lower()
        st = self.state
        if metric == "PH":
            return st.chem.ph
        if metric == "EC":
            return st.chem.ec
        if metric == "TEMPERATURE":
            return st.climate.temp_air_c
        if metric == "WATER_TEMPERATURE":
            return st.tank.water_temp_c
        if metric == "HUMIDITY":
            return st.climate.humidity_air_pct
        if metric == "CO2":
            return st.climate.co2_ppm
        if metric == "WATER_LEVEL":
            if "clean_max" in chan_lower:
                return 1.0 if st.tank.level_clean_max else 0.0
            if "clean_min" in chan_lower:
                return 1.0 if st.tank.level_clean_min else 0.0
            if "solution_max" in chan_lower:
                return 1.0 if st.tank.level_solution_max else 0.0
            if "solution_min" in chan_lower:
                return 1.0 if st.tank.level_solution_min else 0.0
            return None
        if metric == "WATER_CONTENT":
            return st.substrate.water_content_pct
        return None

    def _emit_level_events(
        self,
        ts_seconds: float,
        initial: bool,
    ) -> List[LevelSwitchEvent]:
        """Сравнить latch с предыдущим, эмитить event для каждого изменения."""
        st = self.state
        current_levels: Dict[str, int] = {
            "level_clean_min": int(st.tank.level_clean_min),
            "level_clean_max": int(st.tank.level_clean_max),
            "level_solution_min": int(st.tank.level_solution_min),
            "level_solution_max": int(st.tank.level_solution_max),
        }
        events: List[LevelSwitchEvent] = []
        for spec in self._sensor_channels:
            metric = resolve_metric_type(spec.channel, spec.metric_type)
            if metric != "WATER_LEVEL":
                continue
            chan_lower = (spec.channel or "").lower()
            for name, value in current_levels.items():
                if name in chan_lower:
                    prev = self._latches.levels.get((spec.node_uid, spec.channel))
                    if initial or prev is None or prev != value:
                        self._latches.levels[(spec.node_uid, spec.channel)] = value
                        events.append(LevelSwitchEvent(
                            node_uid=spec.node_uid,
                            channel=spec.channel,
                            state=value,
                            initial=initial,
                            ts_seconds=ts_seconds,
                        ))
                    break
        return events


def _now_seconds() -> float:
    """Текущий wall-clock UTC в секундах (для ts полей в публикуемых сообщениях)."""
    import time
    return time.time()

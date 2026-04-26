"""ActuatorSolver — превращает события cmd → потоки и dose-эффекты.

Phase B: command-driven dynamics.

Поведение:
- `apply_command(cmd, channel, params, overrides)` обновляет внутренний state
  активных актуаторов (открытые клапаны, незавершённые дозы).
- `step(dt_seconds, solution_volume_l)` шагает все активные actuators на dt и
  возвращает `ActuatorEffect`:
    * `flows` — l/час для TankSolver (`clean_in/clean_to_solution/dose_in/irrigation_out`)
    * `chem_effect` — incremental EC-нутриенты и pH-дозы для ChemSolver

Реальные параметры калибровок (`ml_per_sec`, `acid_meq_per_ml`, ...) берутся
из `params_by_group['actuator']`. По умолчанию — безопасные defaults.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .channel_roles import KNOWN_ROLES, resolve_channel_role


# ---------------------------------------------------------------------------
# Параметры


DEFAULT_ACTUATOR_PARAMS: Dict[str, float] = {
    # Скорости потоков на ON-клапаны (l/час).
    "source_clean_l_per_hour": 60.0,
    "main_pump_l_per_hour": 30.0,
    "irrigation_l_per_hour": 12.0,
    # Калибровки насосов по умолчанию (ml/sec на канал).
    "default_pump_ml_per_sec": 1.0,
    # Концентрации pH-реагентов (meq/ml).
    "acid_meq_per_ml": 1.0,
    "base_meq_per_ml": 1.0,
    # Вклад 1ml EC-нутриента в EC при объёме 1л (mS/cm/ml/l).
    "ec_per_ml_per_l": 0.4,
    # Вклад 1 meq H+/OH- в pH при объёме 1л (упрощённая буферная модель).
    "ph_per_meq_per_l": 0.5,
}


# ---------------------------------------------------------------------------
# State


@dataclass
class _Pulse:
    """Незавершённая доза — оставшийся объём ml и скорость насоса."""

    ml_remaining: float
    flow_ml_per_sec: float


@dataclass
class ActuatorState:
    """Текущее состояние всех каналов зоны."""

    # role -> bool (для valve и режимных pump_main)
    valves_open: Dict[str, bool] = field(default_factory=dict)
    # role -> list of pulses (для pump_*)
    pulses_by_role: Dict[str, List[_Pulse]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Effect (output одного шага)


@dataclass
class ChemDoseEffect:
    """Net вклад mass-balance в pH/EC за шаг."""

    ec_dose_ml: float = 0.0          # суммарный объём EC-нутриентов
    ph_dose_meq_net: float = 0.0     # net (positive = pH вверх, negative = вниз)


@dataclass
class ActuatorEffect:
    """Аутпут одного шага ActuatorSolver."""

    flows: Dict[str, float] = field(default_factory=dict)
    chem: ChemDoseEffect = field(default_factory=ChemDoseEffect)


# ---------------------------------------------------------------------------
# Solver


class ActuatorSolver:
    """State + step для актуаторов зоны."""

    def __init__(self, params: Optional[Dict[str, float]] = None) -> None:
        merged: Dict[str, float] = dict(DEFAULT_ACTUATOR_PARAMS)
        roles_overrides: Dict[str, str] = {}
        calibrations: Dict[str, float] = {}
        if params:
            for key, value in params.items():
                if key == "channel_roles" and isinstance(value, dict):
                    roles_overrides = {str(k): str(v) for k, v in value.items()}
                    continue
                if key == "channel_calibrations" and isinstance(value, dict):
                    for ch, ml_per_sec in value.items():
                        if ml_per_sec is None:
                            continue
                        try:
                            calibrations[str(ch)] = float(ml_per_sec)
                        except (TypeError, ValueError):
                            continue
                    continue
                if value is None:
                    continue
                try:
                    merged[key] = float(value)
                except (TypeError, ValueError):
                    continue
        self.params = merged
        self.channel_roles_overrides = roles_overrides
        self.channel_calibrations = calibrations
        self.state = ActuatorState()

    # ---- public API --------------------------------------------------------

    def role_of(self, channel: str) -> str:
        return resolve_channel_role(channel, self.channel_roles_overrides)

    def apply_command(
        self,
        cmd: str,
        channel: str,
        params: Optional[Dict[str, object]] = None,
    ) -> str:
        """Зарегистрировать команду. Возвращает резолвлённую role."""
        params = params or {}
        role = self.role_of(channel)
        cmd_norm = str(cmd or "").strip().lower()

        if cmd_norm == "set_relay":
            state = bool(params.get("state", False))
            self.state.valves_open[role] = state
            return role

        if cmd_norm in ("dose", "run_pump"):
            ml_per_sec = self._calibration_for(channel, role)
            if cmd_norm == "dose":
                ml = self._to_float(params.get("ml"), default=0.0)
                if ml <= 0:
                    return role
                pulse = _Pulse(ml_remaining=ml, flow_ml_per_sec=ml_per_sec)
            else:
                duration_ms = self._to_float(
                    params.get("duration_ms")
                    or params.get("duration")
                    or 0.0,
                    default=0.0,
                )
                if duration_ms <= 0:
                    return role
                ml = ml_per_sec * (duration_ms / 1000.0)
                pulse = _Pulse(ml_remaining=ml, flow_ml_per_sec=ml_per_sec)
            self.state.pulses_by_role.setdefault(role, []).append(pulse)
            return role

        # state / restart / calibrate — для DT не вызывают физического воздействия
        return role

    def step(
        self,
        dt_seconds: float,
        solution_volume_l: float,
    ) -> ActuatorEffect:
        """Прошагать все активные actuators на dt секунд.

        Возвращает потоки в TankSolver-формате (l/час) и net dose effect для ChemSolver.
        """
        flows: Dict[str, float] = {
            "clean_in_l_per_hour": 0.0,
            "clean_to_solution_l_per_hour": 0.0,
            "dose_in_l_per_hour": 0.0,
            "irrigation_out_l_per_hour": 0.0,
        }
        chem_eff = ChemDoseEffect()

        if dt_seconds <= 0:
            return ActuatorEffect(flows=flows, chem=chem_eff)

        # Valves --------------------------------------------------------------
        if self.state.valves_open.get("valve_clean_fill"):
            flows["clean_in_l_per_hour"] += float(self.params["source_clean_l_per_hour"])

        # clean→solution возможен, когда открыт valve_clean_supply, valve_solution_fill
        # И включён pump_main как ON-режим (для упрощения хватает любого pump_main=ON
        # или valve_solution_fill+pump_main).
        pump_main_on = self.state.valves_open.get("pump_main", False)
        clean_supply = self.state.valves_open.get("valve_clean_supply", False)
        sol_fill = self.state.valves_open.get("valve_solution_fill", False)
        if pump_main_on and clean_supply and sol_fill:
            flows["clean_to_solution_l_per_hour"] += float(
                self.params["main_pump_l_per_hour"]
            )

        # Полив: pump_main + valve_solution_supply + valve_irrigation
        sol_supply = self.state.valves_open.get("valve_solution_supply", False)
        irrig = self.state.valves_open.get("valve_irrigation", False)
        if pump_main_on and sol_supply and irrig:
            flows["irrigation_out_l_per_hour"] += float(self.params["irrigation_l_per_hour"])

        # Pulses (dosing) ----------------------------------------------------
        ec_per_ml_per_l = float(self.params["ec_per_ml_per_l"])
        acid_meq_per_ml = float(self.params["acid_meq_per_ml"])
        base_meq_per_ml = float(self.params["base_meq_per_ml"])

        total_dose_ml = 0.0
        for role, pulses in list(self.state.pulses_by_role.items()):
            applied_ml_for_role = 0.0
            for pulse in pulses:
                ml_to_apply = min(
                    pulse.ml_remaining,
                    pulse.flow_ml_per_sec * dt_seconds,
                )
                pulse.ml_remaining -= ml_to_apply
                applied_ml_for_role += ml_to_apply

            # Вычистить завершённые pulses
            self.state.pulses_by_role[role] = [
                p for p in pulses if p.ml_remaining > 1e-9
            ]
            if not self.state.pulses_by_role[role]:
                del self.state.pulses_by_role[role]

            if applied_ml_for_role <= 0:
                continue

            total_dose_ml += applied_ml_for_role

            if role.startswith("pump_ec_"):
                chem_eff.ec_dose_ml += applied_ml_for_role
            elif role == "pump_ph_up":
                # Базовое реагентирование → pH вверх → положительное net meq
                chem_eff.ph_dose_meq_net += applied_ml_for_role * base_meq_per_ml
            elif role == "pump_ph_down":
                # Кислота → pH вниз → отрицательное net meq
                chem_eff.ph_dose_meq_net -= applied_ml_for_role * acid_meq_per_ml
            else:
                # Неизвестная роль — добавим только в tank (объём раствора растёт).
                pass

        if total_dose_ml > 0:
            # Конвертация ml → l/час: ml_in_dt / dt_hours = ml_per_hour; / 1000 = l/hour.
            dt_hours = dt_seconds / 3600.0
            flows["dose_in_l_per_hour"] += (total_dose_ml / 1000.0) / dt_hours

        # Удерживаем солюшен volume для удобства диагностики (не используется здесь
        # — chem solver применит chem_eff с учётом новой volume).
        _ = solution_volume_l

        return ActuatorEffect(flows=flows, chem=chem_eff)

    # ---- internal helpers --------------------------------------------------

    @staticmethod
    def _to_float(value: object, default: float) -> float:
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _calibration_for(self, channel: str, role: str) -> float:
        """Найти ml_per_sec для канала; fallback по role; fallback default."""
        if channel in self.channel_calibrations:
            return self.channel_calibrations[channel]
        # Можно расширить fallback per-role если калибратор будет писать так.
        return float(self.params["default_pump_ml_per_sec"])

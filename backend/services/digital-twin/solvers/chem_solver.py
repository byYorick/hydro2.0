"""Solver химии раствора (pH + EC).

Phase A: target-driven correction (легаси-совместимо с `PHModel`/`ECModel`).
Phase B: добавлен опциональный mass-balance term от dose-команд (через
`ActuatorEffect.chem`). Когда `dose_effect` не None — pH/EC сначала
считаются по mass-balance (физика), затем применяется тот же legacy drift
+ correction-к-target. Это даёт две вещи одновременно:
  1. Реалистичный мгновенный отклик на дозу (как ловит AE3 observation window).
  2. Сохранённое поведение Phase A, когда команд нет.
"""
from typing import Dict, Optional

from .actuator_solver import ChemDoseEffect
from .state import ChemState


class ChemSolver:
    """Объединённый solver pH/EC.

    Параметры:
        ph_params: {buffer_capacity, natural_drift, correction_rate}
        ec_params: {evaporation_rate, dilution_rate, nutrient_addition_rate}
    """

    DEFAULT_PH_PARAMS: Dict[str, float] = {
        "buffer_capacity": 0.1,
        "natural_drift": 0.01,
        "correction_rate": 0.05,
    }
    DEFAULT_EC_PARAMS: Dict[str, float] = {
        "evaporation_rate": 0.02,
        "dilution_rate": 0.01,
        "nutrient_addition_rate": 0.03,
    }

    def __init__(
        self,
        ph_params: Optional[Dict[str, float]] = None,
        ec_params: Optional[Dict[str, float]] = None,
    ) -> None:
        self.ph_params = self._merge(self.DEFAULT_PH_PARAMS, ph_params)
        self.ec_params = self._merge(self.DEFAULT_EC_PARAMS, ec_params)

    @staticmethod
    def _merge(
        defaults: Dict[str, float], overrides: Optional[Dict[str, float]]
    ) -> Dict[str, float]:
        merged = dict(defaults)
        if overrides:
            for key, value in overrides.items():
                if value is None:
                    continue
                try:
                    merged[key] = float(value)
                except (TypeError, ValueError):
                    continue
        return merged

    def step(
        self,
        state: ChemState,
        targets: Dict[str, float],
        dt_hours: float,
        *,
        dose_effect: Optional[ChemDoseEffect] = None,
        solution_volume_l: float = 100.0,
        ec_per_ml_per_l: float = 0.4,
        ph_per_meq_per_l: float = 0.5,
    ) -> ChemState:
        """Один шаг симуляции химии.

        Phase A: targets задают drift+correction (legacy-эквивалентно).
        Phase B: dose_effect опционально добавляет mass-balance term.
        """
        target_ph = float(targets.get("ph", state.ph))
        target_ec = float(targets.get("ec", state.ec))

        ph_after_dose = state.ph
        ec_after_dose = state.ec
        if dose_effect is not None and solution_volume_l > 0:
            d_ec = dose_effect.ec_dose_ml * ec_per_ml_per_l / solution_volume_l
            ec_after_dose = state.ec + d_ec
            d_ph = (
                dose_effect.ph_dose_meq_net
                * ph_per_meq_per_l
                / solution_volume_l
            )
            ph_after_dose = state.ph + d_ph

        new_ph = self._step_ph(ph_after_dose, target_ph, dt_hours)
        new_ec = self._step_ec(ec_after_dose, target_ec, dt_hours)
        return ChemState(ph=new_ph, ec=new_ec)

    def _step_ph(self, current: float, target: float, dt_hours: float) -> float:
        drift = self.ph_params["natural_drift"] * dt_hours
        diff = target - current
        if abs(diff) > 0.1:
            correction = diff * self.ph_params["correction_rate"] * dt_hours
            correction = max(-0.2, min(0.2, correction))
        else:
            correction = 0.0
        return max(4.0, min(9.0, current + drift + correction))

    def _step_ec(self, current: float, target: float, dt_hours: float) -> float:
        evap = current * self.ec_params["evaporation_rate"] * dt_hours
        diff = target - current
        if abs(diff) > 0.1:
            rate = (
                self.ec_params["nutrient_addition_rate"]
                if diff > 0
                else self.ec_params["dilution_rate"]
            )
            correction = diff * rate * dt_hours
            correction = max(-0.3, min(0.3, correction))
        else:
            correction = 0.0
        return max(0.1, min(5.0, current + evap + correction))

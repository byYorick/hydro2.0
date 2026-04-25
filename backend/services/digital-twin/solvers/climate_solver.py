"""Solver климата (temp_air, humidity_air).

Phase A: target-driven, эквивалентно legacy `ClimateModel`.
Phase B (план): energy/water balance с реальной вентиляцией.
"""
from typing import Dict, Optional

from .state import ClimateState


class ClimateSolver:
    """Solver баланса тепла и влаги.

    Параметры:
        heat_loss_rate: естественные потери тепла (°C/час)
        humidity_decay_rate: естественное снижение влажности (доля/час)
        ventilation_cooling: охлаждение при вентиляции (зарезервирован для phase B)
    """

    DEFAULT_PARAMS: Dict[str, float] = {
        "heat_loss_rate": 0.5,
        "humidity_decay_rate": 0.02,
        "ventilation_cooling": 1.0,
    }

    def __init__(self, params: Optional[Dict[str, float]] = None) -> None:
        merged = dict(self.DEFAULT_PARAMS)
        if params:
            for key, value in params.items():
                if value is None:
                    continue
                try:
                    merged[key] = float(value)
                except (TypeError, ValueError):
                    continue
        self.params = merged

    def step(
        self,
        state: ClimateState,
        targets: Dict[str, float],
        dt_hours: float,
    ) -> ClimateState:
        target_temp = float(targets.get("temp_air", state.temp_air_c))
        target_humidity = float(targets.get("humidity_air", state.humidity_air_pct))

        temp_diff = target_temp - state.temp_air_c
        if abs(temp_diff) > 1.0:
            temp_change = temp_diff * 0.1 * dt_hours
            heat_loss = self.params["heat_loss_rate"] * dt_hours
            new_temp = state.temp_air_c + temp_change - heat_loss
        else:
            new_temp = state.temp_air_c - self.params["heat_loss_rate"] * dt_hours

        humidity_diff = target_humidity - state.humidity_air_pct
        if abs(humidity_diff) > 5.0:
            humidity_change = humidity_diff * 0.05 * dt_hours
        else:
            humidity_change = 0.0
        humidity_decay = (
            state.humidity_air_pct * self.params["humidity_decay_rate"] * dt_hours
        )
        new_humidity = state.humidity_air_pct + humidity_change - humidity_decay

        return ClimateState(
            temp_air_c=max(10.0, min(35.0, new_temp)),
            humidity_air_pct=max(20.0, min(95.0, new_humidity)),
            co2_ppm=state.co2_ppm,
        )

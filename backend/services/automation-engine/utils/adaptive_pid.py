"""
Adaptive PID controller with zones, safety limits and basic statistics.

Примечание: Это легковесная реализация для дозирования pH/EC. Она рассчитана
на вызов с фиксированным шагом (dt в секундах) в автоматизации, не хранит
состояние на диск и живет в памяти процесса automation-engine.
"""
from __future__ import annotations

import copy
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict
import time

logger = logging.getLogger(__name__)


class PidZone(Enum):
    DEAD = "dead"
    CLOSE = "close"
    FAR = "far"


@dataclass
class PidZoneCoeffs:
    kp: float
    ki: float
    kd: float


@dataclass
class PidStats:
    compute_count: int = 0
    corrections_count: int = 0
    saturation_count: int = 0
    total_output: float = 0.0
    max_error: float = 0.0
    avg_error: float = 0.0
    time_in_dead_ms: int = 0
    time_in_close_ms: int = 0
    time_in_far_ms: int = 0


@dataclass
class AdaptivePidConfig:
    setpoint: float
    dead_zone: float
    close_zone: float
    far_zone: float
    zone_coeffs: Dict[PidZone, PidZoneCoeffs]
    max_output: float
    min_output: float = 0.0
    max_integral: float = 100.0
    anti_windup_mode: str = "clamp"  # clamp|conditional|back_calculation
    back_calculation_gain: float = 0.2
    derivative_filter_alpha: float = 1.0  # 1.0 -> без фильтра, 0.0 -> полностью инерционный
    min_interval_ms: int = 60000  # safety: min interval between doses
    enable_autotune: bool = False
    autotune_mode: str = "disabled"  # disabled|service
    adaptation_rate: float = 0.05  # 5% шаг изменения коэффициентов


class AdaptivePid:
    """Адаптивный PID с зонированием и базовыми safety механизмами."""

    def __init__(self, config: AdaptivePidConfig):
        self.config = config
        self.integral = 0.0
        self.prev_error: Optional[float] = None
        self.last_output_ms = 0  # monotonic ms (time.monotonic() * 1000)
        self.emergency = False
        self.stats = PidStats()
        self.current_zone = PidZone.DEAD
        self.prev_derivative = 0.0
        # Начальные коэффициенты для autotune: нижняя граница = 10% от initial
        self._init_zone_coeffs: Dict[PidZone, PidZoneCoeffs] = copy.deepcopy(config.zone_coeffs)
        self._autotune_guard_enabled = os.getenv("AE_PID_AUTOTUNE_SERVICE_MODE", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _select_zone(self, error: float) -> PidZone:
        abs_err = abs(error)
        if abs_err <= self.config.dead_zone:
            return PidZone.DEAD
        if abs_err <= self.config.close_zone:
            return PidZone.CLOSE
        return PidZone.FAR

    def _apply_autotune(self, zone: PidZone, error: float, derivative: float):
        """Простейшая адаптация: если ошибка растет, чуть увеличиваем Kp, если падает — уменьшаем."""
        if not self.config.enable_autotune:
            return
        if str(self.config.autotune_mode).strip().lower() != "service" or not self._autotune_guard_enabled:
            logger.info(
                "PID autotune skipped by guard",
                extra={
                    "autotune_mode": self.config.autotune_mode,
                    "guard_enabled": self._autotune_guard_enabled,
                    "zone": zone.value,
                },
            )
            return

        coeffs = self.config.zone_coeffs[zone]
        rate = self.config.adaptation_rate
        prev_kp = coeffs.kp
        prev_ki = coeffs.ki
        prev_kd = coeffs.kd

        # Ошибка растет -> усилить пропорциональную часть, ослабить интегральную
        if self.prev_error is not None and abs(error) > abs(self.prev_error):
            coeffs.kp *= 1.0 + rate
            coeffs.ki *= 1.0 - rate
        else:
            coeffs.kp *= 1.0 - rate
            coeffs.ki *= 1.0 + rate

        # Нижняя граница — 10% от начального значения (не обнуляем коэффициенты)
        init = self._init_zone_coeffs[zone]
        min_kp = max(init.kp * 0.1, 0.01)
        min_ki = max(init.ki * 0.1, 0.001)

        coeffs.kp = max(min_kp, min(coeffs.kp, 10.0))
        coeffs.ki = max(min_ki, min(coeffs.ki, 1.0))
        coeffs.kd = max(0.0, min(coeffs.kd, 1.0))

        logger.debug(
            "PID autotune zone=%s kp=%.4f ki=%.4f kd=%.4f",
            zone.value, coeffs.kp, coeffs.ki, coeffs.kd,
        )
        logger.info(
            "PID autotune coeff update",
            extra={
                "zone": zone.value,
                "kp_before": prev_kp,
                "kp_after": coeffs.kp,
                "ki_before": prev_ki,
                "ki_after": coeffs.ki,
                "kd_before": prev_kd,
                "kd_after": coeffs.kd,
                "error": error,
                "derivative": derivative,
            },
        )

    def compute(self, current_value: float, dt_seconds: float) -> float:
        """
        Рассчитать дозу (положительное число).

        Safety:
        - Если emergency, возвращает 0.
        - min_interval_ms: если с предыдущей дозы прошло меньше — 0.
        """
        if dt_seconds <= 0:
            logger.warning(
                "PID compute skipped: non-positive dt",
                extra={
                    "dt_seconds": dt_seconds,
                    "current_value": current_value,
                    "setpoint": self.config.setpoint,
                },
            )
            return 0.0

        if self.emergency:
            logger.info(
                "PID compute skipped: emergency mode active",
                extra={"current_value": current_value, "setpoint": self.config.setpoint},
            )
            return 0.0

        # Используем монотонные часы — не зависят от NTP-скачков и перевода системного времени
        now_mono_ms = int(time.monotonic() * 1000)
        elapsed_ms = now_mono_ms - self.last_output_ms if self.last_output_ms else None
        if self.last_output_ms and elapsed_ms is not None and elapsed_ms < self.config.min_interval_ms:
            remaining_ms = self.config.min_interval_ms - elapsed_ms
            logger.debug(
                "PID compute skipped: min interval guard",
                extra={
                    "elapsed_ms": elapsed_ms,
                    "remaining_ms": remaining_ms,
                    "min_interval_ms": self.config.min_interval_ms,
                    "current_value": current_value,
                    "setpoint": self.config.setpoint,
                },
            )
            return 0.0

        error = self.config.setpoint - current_value
        self.stats.compute_count += 1
        zone = self._select_zone(error)
        self.current_zone = zone

        # Обновление статистики времени в зонах
        dt_ms = int(dt_seconds * 1000)
        if zone == PidZone.DEAD:
            self.stats.time_in_dead_ms += dt_ms
        elif zone == PidZone.CLOSE:
            self.stats.time_in_close_ms += dt_ms
        else:
            self.stats.time_in_far_ms += dt_ms

        # Dead zone — нулевая коррекция
        if zone == PidZone.DEAD:
            self.prev_error = error
            logger.debug(
                "PID compute skipped: dead zone",
                extra={
                    "error": error,
                    "dead_zone": self.config.dead_zone,
                    "current_value": current_value,
                    "setpoint": self.config.setpoint,
                },
            )
            return 0.0

        coeffs = self.config.zone_coeffs.get(zone, self.config.zone_coeffs[PidZone.CLOSE])

        # Вычисляем производную
        derivative_raw = 0.0
        if self.prev_error is not None and dt_seconds > 0:
            derivative_raw = (error - self.prev_error) / dt_seconds
        alpha = max(0.0, min(1.0, float(self.config.derivative_filter_alpha)))
        derivative = (alpha * derivative_raw) + ((1.0 - alpha) * self.prev_derivative)
        self.prev_derivative = derivative

        integral_before = self.integral
        integration_candidate = integral_before + (error * dt_seconds)
        mode = str(self.config.anti_windup_mode).strip().lower() or "clamp"
        if mode == "conditional":
            candidate_output = (
                coeffs.kp * error
                + coeffs.ki * integration_candidate
                + coeffs.kd * derivative
            )
            saturating_same_dir = (
                abs(candidate_output) > self.config.max_output
                and ((candidate_output > 0 and error > 0) or (candidate_output < 0 and error < 0))
            )
            if saturating_same_dir:
                integration_candidate = integral_before
        self.integral = max(-self.config.max_integral, min(integration_candidate, self.config.max_integral))
        if abs(self.integral - integration_candidate) > 1e-9:
            logger.debug(
                "PID integral clamped",
                extra={
                    "integral_before": integral_before,
                    "integral_after": self.integral,
                    "max_integral": self.config.max_integral,
                    "error": error,
                    "dt_seconds": dt_seconds,
                },
            )

        proportional = coeffs.kp * error
        integral_term = coeffs.ki * self.integral
        derivative_term = coeffs.kd * derivative
        raw_output = (
            proportional +
            integral_term +
            derivative_term
        )
        if mode == "back_calculation" and coeffs.ki > 1e-9:
            clamped_signed = max(-self.config.max_output, min(raw_output, self.config.max_output))
            correction = float(self.config.back_calculation_gain) * (clamped_signed - raw_output) / coeffs.ki
            if abs(correction) > 0:
                self.integral = max(
                    -self.config.max_integral,
                    min(self.integral + correction, self.config.max_integral),
                )
                integral_term = coeffs.ki * self.integral
                raw_output = proportional + integral_term + derivative_term

        # Выход — абсолютная доза
        output = abs(raw_output)
        unclamped_output = output
        output = max(self.config.min_output, min(output, self.config.max_output))
        if abs(output - unclamped_output) > 1e-9:
            self.stats.saturation_count += 1
            logger.debug(
                "PID output clamped",
                extra={
                    "unclamped_output": unclamped_output,
                    "clamped_output": output,
                    "min_output": self.config.min_output,
                    "max_output": self.config.max_output,
                },
            )

        if output > 0:
            self.stats.corrections_count += 1
            self.stats.total_output += output
            self.stats.max_error = max(self.stats.max_error, abs(error))
            # бегущее среднее ошибки
            n = self.stats.corrections_count
            self.stats.avg_error = ((self.stats.avg_error * (n - 1)) + abs(error)) / n
            self.last_output_ms = now_mono_ms

        logger.debug(
            "PID compute result",
            extra={
                "zone": zone.value,
                "error": error,
                "current_value": current_value,
                "setpoint": self.config.setpoint,
                "dt_seconds": dt_seconds,
                "proportional": proportional,
                "integral_term": integral_term,
                "derivative_term": derivative_term,
                "derivative_raw": derivative_raw,
                "anti_windup_mode": mode,
                "raw_output": raw_output,
                "output": output,
                "integral_state": self.integral,
                "prev_error": self.prev_error,
                "autotune_enabled": self.config.enable_autotune,
            },
        )

        self.prev_error = error
        # Autotune применяется после финального вычисления — не влияет на текущий output
        self._apply_autotune(zone, error, derivative)
        return output

    def update_setpoint(self, setpoint: float):
        """Обновить целевое значение и сбросить интеграл, если target изменился значительно."""
        if abs(self.config.setpoint - setpoint) > 1e-3:
            self.config.setpoint = setpoint
            self.integral = 0.0
            self.prev_error = None

    def reset(self):
        self.integral = 0.0
        self.prev_error = None
        self.prev_derivative = 0.0
        self.last_output_ms = 0
        self.emergency = False
        self.stats = PidStats()

    def emergency_stop(self):
        self.emergency = True
        self.integral = 0.0
        self.prev_error = None
        self.prev_derivative = 0.0

    def resume(self):
        self.emergency = False
        self.last_output_ms = 0

    def get_zone(self) -> PidZone:
        return self.current_zone

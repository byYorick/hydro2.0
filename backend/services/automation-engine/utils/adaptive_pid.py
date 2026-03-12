"""
Adaptive PID controller with zones, safety limits and basic statistics.

.. note::
    **NOT USED in production correction flow.**

    The active correction logic lives in
    ``ae3lite.domain.services.correction_planner`` which maintains PID state
    (integral, prev_error, prev_derivative) persistently in PostgreSQL and
    computes doses inline using zone-specific parameters from
    ``correction_config``.

    This module provides ``AdaptivePid`` (in-memory, zone-aware PID) and
    ``RelayAutotuner`` (Astrom-Hagglund autotune) as **standalone utilities**
    intended for:

    * Future integration with relay autotune workflows
    * Offline tuning simulations / notebooks
    * Unit-testing PID behaviour in isolation

    Do NOT wire ``AdaptivePid.compute()`` into the correction handler without
    first solving the state-persistence gap (the in-memory ``self.integral``
    is lost on process restart; persistence is owned by
    ``PgPidStateRepository``).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
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
    # max_integral ограничивает накопление integral_term = Ki * integral (anti-windup)
    max_integral: float = 100.0
    anti_windup_mode: str = "clamp"  # clamp|conditional|back_calculation
    back_calculation_gain: float = 0.2
    derivative_filter_alpha: float = 0.35  # 1.0 -> без фильтра, 0.0 -> полностью инерционный
    min_interval_ms: int = 60000  # safety: min interval between doses


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

    def _select_zone(self, error: float) -> PidZone:
        abs_err = abs(error)
        if abs_err <= self.config.dead_zone:
            return PidZone.DEAD
        if abs_err <= self.config.close_zone:
            return PidZone.CLOSE
        return PidZone.FAR

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
            },
        )

        self.prev_error = error
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


@dataclass
class RelayAutotuneConfig:
    relay_amplitude_ml: float  # амплитуда relay в мл (pH: 3.0, EC: 10.0)
    min_cycles: int = 3  # минимум полных колебаний перед расчетом
    max_duration_sec: float = 7200.0  # таймаут 2 часа
    min_oscillation_amplitude: float = 0.02  # минимальная амплитуда для pH; для EC: 0.1
    # SIMC tuning factors:
    simc_kp_factor: float = 0.45  # Kp = simc_kp_factor * Ku
    simc_ti_factor: float = 0.83  # Ti = simc_ti_factor * Tu -> Ki = Kp / Ti


@dataclass
class RelayAutotuneResult:
    kp: float
    ki: float
    kd: float = 0.0
    ku: float = 0.0  # ultimate gain
    tu_sec: float = 0.0  # ultimate period
    oscillation_amplitude: float = 0.0
    cycles_detected: int = 0
    duration_sec: float = 0.0


class RelayAutotuner:
    """
    Relay feedback autotune (Astrom-Hagglund, 1984).
    Применяется ВМЕСТО PID во время процедуры автотюнинга.

    Алгоритм:
      1. Подаем relay output: +d если error > 0, -d если error < 0
      2. Фиксируем extrema по сменам знака ошибки
      3. После min_cycles полных колебаний вычисляем Ku и Tu
      4. Применяем SIMC: Kp = 0.45*Ku, Ti = 0.83*Tu, Ki = Kp/Ti
    """

    def __init__(self, config: RelayAutotuneConfig, setpoint: float, start_time_sec: float):
        self.config = config
        self.setpoint = setpoint
        self.start_time_sec = start_time_sec
        self._complete = False
        self._timed_out = False
        self._result: Optional[RelayAutotuneResult] = None

        self._relay_state: int = 1  # +1 или -1
        self._extrema: List[float] = []  # значения extrema
        self._extrema_times: List[float] = []  # времена extrema
        self._last_error: Optional[float] = None
        self._zero_crossings: int = 0

    def update(self, current_value: float, now_sec: float) -> Optional[float]:
        """
        Обновить автотюнер, вернуть relay output (в мл) или None если завершен.

        Returns:
            float: relay output (±relay_amplitude_ml)
            None: автотюнинг завершен (complete или timeout)
        """
        if self._complete or self._timed_out:
            return None

        elapsed = now_sec - self.start_time_sec
        if elapsed > self.config.max_duration_sec:
            self._timed_out = True
            logger.warning(
                "RelayAutotuner timed out after %.1f sec, %d extrema collected",
                elapsed,
                len(self._extrema),
            )
            return None

        error = self.setpoint - current_value

        # На первом тике задаем полярность relay по текущему знаку ошибки.
        if self._last_error is None:
            self._relay_state = 1 if error >= 0 else -1
        # Смена знака ошибки (нулевое пересечение) -> смена relay state
        else:
            if (error > 0 and self._last_error <= 0) or (error < 0 and self._last_error >= 0):
                self._relay_state *= -1
                self._zero_crossings += 1
                self._extrema.append(current_value)
                self._extrema_times.append(now_sec)

                if self._zero_crossings >= self.config.min_cycles * 2:
                    result = self._compute_params(elapsed)
                    if result is not None:
                        self._result = result
                        self._complete = True
                        return None

        self._last_error = error
        return float(self.config.relay_amplitude_ml * self._relay_state)

    def _compute_params(self, elapsed_sec: float) -> Optional[RelayAutotuneResult]:
        """Вычислить Kp, Ki по SIMC из собранных данных."""
        if len(self._extrema) < 4 or len(self._extrema_times) < 4:
            return None

        peaks = self._extrema[0::2]
        valleys = self._extrema[1::2]
        if not peaks or not valleys:
            return None

        au = (max(peaks) - min(valleys)) / 2.0
        if au < self.config.min_oscillation_amplitude:
            logger.warning(
                "RelayAutotuner: oscillation amplitude %.4f < min %.4f, insufficient response",
                au,
                self.config.min_oscillation_amplitude,
            )
            return None

        periods = []
        for idx in range(1, len(self._extrema_times)):
            periods.append((self._extrema_times[idx] - self._extrema_times[idx - 1]) * 2.0)
        tu = sum(periods) / len(periods) if periods else 0.0
        if tu < 10.0:
            logger.warning("RelayAutotuner: Tu=%.1f sec too small, ignoring", tu)
            return None

        d = self.config.relay_amplitude_ml
        ku = (4.0 * d) / (math.pi * au)
        kp = self.config.simc_kp_factor * ku
        ti = self.config.simc_ti_factor * tu
        ki = kp / ti if ti > 0 else 0.0

        logger.info(
            "RelayAutotuner complete: Ku=%.3f Tu=%.1fs -> Kp=%.3f Ki=%.4f Au=%.4f cycles=%d",
            ku,
            tu,
            kp,
            ki,
            au,
            self._zero_crossings // 2,
        )

        return RelayAutotuneResult(
            kp=round(kp, 4),
            ki=round(ki, 5),
            kd=0.0,
            ku=round(ku, 4),
            tu_sec=round(tu, 2),
            oscillation_amplitude=round(au, 4),
            cycles_detected=self._zero_crossings // 2,
            duration_sec=round(elapsed_sec, 1),
        )

    @property
    def is_complete(self) -> bool:
        return self._complete

    @property
    def is_timed_out(self) -> bool:
        return self._timed_out

    @property
    def result(self) -> Optional[RelayAutotuneResult]:
        return self._result

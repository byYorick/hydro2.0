"""
Adaptive PID controller with zones, safety limits and basic statistics.

Примечание: Это легковесная реализация для дозирования pH/EC. Она рассчитана
на вызов с фиксированным шагом (dt в секундах) в автоматизации, не хранит
состояние на диск и живет в памяти процесса automation-engine.
"""
from __future__ import annotations

import copy
import logging
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
    corrections_count: int = 0
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
    min_interval_ms: int = 60000  # safety: min interval between doses
    enable_autotune: bool = False
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
        # Начальные коэффициенты для autotune: нижняя граница = 10% от initial
        self._init_zone_coeffs: Dict[PidZone, PidZoneCoeffs] = copy.deepcopy(config.zone_coeffs)

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

        coeffs = self.config.zone_coeffs[zone]
        rate = self.config.adaptation_rate

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

    def compute(self, current_value: float, dt_seconds: float) -> float:
        """
        Рассчитать дозу (положительное число).

        Safety:
        - Если emergency, возвращает 0.
        - min_interval_ms: если с предыдущей дозы прошло меньше — 0.
        """
        if self.emergency:
            return 0.0

        # Используем монотонные часы — не зависят от NTP-скачков и перевода системного времени
        now_mono_ms = int(time.monotonic() * 1000)
        if self.last_output_ms and (now_mono_ms - self.last_output_ms) < self.config.min_interval_ms:
            return 0.0

        error = self.config.setpoint - current_value
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
            return 0.0

        coeffs = self.config.zone_coeffs.get(zone, self.config.zone_coeffs[PidZone.CLOSE])

        # Вычисляем производную
        derivative = 0.0
        if self.prev_error is not None and dt_seconds > 0:
            derivative = (error - self.prev_error) / dt_seconds

        # Накапливаем интеграл с bounded clamping (anti-windup: max_integral ограничивает накопление)
        self.integral += error * dt_seconds
        self.integral = max(-self.config.max_integral, min(self.integral, self.config.max_integral))

        output = (
            coeffs.kp * error +
            coeffs.ki * self.integral +
            coeffs.kd * derivative
        )

        # Выход — абсолютная доза
        output = abs(output)
        output = max(self.config.min_output, min(output, self.config.max_output))

        if output > 0:
            self.stats.corrections_count += 1
            self.stats.total_output += output
            self.stats.max_error = max(self.stats.max_error, abs(error))
            # бегущее среднее ошибки
            n = self.stats.corrections_count
            self.stats.avg_error = ((self.stats.avg_error * (n - 1)) + abs(error)) / n
            self.last_output_ms = now_mono_ms

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
        self.last_output_ms = 0
        self.emergency = False
        self.stats = PidStats()

    def emergency_stop(self):
        self.emergency = True
        self.integral = 0.0
        self.prev_error = None

    def resume(self):
        self.emergency = False
        self.last_output_ms = 0

    def get_zone(self) -> PidZone:
        return self.current_zone


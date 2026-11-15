"""Immutable correction dose plan DTOs shared by planners and execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class EcDoseStep:
    component: str
    node_uid: str
    channel: str
    amount_ml: float
    duration_ms: int
    requested_ml: float | None = None


@dataclass(frozen=True)
class DosePlan:
    """Разрешённые действия коррекции для текущего snapshot измерений."""

    needs_ec: bool = False
    ec_component: str = ""
    ec_node_uid: str = ""
    ec_channel: str = ""
    ec_amount_ml: float = 0.0
    ec_requested_ml: float = 0.0
    ec_duration_ms: int = 0
    ec_retry_after_sec: Optional[int] = None
    ec_dose_sequence: tuple[EcDoseStep, ...] = ()
    ec_dosing_mode: str = "single"

    needs_ph_up: bool = False
    needs_ph_down: bool = False
    ph_node_uid: str = ""
    ph_channel: str = ""
    ph_amount_ml: float = 0.0
    ph_requested_ml: float = 0.0
    ph_duration_ms: int = 0
    ph_retry_after_sec: Optional[int] = None

    retry_after_sec: Optional[int] = None
    dose_discarded_reason: str = ""
    dose_discarded_details: Mapping[str, Any] = field(default_factory=dict)
    #: Saturation clamp (доза всё ещё уходит) — НЕ discard. Отдельно от dose_discarded_*.
    dose_clamped_reason: str = ""
    dose_clamped_details: Mapping[str, Any] = field(default_factory=dict)
    dead_zone_details: Mapping[str, Any] = field(default_factory=dict)
    pid_state_updates: Mapping[str, Any] = field(default_factory=dict)
    ec_pid_zone: str = ""
    ph_pid_zone: str = ""
    ec_pid_coeffs: Mapping[str, Any] = field(default_factory=dict)
    ph_pid_coeffs: Mapping[str, Any] = field(default_factory=dict)
    dual_calibration_mismatches: tuple[Mapping[str, Any], ...] = ()

    @property
    def needs_any(self) -> bool:
        return self.needs_ec or self.needs_ph_up or self.needs_ph_down

    @property
    def ph_direction(self) -> str:
        if self.needs_ph_up:
            return "up"
        if self.needs_ph_down:
            return "down"
        return "none"

"""Неизменяемый DTO read-model для runtime snapshot зоны AE3-Lite."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class ZoneActuatorRef:
    """Разрешённый online command channel для поиска ноды на этапе planner'а."""

    node_uid: str
    node_type: str
    channel: str
    node_channel_id: int
    channel_type: str = "ACTUATOR"
    role: Optional[str] = None
    pump_calibration: Optional[Mapping[str, Any]] = None


@dataclass(frozen=True)
class ZoneSnapshot:
    """Неизменяемый runtime snapshot зоны, загружаемый из PostgreSQL в одной транзакции."""

    zone_id: int
    greenhouse_id: Optional[int]
    automation_runtime: str
    grow_cycle_id: Optional[int]
    current_phase_id: Optional[int]
    phase_name: Optional[str]
    workflow_phase: str
    workflow_version: int
    targets: Mapping[str, Any]
    diagnostics_execution: Mapping[str, Any]
    command_plans: Mapping[str, Any]
    telemetry_last: Mapping[str, Any]
    pid_state: Mapping[str, Any]
    pid_configs: Mapping[str, Any]
    actuators: Tuple[ZoneActuatorRef, ...]
    bundle_revision: Optional[str] = None
    process_calibrations: Optional[Mapping[str, Any]] = None
    correction_config: Optional[Mapping[str, Any]] = None
    phase_targets: Optional[Mapping[str, Any]] = None

"""Typed dose-planning request and application error boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import PlannerConfigurationError, TaskExecutionError
from ae3lite.domain.services.correction_dose_plan import DosePlan


@dataclass(frozen=True)
class CorrectionDoseRequest:
    """Immutable input for one planning attempt; no handler or service registry."""

    task: Any
    corr: CorrectionState
    current_ph: float
    current_ec: float
    target_ph: float
    target_ec: float
    now: datetime
    runtime: Any
    ph_tol_pct: float
    ec_tol_pct: float
    target_ph_min: float | None
    target_ph_max: float | None
    target_ec_min: float | None
    target_ec_max: float | None
    correction_cfg: Mapping[str, Any]
    pid_state: Mapping[str, Any]
    dose_flags: Mapping[str, Any]
    actuators: Mapping[str, Any]


async def build_checked_dose_plan(
    *, request: CorrectionDoseRequest, planner: Any, runtime_config: Any, log_event: Callable[..., Awaitable[Any]]
) -> DosePlan:
    try:
        process_calibrations = {
            str(phase_key): runtime_config.mapping_view(cfg)
            for phase_key, cfg in request.runtime.process_calibrations.items()
        }
        dose_plan = planner.build_dose_plan(
            current_ph=request.current_ph,
            current_ec=request.current_ec,
            target_ph=request.target_ph,
            target_ec=request.target_ec,
            ph_tolerance_pct=request.ph_tol_pct,
            ec_tolerance_pct=request.ec_tol_pct,
            correction_config=request.correction_cfg,
            workflow_phase=request.task.workflow.workflow_phase,
            process_calibrations=process_calibrations,
            ec_component_policy=request.correction_cfg.get('ec_component_policy'),
            pid_state=request.pid_state,
            pid_configs=request.runtime.pid_configs,
            now=request.now,
            ph_min=request.target_ph_min,
            ph_max=request.target_ph_max,
            ec_min=request.target_ec_min,
            ec_max=request.target_ec_max,
            ec_actuator=request.actuators.get('ec'),
            ec_actuators=request.actuators.get('ec_actuators'),
            ph_up_actuator=request.actuators.get('ph_up'),
            ph_down_actuator=request.actuators.get('ph_down'),
            active_component=request.dose_flags.get('active_component'),
            allow_ec=bool(request.dose_flags.get('allow_ec', True)),
            allow_ph=bool(request.dose_flags.get('allow_ph', True)),
            freeze_ec_pid=bool(request.dose_flags.get('freeze_ec_pid', False)),
        )
    except PlannerConfigurationError as exc:
        await log_event(
            zone_id=request.task.zone_id,
            event_type='CORRECTION_PLANNER_CONFIG_INVALID',
            task=request.task,
            corr=request.corr,
            payload={
                'reason': str(exc),
                'current_ph': request.current_ph,
                'current_ec': request.current_ec,
                'target_ph': request.target_ph,
                'target_ec': request.target_ec,
            },
        )
        raise TaskExecutionError(
            'corr_planner_config_invalid', f'Некорректная конфигурация CorrectionPlanner: {exc}'
        ) from exc
    return dose_plan

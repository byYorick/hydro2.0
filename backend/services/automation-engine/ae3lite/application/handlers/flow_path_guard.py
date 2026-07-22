"""FlowPathGuard — fail-safe остановка flow-path при manual/semi и провале stop-команд (PR7)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import FLOW_STOP_FAILED, inc_observability_write_failed
from common.biz_alerts import send_biz_alert
from common.db import create_zone_event

_logger = logging.getLogger(__name__)

MANUAL_HOLD_STAGE = "manual_hold"
MANUAL_HOLD_RETURN_PREFIX = "__mh_return:"
MANUAL_HOLD_STEP_PREFIX = "__mh_step:"

CORRECTION_DOSE_STEPS = frozenset(
    {"corr_dose_ec", "corr_dose_ph", "corr_wait_ec", "corr_wait_ph"},
)
# Backward-compatible alias for internal callers.
_CORRECTION_DOSE_STEPS = CORRECTION_DOSE_STEPS


@dataclass(frozen=True)
class FlowPathStageConfig:
    stop_plan_names: tuple[str, ...]
    off_expected: Mapping[str, bool]


_FLOW_PATH_STAGES: dict[str, FlowPathStageConfig] = {
    "clean_fill_check": FlowPathStageConfig(
        stop_plan_names=("clean_fill_stop",),
        off_expected={"valve_clean_fill": False, "pump_main": False},
    ),
    "solution_fill_check": FlowPathStageConfig(
        stop_plan_names=("solution_fill_stop", "sensor_mode_deactivate"),
        off_expected={
            "valve_clean_supply": False,
            "valve_solution_fill": False,
            "pump_main": False,
        },
    ),
    "prepare_recirculation_check": FlowPathStageConfig(
        stop_plan_names=("prepare_recirculation_stop", "sensor_mode_deactivate"),
        off_expected={
            "valve_solution_supply": False,
            "valve_solution_fill": False,
            "pump_main": False,
        },
    ),
    "irrigation_check": FlowPathStageConfig(
        stop_plan_names=("irrigation_stop", "sensor_mode_deactivate"),
        off_expected={
            "valve_solution_supply": False,
            "valve_irrigation": False,
            "pump_main": False,
        },
    ),
    "irrigation_recovery_check": FlowPathStageConfig(
        stop_plan_names=("irrigation_recovery_stop", "sensor_mode_deactivate"),
        off_expected={
            "valve_solution_supply": False,
            "valve_solution_fill": False,
            "valve_irrigation": False,
            "pump_main": False,
        },
    ),
    "solution_drain_check": FlowPathStageConfig(
        stop_plan_names=("solution_drain_stop",),
        off_expected={"valve_drain": False},
    ),
}


@dataclass(frozen=True)
class FlowStopOutcome:
    confirmed: bool
    task: Any | None = None
    error_code: str | None = None
    error_message: str | None = None
    commands: tuple[str, ...] = ()


def is_flow_path_check_stage(stage: object) -> bool:
    normalized = str(stage or "").strip().lower()
    return normalized in _FLOW_PATH_STAGES


def flow_path_stage_config(stage: object) -> FlowPathStageConfig | None:
    normalized = str(stage or "").strip().lower()
    return _FLOW_PATH_STAGES.get(normalized)


def should_interrupt_flow_for_control_mode(*, control_mode: str, runtime: Any) -> bool:
    mode = str(control_mode or "auto").strip().lower()
    if mode == "manual":
        return True
    if mode == "semi":
        return not bool(getattr(runtime, "semi_allows_active_flow", False))
    return False


def encode_manual_hold_return_stage(return_stage: str) -> str:
    return f"{MANUAL_HOLD_RETURN_PREFIX}{return_stage}"


def encode_manual_hold_operator_step(*, return_stage: str, manual_step: str) -> str:
    return f"{MANUAL_HOLD_STEP_PREFIX}{return_stage}:{manual_step}"


def decode_manual_hold_return_stage(pending_manual_step: object) -> str | None:
    raw = str(pending_manual_step or "").strip()
    if raw.startswith(MANUAL_HOLD_RETURN_PREFIX):
        return raw[len(MANUAL_HOLD_RETURN_PREFIX) :] or None
    if raw.startswith(MANUAL_HOLD_STEP_PREFIX):
        payload = raw[len(MANUAL_HOLD_STEP_PREFIX) :]
        if ":" in payload:
            return payload.split(":", 1)[0] or None
    return None


def decode_manual_hold_operator_step(pending_manual_step: object) -> str | None:
    raw = str(pending_manual_step or "").strip()
    if raw.startswith(MANUAL_HOLD_STEP_PREFIX):
        payload = raw[len(MANUAL_HOLD_STEP_PREFIX) :]
        if ":" in payload:
            return payload.split(":", 1)[1] or None
    return None


def is_manual_hold_pending_marker(pending_manual_step: object) -> bool:
    raw = str(pending_manual_step or "").strip()
    return raw.startswith(MANUAL_HOLD_RETURN_PREFIX) or raw.startswith(MANUAL_HOLD_STEP_PREFIX)


def _resolve_stop_commands(*, plan: Any, plan_names: Sequence[str]) -> tuple[Any, ...]:
    named = getattr(plan, "named_plans", None)
    if not isinstance(named, Mapping):
        return ()
    commands: list[Any] = []
    for plan_name in plan_names:
        commands.extend(named.get(plan_name, ()))
    return tuple(commands)


async def ensure_flow_stopped(
    handler: Any,
    *,
    task: Any,
    plan: Any,
    now: datetime,
    stage: str,
    reason: str,
) -> FlowStopOutcome:
    """Отправляет stop-план stage, подтверждает OFF через irr_state probe."""
    config = flow_path_stage_config(stage)
    if config is None:
        return FlowStopOutcome(confirmed=True, task=task)

    commands = _resolve_stop_commands(plan=plan, plan_names=config.stop_plan_names)
    if not commands:
        return FlowStopOutcome(
            confirmed=False,
            task=task,
            error_code="ae3_empty_command_plan",
            error_message=f"Не удалось разрешить stop-команды для stage={stage}: {config.stop_plan_names}",
            commands=config.stop_plan_names,
        )

    current_task = task
    try:
        result = await handler._run_command_batch_checked(
            task=current_task,
            commands=commands,
            now=now,
        )
        current_task = result.get("task") or current_task
    except TaskExecutionError as exc:
        await _emit_flow_stop_failed(
            task=task,
            stage=stage,
            reason=reason,
            commands=config.stop_plan_names,
            detail={"stop_error_code": exc.code, "stop_error_message": str(exc)},
            now=now,
        )
        return FlowStopOutcome(
            confirmed=False,
            task=current_task,
            error_code=str(exc.code),
            error_message=str(exc),
            commands=config.stop_plan_names,
        )

    try:
        await handler._probe_irr_state(
            task=current_task,
            plan=plan,
            now=now,
            expected=dict(config.off_expected),
        )
    except TaskExecutionError as exc:
        await _emit_flow_stop_failed(
            task=task,
            stage=stage,
            reason=reason,
            commands=config.stop_plan_names,
            detail={"probe_error_code": exc.code, "probe_error_message": str(exc)},
            now=now,
        )
        return FlowStopOutcome(
            confirmed=False,
            task=current_task,
            error_code="ae3_flow_stop_unconfirmed",
            error_message=str(exc),
            commands=config.stop_plan_names,
        )

    return FlowStopOutcome(confirmed=True, task=current_task, commands=config.stop_plan_names)


async def handle_control_mode_flow_path_interrupt(
    handler: Any,
    *,
    task: Any,
    plan: Any,
    now: datetime,
    control_mode: str,
    reason: str = "control_mode_manual",
) -> StageOutcome | None:
    """При manual/semi на активном flow-path: stop → manual_hold или terminal fail."""
    runtime = handler._require_runtime_plan(plan=plan)
    if not should_interrupt_flow_for_control_mode(control_mode=control_mode, runtime=runtime):
        return None

    stage = str(task.current_stage or "").strip()
    if not is_flow_path_check_stage(stage):
        return None

    stop_outcome = await ensure_flow_stopped(
        handler,
        task=task,
        plan=plan,
        now=now,
        stage=stage,
        reason=reason,
    )
    if not stop_outcome.confirmed:
        return StageOutcome(
            kind="fail",
            error_code=stop_outcome.error_code or "ae3_flow_stop_unconfirmed",
            error_message=stop_outcome.error_message or "Не удалось подтвердить остановку flow-path",
            task_override=stop_outcome.task,
        )

    await _emit_control_mode_flow_stopped(
        task=task,
        stage=stage,
        reason=reason,
        commands=stop_outcome.commands,
        now=now,
    )
    return StageOutcome(
        kind="transition",
        next_stage=MANUAL_HOLD_STAGE,
        flow_hold_return_stage=stage,
        due_delay_sec=int(runtime.level_poll_interval_sec),
        task_override=stop_outcome.task,
    )


async def emit_correction_interrupted_hardware_risk(
    *,
    task: Any,
    now: datetime,
    recovery_source: str = "startup_recovery",
) -> None:
    """После fail прерванной коррекции — алерт, если дозирование могло остаться активным.

    v1 (PR7): эвристика по ``corr_step`` (``corr_dose_*`` / ``corr_wait_*``); отдельный
    probe дозирующего насоса через telemetry/command status — planned (нет единого
    irr_state snapshot для EC/pH pump channels).
    """
    correction = getattr(task, "correction", None)
    if correction is None:
        return
    corr_step = str(getattr(correction, "corr_step", "") or "").strip().lower()
    if corr_step not in CORRECTION_DOSE_STEPS:
        return

    stage = str(task.current_stage or "").strip()
    config = flow_path_stage_config(stage)
    commands: tuple[str, ...] = config.stop_plan_names if config is not None else ()
    await _emit_flow_stop_failed(
        task=task,
        stage=stage or "correction",
        reason="startup_recovery_correction_interrupted",
        commands=commands,
        detail={
            "corr_step": corr_step,
            "recovery_source": recovery_source,
            "message": "Проверьте оборудование: коррекция прервана во время дозирования",
        },
        now=now,
    )


async def _emit_control_mode_flow_stopped(
    *,
    task: Any,
    stage: str,
    reason: str,
    commands: Sequence[str],
    now: datetime,
) -> None:
    payload = with_runtime_event_contract(
        {
            "task_id": int(getattr(task, "id", 0) or 0),
            "stage": stage,
            "reason": reason,
            "commands": list(commands),
            "control_mode": str(getattr(task.workflow, "control_mode", "") or ""),
        }
    )
    try:
        await create_zone_event(int(task.zone_id), "CONTROL_MODE_FLOW_STOPPED", payload)
    except Exception:
        inc_observability_write_failed(kind="zone_event")
        _logger.warning(
            "AE3 flow_path_guard: не удалось записать CONTROL_MODE_FLOW_STOPPED zone_id=%s task_id=%s",
            task.zone_id,
            task.id,
            exc_info=True,
        )


async def _emit_flow_stop_failed(
    *,
    task: Any,
    stage: str,
    reason: str,
    commands: Sequence[str],
    detail: Mapping[str, Any],
    now: datetime,
) -> None:
    FLOW_STOP_FAILED.labels(stage=stage or "unknown").inc()
    payload = with_runtime_event_contract(
        {
            "task_id": int(getattr(task, "id", 0) or 0),
            "stage": stage,
            "reason": reason,
            "commands": list(commands),
            **dict(detail),
        }
    )
    try:
        await create_zone_event(
            int(task.zone_id),
            "FLOW_STOP_FAILED_HARDWARE_MAY_BE_ACTIVE",
            payload,
        )
    except Exception:
        inc_observability_write_failed(kind="zone_event")
        _logger.warning(
            "AE3 flow_path_guard: не удалось записать FLOW_STOP_FAILED zone_id=%s task_id=%s",
            task.zone_id,
            task.id,
            exc_info=True,
        )

    try:
        await send_biz_alert(
            zone_id=int(task.zone_id),
            code="biz_flow_stop_failed_hardware_may_be_active",
            severity="critical",
            message="Не удалось подтвердить остановку flow-path; оборудование может оставаться активным",
            details={
                "task_id": int(getattr(task, "id", 0) or 0),
                "stage": stage,
                "reason": reason,
                "commands": list(commands),
                **dict(detail),
            },
            scope_parts=(f"stage:{stage}",),
        )
    except Exception:
        inc_observability_write_failed(kind="biz_alert")
        _logger.warning(
            "AE3 flow_path_guard: не удалось создать biz-alert flow stop failed zone_id=%s",
            task.zone_id,
            exc_info=True,
        )


__all__ = [
    "CORRECTION_DOSE_STEPS",
    "FlowStopOutcome",
    "MANUAL_HOLD_RETURN_PREFIX",
    "MANUAL_HOLD_STAGE",
    "MANUAL_HOLD_STEP_PREFIX",
    "decode_manual_hold_operator_step",
    "decode_manual_hold_return_stage",
    "emit_correction_interrupted_hardware_risk",
    "encode_manual_hold_operator_step",
    "encode_manual_hold_return_stage",
    "ensure_flow_stopped",
    "flow_path_stage_config",
    "handle_control_mode_flow_path_interrupt",
    "is_flow_path_check_stage",
    "is_manual_hold_pending_marker",
    "should_interrupt_flow_for_control_mode",
]

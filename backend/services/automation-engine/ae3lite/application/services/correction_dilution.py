"""Correction dilution: explicit collaborators, per-call task context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.correction_shared import (
    _DEFAULT_DILUTE_PULSE_SEC,
    _DEFAULT_DILUTE_SETTLE_SEC,
    _logger,
)
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError


@dataclass(frozen=True)
class CorrectionDilutionPorts:
    completion_anchored_window: Callable[..., Any]
    enter_correction_after_delay_or_interrupt: Callable[..., Any]
    log_correction_event: Callable[..., Awaitable[Any]]
    pid_state: Callable[[], Any]
    read_level: Callable[[], Any]
    require_runtime_plan: Callable[[], Any]
    run_command_batch_checked: Callable[[], Any]


class CorrectionDilution:
    def __init__(self, ports: CorrectionDilutionPorts) -> None:
        self._ports = ports

    async def run_dilute_pulse(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        """Open valve_clean_supply for dilute_pulse_sec, then settle."""
        runtime = self._ports.require_runtime_plan()(plan=plan)
        solution_max = await self._ports.read_level()(
            task=task,
            zone_id=task.zone_id,
            labels=runtime.solution_max_sensor_labels,
            threshold=runtime.level_switch_on_threshold,
            telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
            unavailable_error="two_tank_solution_max_level_unavailable",
            stale_error="two_tank_solution_max_level_stale",
            stale_recheck_delay_sec=0.25,
            prefer_probe_snapshot=True,
        )
        if solution_max.get("is_triggered"):
            # Бак полный: воду доливать нельзя. Краткий выброс EC (отклик дозы)
            # не должен валить цикл — возвращаемся в corr_check и ждём оседания.
            # Устойчивый перелёт закроет stage deadline.
            await self._ports.log_correction_event(
                zone_id=task.zone_id,
                event_type="RECIRC_DILUTE_BLOCKED",
                task=task,
                corr=corr,
                payload={"reason": "solution_max", "resume": "corr_check"},
            )
            next_corr = replace(corr, corr_step="corr_check")
            return self._ports.enter_correction_after_delay_or_interrupt(
                task=task,
                plan=plan,
                corr=next_corr,
                now=now,
                due_delay_sec=float(getattr(getattr(runtime, "recirc", None), "dilute_settle_sec", 30) or 30),
            )

        named = plan.named_plans if hasattr(plan, "named_plans") else {}
        start_cmds = tuple(named.get("recirc_dilute_start") or ())
        if not start_cmds:
            raise TaskExecutionError(
                "ae3_empty_command_plan",
                "Отсутствует command plan recirc_dilute_start",
            )
        result = await self._ports.run_command_batch_checked()(task=task, commands=start_cmds, now=now)
        current_task = result.get("task") or task
        pulse_sec = int(
            getattr(getattr(runtime, "recirc", None), "dilute_pulse_sec", _DEFAULT_DILUTE_PULSE_SEC)
            or _DEFAULT_DILUTE_PULSE_SEC
        )
        _, _, pulse_delay_sec = self._ports.completion_anchored_window(
            now=now,
            wait_sec=max(1, pulse_sec),
        )
        next_corr = replace(corr, corr_step="corr_dilute_settle")
        return self._ports.enter_correction_after_delay_or_interrupt(
            task=task,
            plan=plan,
            corr=next_corr,
            now=now,
            due_delay_sec=pulse_delay_sec,
            task_override=current_task if current_task is not task else None,
        )

    async def run_dilute_settle(
        self,
        *,
        task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
    ) -> StageOutcome:
        """Close dilute valve, reset EC PID I/D + no_effect, resume corr_check."""
        runtime = self._ports.require_runtime_plan()(plan=plan)
        named = plan.named_plans if hasattr(plan, "named_plans") else {}
        stop_cmds = tuple(named.get("recirc_dilute_stop") or ())
        current_task = task
        if stop_cmds:
            result = await self._ports.run_command_batch_checked()(task=task, commands=stop_cmds, now=now)
            current_task = result.get("task") or task

        await self.reset_ec_pid_for_pipeline(
            task=task,
            corr=corr,
            reason="dilute",
            now=now,
        )
        await self._ports.pid_state().reset_no_effect_counts(
            task=task,
            corr=corr,
            context="RECIRC_DILUTE",
        )
        settle_sec = int(
            getattr(getattr(runtime, "recirc", None), "dilute_settle_sec", _DEFAULT_DILUTE_SETTLE_SEC)
            or _DEFAULT_DILUTE_SETTLE_SEC
        )
        _, _, settle_delay_sec = self._ports.completion_anchored_window(
            now=now,
            wait_sec=max(0, settle_sec),
        )
        next_corr = replace(corr, corr_step="corr_check")
        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="RECIRC_DILUTE_COMPLETED",
            task=task,
            corr=next_corr,
            payload={"dilute_attempts": int(getattr(corr, "dilute_attempts", 0) or 0)},
        )
        return self._ports.enter_correction_after_delay_or_interrupt(
            task=task,
            plan=plan,
            corr=next_corr,
            now=now,
            due_delay_sec=settle_delay_sec,
            task_override=current_task if current_task is not task else None,
        )

    async def reset_ec_pid_for_pipeline(
        self,
        *,
        task: Any,
        corr: CorrectionState,
        reason: str,
        now: datetime,
    ) -> None:
        """Reset EC integral/derivative (and emit PID_EC_RESET)."""
        try:
            await self._ports.pid_state().persist(
                zone_id=int(task.zone_id),
                now=now,
                updates={
                    "ec": {
                        "integral": 0.0,
                        "prev_error": 0.0,
                        "prev_derivative": 0.0,
                        "last_measurement_at": now,
                    }
                },
            )
        except Exception:
            _logger.warning(
                "PID_EC_RESET failed zone_id=%s reason=%s",
                getattr(task, "zone_id", None),
                reason,
                exc_info=True,
            )
        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="PID_EC_RESET",
            task=task,
            corr=corr,
            payload={
                "reason": reason,
                "pipeline_phase": getattr(corr, "pipeline_phase", None),
                "active_component": getattr(corr, "active_component", None),
            },
        )

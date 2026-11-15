"""SolutionFillCheckHandler coordination: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.hydraulics.failure_report import note_upward_report


@dataclass(frozen=True)
class SolutionFillCoordinationPorts:
    stale_recheck_delay_sec: Callable[[], Any]
    checkpoint: Callable[[], Any]
    completed_outcome: Callable[..., Awaitable[Any]]
    deadline_reached: Callable[[], Any]
    enter_fill_calcium_correction: Callable[..., Awaitable[Any]]
    fill_ec_target_reached: Callable[..., Awaitable[Any]]
    handle_control_mode_flow_path_interrupt: Callable[[], Any]
    observe_fail_safe_transition: Callable[[], Any]
    probe_irr_state: Callable[[], Any]
    read_level: Callable[[], Any]
    read_recent_storage_event: Callable[[], Any]
    reconcile_recent_emergency_stop: Callable[[], Any]
    require_runtime_plan: Callable[[], Any]
    should_finish_to_ready: Callable[..., Awaitable[Any]]
    stage_elapsed_ms: Callable[[], Any]
    global_stage_deadline_exceeded: Callable[..., Any]
    global_logger: Callable[..., Any]


class SolutionFillCoordination:
    def __init__(self, ports: SolutionFillCoordinationPorts) -> None:
        self._ports = ports

    async def run(
        self,
        *,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> StageOutcome:
        plan = await self._ports.checkpoint()(task=task, plan=plan, now=now)
        runtime = self._ports.require_runtime_plan()(plan=plan)
        control_mode = str(getattr(task.workflow, "control_mode", "") or "auto").strip().lower()
        pending_manual_step = str(getattr(task.workflow, "pending_manual_step", "") or "")
        fail_safe_guards = runtime.fail_safe_guards
        recent_storage_event = await self._ports.read_recent_storage_event()(
            task=task,
            event_types=(
                "SOLUTION_FILL_SOURCE_EMPTY",
                "SOLUTION_FILL_LEAK_DETECTED",
                "SOLUTION_FILL_COMPLETED",
                "EMERGENCY_STOP_ACTIVATED",
            ),
            max_age_sec=86400,  # config-literal: one-day storage-event replay window
        )
        recent_event_type = str((recent_storage_event or {}).get("event_type") or "").strip().upper()
        if recent_event_type == "SOLUTION_FILL_SOURCE_EMPTY":
            self._ports.observe_fail_safe_transition()(
                task=task,
                reason="solution_fill_source_empty",
                source="node_event",
                next_stage="solution_fill_source_empty_stop",
            )
            return StageOutcome(kind="transition", next_stage="solution_fill_source_empty_stop")
        if recent_event_type == "SOLUTION_FILL_LEAK_DETECTED":
            self._ports.observe_fail_safe_transition()(
                task=task,
                reason="solution_fill_leak_detected",
                source="node_event",
                next_stage="solution_fill_leak_stop",
            )
            return StageOutcome(kind="transition", next_stage="solution_fill_leak_stop")
        if recent_event_type == "EMERGENCY_STOP_ACTIVATED":
            await self._ports.reconcile_recent_emergency_stop()(
                task=task,
                plan=plan,
                now=now,
                expected={
                    "valve_clean_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
            )
        if recent_event_type == "SOLUTION_FILL_COMPLETED":
            return await self._ports.completed_outcome(task=task, plan=plan, now=now, runtime=runtime)

        # Stop до ON probe: насос уже может быть выключен flow interrupt'ом.
        if pending_manual_step == "solution_fill_stop":
            if str(getattr(task, "task_type", "") or "").strip().lower() == "solution_change":
                return StageOutcome(kind="transition", next_stage="solution_fill_stop_to_refill_confirm")
            if await self._ports.should_finish_to_ready(task=task, plan=plan, now=now, runtime=runtime):
                return StageOutcome(kind="transition", next_stage="solution_fill_stop_to_ready")
            return StageOutcome(kind="transition", next_stage="solution_fill_stop_to_prepare")

        try:
            await self._ports.probe_irr_state()(
                task=task,
                plan=plan,
                now=now,
                expected={
                    "valve_clean_supply": True,
                    "valve_solution_fill": True,
                    "pump_main": True,
                },
            )
        except TaskExecutionError as exc:
            if exc.code == "irr_state_mismatch":
                raced_completion_event = await self._ports.read_recent_storage_event()(
                    task=task,
                    event_types=("SOLUTION_FILL_COMPLETED",),
                    max_age_sec=86400,  # config-literal: one-day completion-event replay window
                )
                raced_event_type = str((raced_completion_event or {}).get("event_type") or "").strip().upper()
                if raced_event_type == "SOLUTION_FILL_COMPLETED":
                    self._ports.global_logger().info(
                        "solution_fill_check: probe увидел уже выключенный fill-state, но node успела опубликовать completion; завершаем штатно zone_id=%s task_id=%s",
                        task.zone_id,
                        getattr(task, "id", None),
                    )
                    return await self._ports.completed_outcome(task=task, plan=plan, now=now, runtime=runtime)
            raise

        flow_hold = await self._ports.handle_control_mode_flow_path_interrupt()(
            task=task,
            plan=plan,
            now=now,
            control_mode=control_mode,
        )
        if flow_hold is not None:
            return flow_hold

        clean_min_check_delay_ms = int(fail_safe_guards.solution_fill_clean_min_check_delay_ms)
        if self._ports.stage_elapsed_ms()(task=task, now=now) >= max(0, clean_min_check_delay_ms):
            clean_min = await self._ports.read_level()(
                task=task,
                zone_id=task.zone_id,
                labels=runtime.clean_min_sensor_labels,
                threshold=runtime.level_switch_on_threshold,
                telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
                unavailable_error="two_tank_clean_min_level_unavailable",
                stale_error="two_tank_clean_min_level_stale",
                stale_recheck_delay_sec=self._ports.stale_recheck_delay_sec(),
                prefer_probe_snapshot=True,
            )
            if not clean_min["is_triggered"]:
                self._ports.observe_fail_safe_transition()(
                    task=task,
                    reason="solution_fill_source_empty",
                    source="sensor",
                    next_stage="solution_fill_source_empty_stop",
                )
                return StageOutcome(kind="transition", next_stage="solution_fill_source_empty_stop")

        solution_min_check_delay_ms = int(fail_safe_guards.solution_fill_solution_min_check_delay_ms)
        if self._ports.stage_elapsed_ms()(task=task, now=now) >= max(0, solution_min_check_delay_ms):
            solution_min = await self._ports.read_level()(
                task=task,
                zone_id=task.zone_id,
                labels=runtime.solution_min_sensor_labels,
                threshold=runtime.level_switch_on_threshold,
                telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
                unavailable_error="two_tank_solution_min_level_unavailable",
                stale_error="two_tank_solution_min_level_stale",
                stale_recheck_delay_sec=self._ports.stale_recheck_delay_sec(),
                prefer_probe_snapshot=True,
            )
            if not solution_min["is_triggered"]:
                self._ports.observe_fail_safe_transition()(
                    task=task,
                    reason="solution_fill_leak_detected",
                    source="sensor",
                    next_stage="solution_fill_leak_stop",
                )
                return StageOutcome(kind="transition", next_stage="solution_fill_leak_stop")

        solution_max = await self._ports.read_level()(
            task=task,
            zone_id=task.zone_id,
            labels=runtime.solution_max_sensor_labels,
            threshold=runtime.level_switch_on_threshold,
            telemetry_max_age_sec=int(runtime.telemetry_max_age_sec),
            unavailable_error="two_tank_solution_level_unavailable",
            stale_error="two_tank_solution_level_stale",
            stale_recheck_delay_sec=self._ports.stale_recheck_delay_sec(),
            prefer_probe_snapshot=True,
        )

        if solution_max["is_triggered"]:
            return await self._ports.completed_outcome(task=task, plan=plan, now=now, runtime=runtime)

        # Проверка дедлайна
        deadline = task.workflow.stage_deadline_at
        if self._ports.deadline_reached()(now=now, deadline=deadline):
            self._ports.global_logger().warning(
                "solution_fill_check: дедлайн превышен, заполнение останавливается zone_id=%s", task.zone_id
            )
            self._ports.global_stage_deadline_exceeded().labels(
                topology=str(getattr(task, "topology", "") or ""),
                stage="solution_fill_check",
            ).inc()
            try:
                await note_upward_report(
                    code="biz_solution_fill_timeout",
                    alert_type="AE3 Solution Fill Timeout",
                    message="Превышено время заполнения бака раствором до завершения этапа.",
                    severity="warning",
                    zone_id=int(task.zone_id),
                    details={
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "topology": str(getattr(task, "topology", "") or ""),
                        "stage": "solution_fill_check",
                        "component": "handler:solution_fill_check",
                        "message": "Превышено время заполнения бака раствором; проверьте клапан подачи раствора и насос.",
                    },
                    scope_parts=("stage:solution_fill_check",),
                )
            except Exception:
                # Audit F9: include full exception context so downstream debugging
                # of failed alert delivery isn't blocked by a message without
                # zone/task identification.
                self._ports.global_logger().warning(
                    "Не удалось отправить alert biz_solution_fill_timeout zone_id=%s task_id=%s",
                    task.zone_id,
                    getattr(task, "id", None),
                    exc_info=True,
                )
            return StageOutcome(kind="transition", next_stage="solution_fill_timeout_stop")

        # Fill doses calcium only → gate is EC-only to T_ca (skip pH).
        if await self._ports.fill_ec_target_reached(task=task, plan=plan, now=now, runtime=runtime):
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime.level_poll_interval_sec),
            )

        if int(getattr(task.workflow, "stage_retry_count", 0) or 0) > 0:
            self._ports.global_logger().info(
                "solution_fill_check: in-flow correction уже исчерпана, заполнение продолжается без новой коррекции zone_id=%s retry_count=%s",
                task.zone_id,
                getattr(task.workflow, "stage_retry_count", 0),
            )
            return StageOutcome(
                kind="poll",
                due_delay_sec=int(runtime.level_poll_interval_sec),
            )

        self._ports.global_logger().info(
            "solution_fill_check: заполнение продолжается, цели не достигнуты; вход в in-flow correction zone_id=%s",
            task.zone_id,
        )
        corr = await self._ports.enter_fill_calcium_correction(
            task=task,
            plan=plan,
            runtime=runtime,
            now=now,
            return_stage_success=stage_def.on_corr_success or "solution_fill_check",
            return_stage_fail=stage_def.on_corr_fail or "solution_fill_check",
        )
        return StageOutcome(kind="enter_correction", correction=corr, task_override=task)

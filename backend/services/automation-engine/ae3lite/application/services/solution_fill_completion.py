"""SolutionFillCheckHandler completion: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ae3lite.application.dto.stage_outcome import StageOutcome


@dataclass(frozen=True)
class SolutionFillCompletionPorts:
    stale_recheck_delay_sec: Callable[[], Any]
    check_sensor_consistency: Callable[[], Any]
    finish_ready_or_irrigation_short_circuit: Callable[[], Any]
    read_level: Callable[[], Any]
    global_logger: Callable[..., Any]


class SolutionFillCompletion:
    def __init__(self, ports: SolutionFillCompletionPorts) -> None:
        self._ports = ports

    async def should_finish_to_ready(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> bool:
        if runtime is None:
            runtime = plan.runtime
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
        if not solution_max["is_triggered"]:
            return False

        await self._ports.check_sensor_consistency()(
            task=task,
            runtime=runtime,
            min_labels_key="solution_min_sensor_labels",
            min_unavailable_error="two_tank_solution_min_level_unavailable",
            min_stale_error="two_tank_solution_min_level_stale",
            stale_recheck_delay_sec=self._ports.stale_recheck_delay_sec(),
            prefer_probe_snapshot=True,
        )
        return await self._ports.finish_ready_or_irrigation_short_circuit()(
            task=task,
            plan=plan,
            now=now,
            runtime=runtime,
        )

    async def completed_outcome(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        runtime: Any = None,
    ) -> StageOutcome:
        if runtime is None:
            runtime = plan.runtime
        await self._ports.check_sensor_consistency()(
            task=task,
            runtime=runtime,
            min_labels_key="solution_min_sensor_labels",
            min_unavailable_error="two_tank_solution_min_level_unavailable",
            min_stale_error="two_tank_solution_min_level_stale",
            stale_recheck_delay_sec=self._ports.stale_recheck_delay_sec(),
            prefer_probe_snapshot=True,
        )

        if str(getattr(task, "task_type", "") or "").strip().lower() == "solution_change":
            self._ports.global_logger().info(
                "solution_fill_check: refill завершён, ожидание operator confirm (G2) zone_id=%s",
                task.zone_id,
            )
            return StageOutcome(
                kind="transition",
                next_stage="solution_fill_stop_to_refill_confirm",
            )

        if await self._ports.finish_ready_or_irrigation_short_circuit()(
            task=task,
            plan=plan,
            now=now,
            runtime=runtime,
        ):
            self._ports.global_logger().info(
                "solution_fill_check: бак полон и раствор в prepare-band или irrigation short-circuit → ready "
                "zone_id=%s",
                task.zone_id,
            )
            return StageOutcome(
                kind="transition",
                next_stage="solution_fill_stop_to_ready",
            )

        self._ports.global_logger().info(
            "solution_fill_check: бак заполнен, но цели не достигнуты; переход в prepare recirculation zone_id=%s",
            task.zone_id,
        )
        return StageOutcome(
            kind="transition",
            next_stage="solution_fill_stop_to_prepare",
        )

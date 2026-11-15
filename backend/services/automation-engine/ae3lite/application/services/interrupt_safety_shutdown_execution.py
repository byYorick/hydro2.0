"""interrupt safety shutdown execution: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

from ae3lite.application.services.interrupt_safety_records import (
    CorrectionInterruptFailSafeStopResult,
    CorrectionInterruptPendingCheck,
    _FakeTaskForFailSafe,
)


@dataclass(frozen=True)
class InterruptSafetyShutdownExecutionPorts:
    logger: Callable[..., Any]
    normalize_fail_safe_actuators: Callable[..., Any]
    topology_fail_safe_on_flow: Callable[..., Any]
    build_fail_safe_shutdown_commands: Callable[..., Any]
    load_irrig_fail_safe_actuators: Callable[..., Any]


class InterruptSafetyShutdownExecution:
    def __init__(self, ports: InterruptSafetyShutdownExecutionPorts) -> None:
        self._ports = ports

    async def attempt_task_fail_safe_shutdown(
        self,
        *,
        task: Any,
        now: datetime,
        command_gateway: Any | None,
        snapshot_actuators: Sequence[Any] | None,
        planner_step_prefix: str,
    ) -> CorrectionInterruptFailSafeStopResult:
        """Publish-only OFF irrig actuators through history-logger gateway.

        Does not skip inactive/failed tasks: ae_commands still need a valid task_id FK.
        Skip only when there is no gateway or no irrig fail-safe actuators.
        """
        if command_gateway is None or not callable(getattr(command_gateway, "run_publish_only_batch", None)):
            return CorrectionInterruptFailSafeStopResult(
                attempted=False,
                success=False,
                reason="no_command_gateway",
            )

        topology = str(getattr(task, "topology", "") or "").strip().lower()
        if not self._ports.topology_fail_safe_on_flow(topology):
            return CorrectionInterruptFailSafeStopResult(
                attempted=False,
                success=False,
                reason=f"unsupported_topology:{topology}",
            )

        actuators: tuple[Mapping[str, Any], ...]
        if snapshot_actuators is not None:
            actuators = self._ports.normalize_fail_safe_actuators(snapshot_actuators)
        else:
            try:
                actuators = await self._ports.load_irrig_fail_safe_actuators(zone_id=int(task.zone_id))
            except Exception:
                self._ports.logger().warning(
                    "AE3 fail-safe shutdown: не удалось загрузить irrig actuators zone_id=%s task_id=%s",
                    getattr(task, "zone_id", None),
                    getattr(task, "id", None),
                    exc_info=True,
                )
                return CorrectionInterruptFailSafeStopResult(
                    attempted=False,
                    success=False,
                    reason="actuators_load_failed",
                )
        commands = self._ports.build_fail_safe_shutdown_commands(
            actuators=actuators,
            planner_step_prefix=planner_step_prefix,
        )
        if not commands:
            return CorrectionInterruptFailSafeStopResult(
                attempted=False,
                success=False,
                reason="no_irrig_actuators",
            )

        try:
            result = await command_gateway.run_publish_only_batch(
                task=task,
                commands=commands,
                now=now,
            )
        except Exception as exc:
            self._ports.logger().warning(
                "AE3 fail-safe shutdown: publish failed zone_id=%s task_id=%s",
                getattr(task, "zone_id", None),
                getattr(task, "id", None),
                exc_info=True,
            )
            return CorrectionInterruptFailSafeStopResult(
                attempted=True,
                success=False,
                reason=f"publish_exception:{type(exc).__name__}",
                commands_total=len(commands),
            )

        success = bool(isinstance(result, Mapping) and result.get("success"))
        if success:
            return CorrectionInterruptFailSafeStopResult(
                attempted=True,
                success=True,
                reason="publish_accepted_unconfirmed",
                commands_total=len(commands),
                confirmed=False,
            )
        error_code = (
            str(result.get("error_code") or "publish_failed") if isinstance(result, Mapping) else "publish_failed"
        )
        self._ports.logger().error(
            "AE3 fail-safe shutdown non-success zone_id=%s task_id=%s error_code=%s",
            getattr(task, "zone_id", None),
            getattr(task, "id", None),
            error_code,
        )
        return CorrectionInterruptFailSafeStopResult(
            attempted=True,
            success=False,
            reason=error_code,
            commands_total=len(commands),
        )

    async def attempt_correction_interrupt_fail_safe_stop(
        self, *, check: CorrectionInterruptPendingCheck, now: datetime, command_gateway: Any | None
    ) -> CorrectionInterruptFailSafeStopResult:
        """Publish-only fail-safe OFF irrig actuators через history-logger gateway.

        Не ждёт terminal DONE (как ExecuteTaskUseCase._attempt_fail_safe_shutdown).
        Не требует active task: failed task_id остаётся валидным FK для ae_commands.
        """
        if command_gateway is None or not callable(getattr(command_gateway, "run_publish_only_batch", None)):
            return CorrectionInterruptFailSafeStopResult(
                attempted=False,
                success=False,
                reason="no_command_gateway",
            )

        topology = str(check.topology or "").strip().lower()
        if not self._ports.topology_fail_safe_on_flow(topology):
            return CorrectionInterruptFailSafeStopResult(
                attempted=False,
                success=False,
                reason=f"unsupported_topology:{topology}",
            )

        try:
            actuators = await self._ports.load_irrig_fail_safe_actuators(zone_id=int(check.zone_id))
        except Exception:
            self._ports.logger().warning(
                "AE3 correction interrupt: не удалось загрузить irrig actuators zone_id=%s",
                check.zone_id,
                exc_info=True,
            )
            return CorrectionInterruptFailSafeStopResult(
                attempted=False,
                success=False,
                reason="actuators_load_failed",
            )
        commands = self._ports.build_fail_safe_shutdown_commands(actuators=actuators)
        if not commands:
            return CorrectionInterruptFailSafeStopResult(
                attempted=False,
                success=False,
                reason="no_irrig_actuators",
            )

        task = _FakeTaskForFailSafe(check)
        try:
            result = await command_gateway.run_publish_only_batch(
                task=task,
                commands=commands,
                now=now,
            )
        except Exception as exc:
            self._ports.logger().warning(
                "AE3 correction interrupt: fail-safe publish failed zone_id=%s task_id=%s",
                check.zone_id,
                check.task_id,
                exc_info=True,
            )
            return CorrectionInterruptFailSafeStopResult(
                attempted=True,
                success=False,
                reason=f"publish_exception:{type(exc).__name__}",
                commands_total=len(commands),
            )

        success = bool(isinstance(result, Mapping) and result.get("success"))
        if success:
            self._ports.logger().info(
                "AE3 correction interrupt fail-safe stop published zone_id=%s task_id=%s commands=%s",
                check.zone_id,
                check.task_id,
                len(commands),
            )
            return CorrectionInterruptFailSafeStopResult(
                attempted=True,
                success=True,
                reason="ok",
                commands_total=len(commands),
            )
        error_code = (
            str(result.get("error_code") or "publish_failed") if isinstance(result, Mapping) else "publish_failed"
        )
        self._ports.logger().error(
            "AE3 correction interrupt fail-safe stop non-success zone_id=%s task_id=%s error_code=%s",
            check.zone_id,
            check.task_id,
            error_code,
        )
        return CorrectionInterruptFailSafeStopResult(
            attempted=True,
            success=False,
            reason=error_code,
            commands_total=len(commands),
        )

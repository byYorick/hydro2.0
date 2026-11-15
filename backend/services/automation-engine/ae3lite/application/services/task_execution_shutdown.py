"""ExecuteTaskUseCase shutdown: explicit collaborators and invocation context."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.application.services.task_execution_shared import logger
from ae3lite.application.services.workflow_topology import TopologyRegistry
from ae3lite.domain.claim_fence import same_claim_token
from ae3lite.infrastructure.metrics import FLOW_STOP_FAILED, inc_observability_write_failed


@dataclass(frozen=True)
class TaskExecutionShutdownPorts:
    attempt_fail_safe_shutdown: Callable[..., Awaitable[Any]]
    command_gateway: Callable[[], Any]
    failure_state: Callable[..., Any]
    task_repository: Callable[[], Any]
    global_send_biz_alert: Callable[..., Any]


class TaskExecutionShutdown:
    def __init__(self, ports: TaskExecutionShutdownPorts) -> None:
        self._ports = ports

    async def shutdown_once(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        state = self._ports.failure_state(task)
        if state.get("shutdown_attempted"):
            return
        state["shutdown_attempted"] = True
        await self._ports.attempt_fail_safe_shutdown(
            task=task,
            snapshot=snapshot,
            plan=plan,
            now=now,
        )

    async def shutdown_terminal_flow_if_needed(
        self,
        *,
        terminal_task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        status = str(getattr(terminal_task, "status", "") or "").strip().lower()
        if status not in {"failed", "cancelled"}:
            return
        from ae3lite.application.handlers.flow_path_guard import (
            should_fail_safe_shutdown_on_task_fail,
        )

        if not should_fail_safe_shutdown_on_task_fail(terminal_task):
            return
        await self.shutdown_once(
            task=terminal_task,
            snapshot=snapshot,
            plan=plan,
            now=now,
        )

    async def attempt_fail_safe_shutdown(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
    ) -> None:
        topology = str(getattr(plan, "topology", "") or getattr(task, "topology", "")).strip().lower()
        pack = TopologyRegistry().try_pack(topology)
        if pack is None or not pack.fail_safe_on_flow:
            return
        get_task_by_id = getattr(self._ports.task_repository(), "get_by_id", None)
        if callable(get_task_by_id):
            try:
                current_task = await get_task_by_id(task_id=int(getattr(task, "id", 0) or 0))
            except Exception:
                logger.warning(
                    "AE3 fail-safe shutdown preflight не смог загрузить состояние задачи: task_id=%s zone_id=%s",
                    getattr(task, "id", None),
                    getattr(task, "zone_id", None),
                    exc_info=True,
                )
                current_task = None
            # Inactive/missing task still needs hardware stop; keep original task as FK.
            if current_task is not None:
                if not same_claim_token(task, current_task) and str(current_task.status) in {
                    "pending",
                    "claimed",
                    "running",
                    "waiting_command",
                }:
                    logger.warning("AE3 stale failure cannot stop new claim: task_id=%s", task.id)
                    return
                # Never borrow a newer claim's authority for a shutdown.
        from ae3lite.application.services.correction_interrupt_safety import (
            attempt_task_fail_safe_shutdown,
        )

        # Empty snapshot actuators must not skip: pass None so DB fallback loads irrig channels.
        snapshot_actuators = getattr(snapshot, "actuators", None) if snapshot is not None else None
        if not snapshot_actuators:
            snapshot_actuators = None

        try:
            result = await attempt_task_fail_safe_shutdown(
                task=task,
                now=now,
                command_gateway=self._ports.command_gateway(),
                snapshot_actuators=snapshot_actuators,
                planner_step_prefix="execute_task_fail_safe",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "AE3 fail-safe shutdown batch завершился ошибкой: task_id=%s zone_id=%s",
                getattr(task, "id", None),
                getattr(task, "zone_id", None),
            )
            await self.emit_fail_safe_shutdown_alert(
                task=task,
                reason="fail_safe_shutdown_exception",
                error_code=str(getattr(exc, "code", "") or type(exc).__name__),
            )
            return

        if not result.attempted:
            reason = str(result.reason or "not_attempted")
            if reason == "actuators_load_failed":
                await self.emit_fail_safe_shutdown_alert(
                    task=task,
                    reason="actuators_load_failed",
                    error_code="actuators_load_failed",
                )
                return
            self.log_skip_fail_safe_shutdown(task=task, reason=reason)
            return
        if bool(getattr(result, "confirmed", False)):
            logger.error(
                "AE3 fail-safe shutdown вернул confirmed без probe: task_id=%s zone_id=%s reason=%s",
                getattr(task, "id", None),
                getattr(task, "zone_id", None),
                result.reason,
            )
        if result.success or str(result.reason or "") == "publish_accepted_unconfirmed":
            return
        reason = str(result.reason or "unknown")
        if reason.startswith("publish_exception:"):
            await self.emit_fail_safe_shutdown_alert(
                task=task,
                reason="fail_safe_shutdown_exception",
                error_code=reason.split(":", 1)[1] or "unknown",
            )
            return
        logger.error(
            "AE3 fail-safe shutdown batch вернул non-success: task_id=%s zone_id=%s stage=%s error_code=%s",
            getattr(task, "id", None),
            getattr(task, "zone_id", None),
            str(getattr(task, "current_stage", "") or "unknown"),
            reason,
        )
        await self.emit_fail_safe_shutdown_alert(
            task=task,
            reason="fail_safe_shutdown_non_success",
            error_code=reason,
        )

    async def emit_fail_safe_shutdown_alert(
        self,
        *,
        task: Any,
        reason: str,
        error_code: str,
    ) -> None:
        stage = str(getattr(task, "current_stage", "") or "unknown")
        FLOW_STOP_FAILED.labels(stage=stage or "unknown").inc()
        try:
            await self._ports.global_send_biz_alert(
                zone_id=int(task.zone_id),
                code="biz_flow_stop_failed_hardware_may_be_active",
                severity="critical",
                message="Не удалось подтвердить остановку flow-path; оборудование может оставаться активным",
                details={
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "stage": stage,
                    "reason": reason,
                    "error_code": error_code,
                },
                scope_parts=(f"stage:{stage}",),
            )
        except Exception:
            inc_observability_write_failed(kind="biz_alert")
            logger.warning(
                "AE3 fail-safe shutdown: не удалось создать biz-alert zone_id=%s task_id=%s",
                getattr(task, "zone_id", None),
                getattr(task, "id", None),
                exc_info=True,
            )

    def log_skip_fail_safe_shutdown(self, *, task: Any, reason: str) -> None:
        logger.info(
            "AE3 пропускает fail-safe shutdown: task_id=%s zone_id=%s reason=%s",
            getattr(task, "id", None),
            getattr(task, "zone_id", None),
            reason,
        )

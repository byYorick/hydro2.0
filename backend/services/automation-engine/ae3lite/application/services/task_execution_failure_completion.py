"""ExecuteTaskUseCase failure completion: explicit collaborators and invocation context."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.services.task_execution_shared import (
    TASK_EXECUTION_LEASE_LOST_CANCEL_MSG,
    TASK_EXECUTION_OVERALL_DEADLINE_CANCEL_MSG,
    TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
    logger,
)
from ae3lite.application.services.task_failed_alert import emit_task_failed_alert
from ae3lite.domain.claim_fence import claim_generation, claim_owner, same_claim_token


@dataclass(frozen=True)
class TaskExecutionFailureCompletionPorts:
    alert_repository: Callable[[], Any]
    build_failure_observability_details: Callable[..., Awaitable[Any]]
    failure_states: Callable[[], Any]
    finalize_task_use_case: Callable[[], Any]
    shutdown_once: Callable[..., Awaitable[Any]]
    sync_workflow_failure_state: Callable[..., Awaitable[Any]]
    task_repository: Callable[[], Any]
    workflow_repository: Callable[[], Any]
    global_create_zone_event: Callable[..., Any]
    global_publish_upward_reports: Callable[..., Any]


class TaskExecutionFailureCompletion:
    def __init__(self, ports: TaskExecutionFailureCompletionPorts) -> None:
        self._ports = ports

    async def fail_closed(
        self,
        *,
        task: Any,
        owner: str,
        error_code: str,
        error_message: str,
        now: datetime,
        extra_details: Mapping[str, Any] | None = None,
        upward_reports: tuple[Any, ...] = (),
    ) -> Any:
        get_task = getattr(self._ports.task_repository(), "get_by_id", None)
        if callable(get_task):
            current = await get_task(task_id=task.id)
            if (
                current is not None
                and str(current.status) in {"pending", "claimed", "running", "waiting_command"}
                and not same_claim_token(task, current)
            ):
                return current
        extra_details = dict(extra_details) if isinstance(extra_details, Mapping) else {}
        if upward_reports:
            await self._ports.global_publish_upward_reports(upward_reports)
        timeout_observability = await self._ports.build_failure_observability_details(
            task=task,
            error_code=error_code,
            now=now,
        )
        if isinstance(timeout_observability, Mapping):
            for key, value in timeout_observability.items():
                if key not in extra_details:
                    extra_details[key] = value
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        task_still_exists = await self.task_still_exists(task=task)
        if task_still_exists:
            await self._ports.sync_workflow_failure_state(task=task, now=now, fail_closed=True)
            await self.emit_task_failed_alert(
                task=task,
                error_code=error_code,
                error_message=error_message,
                now=now,
                extra_details=extra_details,
            )
        else:
            logger.info(
                "AE3 fail-closed skipping zone-bound side-effects because task was already cleaned up: zone_id=%s task_id=%s",
                zone_id,
                int(getattr(task, "id", 0) or 0),
            )
        try:
            startup_probe_timeout = extra_details.get("startup_probe_timeout")
            if task_still_exists and isinstance(startup_probe_timeout, Mapping):
                await self._ports.global_create_zone_event(
                    zone_id,
                    "AE_STARTUP_PROBE_TIMEOUT",
                    {
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "stage": str(getattr(task, "current_stage", "") or ""),
                        "topology": str(getattr(task, "topology", "") or ""),
                        **dict(startup_probe_timeout),
                    },
                )
            if task_still_exists:
                await self._ports.global_create_zone_event(
                    zone_id,
                    "AE_TASK_FAILED",
                    {
                        "task_id": int(getattr(task, "id", 0) or 0),
                        "error_code": str(error_code),
                        "error_message": str(error_message),
                        "stage": str(getattr(task, "current_stage", "") or ""),
                        "topology": str(getattr(task, "topology", "") or ""),
                        **extra_details,
                    },
                )
        except Exception:
            logger.warning(
                "AE3 не смог записать событие AE_TASK_FAILED zone_id=%s task_id=%s error_code=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                error_code,
                exc_info=True,
            )
        return await self._ports.finalize_task_use_case().fail_closed(
            task=task,
            owner=owner,
            error_code=error_code,
            error_message=error_message,
            now=now,
        )

    async def apply_terminal_task_side_effects(self, *, task: Any, now: datetime) -> None:
        """Side-effects для terminal task, помеченного вне fail_closed (gateway/router)."""
        status = str(getattr(task, "status", "") or "").strip().lower()
        if status != "failed":
            return
        await self._ports.sync_workflow_failure_state(task=task, now=now)
        error_code = (
            str(getattr(task, "error_code", "") or "ae3_task_execution_failed").strip() or "ae3_task_execution_failed"
        )
        error_message = str(getattr(task, "error_message", "") or "Задача завершилась с ошибкой")
        await self.emit_task_failed_alert(
            task=task,
            error_code=error_code,
            error_message=error_message,
            now=now,
        )

    async def sync_workflow_failure_state(
        self,
        *,
        task: Any,
        now: datetime,
        fail_closed: bool = False,
    ) -> None:
        if self._ports.workflow_repository() is None:
            return
        from ae3lite.domain.errors import ErrorCodes
        from ae3lite.domain.services.workflow_failure_rollback import (
            resolve_workflow_phase_after_task_failure,
        )
        from ae3lite.domain.services.workflow_state_sync import (
            WorkflowStateSyncError,
            upsert_workflow_phase_strict,
        )

        rollback_phase = resolve_workflow_phase_after_task_failure(task)
        # irrig_recirc: legacy compat only for old tasks.
        scheduler_task_id = (
            None if rollback_phase in {"ready", "irrig_recirc"} else str(getattr(task, "id", "") or "") or None
        )
        payload = {
            "ae3_cycle_start_stage": str(getattr(task, "current_stage", "") or ""),
            "ae3_failure_rollback": True,
            "ae3_failed_task_id": int(getattr(task, "id", 0) or 0) or None,
        }
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        task_id = int(getattr(task, "id", 0) or 0)
        try:
            await upsert_workflow_phase_strict(
                self._ports.workflow_repository(),
                zone_id=zone_id,
                workflow_phase=rollback_phase,
                payload=payload,
                scheduler_task_id=scheduler_task_id,
                now=now,
            )
        except WorkflowStateSyncError:
            logger.error(
                "AE3 не смог синхронизировать zone_workflow_state в fail-closed path zone_id=%s task_id=%s phase=%s",
                zone_id,
                task_id,
                rollback_phase,
                exc_info=True,
            )
            try:
                await self._ports.global_create_zone_event(
                    zone_id,
                    "AE_WORKFLOW_STATE_SYNC_FAILED",
                    {
                        "task_id": task_id,
                        "workflow_phase": rollback_phase,
                        "ae3_failure_rollback": True,
                        "error_code": ErrorCodes.AE3_WORKFLOW_STATE_SYNC_FAILED,
                    },
                )
            except Exception:
                logger.warning(
                    "AE3 не смог записать AE_WORKFLOW_STATE_SYNC_FAILED zone_id=%s task_id=%s",
                    zone_id,
                    task_id,
                    exc_info=True,
                )
            if not fail_closed:
                raise

    async def task_still_exists(self, *, task: Any) -> bool:
        get_by_id = getattr(self._ports.task_repository(), "get_by_id", None)
        if not callable(get_by_id):
            return True
        current = await get_by_id(task_id=int(getattr(task, "id", 0) or 0))
        return current is not None

    async def emit_task_failed_alert(
        self,
        *,
        task: Any,
        error_code: str,
        error_message: str,
        now: datetime,
        extra_details: Mapping[str, Any] | None = None,
    ) -> None:
        await emit_task_failed_alert(
            alert_repository=self._ports.alert_repository(),
            task=task,
            error_code=error_code,
            error_message=error_message,
            now=now,
            extra_details=extra_details,
        )

    def failure_key(self, task: Any) -> tuple[int, str, int]:
        return int(task.id), claim_owner(task), claim_generation(task)

    def failure_state(self, task: Any) -> dict[str, Any]:
        key = self.failure_key(task)
        if key not in self._ports.failure_states():
            # Bound completed-claim bookkeeping; never evict an in-flight failure.
            for old_key, state in list(self._ports.failure_states().items()):
                if len(self._ports.failure_states()) < 1024:
                    break
                if state.get("inflight") is None:
                    del self._ports.failure_states()[old_key]
            self._ports.failure_states()[key] = {}
        return self._ports.failure_states()[key]

    def clear_failure_guards(self, task: Any) -> None:
        self._ports.failure_states().pop(self.failure_key(task), None)

    def is_guarded_task_cancellation(self, exc: BaseException) -> bool:
        """Timeout и lease-lost — помеченные отмены safety-path. Голый CancelledError — нет."""
        if not isinstance(exc, asyncio.CancelledError):
            return False
        return (
            self.is_timeout_cancellation(exc)
            or self.is_lease_lost_cancellation(exc)
            or self.is_overall_deadline_cancellation(exc)
        )

    async def complete_execution_failure(
        self,
        *,
        task: Any,
        snapshot: Any,
        plan: Any,
        now: datetime,
        owner: str,
        error_code: str,
        error_message: str,
        extra_details: Mapping[str, Any] | None = None,
        upward_reports: tuple[Any, ...] = (),
    ) -> Any:
        """Общий safety-path: stop доступных актуаторов, затем terminal fail.

        Повторный вход не шлёт новый ordinary batch и не зацикливает stop/fail.
        Запись failed сама по себе остановкой не считается.
        """
        state = self.failure_state(task)
        if "result" in state:
            return state["result"]
        inflight = state.get("inflight")
        if inflight is not None:
            if state.get("caller") is asyncio.current_task():
                return task
            return await asyncio.shield(inflight)
        completion = asyncio.get_running_loop().create_future()
        state["inflight"] = completion
        state["caller"] = asyncio.current_task()
        try:
            await self._ports.shutdown_once(task=task, snapshot=snapshot, plan=plan, now=now)
            result = await self.fail_closed(
                task=task,
                owner=owner,
                error_code=error_code,
                error_message=error_message,
                now=now,
                extra_details=extra_details,
                upward_reports=upward_reports,
            )
            state["result"] = result
            completion.set_result(result)
            return result
        except BaseException:
            completion.cancel()
            raise
        finally:
            state["inflight"] = None
            state.pop("caller", None)

    async def load_terminal_task_or_none(self, *, task_id: int, fallback_task: Any) -> Any | None:
        if task_id <= 0:
            task = fallback_task
        else:
            get_task_by_id = getattr(self._ports.task_repository(), "get_by_id", None)
            if callable(get_task_by_id):
                try:
                    task = await get_task_by_id(task_id=task_id)
                except Exception:
                    logger.warning(
                        "AE3 не смог загрузить текущее состояние задачи для terminal short-circuit: task_id=%s",
                        task_id,
                        exc_info=True,
                    )
                    task = fallback_task
            else:
                task = fallback_task
        if task is None or bool(getattr(task, "is_active", False)):
            if fallback_task is None or bool(getattr(fallback_task, "is_active", False)):
                return None
            return fallback_task
        return task

    def is_timeout_cancellation(self, exc: asyncio.CancelledError) -> bool:
        return any(str(arg) == TASK_EXECUTION_TIMEOUT_CANCEL_MSG for arg in getattr(exc, "args", ()))

    def is_lease_lost_cancellation(self, exc: asyncio.CancelledError) -> bool:
        return any(str(arg) == TASK_EXECUTION_LEASE_LOST_CANCEL_MSG for arg in getattr(exc, "args", ()))

    def is_overall_deadline_cancellation(self, exc: asyncio.CancelledError) -> bool:
        return any(str(arg) == TASK_EXECUTION_OVERALL_DEADLINE_CANCEL_MSG for arg in getattr(exc, "args", ()))

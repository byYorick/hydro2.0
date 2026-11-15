"""Ae3RuntimeWorker execution: explicit collaborators and invocation context."""

from __future__ import annotations

import asyncio
import types
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable

from ae3lite.application.use_cases.execute_task import (
    TASK_EXECUTION_LEASE_LOST_CANCEL_MSG,
    TASK_EXECUTION_OVERALL_DEADLINE_CANCEL_MSG,
    TASK_EXECUTION_TIMEOUT_CANCEL_MSG,
)
from ae3lite.domain.task_deadline import overall_deadline_remaining_sec
from ae3lite.infrastructure.log_context import log_context_scope
from ae3lite.infrastructure.metrics import (
    ACTIVE_TASKS,
    TASK_EXECUTION_CRASHED,
    TICK_DURATION,
    TICK_ERRORS,
    ZONE_LEASE_RELEASE_FAILED,
)
from ae3lite.runtime.worker_runtime_state import WorkerRuntimeState


@dataclass(frozen=True)
class WorkerRuntimeExecutionPorts:
    abort_task_after_intent_sync_failure: Callable[..., Awaitable[Any]]
    execute_task_use_case: Callable[[], Any]
    lease_heartbeat: Callable[..., Awaitable[Any]]
    log_debug: Callable[..., Any]
    logger: Callable[[], Any]
    max_task_execution_sec: Callable[[], Any]
    maybe_resolve_zone_lease_release_alert: Callable[..., Awaitable[Any]]
    now_fn: Callable[..., Any]
    owner: Callable[[], Any]
    safe_mark_intent_running: Callable[..., Awaitable[Any]]
    safe_mark_intent_terminal: Callable[..., Awaitable[Any]]
    spawn_background_task_fn: Callable[..., Any]
    task_repository: Callable[[], Any]
    zone_lease_repository: Callable[[], Any]
    global_send_infra_alert: Callable[..., Any]


class WorkerRuntimeExecution:
    def __init__(self, ports: WorkerRuntimeExecutionPorts, state: WorkerRuntimeState) -> None:
        self._ports = ports
        self._state = state

    async def execute_claimed_task_safe(self, *, task: Any) -> None:
        trace_id = self.task_trace_id(task)
        context_kwargs: dict[str, Any] = {
            "task_id": getattr(task, "id", None),
            "zone_id": getattr(task, "zone_id", None),
        }
        if trace_id:
            context_kwargs["trace_id"] = trace_id
        with log_context_scope(**context_kwargs):
            try:
                await self.execute_claimed_task(task=task)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error_name = type(exc).__name__
                TASK_EXECUTION_CRASHED.labels(error=error_name).inc()
                self._ports.logger().error(
                    "AE3 task execution crashed outside the pre-release safety-path: "
                    "zone_id=%s task_id=%s owner=%s error_type=%s",
                    getattr(task, "zone_id", None),
                    getattr(task, "id", None),
                    self._ports.owner(),
                    error_name,
                    exc_info=True,
                )

    @staticmethod
    def task_trace_id(task: Any) -> str | None:
        intent_meta = getattr(task, "intent_meta", None)
        if not isinstance(intent_meta, dict):
            return None
        trace_id = str(intent_meta.get("trace_id") or "").strip()
        return trace_id or None

    @staticmethod
    def claim_generation(task: Any) -> int:
        return int(getattr(task, "claim_generation", 0) or 0)

    def is_guarded_task_cancellation(self, exc: BaseException) -> bool:
        checker = getattr(self._ports.execute_task_use_case(), "is_guarded_task_cancellation", None)
        if not isinstance(checker, types.MethodType):
            return False
        return bool(checker(exc))

    async def fail_task_after_execution_crash(self, *, task: Any, exc: BaseException) -> None:
        """Stop до release lease. fail_for_recovery — только учёт, не остановка."""
        error_message = str(exc).strip() or type(exc).__name__
        task_id = int(getattr(task, "id", 0) or 0)
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        error_name = type(exc).__name__
        TASK_EXECUTION_CRASHED.labels(error=error_name).inc()
        terminal_task = None
        complete = getattr(self._ports.execute_task_use_case(), "complete_execution_failure", None)
        if isinstance(complete, types.MethodType):
            try:
                completed = await complete(
                    task=task,
                    snapshot=None,
                    plan=None,
                    now=self._ports.now_fn(),
                    owner=str(getattr(task, "claimed_by", None) or self._ports.owner()),
                    error_code="ae3_task_execution_crashed",
                    error_message=error_message,
                )
                if not getattr(completed, "is_active", True):
                    terminal_task = completed
            except asyncio.CancelledError:
                raise
            except Exception:
                self._ports.logger().warning(
                    "AE3 runtime не смог завершить safety-path после crash: zone_id=%s task_id=%s owner=%s",
                    zone_id,
                    task_id,
                    self._ports.owner(),
                    exc_info=True,
                )
        if terminal_task is None and task_id > 0 and self._ports.task_repository() is not None:
            fail_for_recovery = getattr(self._ports.task_repository(), "fail_for_recovery", None)
            if callable(fail_for_recovery):
                try:
                    failed = await fail_for_recovery(
                        task_id=task_id,
                        error_code="ae3_task_execution_crashed",
                        error_message=error_message,
                        now=self._ports.now_fn(),
                        owner=str(getattr(task, "claimed_by", None) or self._ports.owner()),
                        claim_generation=self.claim_generation(task),
                    )
                    if failed is not None and not getattr(failed, "is_active", True):
                        terminal_task = failed
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._ports.logger().warning(
                        "AE3 runtime не смог перевести задачу в failed после crash: zone_id=%s task_id=%s owner=%s",
                        zone_id,
                        task_id,
                        self._ports.owner(),
                        exc_info=True,
                    )
        intent_id = int(getattr(task, "intent_id", 0) or 0)
        if intent_id > 0 and terminal_task is not None:
            await self._ports.safe_mark_intent_terminal(task=terminal_task, intent_id=intent_id)
        elif intent_id > 0:
            self._ports.logger().warning(
                "AE3 runtime left intent non-terminal after task crash CAS miss: intent_id=%s task_id=%s",
                intent_id,
                task_id,
            )

    async def execute_claimed_task(self, *, task: Any) -> None:
        intent_id = int(task.intent_id or 0)
        if intent_id > 0:
            if not await self._ports.safe_mark_intent_running(
                intent_id=intent_id,
                task_id=int(task.id),
                zone_id=int(task.zone_id),
            ):
                await self._ports.abort_task_after_intent_sync_failure(task=task, intent_id=intent_id)
                return

        lease_lost_event = asyncio.Event()
        heartbeat_task = self._ports.spawn_background_task_fn(
            self._ports.lease_heartbeat(
                zone_id=task.zone_id,
                lease_lost_event=lease_lost_event,
                claim_generation=self.claim_generation(task),
            ),
            task_name="ae3lite_lease_heartbeat",
        )
        final_task = task
        timed_out = False
        execution_crash: BaseException | None = None
        ACTIVE_TASKS.labels(topology=task.topology).inc()
        try:
            with TICK_DURATION.time():
                execution_now = self._ports.now_fn()
                effective_timeout_sec, timeout_cancel_msg = self.effective_task_timeout(
                    task=task,
                    now=execution_now,
                )
                execution_task = asyncio.create_task(
                    self._ports.execute_task_use_case().run(task=task, now=execution_now),
                    name=f"ae3lite_execute_task:{task.id}",
                )
                lease_wait_task = asyncio.create_task(
                    lease_lost_event.wait(),
                    name=f"ae3lite_lease_wait:{task.id}",
                )
                try:
                    done, _pending = await asyncio.wait(
                        {execution_task, lease_wait_task},
                        timeout=effective_timeout_sec,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if execution_task in done:
                        try:
                            final_task = await execution_task
                        except asyncio.CancelledError as exc:
                            if not self.is_guarded_task_cancellation(exc):
                                raise
                            execution_crash = exc
                            final_task = None
                    elif lease_wait_task in done and lease_lost_event.is_set():
                        execution_task.cancel(TASK_EXECUTION_LEASE_LOST_CANCEL_MSG)
                        try:
                            final_task = await execution_task
                        except asyncio.CancelledError as exc:
                            if not self.is_guarded_task_cancellation(exc):
                                raise
                            execution_crash = exc
                            final_task = None
                        TICK_ERRORS.labels(error_type="LeaseLost").inc()
                        self._ports.logger().error(
                            "AE3 task execution cancelled after lease loss: zone_id=%s task_id=%s",
                            task.zone_id,
                            task.id,
                        )
                    else:
                        timed_out = True
                        execution_task.cancel(timeout_cancel_msg)
                        try:
                            final_task = await execution_task
                        except asyncio.CancelledError as exc:
                            if not self.is_guarded_task_cancellation(exc):
                                raise
                            execution_crash = exc
                            final_task = None
                        TICK_ERRORS.labels(
                            error_type=(
                                "OverallDeadlineExceeded"
                                if timeout_cancel_msg == TASK_EXECUTION_OVERALL_DEADLINE_CANCEL_MSG
                                else "TimeoutError"
                            )
                        ).inc()
                        self._ports.logger().error(
                            "AE3 task execution timeout: zone_id=%s task_id=%s timeout_sec=%s",
                            task.zone_id,
                            task.id,
                            effective_timeout_sec,
                        )
                except asyncio.CancelledError:
                    lease_wait_task.cancel()
                    execution_task.cancel()
                    raise
                finally:
                    lease_wait_task.cancel()
        except Exception as exc:
            TICK_ERRORS.labels(error_type=type(exc).__name__).inc()
            execution_crash = exc
        finally:
            ACTIVE_TASKS.labels(topology=task.topology).dec()
            cancel = getattr(heartbeat_task, "cancel", None)
            if callable(cancel):
                cancel()
            if execution_crash is not None:
                await self.fail_task_after_execution_crash(task=task, exc=execution_crash)
            if lease_lost_event.is_set():
                self._ports.logger().warning(
                    "AE3 runtime task finished after lease was lost: zone_id=%s task_id=%s",
                    task.zone_id,
                    task.id,
                )
            claim_generation = self.claim_generation(task)
            released = await self._ports.zone_lease_repository().release(
                zone_id=task.zone_id,
                owner=self._ports.owner(),
                claim_generation=claim_generation,
            )
            if not released:
                await asyncio.sleep(0.05)
                released = await self._ports.zone_lease_repository().release(
                    zone_id=task.zone_id,
                    owner=self._ports.owner(),
                    claim_generation=claim_generation,
                )
            if released:
                await self._ports.maybe_resolve_zone_lease_release_alert(task=task, reason="released")
            else:
                lease_after_release = await self._ports.zone_lease_repository().get(zone_id=task.zone_id)
                if lease_after_release is None:
                    # Lease уже снят — не ошибка; resolve только known-fail / TTL opportunistic.
                    self._ports.log_debug(
                        "AE3 runtime lease already absent during release: zone_id=%s owner=%s task_id=%s",
                        task.zone_id,
                        self._ports.owner(),
                        task.id,
                    )
                    await self._ports.maybe_resolve_zone_lease_release_alert(task=task, reason="already_absent")
                elif (
                    lease_after_release.owner != self._ports.owner()
                    or int(getattr(lease_after_release, "claim_generation", 0) or 0) != claim_generation
                ):
                    self._ports.log_debug(
                        "AE3 runtime lease owned by another worker after task finish: zone_id=%s owner=%s task_id=%s lease_owner=%s",
                        task.zone_id,
                        self._ports.owner(),
                        task.id,
                        lease_after_release.owner,
                    )
                    await self._ports.maybe_resolve_zone_lease_release_alert(task=task, reason="foreign_owner")
                else:
                    self._ports.logger().warning(
                        "AE3 runtime failed to release zone lease: zone_id=%s owner=%s task_id=%s",
                        task.zone_id,
                        self._ports.owner(),
                        task.id,
                    )
                    ZONE_LEASE_RELEASE_FAILED.labels(zone_id=str(task.zone_id)).inc()
                    try:
                        sent = await self._ports.global_send_infra_alert(
                            code="ae3_zone_lease_release_failed",
                            alert_type="AE3 Zone Lease Release Failed",
                            message="Не удалось освободить lease зоны после завершения задачи.",
                            severity="error",
                            zone_id=int(task.zone_id),
                            service="automation-engine",
                            component="worker:lease",
                            details={
                                "task_id": int(task.id),
                                "owner": self._ports.owner(),
                                "topology": str(getattr(task, "topology", "")),
                                "message": "Не удалось освободить lease зоны после завершения задачи: зона могла остаться заблокированной.",
                            },
                        )
                        if sent:
                            self._state.lease_release_fail_zones.add(int(task.zone_id))
                    except Exception:
                        self._ports.logger().warning(
                            "AE3 не смог отправить alert lease_release_failed zone_id=%s",
                            task.zone_id,
                            exc_info=True,
                        )

        if timed_out:
            if intent_id > 0 and final_task is not None and not getattr(final_task, "is_active", True):
                await self._ports.safe_mark_intent_terminal(task=final_task, intent_id=intent_id)
            self._ports.log_debug(
                "AE3 runtime продолжает drain после задачи с превышенным timeout: task_id=%s", task.id
            )
            return

        if lease_lost_event.is_set():
            if intent_id > 0 and final_task is not None and not getattr(final_task, "is_active", True):
                await self._ports.safe_mark_intent_terminal(task=final_task, intent_id=intent_id)
            self._ports.log_debug("AE3 runtime продолжает drain после потери lease: task_id=%s", task.id)
            return

        if intent_id > 0 and final_task is not None and not final_task.is_active:
            await self._ports.safe_mark_intent_terminal(task=final_task, intent_id=intent_id)

    def effective_task_timeout(self, *, task: Any, now: datetime) -> tuple[float, str]:
        tick_timeout = max(0.001, float(self._ports.max_task_execution_sec()))
        remaining_sec = overall_deadline_remaining_sec(task=task, now=now)
        if remaining_sec is None:
            return tick_timeout, TASK_EXECUTION_TIMEOUT_CANCEL_MSG
        if remaining_sec <= tick_timeout:
            return max(0.001, float(remaining_sec)), TASK_EXECUTION_OVERALL_DEADLINE_CANCEL_MSG
        return tick_timeout, TASK_EXECUTION_TIMEOUT_CANCEL_MSG

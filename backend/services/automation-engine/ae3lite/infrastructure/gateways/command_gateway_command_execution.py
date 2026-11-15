"""SequentialCommandGateway command execution: explicit collaborators and invocation context."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import CommandPublishError, TaskExecutionError, TaskTerminalStateReached
from ae3lite.infrastructure.gateways.command_gateway_shared import logger
from ae3lite.infrastructure.gateways.command_publish_pipeline import (
    compute_poll_timeout_sec,
    planner_step_for_command,
)
from ae3lite.infrastructure.log_context import log_context_scope
from ae3lite.infrastructure.metrics import (
    COMMAND_DISPATCH_FAILED,
)


@dataclass(frozen=True)
class CommandGatewayCommandExecutionPorts:
    await_terminal_without_task_fsm: Callable[..., Awaitable[Any]]
    cleanup_race_batch_result: Callable[..., Any]
    command_poll_default_sec: Callable[[], Any]
    command_poll_margin_sec: Callable[[], Any]
    command_repository: Callable[[], Any]
    complete_on_ack: Callable[..., Any]
    emit_poll_deadline_exceeded_event: Callable[..., Awaitable[Any]]
    enrich_command_payload: Callable[..., Any]
    extract_publish_payload: Callable[..., Any]
    maybe_raise_offline_instead_of_command_error: Callable[..., Awaitable[Any]]
    observe_roundtrip_metrics: Callable[..., Any]
    poll_backoff_factor: Callable[[], Any]
    poll_interval_sec: Callable[[], Any]
    poll_max_interval_sec: Callable[[], Any]
    publish_pipeline: Callable[[], Any]
    task_repository: Callable[[], Any]
    task_row_missing: Callable[..., Awaitable[Any]]
    recover_waiting_command: Callable[..., Awaitable[Any]]
    global_utcnow: Callable[..., Any]
    global_send_service_log: Callable[..., Any]


class CommandGatewayCommandExecution:
    def __init__(self, ports: CommandGatewayCommandExecutionPorts) -> None:
        self._ports = ports

    async def run_command(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        now: datetime,
        track_task_state: bool,
        seq_index: int = 0,
        planner_step: str | None = None,
        recovery_resume_marker: Mapping[str, Any] | None = None,
        await_terminal: bool = True,
    ) -> Mapping[str, Any]:
        # complete_on_ack устарел для mutating-команд: terminal success только по DONE (протокол 2.0).
        _ = self._ports.complete_on_ack(command)
        planned = self._ports.enrich_command_payload(
            task=task,
            command=command,
            recovery_resume_marker=recovery_resume_marker,
        )
        resolved_planner_step = planner_step or planner_step_for_command(
            task=task,
            command=planned,
            seq_index=seq_index,
        )
        ae_command_id: int | None = None
        cmd_id = ""
        cmd_name = ""
        try:
            with log_context_scope(
                task_id=int(getattr(task, "id", 0) or 0) or None,
                zone_id=int(getattr(task, "zone_id", 0) or 0) or None,
            ):
                published = await self._ports.publish_pipeline().publish(
                    task=task,
                    command=planned,
                    now=now,
                    planner_step=resolved_planner_step,
                    seq_index=seq_index,
                )
        except TaskExecutionError:
            raise
        except CommandPublishError as exc:
            if "исчезла" in str(exc).lower():
                logger.info(
                    "AE3 command publish: task row missing during allocate "
                    "(likely concurrent cleanup) task_id=%s zone_id=%s",
                    task.id,
                    task.zone_id,
                )
                return self._ports.cleanup_race_batch_result(task=task, message=str(exc))
            return await self.handle_publish_failure(
                task=task,
                planned=planned,
                ae_command_id=ae_command_id,
                cmd_id=cmd_id,
                cmd_name=cmd_name,
                exc=exc,
                now=now,
            )
        except Exception as exc:
            return await self.handle_publish_failure(
                task=task,
                planned=planned,
                ae_command_id=ae_command_id,
                cmd_id=cmd_id,
                cmd_name=cmd_name,
                exc=exc,
                now=now,
            )

        ae_command_id = int(published.ae_command_id)
        cmd_id = published.cmd_id
        published_cmd_id = published.published_cmd_id
        cmd_name = published.cmd_name
        command_payload = dict(planned.payload)
        command_payload["cmd_id"] = cmd_id
        planned = replace(planned, step_no=published.step_no, payload=command_payload)

        with log_context_scope(cmd_id=cmd_id):
            external_id = published.external_id
            status_entry = {
                "ae_command_id": ae_command_id,
                "node_uid": planned.node_uid,
                "channel": planned.channel,
                "cmd": cmd_name,
                "external_id": external_id,
                "legacy_cmd_id": published_cmd_id,
                "terminal_status": None,
            }

            if not await_terminal:
                return {
                    "success": True,
                    "task": task,
                    "command_statuses": [status_entry],
                }

            if not track_task_state:
                return await self._ports.await_terminal_without_task_fsm(
                    task=task,
                    published=published,
                    planned=planned,
                    status_entry=status_entry,
                    now=now,
                )

            waiting_task = task
            if task.status != "waiting_command":
                waiting_task = await self._ports.task_repository().mark_waiting_command(
                    task_id=task.id,
                    owner=str(task.claimed_by or ""),
                    now=now,
                    claim_generation=int(getattr(task, "claim_generation", 0) or 0),
                )
                if waiting_task is None:
                    if await self._ports.task_row_missing(task_id=task.id):
                        logger.warning(
                            "AE3 command publish: mark_waiting_command failed and task row absent "
                            "(likely concurrent cleanup) task_id=%s zone_id=%s cmd_id=%s",
                            task.id,
                            task.zone_id,
                            cmd_id,
                        )
                        return self._ports.cleanup_race_batch_result(
                            task=task,
                            message=(
                                f"Задача {task.id} исчезла до перехода в waiting_command "
                                f"(вероятно параллельная очистка); cmd_id={cmd_id}"
                            ),
                        )
                    raise TaskExecutionError(
                        "ae3_waiting_command_transition_failed",
                        f"Не удалось перевести задачу {task.id} в waiting_command",
                    )

            poll_timeout_sec = compute_poll_timeout_sec(
                params=published.params,
                default_sec=self._ports.command_poll_default_sec(),
                margin_sec=self._ports.command_poll_margin_sec(),
            )
            poll_started_at = self._ports.global_utcnow().replace(microsecond=0)
            poll_deadline = poll_started_at + timedelta(seconds=poll_timeout_sec)
            effective_deadline = poll_deadline

            roundtrip_started_at = time.monotonic()
            poll_interval_sec = self._ports.poll_interval_sec()
            poll_iterations = 0
            while True:
                await asyncio.sleep(poll_interval_sec)
                reconcile_now = self._ports.global_utcnow().replace(microsecond=0)
                result = await self._ports.recover_waiting_command(task=waiting_task, now=reconcile_now)
                poll_iterations += 1
                if result["state"] == "waiting_command":
                    if reconcile_now > effective_deadline:
                        deadline_kind = "poll"
                        await self._ports.emit_poll_deadline_exceeded_event(
                            task=task,
                            command=planned,
                            cmd_id=str(result.get("cmd_id") or status_entry.get("legacy_cmd_id") or ""),
                            external_id=str(result.get("external_id") or status_entry.get("external_id") or ""),
                            checked_at=reconcile_now,
                            deadline=effective_deadline,
                            poll_iterations=poll_iterations,
                            deadline_kind=deadline_kind,
                        )
                        return {
                            "success": False,
                            "task": waiting_task,
                            "command_statuses": [status_entry],
                            "error_code": "ae3_command_poll_deadline_exceeded",
                            "error_message": (
                                f"Опрос команды превысил дедлайн для задачи {task.id} "
                                f"stage={getattr(task, 'current_stage', None)}"
                            ),
                            "deadline_kind": deadline_kind,
                        }
                    poll_interval_sec = min(
                        self._ports.poll_max_interval_sec(), poll_interval_sec * self._ports.poll_backoff_factor()
                    )
                    continue
                self._ports.observe_roundtrip_metrics(
                    channel=planned.channel,
                    terminal_status=result.get("legacy_status"),
                    roundtrip_started_at=roundtrip_started_at,
                    poll_iterations=poll_iterations,
                )
                task_state = result["task"]
                task_status = str(getattr(task_state, "status", "") or "").strip().lower()
                if task_state is not None and task_status in {"cancelled", "completed", "failed"}:
                    raise TaskTerminalStateReached(
                        task=task_state,
                        message=f"Во время command roundtrip задача {task.id} перешла в состояние {task_status}",
                    )
                status_entry = {
                    **status_entry,
                    "external_id": result.get("external_id"),
                    "legacy_cmd_id": result.get("cmd_id"),
                    "terminal_status": result.get("legacy_status"),
                    "response_details": result.get("response_details") or {},
                }
                if result["state"] == "done":
                    return {
                        "success": True,
                        "task": task_state,
                        "command_statuses": [status_entry],
                    }
                return {
                    "success": False,
                    "task": task_state,
                    "command_statuses": [status_entry],
                    "error_code": result["error_code"],
                    "error_message": result["error_message"],
                }

    async def handle_publish_failure(
        self,
        *,
        task: Any,
        planned: PlannedCommand,
        ae_command_id: int | None,
        cmd_id: str,
        cmd_name: str,
        exc: Exception,
        now: datetime,
    ) -> Mapping[str, Any]:
        error_type = type(exc).__name__
        normalized_error = str(exc).strip() or error_type
        if not cmd_name:
            try:
                cmd_name, _ = self._ports.extract_publish_payload(planned)
            except Exception:
                cmd_name = ""
        COMMAND_DISPATCH_FAILED.labels(
            stage=planned.channel or "unknown",
            error_type=error_type,
        ).inc()
        self._ports.global_send_service_log(
            service="automation-engine",
            level="error",
            message="Не удалось отправить команду AE3 до перехода в waiting_command",
            context={
                "zone_id": int(getattr(task, "zone_id", 0) or 0) or None,
                "task_id": int(getattr(task, "id", 0) or 0) or None,
                "stage": str(getattr(task, "current_stage", "") or ""),
                "workflow_phase": str(getattr(task.workflow, "workflow_phase", "") or ""),
                "node_uid": str(planned.node_uid or ""),
                "channel": str(planned.channel or ""),
                "cmd": str(cmd_name or ""),
                "cmd_id": cmd_id or None,
                "error_type": error_type,
                "error_message": normalized_error,
            },
        )
        if ae_command_id is not None:
            try:
                await self._ports.command_repository().mark_publish_failed(
                    ae_command_id=ae_command_id, last_error=normalized_error, now=now
                )
            except Exception:
                logger.debug(
                    "AE3 mark_publish_failed skipped (row may be gone) ae_command_id=%s",
                    ae_command_id,
                    exc_info=True,
                )
        if await self._ports.task_row_missing(task_id=task.id):
            logger.info(
                "AE3 command publish: exception after create_pending but task row gone task_id=%s zone_id=%s exc=%s",
                task.id,
                task.zone_id,
                exc,
            )
            return self._ports.cleanup_race_batch_result(
                task=task,
                message=(f"Задача {task.id} исчезла во время publish pipeline (вероятно параллельная очистка): {exc}"),
            )
        await self._ports.maybe_raise_offline_instead_of_command_error(
            task=task,
            planned=planned,
            error_code="command_send_failed",
            error_message=normalized_error,
        )
        raise TaskExecutionError("command_send_failed", normalized_error) from exc

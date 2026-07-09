"""Последовательный pipeline команд к нодам в AE3-Lite."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import CommandPublishError, ErrorCodes, TaskExecutionError, TaskTerminalStateReached
from ae3lite.infrastructure.gateways.command_publish_pipeline import (
    CommandPublishPipeline,
    compute_poll_timeout_sec,
    planner_step_for_command,
)
from ae3lite.infrastructure.log_context import log_context_scope
from ae3lite.infrastructure.metrics import (
    COMMAND_DISPATCH_FAILED,
    COMMAND_DISPATCH_DURATION,
    COMMAND_DISPATCHED,
    COMMAND_POLL_ITERATIONS,
    COMMAND_ROUNDTRIP_DURATION,
    COMMAND_TERMINAL,
    inc_observability_write_failed,
)
from common.db import create_zone_event
from common.service_logs import send_service_log
from common.utils.time import utcnow_naive as _utcnow

logger = logging.getLogger(__name__)

_NON_TERMINAL_STATUSES = frozenset({"PENDING", "QUEUED", "SENT", "ACK", "RUNNING"})
_TERMINAL_STATUSES = frozenset({"DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"})
_PROTOCOL_VIOLATION_STATUSES = frozenset({"ACCEPTED"})


def _response_details_from_legacy_row(legacy_row: Mapping[str, Any]) -> dict[str, Any]:
    """Собрать dose feedback из legacy ``commands`` (duration_ms + params)."""
    details: dict[str, Any] = {}
    raw_duration = legacy_row.get("duration_ms")
    if raw_duration is not None:
        try:
            actual_ms = max(0, int(raw_duration))
        except (TypeError, ValueError):
            actual_ms = 0
        if actual_ms > 0:
            details["duration_ms"] = actual_ms

    params = legacy_row.get("params")
    param_block: Mapping[str, Any] = {}
    if isinstance(params, Mapping):
        param_block = params
        nested = params.get("params")
        if isinstance(nested, Mapping):
            param_block = nested

    if param_block:
        planned_ms = param_block.get("duration_ms")
        if details.get("duration_ms") and planned_ms is not None:
            try:
                if int(planned_ms) > int(details["duration_ms"]):
                    details["duration_limited"] = True
            except (TypeError, ValueError):
                pass
        planned_ml = param_block.get("ml")
        if planned_ml is not None:
            try:
                details["ml"] = float(planned_ml)
            except (TypeError, ValueError):
                pass
        node_mps = param_block.get("ml_per_second")
        if node_mps is None:
            node_mps = param_block.get("ml_per_sec")
        if node_mps is not None:
            try:
                details["ml_per_second"] = float(node_mps)
            except (TypeError, ValueError):
                pass
    return details


class SequentialCommandGateway:
    """Публикует разрешённые команды по одной и ждёт terminal-статус legacy-команды."""

    def __init__(
        self,
        *,
        task_repository: Any,
        command_repository: Any,
        history_logger_client: Any,
        poll_interval_sec: float,
        poll_backoff_factor: float = 1.5,
        poll_max_interval_sec: float = 5.0,
        command_poll_default_sec: float = 120.0,
        command_poll_margin_sec: float = 30.0,
    ) -> None:
        self._task_repository = task_repository
        self._command_repository = command_repository
        self._history_logger_client = history_logger_client
        self._publish_pipeline = CommandPublishPipeline(
            command_repository=command_repository,
            history_logger_client=history_logger_client,
        )
        self._poll_interval_sec = max(0.05, float(poll_interval_sec))
        self._poll_backoff_factor = max(1.0, float(poll_backoff_factor))
        self._poll_max_interval_sec = max(self._poll_interval_sec, float(poll_max_interval_sec))
        self._command_poll_default_sec = max(1.0, float(command_poll_default_sec))
        self._command_poll_margin_sec = max(0.0, float(command_poll_margin_sec))

    def _cleanup_race_batch_result(self, *, task: Any, message: str) -> dict[str, Any]:
        return {
            "success": False,
            "task": task,
            "command_statuses": [],
            "error_code": ErrorCodes.AE3_TASK_MISSING_DURING_PUBLISH,
            "error_message": message,
        }

    async def _task_row_missing(self, *, task_id: int) -> bool:
        get_by_id = getattr(self._task_repository, "get_by_id", None)
        if not callable(get_by_id):
            return False
        current = await get_by_id(task_id=task_id)
        return current is None

    async def run_batch(
        self,
        *,
        task: Any,
        commands: Sequence[PlannedCommand],
        now: datetime,
        track_task_state: bool = True,
    ) -> Mapping[str, Any]:
        current_task = task
        combined_statuses: list[dict[str, Any]] = []

        for seq_index, command in enumerate(commands):
            result = await self._run_command(
                task=current_task,
                command=command,
                now=now,
                track_task_state=track_task_state,
                seq_index=seq_index,
            )
            combined_statuses.extend(result["command_statuses"])
            current_task = result["task"]
            if not result["success"]:
                return {
                    "success": False,
                    "task": current_task,
                    "commands_total": len(combined_statuses),
                    "commands_failed": 1,
                    "command_statuses": combined_statuses,
                    "error_code": result["error_code"],
                    "error_message": result["error_message"],
                }

        return {
            "success": True,
            "task": current_task,
            "commands_total": len(combined_statuses),
            "commands_failed": 0,
            "command_statuses": combined_statuses,
        }

    async def waiting_command_poll_deadline_exceeded(self, *, task: Any, now: datetime) -> bool:
        ae_command = await self._command_repository.get_latest_for_task(task_id=task.id)
        params: Mapping[str, Any] = {}
        if ae_command is not None:
            payload = ae_command.get("payload")
            if isinstance(payload, Mapping):
                raw_params = payload.get("params")
                if isinstance(raw_params, Mapping):
                    params = raw_params
        poll_timeout_sec = compute_poll_timeout_sec(
            params=params,
            default_sec=self._command_poll_default_sec,
            margin_sec=self._command_poll_margin_sec,
        )
        waiting_since = getattr(task, "updated_at", None)
        if not isinstance(waiting_since, datetime):
            return False
        poll_deadline = waiting_since + timedelta(seconds=poll_timeout_sec)
        stage_deadline = (
            task.workflow.stage_deadline_at
            if hasattr(task, "workflow") and task.workflow.stage_deadline_at is not None
            else None
        )
        effective_deadline = (
            min(stage_deadline, poll_deadline) if stage_deadline is not None else poll_deadline
        )
        return now > effective_deadline

    async def recover_waiting_command(self, *, task: Any, now: datetime) -> Mapping[str, Any]:
        ae_command = await self._command_repository.get_latest_for_task(task_id=task.id)
        if ae_command is None:
            current_task = await self._task_repository.get_by_id(task_id=task.id)
            current_status = str(getattr(current_task, "status", "") or "").strip().lower()
            if current_task is None or current_status in {"cancelled", "completed"}:
                return {
                    "state": "done",
                    "task": current_task or task,
                    "legacy_status": None,
                    "external_id": None,
                    "cmd_id": None,
                }
            raise TaskExecutionError("ae3_missing_ae_command", f"У задачи {task.id} отсутствует ae_command для recovery")
        legacy_row, external_id, cmd_id = await self._resolve_legacy_command(task=task, ae_command=ae_command)
        if legacy_row is None:
            return {"state": "waiting_command", "task": task, "legacy_status": None, "external_id": external_id, "cmd_id": cmd_id}
        return await self._apply_legacy_outcome(task=task, ae_command=ae_command, legacy_row=legacy_row, now=now)

    async def _run_command(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        now: datetime,
        track_task_state: bool,
        seq_index: int = 0,
    ) -> Mapping[str, Any]:
        # complete_on_ack устарел для mutating-команд: terminal success только по DONE (протокол 2.0).
        _ = self._complete_on_ack(command)
        planned = command
        planner_step = planner_step_for_command(task=task, command=command, seq_index=seq_index)
        ae_command_id: int | None = None
        cmd_id = ""
        cmd_name = ""
        try:
            with log_context_scope(
                task_id=int(getattr(task, "id", 0) or 0) or None,
                zone_id=int(getattr(task, "zone_id", 0) or 0) or None,
            ):
                published = await self._publish_pipeline.publish(
                    task=task,
                    command=command,
                    now=now,
                    planner_step=planner_step,
                    seq_index=seq_index,
                )
        except CommandPublishError as exc:
            if "исчезла" in str(exc).lower():
                logger.info(
                    "AE3 command publish: task row missing during allocate "
                    "(likely concurrent cleanup) task_id=%s zone_id=%s",
                    task.id,
                    task.zone_id,
                )
                return self._cleanup_race_batch_result(task=task, message=str(exc))
            return await self._handle_publish_failure(
                task=task,
                planned=command,
                ae_command_id=ae_command_id,
                cmd_id=cmd_id,
                cmd_name=cmd_name,
                exc=exc,
                now=now,
            )
        except Exception as exc:
            return await self._handle_publish_failure(
                task=task,
                planned=command,
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
        command_payload = dict(command.payload)
        command_payload["cmd_id"] = cmd_id
        planned = replace(command, step_no=published.step_no, payload=command_payload)

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

            if not track_task_state:
                return await self._await_terminal_without_task_fsm(
                    task=task,
                    published=published,
                    planned=planned,
                    status_entry=status_entry,
                    now=now,
                )

            waiting_task = task
            if task.status != "waiting_command":
                waiting_task = await self._task_repository.mark_waiting_command(
                    task_id=task.id,
                    owner=str(task.claimed_by or ""),
                    now=now,
                )
                if waiting_task is None:
                    if await self._task_row_missing(task_id=task.id):
                        logger.warning(
                            "AE3 command publish: mark_waiting_command failed and task row absent "
                            "(likely concurrent cleanup) task_id=%s zone_id=%s cmd_id=%s",
                            task.id,
                            task.zone_id,
                            cmd_id,
                        )
                        return self._cleanup_race_batch_result(
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
                default_sec=self._command_poll_default_sec,
                margin_sec=self._command_poll_margin_sec,
            )
            poll_started_at = _utcnow().replace(microsecond=0)
            poll_deadline = poll_started_at + timedelta(seconds=poll_timeout_sec)
            stage_deadline = (
                task.workflow.stage_deadline_at
                if hasattr(task, "workflow") and task.workflow.stage_deadline_at is not None
                else None
            )
            effective_deadline = (
                min(stage_deadline, poll_deadline) if stage_deadline is not None else poll_deadline
            )

            roundtrip_started_at = time.monotonic()
            poll_interval_sec = self._poll_interval_sec
            poll_iterations = 0
            while True:
                await asyncio.sleep(poll_interval_sec)
                reconcile_now = _utcnow().replace(microsecond=0)
                result = await self.recover_waiting_command(task=waiting_task, now=reconcile_now)
                poll_iterations += 1
                if result["state"] == "waiting_command":
                    if reconcile_now > effective_deadline:
                        await self._emit_poll_deadline_exceeded_event(
                            task=task,
                            command=planned,
                            cmd_id=str(result.get("cmd_id") or status_entry.get("legacy_cmd_id") or ""),
                            external_id=str(result.get("external_id") or status_entry.get("external_id") or ""),
                            checked_at=reconcile_now,
                            deadline=effective_deadline,
                            poll_iterations=poll_iterations,
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
                        }
                    poll_interval_sec = min(self._poll_max_interval_sec, poll_interval_sec * self._poll_backoff_factor)
                    continue
                self._observe_roundtrip_metrics(
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

    async def _handle_publish_failure(
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
                cmd_name, _ = self._extract_publish_payload(planned)
            except Exception:
                cmd_name = ""
        COMMAND_DISPATCH_FAILED.labels(
            stage=planned.channel or "unknown",
            error_type=error_type,
        ).inc()
        send_service_log(
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
                await self._command_repository.mark_publish_failed(
                    ae_command_id=ae_command_id, last_error=normalized_error, now=now
                )
            except Exception:
                logger.debug(
                    "AE3 mark_publish_failed skipped (row may be gone) ae_command_id=%s",
                    ae_command_id,
                    exc_info=True,
                )
        if await self._task_row_missing(task_id=task.id):
            logger.info(
                "AE3 command publish: exception after create_pending but task row gone "
                "task_id=%s zone_id=%s exc=%s",
                task.id,
                task.zone_id,
                exc,
            )
            return self._cleanup_race_batch_result(
                task=task,
                message=(
                    f"Задача {task.id} исчезла во время publish pipeline "
                    f"(вероятно параллельная очистка): {exc}"
                ),
            )
        await self._maybe_raise_offline_instead_of_command_error(
            task=task,
            planned=planned,
            error_code="command_send_failed",
            error_message=normalized_error,
        )
        raise TaskExecutionError("command_send_failed", normalized_error) from exc

    async def _emit_poll_deadline_exceeded_event(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        cmd_id: str,
        external_id: str,
        checked_at: datetime,
        deadline: datetime,
        poll_iterations: int,
    ) -> None:
        try:
            await create_zone_event(
                int(task.zone_id),
                "AE_COMMAND_POLL_DEADLINE_EXCEEDED",
                {
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "stage": str(getattr(task, "current_stage", "") or ""),
                    "workflow_phase": str(getattr(task.workflow, "workflow_phase", "") or ""),
                    "corr_step": str(getattr(task.workflow, "corr_step", "") or ""),
                    "channel": str(command.channel or ""),
                    "node_uid": str(command.node_uid or ""),
                    "cmd": str(command.payload.get("cmd") or ""),
                    "cmd_id": cmd_id or None,
                    "external_id": external_id or None,
                    "poll_iterations": int(poll_iterations),
                    "checked_at": checked_at.isoformat(),
                    "stage_deadline_at": deadline.isoformat(),
                },
            )
        except Exception:
            inc_observability_write_failed(kind="zone_event")
            logger.warning(
                "AE3 не смог записать AE_COMMAND_POLL_DEADLINE_EXCEEDED zone_id=%s task_id=%s cmd_id=%s",
                int(getattr(task, "zone_id", 0) or 0),
                int(getattr(task, "id", 0) or 0),
                cmd_id,
                exc_info=True,
            )

    def _observe_roundtrip_metrics(
        self,
        *,
        channel: str | None,
        terminal_status: Any,
        roundtrip_started_at: float,
        poll_iterations: int,
    ) -> None:
        channel_label = str(channel or "").strip() or "unknown"
        terminal_label = str(terminal_status or "").strip().upper() or "UNKNOWN"
        COMMAND_ROUNDTRIP_DURATION.labels(channel=channel_label, terminal_status=terminal_label).observe(
            max(0.0, time.monotonic() - roundtrip_started_at)
        )
        COMMAND_POLL_ITERATIONS.labels(channel=channel_label, terminal_status=terminal_label).inc(
            max(0, poll_iterations)
        )

    async def _resolve_legacy_command(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any] | None, str | None, str | None]:
        external_id = str(ae_command.get("external_id") or "").strip() or None
        payload = ae_command.get("payload") if isinstance(ae_command.get("payload"), Mapping) else {}
        cmd_id = str(payload.get("cmd_id") or "").strip() or None
        if external_id:
            row = await self._command_repository.get_legacy_command_by_id(external_id=external_id)
            if row is None:
                raise TaskExecutionError("ae3_legacy_command_not_found", f"Не найдена legacy command для external_id={external_id}")
            return row, external_id, str(row.get("cmd_id") or "").strip() or cmd_id
        if not cmd_id:
            raise TaskExecutionError(
                "ae3_missing_cmd_id",
                f"У ae_command {ae_command.get('id')} отсутствуют и external_id, и payload.cmd_id",
            )
        row = await self._command_repository.get_legacy_command_by_cmd_id(zone_id=task.zone_id, cmd_id=cmd_id)
        if row is None:
            return None, None, cmd_id
        return row, str(row["id"]), cmd_id

    async def _apply_legacy_outcome(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        legacy_row: Mapping[str, Any],
        now: datetime,
    ) -> Mapping[str, Any]:
        legacy_status = str(legacy_row.get("status") or "").strip().upper()
        if legacy_status in _PROTOCOL_VIOLATION_STATUSES:
            raise TaskExecutionError(
                "command_protocol_violation",
                f"Legacy status {legacy_status} не является terminal outcome протокола 2.0",
            )
        if legacy_status not in _NON_TERMINAL_STATUSES | _TERMINAL_STATUSES:
            raise TaskExecutionError("ae3_unsupported_legacy_status", f"Неподдерживаемый legacy status={legacy_status or 'empty'}")
        external_id = str(legacy_row.get("id") or "")
        cmd_id = str(legacy_row.get("cmd_id") or "").strip() or None
        terminal_status = legacy_status if legacy_status in _TERMINAL_STATUSES else None
        terminal_at = (
            legacy_row.get("failed_at")
            or legacy_row.get("ack_at")
            or legacy_row.get("updated_at")
            or legacy_row.get("sent_at")
            or legacy_row.get("created_at")
        )
        last_error = None if terminal_status in {None, "DONE"} else str(legacy_row.get("error_message") or legacy_status)
        await self._command_repository.update_from_legacy(
            ae_command_id=int(ae_command["id"]),
            external_id=external_id,
            ack_received_at=legacy_row.get("ack_at"),
            terminal_status=terminal_status,
            terminal_at=terminal_at,
            last_error=last_error,
            now=now,
        )
        if terminal_status is None:
            return {
                "state": "waiting_command",
                "task": task,
                "legacy_status": legacy_status,
                "external_id": external_id,
                "cmd_id": cmd_id,
                "response_details": {},
            }
        response_details = _response_details_from_legacy_row(legacy_row)
        if terminal_status == "DONE":
            COMMAND_TERMINAL.labels(terminal_status="DONE").inc()
            resumed_task = await self._task_repository.resume_after_waiting_command(
                task_id=task.id,
                owner=str(task.claimed_by or ""),
                now=now,
            )
            if resumed_task is None:
                current_task = await self._task_repository.get_by_id(task_id=task.id)
                current_status = str(getattr(current_task, "status", "") or "").strip().lower()
                if current_task is not None and current_status in {"cancelled", "completed", "failed"}:
                    return {
                        "state": "done",
                        "task": current_task,
                        "legacy_status": terminal_status,
                        "external_id": external_id,
                        "cmd_id": cmd_id,
                        "response_details": response_details,
                    }
                if current_task is not None and current_status == "running":
                    return {
                        "state": "done",
                        "task": current_task,
                        "legacy_status": terminal_status,
                        "external_id": external_id,
                        "cmd_id": cmd_id,
                        "response_details": response_details,
                    }
                raise TaskExecutionError(
                    "ae3_waiting_command_transition_failed",
                    f"Не удалось перевести задачу {task.id} из waiting_command в running после DONE",
                )
            return {"state": "done", "task": resumed_task, "legacy_status": terminal_status, "external_id": external_id, "cmd_id": cmd_id, "response_details": response_details}

        COMMAND_TERMINAL.labels(terminal_status=terminal_status).inc()
        failed_task = await self._task_repository.mark_failed(
            task_id=task.id,
            owner=str(task.claimed_by or ""),
            error_code=f"command_{terminal_status.strip().lower()}",
            error_message=last_error or f"Команда завершилась с терминальным статусом {terminal_status}",
            now=now,
        )
        if failed_task is None:
            raise TaskExecutionError("ae3_failed_transition_failed", f"Не удалось перевести задачу {task.id} в failed после {terminal_status}")
        return {
            "state": "failed",
            "task": failed_task,
            "legacy_status": terminal_status,
            "external_id": external_id,
            "cmd_id": cmd_id,
            "error_code": failed_task.error_code,
            "error_message": failed_task.error_message,
            "response_details": response_details,
        }

    async def _await_terminal_without_task_fsm(
        self,
        *,
        task: Any,
        published: Any,
        planned: PlannedCommand,
        status_entry: dict[str, Any],
        now: datetime,
    ) -> Mapping[str, Any]:
        """Ожидает terminal DONE без перехода задачи в waiting_command (fail-safe и publish-only)."""
        ae_command = {
            "id": int(published.ae_command_id),
            "external_id": published.external_id,
            "payload": planned.payload,
        }
        poll_timeout_sec = compute_poll_timeout_sec(
            params=published.params,
            default_sec=self._command_poll_default_sec,
            margin_sec=self._command_poll_margin_sec,
        )
        poll_started_at = _utcnow().replace(microsecond=0)
        poll_deadline = poll_started_at + timedelta(seconds=poll_timeout_sec)
        roundtrip_started_at = time.monotonic()
        poll_interval_sec = self._poll_interval_sec
        poll_iterations = 0

        while True:
            await asyncio.sleep(poll_interval_sec)
            reconcile_now = _utcnow().replace(microsecond=0)
            poll_iterations += 1
            legacy_row, external_id, cmd_id = await self._resolve_legacy_command(task=task, ae_command=ae_command)
            if legacy_row is None:
                if reconcile_now > poll_deadline:
                    return {
                        "success": False,
                        "task": task,
                        "command_statuses": [status_entry],
                        "error_code": "ae3_command_poll_deadline_exceeded",
                        "error_message": (
                            f"Опрос команды превысил дедлайн для задачи {task.id} "
                            f"(publish-only, stage={getattr(task, 'current_stage', None)})"
                        ),
                    }
                poll_interval_sec = min(self._poll_max_interval_sec, poll_interval_sec * self._poll_backoff_factor)
                continue

            legacy_status = str(legacy_row.get("status") or "").strip().upper()
            if legacy_status in _PROTOCOL_VIOLATION_STATUSES:
                return {
                    "success": False,
                    "task": task,
                    "command_statuses": [{**status_entry, "terminal_status": legacy_status}],
                    "error_code": "command_protocol_violation",
                    "error_message": f"Legacy status {legacy_status} не является terminal outcome протокола 2.0",
                }
            if legacy_status not in _NON_TERMINAL_STATUSES | _TERMINAL_STATUSES:
                return {
                    "success": False,
                    "task": task,
                    "command_statuses": [status_entry],
                    "error_code": "ae3_unsupported_legacy_status",
                    "error_message": f"Неподдерживаемый legacy status={legacy_status or 'empty'}",
                }

            await self._command_repository.update_from_legacy(
                ae_command_id=int(ae_command["id"]),
                external_id=str(legacy_row.get("id") or external_id or ""),
                ack_received_at=legacy_row.get("ack_at"),
                terminal_status=legacy_status if legacy_status in _TERMINAL_STATUSES else None,
                terminal_at=(
                    legacy_row.get("failed_at")
                    or legacy_row.get("ack_at")
                    or legacy_row.get("updated_at")
                    or legacy_row.get("sent_at")
                    or legacy_row.get("created_at")
                ),
                last_error=None if legacy_status in {None, "DONE"} else str(legacy_row.get("error_message") or legacy_status),
                now=reconcile_now,
            )
            ae_command["external_id"] = str(legacy_row.get("id") or external_id or "")

            if legacy_status in _NON_TERMINAL_STATUSES:
                if reconcile_now > poll_deadline:
                    return {
                        "success": False,
                        "task": task,
                        "command_statuses": [{**status_entry, "terminal_status": None}],
                        "error_code": "ae3_command_poll_deadline_exceeded",
                        "error_message": (
                            f"Опрос команды превысил дедлайн для задачи {task.id} "
                            f"(publish-only, stage={getattr(task, 'current_stage', None)})"
                        ),
                    }
                poll_interval_sec = min(self._poll_max_interval_sec, poll_interval_sec * self._poll_backoff_factor)
                continue

            self._observe_roundtrip_metrics(
                channel=planned.channel,
                terminal_status=legacy_status,
                roundtrip_started_at=roundtrip_started_at,
                poll_iterations=poll_iterations,
            )
            terminal_entry = {
                **status_entry,
                "external_id": str(legacy_row.get("id") or external_id or ""),
                "legacy_cmd_id": cmd_id,
                "terminal_status": legacy_status,
                "response_details": _response_details_from_legacy_row(legacy_row),
            }
            if legacy_status == "DONE":
                COMMAND_TERMINAL.labels(terminal_status="DONE").inc()
                return {
                    "success": True,
                    "task": task,
                    "command_statuses": [terminal_entry],
                }

            COMMAND_TERMINAL.labels(terminal_status=legacy_status).inc()
            return {
                "success": False,
                "task": task,
                "command_statuses": [terminal_entry],
                "error_code": f"command_{legacy_status.strip().lower()}",
                "error_message": str(legacy_row.get("error_message") or f"Команда завершилась с терминальным статусом {legacy_status}"),
            }

    async def _maybe_raise_offline_instead_of_command_error(
        self,
        *,
        task: Any,
        planned: PlannedCommand,
        error_code: str,
        error_message: str,
    ) -> None:
        from ae3lite.domain.services.zone_node_availability import (
            resolve_task_error_with_node_offline,
        )

        node_uid = str(getattr(planned, "node_uid", "") or "").strip()
        if not node_uid:
            return
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        if zone_id <= 0:
            return
        offline = await resolve_task_error_with_node_offline(
            zone_id=zone_id,
            topology=str(getattr(task, "topology", "") or ""),
            error_code=error_code,
            error_message=error_message,
            node_uid=node_uid,
            runtime_monitor=None,
        )
        if offline is not None:
            raise TaskExecutionError(offline.code, offline.message)

    def _extract_publish_payload(self, command: PlannedCommand) -> tuple[str, Mapping[str, Any]]:
        payload = command.payload if isinstance(command.payload, Mapping) else {}
        cmd_name = str(payload.get("cmd") or "").strip()
        params = payload.get("params")
        if not cmd_name or not isinstance(params, Mapping):
            raise TaskExecutionError("ae3_invalid_planned_command", "PlannedCommand должен содержать cmd и params")
        return cmd_name, params

    def _complete_on_ack(self, command: PlannedCommand) -> bool:
        payload = command.payload if isinstance(command.payload, Mapping) else {}
        return bool(payload.get("complete_on_ack"))

"""Sequential AE3-Lite node command pipeline."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from datetime import datetime
from typing import Any, Mapping, Sequence

from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import CommandPublishError, TaskExecutionError
from ae3lite.infrastructure.metrics import COMMAND_DISPATCHED, COMMAND_DISPATCH_DURATION, COMMAND_TERMINAL

_NON_TERMINAL_STATUSES = frozenset({"PENDING", "QUEUED", "SENT", "ACK", "ACCEPTED", "RUNNING"})
_TERMINAL_STATUSES = frozenset({"DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"})


class SequentialCommandGateway:
    """Publishes resolved commands one by one and waits for terminal legacy status."""

    def __init__(
        self,
        *,
        task_repository: Any,
        command_repository: Any,
        history_logger_client: Any,
        poll_interval_sec: float,
    ) -> None:
        self._task_repository = task_repository
        self._command_repository = command_repository
        self._history_logger_client = history_logger_client
        self._poll_interval_sec = max(0.05, float(poll_interval_sec))

    async def run_batch(self, *, task: Any, commands: Sequence[PlannedCommand], now: datetime) -> Mapping[str, Any]:
        current_task = task
        combined_statuses: list[dict[str, Any]] = []

        for command in commands:
            result = await self._run_command(task=current_task, command=command, now=now)
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

    async def recover_waiting_command(self, *, task: Any, now: datetime) -> Mapping[str, Any]:
        ae_command = await self._command_repository.get_latest_for_task(task_id=task.id)
        if ae_command is None:
            raise TaskExecutionError("ae3_missing_ae_command", f"Task {task.id} has no ae_command for recovery")
        legacy_row, external_id, cmd_id = await self._resolve_legacy_command(task=task, ae_command=ae_command)
        if legacy_row is None:
            return {"state": "waiting_command", "task": task, "legacy_status": None, "external_id": external_id, "cmd_id": cmd_id}
        return await self._apply_legacy_outcome(task=task, ae_command=ae_command, legacy_row=legacy_row, now=now)

    async def _run_command(self, *, task: Any, command: PlannedCommand, now: datetime) -> Mapping[str, Any]:
        step_no = await self._command_repository.get_next_step_no(task_id=task.id)
        planned = replace(command, step_no=step_no)
        cmd_name, params = self._extract_publish_payload(planned)
        cmd_id = f"ae3-t{task.id}-z{task.zone_id}-s{step_no}"
        command_payload = dict(planned.payload)
        command_payload["cmd_id"] = cmd_id
        ae_command_id = await self._command_repository.create_pending(
            task_id=task.id,
            step_no=step_no,
            node_uid=planned.node_uid,
            channel=planned.channel,
            payload=command_payload,
            now=now,
        )
        try:
            greenhouse_uid = await self._command_repository.resolve_greenhouse_uid(zone_id=task.zone_id)
            if not greenhouse_uid:
                raise CommandPublishError(f"Unable to resolve greenhouse_uid for zone_id={task.zone_id}")
            _dispatch_start = time.monotonic()
            published_cmd_id = await self._history_logger_client.publish(
                greenhouse_uid=greenhouse_uid,
                zone_id=task.zone_id,
                node_uid=planned.node_uid,
                channel=planned.channel,
                cmd=cmd_name,
                params=params,
                cmd_id=cmd_id,
            )
            COMMAND_DISPATCHED.labels(stage=planned.channel or "unknown").inc()
            COMMAND_DISPATCH_DURATION.observe(time.monotonic() - _dispatch_start)
            legacy_command_id = await self._command_repository.resolve_legacy_command_id(
                zone_id=task.zone_id,
                cmd_id=published_cmd_id,
            )
            if legacy_command_id is None:
                raise CommandPublishError(
                    f"Legacy commands.id not found for zone_id={task.zone_id} cmd_id={published_cmd_id}"
                )
            await self._command_repository.mark_publish_accepted(
                ae_command_id=ae_command_id,
                external_id=str(legacy_command_id),
                now=now,
            )
            waiting_task = await self._task_repository.mark_waiting_command(
                task_id=task.id,
                owner=str(task.claimed_by or ""),
                now=now,
            )
            if waiting_task is None:
                raise TaskExecutionError("ae3_waiting_command_transition_failed", f"Task {task.id} could not enter waiting_command")
        except Exception as exc:
            await self._command_repository.mark_publish_failed(ae_command_id=ae_command_id, last_error=str(exc), now=now)
            raise TaskExecutionError("command_send_failed", str(exc)) from exc

        _poll_deadline = (
            task.workflow.stage_deadline_at
            if hasattr(task, "workflow") and task.workflow.stage_deadline_at is not None
            else None
        )
        while True:
            await asyncio.sleep(self._poll_interval_sec)
            reconcile_now = datetime.utcnow().replace(microsecond=0)
            if _poll_deadline is not None and reconcile_now > _poll_deadline:
                raise TaskExecutionError(
                    "ae3_command_poll_deadline_exceeded",
                    f"Command polling exceeded stage deadline for task {task.id}",
                )
            result = await self.recover_waiting_command(task=waiting_task, now=reconcile_now)
            if result["state"] == "waiting_command":
                continue
            task_state = result["task"]
            status_entry = {
                "ae_command_id": int(ae_command_id),
                "node_uid": planned.node_uid,
                "channel": planned.channel,
                "cmd": cmd_name,
                "external_id": result.get("external_id"),
                "legacy_cmd_id": result.get("cmd_id"),
                "terminal_status": result.get("legacy_status"),
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
                raise TaskExecutionError("ae3_legacy_command_not_found", f"Legacy command not found for external_id={external_id}")
            return row, external_id, str(row.get("cmd_id") or "").strip() or cmd_id
        if not cmd_id:
            raise TaskExecutionError(
                "ae3_missing_cmd_id",
                f"ae_command {ae_command.get('id')} has neither external_id nor payload.cmd_id",
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
        if legacy_status not in _NON_TERMINAL_STATUSES | _TERMINAL_STATUSES:
            raise TaskExecutionError("ae3_unsupported_legacy_status", f"Unsupported legacy status={legacy_status or 'empty'}")
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
            return {"state": "waiting_command", "task": task, "legacy_status": legacy_status, "external_id": external_id, "cmd_id": cmd_id}
        if terminal_status == "DONE":
            COMMAND_TERMINAL.labels(terminal_status="DONE").inc()
            resumed_task = await self._task_repository.resume_after_waiting_command(
                task_id=task.id,
                owner=str(task.claimed_by or ""),
                now=now,
            )
            if resumed_task is None:
                raise TaskExecutionError("ae3_running_transition_failed", f"Task {task.id} could not resume running after DONE")
            return {"state": "done", "task": resumed_task, "legacy_status": terminal_status, "external_id": external_id, "cmd_id": cmd_id}

        COMMAND_TERMINAL.labels(terminal_status=terminal_status).inc()
        failed_task = await self._task_repository.mark_failed(
            task_id=task.id,
            owner=str(task.claimed_by or ""),
            error_code=f"command_{terminal_status.strip().lower()}",
            error_message=last_error or f"Command terminal status {terminal_status}",
            now=now,
        )
        if failed_task is None:
            raise TaskExecutionError("ae3_failed_transition_failed", f"Task {task.id} could not fail on {terminal_status}")
        return {
            "state": "failed",
            "task": failed_task,
            "legacy_status": terminal_status,
            "external_id": external_id,
            "cmd_id": cmd_id,
            "error_code": failed_task.error_code,
            "error_message": failed_task.error_message,
        }

    def _extract_publish_payload(self, command: PlannedCommand) -> tuple[str, Mapping[str, Any]]:
        payload = command.payload if isinstance(command.payload, Mapping) else {}
        cmd_name = str(payload.get("cmd") or "").strip()
        params = payload.get("params")
        if not cmd_name or not isinstance(params, Mapping):
            raise TaskExecutionError("ae3_invalid_planned_command", "PlannedCommand payload must contain cmd and params")
        return cmd_name, params

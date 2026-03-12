"""Reconcile AE3-Lite waiting command against legacy commands table."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional

from ae3lite.application.dto import CommandReconcileResult
from ae3lite.application.use_cases.finalize_task import FinalizeTaskUseCase
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import CommandReconcileError, TaskFinalizeError

_NON_TERMINAL_STATUSES = frozenset({"PENDING", "QUEUED", "SENT", "ACK", "ACCEPTED", "RUNNING"})
_TERMINAL_STATUSES = frozenset({"DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT", "TIMEOUT", "SEND_FAILED"})


class ReconcileCommandUseCase:
    """Reads legacy command status and finalizes AE3-Lite task only on terminal state."""

    def __init__(self, *, task_repository: Any, command_repository: Any, finalize_task_use_case: Any | None = None) -> None:
        self._task_repository = task_repository
        self._command_repository = command_repository
        self._finalize_task_use_case = finalize_task_use_case or FinalizeTaskUseCase(task_repository=task_repository)

    async def run(self, *, task: AutomationTask, now: datetime) -> CommandReconcileResult:
        if not task.claimed_by:
            raise CommandReconcileError(f"Task {task.id} has no claimed_by owner for reconcile")

        ae_command = await self._command_repository.get_latest_for_task(task_id=task.id)
        if ae_command is None:
            raise CommandReconcileError(f"Task {task.id} has no ae_command to reconcile")

        legacy_row, external_id, cmd_id = await self._resolve_legacy_command(task=task, ae_command=ae_command)
        if legacy_row is None:
            return CommandReconcileResult(
                task=task,
                ae_command_id=int(ae_command["id"]),
                external_id=external_id,
                legacy_cmd_id=cmd_id,
                legacy_status=None,
                terminal_status=None,
                is_terminal=False,
            )

        legacy_status = str(legacy_row.get("status") or "").strip().upper()
        if legacy_status not in _NON_TERMINAL_STATUSES | _TERMINAL_STATUSES:
            raise CommandReconcileError(
                f"Unsupported legacy command status={legacy_status or 'empty'} for external_id={external_id}"
            )

        ack_received_at = legacy_row.get("ack_at")
        terminal_status = legacy_status if legacy_status in _TERMINAL_STATUSES else None
        terminal_at = self._resolve_terminal_at(legacy_row) if terminal_status else None
        last_error = self._resolve_last_error(legacy_row, terminal_status)

        await self._command_repository.update_from_legacy(
            ae_command_id=int(ae_command["id"]),
            external_id=external_id,
            ack_received_at=ack_received_at,
            terminal_status=terminal_status,
            terminal_at=terminal_at,
            last_error=last_error,
            now=now,
        )

        try:
            if terminal_status == "DONE":
                task = await self._finalize_task_use_case.complete(
                    task=task,
                    owner=task.claimed_by,
                    now=now,
                )
            elif terminal_status is not None:
                task = await self._finalize_task_use_case.fail(
                    task=task,
                    owner=task.claimed_by,
                    error_code=self._map_error_code(terminal_status),
                    error_message=last_error or f"Command terminal status {terminal_status}",
                    now=now,
                )
        except TaskFinalizeError as exc:
            raise CommandReconcileError(str(exc)) from exc

        return CommandReconcileResult(
            task=task,
            ae_command_id=int(ae_command["id"]),
            external_id=external_id,
            legacy_cmd_id=cmd_id,
            legacy_status=legacy_status,
            terminal_status=terminal_status,
            is_terminal=terminal_status is not None,
        )

    async def _resolve_legacy_command(
        self,
        *,
        task: AutomationTask,
        ae_command: Mapping[str, Any],
    ) -> tuple[Optional[Mapping[str, Any]], Optional[str], Optional[str]]:
        external_id = str(ae_command.get("external_id") or "").strip() or None
        payload = ae_command.get("payload")
        payload = payload if isinstance(payload, Mapping) else {}
        cmd_id = str(payload.get("cmd_id") or "").strip() or None

        if external_id:
            row = await self._command_repository.get_legacy_command_by_id(external_id=external_id)
            if row is None:
                raise CommandReconcileError(f"Legacy command not found for external_id={external_id}")
            return row, external_id, str(row.get("cmd_id") or "").strip() or cmd_id

        if not cmd_id:
            raise CommandReconcileError(f"ae_command {ae_command.get('id')} has neither external_id nor payload.cmd_id")

        row = await self._command_repository.get_legacy_command_by_cmd_id(zone_id=task.zone_id, cmd_id=cmd_id)
        if row is None:
            return None, None, cmd_id
        return row, str(row["id"]), cmd_id

    def _resolve_terminal_at(self, legacy_row: Mapping[str, Any]) -> Optional[datetime]:
        return (
            legacy_row.get("failed_at")
            or legacy_row.get("ack_at")
            or legacy_row.get("updated_at")
            or legacy_row.get("sent_at")
            or legacy_row.get("created_at")
        )

    def _resolve_last_error(self, legacy_row: Mapping[str, Any], terminal_status: Optional[str]) -> Optional[str]:
        if terminal_status in {None, "DONE"}:
            return None
        return str(legacy_row.get("error_message") or f"Command terminal status {terminal_status}")

    def _map_error_code(self, terminal_status: str) -> str:
        return f"command_{terminal_status.strip().lower()}"

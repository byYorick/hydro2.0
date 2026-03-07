"""Publish a planned AE3-Lite command via history-logger."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any, Mapping

from ae3lite.domain.entities import AutomationTask, PlannedCommand
from ae3lite.domain.errors import CommandPublishError


class PublishPlannedCommandUseCase:
    """Persists ae_commands before publish and records legacy external_id after publish."""

    def __init__(self, *, task_repository: Any, command_repository: Any, history_logger_client: Any) -> None:
        self._task_repository = task_repository
        self._command_repository = command_repository
        self._history_logger_client = history_logger_client

    async def run(self, *, task: AutomationTask, command: PlannedCommand, now: datetime) -> PlannedCommand:
        cmd_name, params = self._extract_publish_payload(command)
        cmd_id = self._build_publish_cmd_id(task=task, command=command)
        command_payload = dict(command.payload)
        command_payload["cmd_id"] = cmd_id
        ae_command_id = await self._command_repository.create_pending(
            task_id=task.id,
            step_no=command.step_no,
            node_uid=command.node_uid,
            channel=command.channel,
            payload=command_payload,
            now=now,
        )

        try:
            greenhouse_uid = await self._command_repository.resolve_greenhouse_uid(zone_id=task.zone_id)
            if not greenhouse_uid:
                raise CommandPublishError(f"Unable to resolve greenhouse_uid for zone_id={task.zone_id}")

            history_logger_cmd_id = await self._history_logger_client.publish(
                greenhouse_uid=greenhouse_uid,
                zone_id=task.zone_id,
                node_uid=command.node_uid,
                channel=command.channel,
                cmd=cmd_name,
                params=params,
                cmd_id=cmd_id,
            )
            legacy_command_id = await self._command_repository.resolve_legacy_command_id(
                zone_id=task.zone_id,
                cmd_id=history_logger_cmd_id,
            )
            if legacy_command_id is None:
                raise CommandPublishError(
                    f"Legacy commands.id not found for zone_id={task.zone_id} cmd_id={history_logger_cmd_id}"
                )
            await self._command_repository.mark_publish_accepted(
                ae_command_id=ae_command_id,
                external_id=str(legacy_command_id),
                now=now,
            )
            updated_task = await self._task_repository.mark_waiting_command(
                task_id=task.id,
                owner=str(task.claimed_by or ""),
                now=now,
            )
            if updated_task is None:
                raise CommandPublishError(f"Unable to move task_id={task.id} into waiting_command")
        except Exception as exc:
            await self._command_repository.mark_publish_failed(
                ae_command_id=ae_command_id,
                last_error=str(exc),
                now=now,
            )
            if task.claimed_by:
                await self._task_repository.mark_failed(
                    task_id=task.id,
                    owner=task.claimed_by,
                    error_code="command_send_failed",
                    error_message=str(exc),
                    now=now,
                )
            if isinstance(exc, CommandPublishError):
                raise
            raise CommandPublishError(str(exc)) from exc

        return replace(command, payload=command_payload, external_id=str(legacy_command_id))

    def _extract_publish_payload(self, command: PlannedCommand) -> tuple[str, Mapping[str, Any]]:
        payload = command.payload if isinstance(command.payload, Mapping) else {}
        cmd_name = str(payload.get("cmd") or "").strip()
        params = payload.get("params")
        if not cmd_name or not isinstance(params, Mapping):
            raise CommandPublishError("PlannedCommand payload must contain cmd and params for publish")
        return cmd_name, params

    def _build_publish_cmd_id(self, *, task: AutomationTask, command: PlannedCommand) -> str:
        return f"ae3-t{task.id}-z{task.zone_id}-s{command.step_no}"

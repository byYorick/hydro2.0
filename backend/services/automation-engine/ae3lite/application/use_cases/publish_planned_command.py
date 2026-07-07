"""Публикация planned-команды AE3-Lite через history-logger."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from ae3lite.domain.entities import AutomationTask, PlannedCommand
from ae3lite.domain.errors import CommandPublishError
from ae3lite.infrastructure.gateways.command_publish_pipeline import CommandPublishPipeline


class PublishPlannedCommandUseCase:
    """Сохраняет `ae_commands` перед публикацией и записывает legacy external_id после неё."""

    def __init__(self, *, task_repository: Any, command_repository: Any, history_logger_client: Any) -> None:
        self._task_repository = task_repository
        self._command_repository = command_repository
        self._publish_pipeline = CommandPublishPipeline(
            command_repository=command_repository,
            history_logger_client=history_logger_client,
        )

    async def run(self, *, task: AutomationTask, command: PlannedCommand, now: datetime) -> PlannedCommand:
        try:
            published = await self._publish_pipeline.publish(task=task, command=command, now=now)
        except Exception as exc:
            if isinstance(exc, CommandPublishError):
                raise
            raise CommandPublishError(str(exc)) from exc

        command_payload = dict(command.payload)
        command_payload["cmd_id"] = published.cmd_id

        if published.external_id is None:
            updated_task = await self._task_repository.mark_waiting_command(
                task_id=task.id,
                owner=str(task.claimed_by or ""),
                now=now,
            )
            if updated_task is None:
                raise CommandPublishError(f"Не удалось перевести task_id={task.id} в waiting_command")
            return replace(
                command,
                step_no=published.step_no,
                payload=command_payload,
                external_id=None,
            )

        updated_task = await self._task_repository.mark_waiting_command(
            task_id=task.id,
            owner=str(task.claimed_by or ""),
            now=now,
        )
        if updated_task is None:
            raise CommandPublishError(f"Не удалось перевести task_id={task.id} в waiting_command")

        return replace(
            command,
            step_no=published.step_no,
            payload=command_payload,
            external_id=published.external_id,
        )

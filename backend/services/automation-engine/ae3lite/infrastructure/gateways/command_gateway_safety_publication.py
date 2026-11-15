"""SequentialCommandGateway safety publication: explicit collaborators and invocation context."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping, Sequence

from ae3lite.domain.entities import PlannedCommand
from ae3lite.infrastructure.gateways.command_gateway_shared import _PUMP_MAIN_CHANNEL


@dataclass(frozen=True)
class CommandGatewaySafetyPublicationPorts:
    run_command: Callable[..., Awaitable[Any]]
    publish_without_terminal: Callable[..., Awaitable[Any]]


class CommandGatewaySafetyPublication:
    def __init__(self, ports: CommandGatewaySafetyPublicationPorts) -> None:
        self._ports = ports

    async def run_publish_only_batch(
        self,
        *,
        task: Any,
        commands: Sequence[PlannedCommand],
        now: datetime,
    ) -> Mapping[str, Any]:
        """Fail-safe publish-only: pump_main строго первым, затем fan-out без await terminal.

        Успех = все publish приняты HL/MQTT (HTTP accept). Terminal DONE не ждём:
        команды должны уйти на железо максимально быстро; alert уже есть на failure.
        """
        if not commands:
            return {
                "success": True,
                "task": task,
                "commands_total": 0,
                "commands_failed": 0,
                "command_statuses": [],
            }

        pump_items: list[tuple[int, PlannedCommand]] = []
        other_items: list[tuple[int, PlannedCommand]] = []
        for seq_index, command in enumerate(commands):
            channel = str(command.channel or "").strip().lower()
            if channel == _PUMP_MAIN_CHANNEL:
                pump_items.append((seq_index, command))
            else:
                other_items.append((seq_index, command))

        combined_statuses: list[dict[str, Any]] = []
        failures: list[tuple[str, str]] = []

        def _record_result(result: Mapping[str, Any] | BaseException) -> None:
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                failures.append(
                    (
                        str(getattr(result, "code", "") or "command_send_failed"),
                        str(result).strip() or type(result).__name__,
                    )
                )
                return
            combined_statuses.extend(result["command_statuses"])
            if not bool(result["success"]):
                failures.append(
                    (
                        str(result.get("error_code") or "command_failed"),
                        str(result.get("error_message") or "Команда завершилась ошибкой"),
                    )
                )

        # 1) pump_main OFF — строго первым. Ошибка одного насоса не отменяет
        # остальные доступные каналы: адрес второго устройства всё ещё валиден.
        for seq_index, command in pump_items:
            try:
                result = await self._ports.publish_without_terminal(
                    task=task,
                    command=command,
                    now=now,
                    seq_index=seq_index,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _record_result(exc)
                continue
            _record_result(result)

        # 2) Остальные OFF — fan-out publish без await terminal между ними.
        if other_items:
            gathered = await asyncio.gather(
                *(
                    self._ports.publish_without_terminal(
                        task=task,
                        command=command,
                        now=now,
                        seq_index=seq_index,
                    )
                    for seq_index, command in other_items
                ),
                return_exceptions=True,
            )
            for result in gathered:
                _record_result(result)

        if failures:
            error_code, error_message = failures[0]
            return {
                "success": False,
                "task": task,
                "commands_total": len(commands),
                "commands_failed": len(failures),
                "command_statuses": combined_statuses,
                "error_code": error_code,
                "error_message": error_message,
            }

        return {
            "success": True,
            "task": task,
            "commands_total": len(commands),
            "commands_failed": 0,
            "command_statuses": combined_statuses,
        }

    async def publish_without_terminal(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        now: datetime,
        seq_index: int = 0,
    ) -> Mapping[str, Any]:
        """Publish команды до HL accept без ожидания terminal DONE."""
        return await self._ports.run_command(
            task=task,
            command=command,
            now=now,
            track_task_state=False,
            seq_index=seq_index,
            await_terminal=False,
        )

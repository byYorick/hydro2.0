"""SequentialCommandGateway payload: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.gateways.command_gateway_shared import (
    _AE3_RECOVERY_RESUME_KEY,
    _AE3_STAGE_EXECUTION_TOKEN_KEY,
)


@dataclass(frozen=True)
class CommandGatewayPayloadPorts:
    stage_execution_token: Callable[..., Any]


class CommandGatewayPayload:
    def __init__(self, ports: CommandGatewayPayloadPorts) -> None:
        self._ports = ports

    def planned_command_from_ae_command(self, ae_command: Mapping[str, Any]) -> PlannedCommand | None:
        node_uid = str(ae_command.get("node_uid") or "").strip()
        channel = str(ae_command.get("channel") or "").strip()
        if not node_uid or not channel:
            return None
        payload = ae_command.get("payload")
        if not isinstance(payload, Mapping):
            return None
        cmd = str(payload.get("cmd") or "").strip()
        if not cmd:
            return None
        try:
            step_no = int(ae_command.get("step_no") or 1)
        except (TypeError, ValueError):
            step_no = 1
        return PlannedCommand(
            step_no=max(1, step_no),
            node_uid=node_uid,
            channel=channel,
            payload=dict(payload),
        )

    def enrich_command_payload(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        recovery_resume_marker: Mapping[str, Any] | None = None,
    ) -> PlannedCommand:
        """Добавляет stage token и (при resume) marker, чтобы skip/recovery были scoped."""
        payload = dict(command.payload) if isinstance(command.payload, Mapping) else {}
        payload[_AE3_STAGE_EXECUTION_TOKEN_KEY] = self._ports.stage_execution_token(task=task)
        if recovery_resume_marker is not None:
            payload[_AE3_RECOVERY_RESUME_KEY] = dict(recovery_resume_marker)
        return replace(command, payload=payload)

    def extract_publish_payload(self, command: PlannedCommand) -> tuple[str, Mapping[str, Any]]:
        payload = command.payload if isinstance(command.payload, Mapping) else {}
        cmd_name = str(payload.get("cmd") or "").strip()
        params = payload.get("params")
        if not cmd_name or not isinstance(params, Mapping):
            raise TaskExecutionError("ae3_invalid_planned_command", "PlannedCommand должен содержать cmd и params")
        return cmd_name, params

    def complete_on_ack(self, command: PlannedCommand) -> bool:
        payload = command.payload if isinstance(command.payload, Mapping) else {}
        return bool(payload.get("complete_on_ack"))

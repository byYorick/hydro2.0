"""SequentialCommandGateway diagnostics: explicit collaborators and invocation context."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.gateways.command_gateway_shared import logger
from ae3lite.infrastructure.metrics import (
    COMMAND_POLL_ITERATIONS,
    COMMAND_ROUNDTRIP_DURATION,
    inc_observability_write_failed,
)


@dataclass(frozen=True)
class CommandGatewayDiagnosticsPorts:
    global_create_zone_event: Callable[..., Any]


class CommandGatewayDiagnostics:
    def __init__(self, ports: CommandGatewayDiagnosticsPorts) -> None:
        self._ports = ports

    async def emit_poll_deadline_exceeded_event(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        cmd_id: str,
        external_id: str,
        checked_at: datetime,
        deadline: datetime,
        poll_iterations: int,
        deadline_kind: str = "poll",
    ) -> None:
        try:
            await self._ports.global_create_zone_event(
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
                    "deadline_kind": str(deadline_kind or "poll"),
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

    def observe_roundtrip_metrics(
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

    async def maybe_raise_offline_instead_of_command_error(
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

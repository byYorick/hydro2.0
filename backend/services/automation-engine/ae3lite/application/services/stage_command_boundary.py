"""Stage component: commands. Explicit ports; no handler dependency."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping, Sequence

from ae3lite.domain.errors import ErrorCodes, TaskExecutionError

_logger = logging.getLogger("ae3lite.application.handlers.base")


@dataclass(frozen=True)
class StageCommandBoundaryPorts:
    remap_execution_error: Callable[..., Awaitable[Any]]
    command_gateway: Callable[[], Any]
    extract_irr_probe_node_uid: Callable[..., Any]
    runtime_monitor: Callable[[], Any]


class StageCommandBoundary:
    def __init__(self, ports: StageCommandBoundaryPorts) -> None:
        self._ports = ports

    @staticmethod
    def first_command_node_uid(commands: Sequence[Any]) -> str | None:
        for cmd in commands:
            uid = getattr(cmd, "node_uid", None)
            if uid is None and isinstance(cmd, Mapping):
                uid = cmd.get("node_uid")
            if uid:
                return str(uid).strip() or None
        return None

    async def remap_execution_error(
        self,
        *,
        task: Any,
        error_code: str,
        error_message: str,
        node_uid: str | None = None,
        plan: Any = None,
    ) -> tuple[str, str]:
        from ae3lite.domain.services.zone_node_availability import (
            resolve_task_error_with_node_offline,
        )

        effective_node = node_uid or self._ports.extract_irr_probe_node_uid(plan=plan)
        offline = await resolve_task_error_with_node_offline(
            zone_id=int(getattr(task, "zone_id", 0) or 0),
            topology=str(getattr(task, "topology", "") or ""),
            error_code=error_code,
            error_message=error_message,
            node_uid=effective_node,
            runtime_monitor=self._ports.runtime_monitor(),
        )
        if offline is not None:
            return offline.code, offline.message
        return error_code, error_message

    async def raise_execution_error(
        self,
        *,
        task: Any,
        error_code: str,
        error_message: str,
        node_uid: str | None = None,
        plan: Any = None,
        deadline_kind: str | None = None,
    ) -> None:
        if error_code in {
            ErrorCodes.AE3_COMMAND_POLL_DEADLINE_EXCEEDED,
            ErrorCodes.AE3_COMMAND_STAGE_BUDGET_INSUFFICIENT,
        }:
            code, message = error_code, error_message
        else:
            code, message = await self._ports.remap_execution_error(
                task=task,
                error_code=error_code,
                error_message=error_message,
                node_uid=node_uid,
                plan=plan,
            )
        exc = TaskExecutionError(code, message)
        if deadline_kind is not None:
            exc.deadline_kind = str(deadline_kind)
        raise exc

    async def ensure_command_targets_online(
        self,
        *,
        task: Any,
        commands: Sequence[Any],
    ) -> None:
        from ae3lite.domain.services.zone_node_availability import (
            offline_failure_for_node_liveness,
        )

        zone_id = int(getattr(task, "zone_id", 0) or 0)
        if zone_id <= 0:
            return
        seen: set[str] = set()
        for cmd in commands:
            uid = getattr(cmd, "node_uid", None)
            if uid is None and isinstance(cmd, Mapping):
                uid = cmd.get("node_uid")
            uid = str(uid or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            failure = await offline_failure_for_node_liveness(
                zone_id=zone_id,
                node_uid=uid,
                runtime_monitor=self._ports.runtime_monitor(),
            )
            if failure is not None:
                raise TaskExecutionError(failure.code, failure.message)

    async def run_command_batch_checked(
        self,
        *,
        task: Any,
        commands: Sequence[Any],
        now: datetime,
        track_task_state: bool = True,
    ) -> Mapping[str, Any]:
        await self.ensure_command_targets_online(task=task, commands=commands)
        result = await self._ports.command_gateway().run_batch(
            task=task,
            commands=commands,
            now=now,
            track_task_state=track_task_state,
        )
        if not result["success"]:
            await self.raise_execution_error(
                task=task,
                error_code=str(result["error_code"]),
                error_message=str(result["error_message"]),
                node_uid=self.first_command_node_uid(commands),
                deadline_kind=(str(result.get("deadline_kind")) if result.get("deadline_kind") is not None else None),
            )
        return result

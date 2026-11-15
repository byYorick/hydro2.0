"""WorkflowRouter handler boundary: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Callable, Mapping

from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.zone_node_availability import resolve_task_error_with_node_offline
from ae3lite.hydraulics.failure_report import (
    close_upward_capture,
    drain_upward_reports,
    open_upward_capture,
)
from ae3lite.infrastructure.metrics import (
    TASK_FAILED,
)


@dataclass(frozen=True)
class WorkflowRoutingHandlerBoundaryPorts:
    runtime_monitor: Callable[[], Any]


class WorkflowRoutingHandlerBoundary:
    def __init__(self, ports: WorkflowRoutingHandlerBoundaryPorts) -> None:
        self._ports = ports

    async def invoke_handler(
        self,
        *,
        handler: BaseStageHandler,
        task: Any,
        plan: Any,
        stage_def: Any,
        now: datetime,
    ) -> Any:
        """Запускает модуль и забирает его отчёты. Наружу их здесь не шлёт."""
        token = open_upward_capture()
        try:
            try:
                outcome = await handler.run(
                    task=task,
                    plan=plan,
                    stage_def=stage_def,
                    now=now,
                )
            except TaskExecutionError as exc:
                reports = drain_upward_reports()
                code, message = await self.remap_execution_error_for_task(
                    task=task,
                    error_code=str(exc.code),
                    error_message=str(exc),
                    node_uid=self.extract_irrig_node_uid_from_plan(plan=plan),
                )
                remapped = TaskExecutionError(code, message)
                remapped.upward_reports = tuple(getattr(exc, "upward_reports", ()) or ()) + reports
                deadline_kind = getattr(exc, "deadline_kind", None)
                if deadline_kind is not None:
                    remapped.deadline_kind = str(deadline_kind)
                raise remapped from exc
            reports = drain_upward_reports()
            existing = tuple(getattr(outcome, "upward_reports", ()) or ())
            if reports or existing:
                return replace(outcome, upward_reports=existing + reports)
            return outcome
        finally:
            close_upward_capture(token)

    async def fail_task(
        self,
        *,
        task: Any,
        now: datetime,
        error_code: str,
        error_message: str,
        upward_reports: tuple[Any, ...] = (),
    ) -> Any:
        TASK_FAILED.labels(topology=task.topology, error_code=error_code).inc()
        error = TaskExecutionError(error_code, error_message)
        error.upward_reports = upward_reports
        raise error

    async def remap_execution_error_for_task(
        self,
        *,
        task: Any,
        error_code: str,
        error_message: str,
        node_uid: str | None = None,
    ) -> tuple[str, str]:
        offline = await resolve_task_error_with_node_offline(
            zone_id=int(getattr(task, "zone_id", 0) or 0),
            topology=str(getattr(task, "topology", "") or ""),
            error_code=error_code,
            error_message=error_message,
            node_uid=node_uid,
            runtime_monitor=self._ports.runtime_monitor(),
        )
        if offline is not None:
            return offline.code, offline.message
        return error_code, error_message

    @staticmethod
    def extract_irrig_node_uid_from_plan(*, plan: Any) -> str | None:
        if plan is None:
            return None
        named_plans = getattr(plan, "named_plans", None) or {}
        if isinstance(named_plans, Mapping):
            probe_cmds = named_plans.get("irr_state_probe", ())
            for step in probe_cmds or ():
                uid = str(getattr(step, "node_uid", "") or "").strip()
                if uid:
                    return uid
            for commands in named_plans.values():
                for step in commands or ():
                    uid = str(getattr(step, "node_uid", "") or "").strip()
                    if uid:
                        return uid
        for step in getattr(plan, "steps", ()) or ():
            uid = str(getattr(step, "node_uid", "") or "").strip()
            if uid:
                return uid
        return None

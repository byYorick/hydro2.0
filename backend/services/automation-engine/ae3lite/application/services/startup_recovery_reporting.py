"""StartupRecoveryUseCase reporting: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ae3lite.application.dto import StartupRecoveryTerminalOutcome
from ae3lite.application.services.startup_recovery_shared import _STARTUP_RECOVERY_OUTCOME_EVENT, logger
from ae3lite.application.services.startup_recovery_state import StartupRecoveryState
from ae3lite.domain.entities import AutomationTask


@dataclass(frozen=True)
class StartupRecoveryReportingPorts:
    global_create_zone_event: Callable[..., Any]
    global_send_service_log: Callable[..., Any]


class StartupRecoveryReporting:
    def __init__(self, ports: StartupRecoveryReportingPorts, state: StartupRecoveryState) -> None:
        self._ports = ports
        self._state = state

    async def record_startup_recovery_outcome(
        self,
        *,
        zone_id: int,
        task_id: int,
        topology: str,
        stage: str,
        outcome: str,
        terminal_outcome: StartupRecoveryTerminalOutcome | None,
        recovery_source: str = "startup_recovery",
    ) -> None:
        payload: dict[str, Any] = {
            "task_id": task_id,
            "outcome": outcome,
            "topology": topology,
            "stage": stage,
            "recovery_source": recovery_source,
        }
        if terminal_outcome is not None:
            payload["intent_id"] = int(terminal_outcome.intent_id)
            payload["success"] = bool(terminal_outcome.success)
            if terminal_outcome.error_code:
                payload["error_code"] = str(terminal_outcome.error_code)
            if terminal_outcome.error_message:
                payload["error_message"] = str(terminal_outcome.error_message)
        log_level = "warning" if outcome == "failed" else "info"
        try:
            await self._ports.global_create_zone_event(zone_id, _STARTUP_RECOVERY_OUTCOME_EVENT, payload)
        except Exception:
            logger.warning(
                "Startup recovery: failed to write zone_event zone_id=%s task_id=%s outcome=%s",
                zone_id,
                task_id,
                outcome,
                exc_info=True,
            )
        try:
            self._ports.global_send_service_log(
                service="automation-engine",
                level=log_level,
                message="AE3 startup recovery outcome",
                context={"zone_id": zone_id, **payload},
            )
        except Exception:
            logger.warning(
                "Startup recovery: failed to write service log zone_id=%s task_id=%s outcome=%s",
                zone_id,
                task_id,
                outcome,
                exc_info=True,
            )

    def build_terminal_outcome(self, *, task: AutomationTask) -> StartupRecoveryTerminalOutcome | None:
        intent_id = task.intent_id or 0
        if intent_id <= 0:
            return None
        return StartupRecoveryTerminalOutcome(
            task_id=task.id,
            intent_id=intent_id,
            success=task.status == "completed",
            error_code=task.error_code,
            error_message=task.error_message,
        )

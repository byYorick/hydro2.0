"""Bound misc helper methods for SchedulerTaskExecutor class assignment."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from application.cycle_alerts import emit_cycle_alert as policy_emit_cycle_alert
from application.two_tank_logging import log_two_tank_safety_guard as policy_log_two_tank_safety_guard
from application.executor_constants import ERR_TWO_TANK_COMMAND_FAILED, REASON_CYCLE_REFILL_COMMAND_FAILED
from domain.policies.two_tank_guard_policy import (
    build_two_tank_check_payload as policy_build_two_tank_check_payload,
    build_two_tank_stop_not_confirmed_result as policy_build_two_tank_stop_not_confirmed_result,
)

logger = logging.getLogger(__name__)


async def bound_emit_cycle_alert(
    self,
    *,
    zone_id: int,
    code: str,
    message: str,
    severity: str,
    details: Dict[str, Any],
) -> None:
    await policy_emit_cycle_alert(
        zone_id=zone_id,
        code=code,
        message=message,
        severity=severity,
        details=details,
        send_infra_alert_fn=self.send_infra_alert_fn,
    )


def bound_build_two_tank_check_payload(
    self,
    *,
    payload: Dict[str, Any],
    workflow: str,
    phase_started_at: datetime,
    phase_timeout_at: datetime,
    phase_cycle: Optional[int] = None,
) -> Dict[str, Any]:
    return policy_build_two_tank_check_payload(
        payload=payload,
        workflow=workflow,
        phase_started_at=phase_started_at,
        phase_timeout_at=phase_timeout_at,
        phase_cycle=phase_cycle,
    )


def bound_log_two_tank_safety_guard(
    self,
    *,
    zone_id: int,
    context: Dict[str, Any],
    phase: str,
    stop_result: Dict[str, Any],
    level: int = logging.WARNING,
) -> None:
    policy_log_two_tank_safety_guard(
        logger_obj=logger,
        zone_id=zone_id,
        context=context,
        phase=phase,
        stop_result=stop_result,
        feature_flag_state=self._two_tank_safety_guards_enabled(),
        level=level,
    )


def bound_build_two_tank_stop_not_confirmed_result(
    self,
    *,
    workflow: str,
    mode: str,
    reason: str,
    stop_result: Dict[str, Any],
    fallback_error_code: str = ERR_TWO_TANK_COMMAND_FAILED,
) -> Dict[str, Any]:
    return policy_build_two_tank_stop_not_confirmed_result(
        workflow=workflow,
        mode=mode,
        reason=reason,
        stop_result=stop_result,
        reason_code=REASON_CYCLE_REFILL_COMMAND_FAILED,
        feature_flag_state=self._two_tank_safety_guards_enabled(),
        fallback_error_code=fallback_error_code,
    )


__all__ = [
    "bound_build_two_tank_check_payload",
    "bound_build_two_tank_stop_not_confirmed_result",
    "bound_emit_cycle_alert",
    "bound_log_two_tank_safety_guard",
]

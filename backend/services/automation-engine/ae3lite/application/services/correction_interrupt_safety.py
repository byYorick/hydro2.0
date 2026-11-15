"""Безопасная верификация железа после startup_recovery_correction_interrupted.

После power-loss / рестарта AE нельзя сразу эскалировать critical
``biz_flow_stop_failed_hardware_may_be_active``: узлы ещё offline, актуаторы
обычно уже OFF после brownout. Сначала pending-verify → при подтверждённом
безопасном состоянии — safe; critical только если после grace оборудование
ON или безопасность не подтверждена.

Fail-closed инварианты (safety):
- ``ready|idle`` + отсутствующий/устаревший IRR_STATE_SNAPSHOT **не** auto-safe:
  pending до grace, затем unsafe (нужен свежий OFF snapshot).
- Irrig OFF через irr_state — необходимое, но **недостаточное** условие для
  ``corr_dose_*`` / ``corr_wait_*``: каналы дозирующих насосов EC/pH через
  irr_state пока **недоступны** → dose-path fail-closed (не safe, pending до
  grace / unsafe после). Без подтверждения dose-path нельзя эмитить
  HARDWARE_SAFE и разрешать irrigation replay.
- Resume mid-dose запрещён (pending-check строится только для dose/wait steps;
  safe ≠ resume коррекции).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from ae3lite.application.handlers.flow_path_guard import (
    CORRECTION_DOSE_STEPS,
    emit_correction_interrupted_hardware_risk,
    flow_path_stage_config,
)
from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.services.zone_node_availability import TWO_TANK_REQUIRED_NODE_TYPES
from ae3lite.infrastructure.metrics import inc_observability_write_failed
from ae3lite.infrastructure.metrics import FLOW_STOP_FAILED
from common.biz_alerts import send_biz_alert
from common.db import create_zone_event, fetch

_logger = logging.getLogger(__name__)

PENDING_VERIFY_EVENT = "AE_CORRECTION_INTERRUPT_PENDING_VERIFY"
HARDWARE_SAFE_EVENT = "AE_CORRECTION_INTERRUPT_HARDWARE_SAFE"
ESCALATED_HARDWARE_RISK_EVENT = "FLOW_STOP_FAILED_HARDWARE_MAY_BE_ACTIVE"

DEFAULT_VERIFY_GRACE_SEC = 120
DEFAULT_IRR_STATE_MAX_AGE_SEC = 90
# status=online без свежего last_seen/heartbeat считается stale → не online (fail-closed).
DEFAULT_NODE_ONLINE_MAX_AGE_SEC = 120
# Сколько хранить «открытые» PENDING_VERIFY для reload после рестарта AE.
DEFAULT_PENDING_VERIFY_LOOKBACK_HOURS = 24

# Dose actuators (EC/pH pumps) are not represented in irrig IRR_STATE_SNAPSHOT.
DOSE_ACTUATORS_UNVERIFIABLE_REASON = "dose_actuators_unverifiable_via_irr_state"


from ae3lite.application.services.interrupt_safety_records import (
    CorrectionInterruptPendingCheck,
    CorrectionInterruptSafetyVerdict,
    CorrectionInterruptFailSafeStopResult,
    _FakeTaskForAlert,
    _FakeTaskForFailSafe,
)
from ae3lite.application.services.interrupt_safety_policy import InterruptSafetyPolicy, InterruptSafetyPolicyPorts


def _interrupt_safety_policy() -> InterruptSafetyPolicy:
    return InterruptSafetyPolicy(
        InterruptSafetyPolicyPorts(
            default_verify_grace_sec=lambda: DEFAULT_VERIFY_GRACE_SEC,
            dose_actuators_unverifiable_reason=lambda: DOSE_ACTUATORS_UNVERIFIABLE_REASON,
            is_dose_correction_step=lambda *args, **kwargs: is_dose_correction_step(*args, **kwargs),
        )
    )


from ae3lite.application.services.interrupt_safety_pending_checks import (
    InterruptSafetyPendingChecks,
    InterruptSafetyPendingChecksPorts,
)


def _interrupt_safety_pending_checks() -> InterruptSafetyPendingChecks:
    return InterruptSafetyPendingChecks(
        InterruptSafetyPendingChecksPorts(
            escalated_hardware_risk_event=lambda: ESCALATED_HARDWARE_RISK_EVENT,
            hardware_safe_event=lambda: HARDWARE_SAFE_EVENT,
            pending_verify_event=lambda: PENDING_VERIFY_EVENT,
            parse_deadline_at=lambda *args, **kwargs: _parse_deadline_at(*args, **kwargs),
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
            is_dose_correction_step=lambda *args, **kwargs: is_dose_correction_step(*args, **kwargs),
            pending_check_from_event_payload=lambda *args, **kwargs: pending_check_from_event_payload(*args, **kwargs),
        )
    )


from ae3lite.application.services.interrupt_safety_shutdown_plan import (
    InterruptSafetyShutdownPlan,
    InterruptSafetyShutdownPlanPorts,
)


def _interrupt_safety_shutdown_plan() -> InterruptSafetyShutdownPlan:
    return InterruptSafetyShutdownPlan(
        InterruptSafetyShutdownPlanPorts(
            fail_safe_shutdown_channels=lambda: FAIL_SAFE_SHUTDOWN_CHANNELS,
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
        )
    )


from ae3lite.application.services.interrupt_safety_shutdown_execution import (
    InterruptSafetyShutdownExecution,
    InterruptSafetyShutdownExecutionPorts,
)


def _interrupt_safety_shutdown_execution() -> InterruptSafetyShutdownExecution:
    return InterruptSafetyShutdownExecution(
        InterruptSafetyShutdownExecutionPorts(
            logger=lambda: _logger,
            normalize_fail_safe_actuators=lambda *args, **kwargs: _normalize_fail_safe_actuators(*args, **kwargs),
            topology_fail_safe_on_flow=lambda *args, **kwargs: _topology_fail_safe_on_flow(*args, **kwargs),
            build_fail_safe_shutdown_commands=lambda *args, **kwargs: build_fail_safe_shutdown_commands(
                *args, **kwargs
            ),
            load_irrig_fail_safe_actuators=lambda *args, **kwargs: load_irrig_fail_safe_actuators(*args, **kwargs),
        )
    )


from ae3lite.application.services.interrupt_safety_alerts import InterruptSafetyAlerts, InterruptSafetyAlertsPorts


def _interrupt_safety_alerts() -> InterruptSafetyAlerts:
    return InterruptSafetyAlerts(
        InterruptSafetyAlertsPorts(
            flow_stop_failed=lambda: FLOW_STOP_FAILED,
            hardware_safe_event=lambda: HARDWARE_SAFE_EVENT,
            pending_verify_event=lambda: PENDING_VERIFY_EVENT,
            logger=lambda: _logger,
            create_zone_event=lambda *args, **kwargs: create_zone_event(*args, **kwargs),
            emit_correction_interrupted_hardware_risk=lambda *args, **kwargs: emit_correction_interrupted_hardware_risk(
                *args, **kwargs
            ),
            inc_observability_write_failed=lambda *args, **kwargs: inc_observability_write_failed(*args, **kwargs),
            pending_check_to_event_payload=lambda *args, **kwargs: pending_check_to_event_payload(*args, **kwargs),
            send_biz_alert=lambda *args, **kwargs: send_biz_alert(*args, **kwargs),
        )
    )


from ae3lite.application.services.interrupt_safety_availability import (
    InterruptSafetyAvailability,
    InterruptSafetyAvailabilityPorts,
)


def _interrupt_safety_availability() -> InterruptSafetyAvailability:
    return InterruptSafetyAvailability(
        InterruptSafetyAvailabilityPorts(
            node_is_fresh_online=lambda *args, **kwargs: _node_is_fresh_online(*args, **kwargs),
            fetch=lambda *args, **kwargs: fetch(*args, **kwargs),
        )
    )


from ae3lite.application.services.interrupt_safety_verification import (
    InterruptSafetyVerification,
    InterruptSafetyVerificationPorts,
)


def _interrupt_safety_verification() -> InterruptSafetyVerification:
    return InterruptSafetyVerification(
        InterruptSafetyVerificationPorts(
            pending_or_unsafe_after_grace=lambda *args, **kwargs: _pending_or_unsafe_after_grace(*args, **kwargs),
            assess_dose_path_risk=lambda *args, **kwargs: assess_dose_path_risk(*args, **kwargs),
            flow_snapshot_is_safe=lambda *args, **kwargs: flow_snapshot_is_safe(*args, **kwargs),
            read_workflow_phase=lambda *args, **kwargs: read_workflow_phase(*args, **kwargs),
            required_nodes_online=lambda *args, **kwargs: required_nodes_online(*args, **kwargs),
            zone_has_active_ae_task=lambda *args, **kwargs: zone_has_active_ae_task(*args, **kwargs),
        )
    )


async def emit_task_fail_safe_failure_alert(*, task: Any, reason: str, source: str) -> None:
    return await _interrupt_safety_alerts().emit_task_fail_safe_failure_alert(task=task, reason=reason, source=source)


# Канонический набор irrig-каналов для fail-safe OFF. pump_main остаётся первым в batch.
# ExecuteTaskUseCase.FAIL_SAFE_SHUTDOWN_CHANNELS — ссылка на этот же кортеж.
# Только эти гидравлические каналы, не все актуаторы зоны.
FAIL_SAFE_SHUTDOWN_CHANNELS = (
    "pump_main",
    "valve_clean_fill",
    "valve_clean_supply",
    "valve_solution_fill",
    "valve_solution_supply",
    "valve_irrigation",
    "valve_drain",
)


def is_dose_correction_step(corr_step: object) -> bool:
    return _interrupt_safety_policy().is_dose_correction_step(corr_step=corr_step)


def assess_dose_path_risk(*, corr_step: object) -> str | None:
    return _interrupt_safety_policy().assess_dose_path_risk(corr_step=corr_step)


def _parse_deadline_at(raw: object, *, fallback_now: datetime) -> datetime:
    return _interrupt_safety_policy().parse_deadline_at(raw=raw, fallback_now=fallback_now)


def pending_check_to_event_payload(check: CorrectionInterruptPendingCheck) -> dict[str, Any]:
    return _interrupt_safety_pending_checks().pending_check_to_event_payload(check=check)


def pending_check_from_event_payload(
    *,
    zone_id: int,
    payload: Mapping[str, Any],
    fallback_now: datetime | None = None,
) -> CorrectionInterruptPendingCheck | None:
    return _interrupt_safety_pending_checks().pending_check_from_event_payload(
        zone_id=zone_id, payload=payload, fallback_now=fallback_now
    )


async def load_open_pending_correction_interrupt_checks(
    *,
    now: datetime,
    lookback_hours: int = DEFAULT_PENDING_VERIFY_LOOKBACK_HOURS,
) -> tuple[CorrectionInterruptPendingCheck, ...]:
    return await _interrupt_safety_pending_checks().load_open_pending_correction_interrupt_checks(
        now=now, lookback_hours=lookback_hours
    )


async def load_irrig_fail_safe_actuators(*, zone_id: int) -> tuple[Mapping[str, Any], ...]:
    return await _interrupt_safety_shutdown_plan().load_irrig_fail_safe_actuators(zone_id=zone_id)


def build_fail_safe_shutdown_commands(
    *,
    actuators: Sequence[Mapping[str, Any]],
    planner_step_prefix: str = "corr_interrupt_fail_safe",
) -> tuple[PlannedCommand, ...]:
    return _interrupt_safety_shutdown_plan().build_fail_safe_shutdown_commands(
        actuators=actuators, planner_step_prefix=planner_step_prefix
    )


def _normalize_fail_safe_actuators(actuators: Sequence[Any]) -> tuple[Mapping[str, Any], ...]:
    return _interrupt_safety_shutdown_plan().normalize_fail_safe_actuators(actuators=actuators)


def _topology_fail_safe_on_flow(topology: str) -> bool:
    return _interrupt_safety_shutdown_plan().topology_fail_safe_on_flow(topology=topology)


async def attempt_task_fail_safe_shutdown(
    *,
    task: Any,
    now: datetime,
    command_gateway: Any | None,
    snapshot_actuators: Sequence[Any] | None = None,
    planner_step_prefix: str = "fail_safe_shutdown",
) -> CorrectionInterruptFailSafeStopResult:
    return await _interrupt_safety_shutdown_execution().attempt_task_fail_safe_shutdown(
        task=task,
        now=now,
        command_gateway=command_gateway,
        snapshot_actuators=snapshot_actuators,
        planner_step_prefix=planner_step_prefix,
    )


async def attempt_correction_interrupt_fail_safe_stop(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
    command_gateway: Any | None,
) -> CorrectionInterruptFailSafeStopResult:
    return await _interrupt_safety_shutdown_execution().attempt_correction_interrupt_fail_safe_stop(
        check=check, now=now, command_gateway=command_gateway
    )


def build_pending_check_from_task(
    *,
    task: Any,
    now: datetime,
    recovery_source: str = "startup_recovery",
    verify_grace_sec: int = DEFAULT_VERIFY_GRACE_SEC,
) -> CorrectionInterruptPendingCheck | None:
    return _interrupt_safety_policy().build_pending_check_from_task(
        task=task, now=now, recovery_source=recovery_source, verify_grace_sec=verify_grace_sec
    )


def flow_snapshot_is_safe(*, stage: str, snapshot: Mapping[str, Any] | None) -> bool:
    return _interrupt_safety_policy().flow_snapshot_is_safe(stage=stage, snapshot=snapshot)


async def emit_correction_interrupt_pending_verify(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
) -> None:
    return await _interrupt_safety_alerts().emit_correction_interrupt_pending_verify(check=check, now=now)


async def emit_correction_interrupt_hardware_safe(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
    reason: str,
    snapshot: Mapping[str, Any] | None = None,
) -> None:
    return await _interrupt_safety_alerts().emit_correction_interrupt_hardware_safe(
        check=check, now=now, reason=reason, snapshot=snapshot
    )


async def escalate_correction_interrupt_hardware_risk(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
    reason: str,
) -> None:
    return await _interrupt_safety_alerts().escalate_correction_interrupt_hardware_risk(
        check=check, now=now, reason=reason
    )


async def zone_has_active_ae_task(*, zone_id: int) -> bool:
    return await _interrupt_safety_availability().zone_has_active_ae_task(zone_id=zone_id)


def _node_is_fresh_online(
    *,
    status: str,
    last_seen_age_sec: int | None,
    max_age_sec: int,
) -> bool:
    return _interrupt_safety_policy().node_is_fresh_online(
        status=status, last_seen_age_sec=last_seen_age_sec, max_age_sec=max_age_sec
    )


async def required_nodes_online(
    *,
    zone_id: int,
    required_types: Sequence[str] = tuple(sorted(TWO_TANK_REQUIRED_NODE_TYPES)),
    max_age_sec: int = DEFAULT_NODE_ONLINE_MAX_AGE_SEC,
) -> tuple[bool, tuple[str, ...]]:
    return await _interrupt_safety_availability().required_nodes_online(
        zone_id=zone_id, required_types=required_types, max_age_sec=max_age_sec
    )


async def read_workflow_phase(*, zone_id: int) -> str | None:
    return await _interrupt_safety_availability().read_workflow_phase(zone_id=zone_id)


def _pending_or_unsafe_after_grace(
    *,
    now: datetime,
    deadline_at: datetime,
    pending_reason: str,
    unsafe_reason: str,
    snapshot: Mapping[str, Any] | None = None,
    nodes_online: bool = True,
    dose_risk: str | None = None,
) -> CorrectionInterruptSafetyVerdict:
    return _interrupt_safety_policy().pending_or_unsafe_after_grace(
        now=now,
        deadline_at=deadline_at,
        pending_reason=pending_reason,
        unsafe_reason=unsafe_reason,
        snapshot=snapshot,
        nodes_online=nodes_online,
        dose_risk=dose_risk,
    )


async def evaluate_correction_interrupt_safety(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
    runtime_monitor: Any,
    irr_state_max_age_sec: int = DEFAULT_IRR_STATE_MAX_AGE_SEC,
) -> CorrectionInterruptSafetyVerdict:
    return await _interrupt_safety_verification().evaluate_correction_interrupt_safety(
        check=check, now=now, runtime_monitor=runtime_monitor, irr_state_max_age_sec=irr_state_max_age_sec
    )


__all__ = [
    "CorrectionInterruptFailSafeStopResult",
    "CorrectionInterruptPendingCheck",
    "CorrectionInterruptSafetyVerdict",
    "DEFAULT_IRR_STATE_MAX_AGE_SEC",
    "DEFAULT_NODE_ONLINE_MAX_AGE_SEC",
    "DEFAULT_PENDING_VERIFY_LOOKBACK_HOURS",
    "DEFAULT_VERIFY_GRACE_SEC",
    "DOSE_ACTUATORS_UNVERIFIABLE_REASON",
    "ESCALATED_HARDWARE_RISK_EVENT",
    "FAIL_SAFE_SHUTDOWN_CHANNELS",
    "HARDWARE_SAFE_EVENT",
    "PENDING_VERIFY_EVENT",
    "assess_dose_path_risk",
    "attempt_correction_interrupt_fail_safe_stop",
    "attempt_task_fail_safe_shutdown",
    "build_fail_safe_shutdown_commands",
    "build_pending_check_from_task",
    "emit_correction_interrupt_hardware_safe",
    "emit_correction_interrupt_pending_verify",
    "escalate_correction_interrupt_hardware_risk",
    "evaluate_correction_interrupt_safety",
    "flow_snapshot_is_safe",
    "is_dose_correction_step",
    "load_irrig_fail_safe_actuators",
    "load_open_pending_correction_interrupt_checks",
    "pending_check_from_event_payload",
    "pending_check_to_event_payload",
    "read_workflow_phase",
    "required_nodes_online",
    "zone_has_active_ae_task",
]

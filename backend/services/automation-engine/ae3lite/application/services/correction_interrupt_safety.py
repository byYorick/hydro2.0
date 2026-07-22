"""Безопасная верификация железа после startup_recovery_correction_interrupted.

После power-loss / рестарта AE нельзя сразу эскалировать critical
``biz_flow_stop_failed_hardware_may_be_active``: узлы ещё offline, актуаторы
обычно уже OFF после brownout. Сначала pending-verify → при подтверждённом
OFF — safe; critical только если после grace оборудование ON или не подтверждено.
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
from ae3lite.domain.services.zone_node_availability import TWO_TANK_REQUIRED_NODE_TYPES
from ae3lite.infrastructure.metrics import inc_observability_write_failed
from common.biz_alerts import send_biz_alert
from common.db import create_zone_event, fetch

_logger = logging.getLogger(__name__)

PENDING_VERIFY_EVENT = "AE_CORRECTION_INTERRUPT_PENDING_VERIFY"
HARDWARE_SAFE_EVENT = "AE_CORRECTION_INTERRUPT_HARDWARE_SAFE"

DEFAULT_VERIFY_GRACE_SEC = 120
DEFAULT_IRR_STATE_MAX_AGE_SEC = 90


@dataclass(frozen=True)
class CorrectionInterruptPendingCheck:
    """Отложенная проверка железа после fail коррекции на startup recovery."""

    zone_id: int
    task_id: int
    task_type: str
    topology: str
    stage: str
    corr_step: str
    workflow_phase: str
    recovery_source: str
    deadline_at: datetime
    irrigation_mode: str | None = None
    irrigation_requested_duration_sec: int | None = None
    intent_id: int | None = None


@dataclass(frozen=True)
class CorrectionInterruptSafetyVerdict:
    """Итог одной попытки verify: pending | safe | unsafe."""

    status: str  # pending | safe | unsafe
    reason: str
    snapshot: Mapping[str, Any] | None = None
    nodes_online: bool = False


def is_dose_correction_step(corr_step: object) -> bool:
    return str(corr_step or "").strip().lower() in CORRECTION_DOSE_STEPS


def build_pending_check_from_task(
    *,
    task: Any,
    now: datetime,
    recovery_source: str = "startup_recovery",
    verify_grace_sec: int = DEFAULT_VERIFY_GRACE_SEC,
) -> CorrectionInterruptPendingCheck | None:
    correction = getattr(task, "correction", None)
    if correction is None:
        return None
    corr_step = str(getattr(correction, "corr_step", "") or "").strip().lower()
    if not is_dose_correction_step(corr_step):
        return None
    grace = max(15, int(verify_grace_sec))
    intent_id_raw = getattr(task, "intent_id", None)
    intent_id = int(intent_id_raw) if intent_id_raw not in (None, "") else None
    duration_raw = getattr(task, "irrigation_requested_duration_sec", None)
    duration = int(duration_raw) if duration_raw not in (None, "") else None
    return CorrectionInterruptPendingCheck(
        zone_id=int(task.zone_id),
        task_id=int(task.id),
        task_type=str(getattr(task, "task_type", "") or "").strip().lower(),
        topology=str(getattr(task, "topology", "") or "").strip().lower(),
        stage=str(getattr(task, "current_stage", "") or "").strip().lower(),
        corr_step=corr_step,
        workflow_phase=str(getattr(task, "workflow_phase", "") or "").strip().lower(),
        recovery_source=str(recovery_source or "startup_recovery"),
        deadline_at=now + timedelta(seconds=grace),
        irrigation_mode=str(getattr(task, "irrigation_mode", "") or "").strip().lower() or None,
        irrigation_requested_duration_sec=duration,
        intent_id=intent_id,
    )


def flow_snapshot_is_safe(*, stage: str, snapshot: Mapping[str, Any] | None) -> bool:
    """True, если irr_state соответствует OFF-ожиданиям stop-плана stage."""
    config = flow_path_stage_config(stage)
    if config is None:
        return True
    if not isinstance(snapshot, Mapping):
        return False
    for channel, expected_off in config.off_expected.items():
        raw = snapshot.get(channel)
        if raw is None:
            # отсутствует ключ — не подтверждаем safe
            return False
        actual = bool(raw)
        if actual != bool(expected_off):
            return False
    return True


async def emit_correction_interrupt_pending_verify(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
) -> None:
    payload = with_runtime_event_contract(
        {
            "task_id": check.task_id,
            "stage": check.stage,
            "corr_step": check.corr_step,
            "task_type": check.task_type,
            "topology": check.topology,
            "workflow_phase": check.workflow_phase,
            "recovery_source": check.recovery_source,
            "deadline_at": check.deadline_at.astimezone(timezone.utc).isoformat(),
            "reason": "startup_recovery_correction_interrupted",
            "message": (
                "Коррекция прервана при recovery; ожидается подтверждение безопасного "
                "состояния оборудования после восстановления узлов"
            ),
        }
    )
    try:
        await create_zone_event(check.zone_id, PENDING_VERIFY_EVENT, payload)
    except Exception:
        inc_observability_write_failed(kind="zone_event")
        _logger.warning(
            "AE3 correction interrupt: не удалось записать PENDING_VERIFY zone_id=%s task_id=%s",
            check.zone_id,
            check.task_id,
            exc_info=True,
        )
    try:
        await send_biz_alert(
            zone_id=check.zone_id,
            code="biz_ae3_correction_interrupt_pending_verify",
            severity="warning",
            message=(
                "Коррекция прервана при recovery — проверяем оборудование "
                "после восстановления узлов"
            ),
            details={
                "task_id": check.task_id,
                "stage": check.stage,
                "corr_step": check.corr_step,
                "recovery_source": check.recovery_source,
                "deadline_at": check.deadline_at.astimezone(timezone.utc).isoformat(),
                "alert_policy_mode": "auto_resolve",
                "auto_resolve_eligible": True,
            },
            scope_parts=(f"task_id:{check.task_id}", f"stage:{check.stage}"),
        )
    except Exception:
        inc_observability_write_failed(kind="biz_alert")
        _logger.warning(
            "AE3 correction interrupt: не удалось создать pending-verify alert zone_id=%s",
            check.zone_id,
            exc_info=True,
        )


async def emit_correction_interrupt_hardware_safe(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
    reason: str,
    snapshot: Mapping[str, Any] | None = None,
) -> None:
    payload = with_runtime_event_contract(
        {
            "task_id": check.task_id,
            "stage": check.stage,
            "corr_step": check.corr_step,
            "task_type": check.task_type,
            "recovery_source": check.recovery_source,
            "reason": reason,
            "snapshot": dict(snapshot) if isinstance(snapshot, Mapping) else None,
            "message": "Оборудование подтверждено в безопасном состоянии после прерывания коррекции",
        }
    )
    try:
        await create_zone_event(check.zone_id, HARDWARE_SAFE_EVENT, payload)
    except Exception:
        inc_observability_write_failed(kind="zone_event")
        _logger.warning(
            "AE3 correction interrupt: не удалось записать HARDWARE_SAFE zone_id=%s task_id=%s",
            check.zone_id,
            check.task_id,
            exc_info=True,
        )
    # Закрываем pending-verify warning (тот же dedupe scope, что и raise).
    try:
        from common.biz_alerts import _build_dedupe_key
        from common.alert_publisher import AlertPublisher

        details = {
            "task_id": check.task_id,
            "stage": check.stage,
            "corr_step": check.corr_step,
            "recovery_source": check.recovery_source,
            "message": "Оборудование подтверждено безопасным после recovery",
            "resolved_reason": reason,
        }
        dedupe_key = _build_dedupe_key(
            code="biz_ae3_correction_interrupt_pending_verify",
            zone_id=check.zone_id,
            details=details,
            scope_parts=(f"task_id:{check.task_id}", f"stage:{check.stage}"),
        )
        publisher = AlertPublisher(default_source="biz")
        await publisher.resolve(
            zone_id=check.zone_id,
            source="biz",
            code="biz_ae3_correction_interrupt_pending_verify",
            alert_type="Business Alert",
            details=details,
            dedupe_key=dedupe_key,
            scoped=True,
            severity="warning",
        )
    except Exception:
        _logger.warning(
            "AE3 correction interrupt: не удалось resolve pending-verify alert zone_id=%s",
            check.zone_id,
            exc_info=True,
        )


async def escalate_correction_interrupt_hardware_risk(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
    reason: str,
) -> None:
    """Эскалация в critical — только после неуспешной верификации / grace timeout."""
    task = _FakeTaskForAlert(check)
    await emit_correction_interrupted_hardware_risk(
        task=task,
        now=now,
        recovery_source=f"{check.recovery_source}:{reason}",
    )


class _FakeTaskForAlert:
    """Минимальный task-like для emit_correction_interrupted_hardware_risk."""

    def __init__(self, check: CorrectionInterruptPendingCheck) -> None:
        self.id = check.task_id
        self.zone_id = check.zone_id
        self.current_stage = check.stage
        self.correction = type("C", (), {"corr_step": check.corr_step})()
        self.workflow = type("W", (), {"control_mode": "auto"})()


async def zone_has_active_ae_task(*, zone_id: int) -> bool:
    rows = await fetch(
        """
        SELECT 1
        FROM ae_tasks
        WHERE zone_id = $1
          AND status = ANY(ARRAY['pending','claimed','running','waiting_command']::text[])
        LIMIT 1
        """,
        zone_id,
    )
    return bool(rows)


async def required_nodes_online(
    *,
    zone_id: int,
    required_types: Sequence[str] = tuple(sorted(TWO_TANK_REQUIRED_NODE_TYPES)),
) -> tuple[bool, tuple[str, ...]]:
    rows = await fetch(
        """
        SELECT LOWER(COALESCE(type, '')) AS node_type,
               LOWER(TRIM(COALESCE(status, ''))) AS status
        FROM nodes
        WHERE zone_id = $1
        """,
        zone_id,
    )
    by_type: dict[str, str] = {}
    for row in rows:
        node_type = str(row.get("node_type") or "").strip().lower()
        if node_type and node_type not in by_type:
            by_type[node_type] = str(row.get("status") or "").strip().lower()
    missing = tuple(
        node_type
        for node_type in required_types
        if by_type.get(node_type) != "online"
    )
    return (not missing, missing)


async def read_workflow_phase(*, zone_id: int) -> str | None:
    rows = await fetch(
        """
        SELECT workflow_phase
        FROM zone_workflow_state
        WHERE zone_id = $1
        LIMIT 1
        """,
        zone_id,
    )
    if not rows:
        return None
    return str(rows[0].get("workflow_phase") or "").strip().lower() or None


async def evaluate_correction_interrupt_safety(
    *,
    check: CorrectionInterruptPendingCheck,
    now: datetime,
    runtime_monitor: Any,
    irr_state_max_age_sec: int = DEFAULT_IRR_STATE_MAX_AGE_SEC,
) -> CorrectionInterruptSafetyVerdict:
    """Оценивает, можно ли считать железо безопасным после interrupt."""
    if await zone_has_active_ae_task(zone_id=check.zone_id):
        return CorrectionInterruptSafetyVerdict(
            status="pending",
            reason="zone_has_active_task",
            nodes_online=True,
        )

    nodes_ok, missing = await required_nodes_online(zone_id=check.zone_id)
    if not nodes_ok:
        if now >= check.deadline_at:
            return CorrectionInterruptSafetyVerdict(
                status="unsafe",
                reason=f"required_nodes_offline:{','.join(missing)}",
                nodes_online=False,
            )
        return CorrectionInterruptSafetyVerdict(
            status="pending",
            reason=f"waiting_nodes:{','.join(missing)}",
            nodes_online=False,
        )

    state = await runtime_monitor.read_latest_irr_state(
        zone_id=check.zone_id,
        max_age_sec=max(5, int(irr_state_max_age_sec)),
    )
    snapshot = state.get("snapshot") if isinstance(state, Mapping) else None
    has_snapshot = bool(isinstance(state, Mapping) and state.get("has_snapshot"))
    is_stale = bool(isinstance(state, Mapping) and state.get("is_stale"))
    workflow_phase = await read_workflow_phase(zone_id=check.zone_id)

    # После power-loss / completed cycle snapshot часто устаревший (ещё с mid-recirc ON).
    # В ready/idle без active task актуаторы не принадлежат workflow → safe, если нет
    # свежего ON-снимка.
    if workflow_phase in {"ready", "idle"} and (not has_snapshot or is_stale):
        return CorrectionInterruptSafetyVerdict(
            status="safe",
            reason=f"workflow_{workflow_phase}_idle_no_fresh_on_snapshot",
            snapshot=snapshot if isinstance(snapshot, Mapping) else None,
            nodes_online=True,
        )

    if not has_snapshot or is_stale or not isinstance(snapshot, Mapping):
        if now >= check.deadline_at:
            return CorrectionInterruptSafetyVerdict(
                status="unsafe",
                reason="irr_state_unavailable_after_grace",
                snapshot=snapshot if isinstance(snapshot, Mapping) else None,
                nodes_online=True,
            )
        return CorrectionInterruptSafetyVerdict(
            status="pending",
            reason="waiting_fresh_irr_state",
            nodes_online=True,
        )

    if flow_snapshot_is_safe(stage=check.stage, snapshot=snapshot):
        return CorrectionInterruptSafetyVerdict(
            status="safe",
            reason="irr_state_off_confirmed",
            snapshot=dict(snapshot),
            nodes_online=True,
        )

    # Свежий ON в ready — реально опасный stuck actuator.
    if workflow_phase in {"ready", "idle"}:
        if now >= check.deadline_at:
            return CorrectionInterruptSafetyVerdict(
                status="unsafe",
                reason="irr_state_actuators_active_in_ready",
                snapshot=dict(snapshot),
                nodes_online=True,
            )
        return CorrectionInterruptSafetyVerdict(
            status="pending",
            reason="waiting_actuators_off_in_ready",
            snapshot=dict(snapshot),
            nodes_online=True,
        )

    if now >= check.deadline_at:
        return CorrectionInterruptSafetyVerdict(
            status="unsafe",
            reason="irr_state_actuators_active_after_grace",
            snapshot=dict(snapshot),
            nodes_online=True,
        )
    return CorrectionInterruptSafetyVerdict(
        status="pending",
        reason="waiting_actuators_off",
        snapshot=dict(snapshot),
        nodes_online=True,
    )


__all__ = [
    "CorrectionInterruptPendingCheck",
    "CorrectionInterruptSafetyVerdict",
    "DEFAULT_IRR_STATE_MAX_AGE_SEC",
    "DEFAULT_VERIFY_GRACE_SEC",
    "HARDWARE_SAFE_EVENT",
    "PENDING_VERIFY_EVENT",
    "build_pending_check_from_task",
    "emit_correction_interrupt_hardware_safe",
    "emit_correction_interrupt_pending_verify",
    "escalate_correction_interrupt_hardware_risk",
    "evaluate_correction_interrupt_safety",
    "flow_snapshot_is_safe",
    "is_dose_correction_step",
    "read_workflow_phase",
    "required_nodes_online",
    "zone_has_active_ae_task",
]

"""interrupt safety alerts: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.application.services.interrupt_safety_records import CorrectionInterruptPendingCheck, _FakeTaskForAlert


@dataclass(frozen=True)
class InterruptSafetyAlertsPorts:
    flow_stop_failed: Callable[..., Any]
    hardware_safe_event: Callable[..., Any]
    pending_verify_event: Callable[..., Any]
    logger: Callable[..., Any]
    create_zone_event: Callable[..., Any]
    emit_correction_interrupted_hardware_risk: Callable[..., Any]
    inc_observability_write_failed: Callable[..., Any]
    pending_check_to_event_payload: Callable[..., Any]
    send_biz_alert: Callable[..., Any]


class InterruptSafetyAlerts:
    def __init__(self, ports: InterruptSafetyAlertsPorts) -> None:
        self._ports = ports

    async def emit_task_fail_safe_failure_alert(self, *, task: Any, reason: str, source: str) -> None:
        """Surface an unconfirmed operator/control-mode stop to the operator."""
        normalized_reason = str(reason or "unknown")
        if normalized_reason.startswith("unsupported_topology:") or normalized_reason == "no_irrig_actuators":
            return
        stage = str(getattr(task, "current_stage", "") or "unknown")
        self._ports.flow_stop_failed().labels(stage=stage).inc()
        try:
            await self._ports.send_biz_alert(
                zone_id=int(task.zone_id),
                code="biz_flow_stop_failed_hardware_may_be_active",
                severity="critical",
                message="Не удалось подтвердить остановку flow-path; оборудование может оставаться активным",
                details={
                    "task_id": int(getattr(task, "id", 0) or 0),
                    "stage": stage,
                    "reason": normalized_reason,
                    "source": source,
                },
                scope_parts=(f"stage:{stage}",),
            )
        except Exception:
            self._ports.inc_observability_write_failed(kind="biz_alert")
            self._ports.logger().warning(
                "AE3 fail-safe alert failed zone_id=%s task_id=%s", task.zone_id, task.id, exc_info=True
            )

    async def emit_correction_interrupt_pending_verify(
        self, *, check: CorrectionInterruptPendingCheck, now: datetime
    ) -> None:
        payload = with_runtime_event_contract(
            {
                **self._ports.pending_check_to_event_payload(check),
                "message": (
                    "Коррекция прервана при recovery; ожидается подтверждение безопасного "
                    "состояния оборудования после восстановления узлов"
                ),
            }
        )
        try:
            await self._ports.create_zone_event(check.zone_id, self._ports.pending_verify_event(), payload)
        except Exception:
            self._ports.inc_observability_write_failed(kind="zone_event")
            self._ports.logger().warning(
                "AE3 correction interrupt: не удалось записать PENDING_VERIFY zone_id=%s task_id=%s",
                check.zone_id,
                check.task_id,
                exc_info=True,
            )
        try:
            await self._ports.send_biz_alert(
                zone_id=check.zone_id,
                code="biz_ae3_correction_interrupt_pending_verify",
                severity="warning",
                message=("Коррекция прервана при recovery — проверяем оборудование после восстановления узлов"),
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
            self._ports.inc_observability_write_failed(kind="biz_alert")
            self._ports.logger().warning(
                "AE3 correction interrupt: не удалось создать pending-verify alert zone_id=%s",
                check.zone_id,
                exc_info=True,
            )

    async def emit_correction_interrupt_hardware_safe(
        self, *, check: CorrectionInterruptPendingCheck, now: datetime, reason: str, snapshot: Mapping[str, Any] | None
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
            await self._ports.create_zone_event(check.zone_id, self._ports.hardware_safe_event(), payload)
        except Exception:
            self._ports.inc_observability_write_failed(kind="zone_event")
            self._ports.logger().warning(
                "AE3 correction interrupt: не удалось записать HARDWARE_SAFE zone_id=%s task_id=%s",
                check.zone_id,
                check.task_id,
                exc_info=True,
            )
        # Закрываем pending-verify warning (тот же dedupe scope, что и raise).
        try:
            from common.alert_publisher import AlertPublisher
            from common.biz_alerts import _build_dedupe_key

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
            self._ports.logger().warning(
                "AE3 correction interrupt: не удалось resolve pending-verify alert zone_id=%s",
                check.zone_id,
                exc_info=True,
            )

    async def escalate_correction_interrupt_hardware_risk(
        self, *, check: CorrectionInterruptPendingCheck, now: datetime, reason: str
    ) -> None:
        """Эскалация в critical — только после неуспешной верификации / grace timeout."""
        task = _FakeTaskForAlert(check)
        await self._ports.emit_correction_interrupted_hardware_risk(
            task=task,
            now=now,
            recovery_source=f"{check.recovery_source}:{reason}",
        )

"""interrupt safety pending checks: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from ae3lite.application.services.interrupt_safety_records import CorrectionInterruptPendingCheck


@dataclass(frozen=True)
class InterruptSafetyPendingChecksPorts:
    escalated_hardware_risk_event: Callable[..., Any]
    hardware_safe_event: Callable[..., Any]
    pending_verify_event: Callable[..., Any]
    parse_deadline_at: Callable[..., Any]
    fetch: Callable[..., Any]
    is_dose_correction_step: Callable[..., Any]
    pending_check_from_event_payload: Callable[..., Any]


class InterruptSafetyPendingChecks:
    def __init__(self, ports: InterruptSafetyPendingChecksPorts) -> None:
        self._ports = ports

    def pending_check_to_event_payload(self, check: CorrectionInterruptPendingCheck) -> dict[str, Any]:
        """Сериализация pending-check в payload zone_event (для persist/restore)."""
        payload: dict[str, Any] = {
            "task_id": int(check.task_id),
            "stage": check.stage,
            "corr_step": check.corr_step,
            "task_type": check.task_type,
            "topology": check.topology,
            "workflow_phase": check.workflow_phase,
            "recovery_source": check.recovery_source,
            "deadline_at": check.deadline_at.astimezone(timezone.utc).isoformat(),
            "reason": "startup_recovery_correction_interrupted",
        }
        if check.irrigation_mode:
            payload["irrigation_mode"] = check.irrigation_mode
        if check.irrigation_requested_duration_sec is not None:
            payload["irrigation_requested_duration_sec"] = int(check.irrigation_requested_duration_sec)
        if check.intent_id is not None:
            payload["intent_id"] = int(check.intent_id)
        return payload

    def pending_check_from_event_payload(
        self, *, zone_id: int, payload: Mapping[str, Any], fallback_now: datetime | None
    ) -> CorrectionInterruptPendingCheck | None:
        """Восстанавливает pending-check из payload PENDING_VERIFY zone_event."""
        try:
            task_id = int(payload.get("task_id") or 0)
        except (TypeError, ValueError):
            return None
        if zone_id <= 0 or task_id <= 0:
            return None
        corr_step = str(payload.get("corr_step") or "").strip().lower()
        if not self._ports.is_dose_correction_step(corr_step):
            return None
        base_now = fallback_now or datetime.now(timezone.utc)
        intent_raw = payload.get("intent_id")
        try:
            intent_id = int(intent_raw) if intent_raw not in (None, "") else None
        except (TypeError, ValueError):
            intent_id = None
        duration_raw = payload.get("irrigation_requested_duration_sec")
        try:
            duration = int(duration_raw) if duration_raw not in (None, "") else None
        except (TypeError, ValueError):
            duration = None
        return CorrectionInterruptPendingCheck(
            zone_id=int(zone_id),
            task_id=task_id,
            task_type=str(payload.get("task_type") or "").strip().lower(),
            topology=str(payload.get("topology") or "").strip().lower(),
            stage=str(payload.get("stage") or "").strip().lower(),
            corr_step=corr_step,
            workflow_phase=str(payload.get("workflow_phase") or "").strip().lower(),
            recovery_source=str(payload.get("recovery_source") or "startup_recovery").strip() or "startup_recovery",
            deadline_at=self._ports.parse_deadline_at(payload.get("deadline_at"), fallback_now=base_now),
            irrigation_mode=str(payload.get("irrigation_mode") or "").strip().lower() or None,
            irrigation_requested_duration_sec=duration,
            intent_id=intent_id,
        )

    async def load_open_pending_correction_interrupt_checks(
        self, *, now: datetime, lookback_hours: int
    ) -> tuple[CorrectionInterruptPendingCheck, ...]:
        """Восстанавливает незакрытые PENDING_VERIFY после рестарта AE.

        «Закрыт» = для того же task_id уже есть HARDWARE_SAFE или FLOW_STOP_FAILED
        после PENDING_VERIFY. Дедуп по task_id: последний payload побеждает.
        """
        lookback = max(1, int(lookback_hours))
        rows = await self._ports.fetch(
            """
            WITH pending AS (
                SELECT
                    zone_id,
                    id AS event_id,
                    created_at,
                    COALESCE(payload_json, details, '{}'::jsonb) AS payload
                FROM zone_events
                WHERE type = $1
                  AND created_at >= (NOW() - ($3::text || ' hours')::interval)
            ),
            closed AS (
                SELECT
                    zone_id,
                    NULLIF(COALESCE(payload_json->>'task_id', details->>'task_id'), '')::bigint AS task_id,
                    MAX(created_at) AS closed_at
                FROM zone_events
                WHERE type = ANY($2::text[])
                  AND created_at >= (NOW() - ($3::text || ' hours')::interval)
                GROUP BY 1, 2
            )
            SELECT p.zone_id, p.payload, p.created_at
            FROM pending p
            LEFT JOIN closed c
              ON c.zone_id = p.zone_id
             AND c.task_id = NULLIF(p.payload->>'task_id', '')::bigint
             AND c.closed_at >= p.created_at
            WHERE c.task_id IS NULL
            ORDER BY p.created_at ASC, p.event_id ASC
            """,
            self._ports.pending_verify_event(),
            [self._ports.hardware_safe_event(), self._ports.escalated_hardware_risk_event()],
            str(lookback),
        )
        by_task: dict[int, CorrectionInterruptPendingCheck] = {}
        for row in rows or ():
            try:
                zone_id = int(row.get("zone_id") or 0)
            except (TypeError, ValueError):
                continue
            payload = row.get("payload")
            if isinstance(payload, str):
                import json

                try:
                    payload = json.loads(payload)
                except (TypeError, ValueError):
                    continue
            if not isinstance(payload, Mapping):
                continue
            check = self._ports.pending_check_from_event_payload(
                zone_id=zone_id,
                payload=payload,
                fallback_now=now,
            )
            if check is None:
                continue
            by_task[int(check.task_id)] = check
        return tuple(by_task.values())

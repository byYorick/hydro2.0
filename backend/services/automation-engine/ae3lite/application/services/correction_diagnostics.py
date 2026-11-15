"""Correction diagnostics: explicit collaborators, per-call task context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Mapping

from ae3lite.application.runtime_event_contract import with_runtime_event_contract
from ae3lite.application.services.correction_shared import _logger
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.services.correction_planner import (
    DosePlan,
)
from ae3lite.domain.services.pid_output_event import build_pid_output_detail
from ae3lite.infrastructure.metrics import (
    CORRECTION_DOSE_CLAMPED,
    CORRECTION_PUMP_CALIBRATION_MIRROR_MISMATCH,
)


@dataclass(frozen=True)
class CorrectionDiagnosticsPorts:
    log_correction_event: Callable[..., Awaitable[Any]]
    create_zone_event: Callable[..., Awaitable[Any]]
    datetime_type: Callable[[], Any]


class CorrectionDiagnostics:
    def __init__(self, ports: CorrectionDiagnosticsPorts) -> None:
        self._ports = ports

    @staticmethod
    def record_dose_clamp_metrics(dose_plan: DosePlan) -> None:
        if dose_plan.needs_ec:
            if dose_plan.ec_dose_sequence:
                for step in dose_plan.ec_dose_sequence:
                    requested = float(step.requested_ml) if step.requested_ml is not None else float(step.amount_ml)
                    if requested > float(step.amount_ml) + 1e-9:
                        CORRECTION_DOSE_CLAMPED.labels(pid_type="ec").inc()
            elif dose_plan.ec_requested_ml > dose_plan.ec_amount_ml + 1e-9:
                CORRECTION_DOSE_CLAMPED.labels(pid_type="ec").inc()
        if (
            dose_plan.needs_ph_up or dose_plan.needs_ph_down
        ) and dose_plan.ph_requested_ml > dose_plan.ph_amount_ml + 1e-9:
            CORRECTION_DOSE_CLAMPED.labels(pid_type="ph").inc()

    async def record_dual_calibration_mismatch_observability(
        self,
        *,
        task: Any,
        corr: CorrectionState,
        dose_plan: DosePlan,
    ) -> None:
        if not dose_plan.dual_calibration_mismatches:
            return

        payload_mismatches = []
        for item in dose_plan.dual_calibration_mismatches:
            field = str(item.get("field") or "unknown")
            CORRECTION_PUMP_CALIBRATION_MIRROR_MISMATCH.labels(field=field).inc()
            payload_mismatches.append(dict(item))

        await self._ports.log_correction_event(
            zone_id=task.zone_id,
            event_type="PUMP_CALIBRATION_MIRROR_MISMATCH",
            task=task,
            corr=corr,
            payload={"mismatches": payload_mismatches},
        )

    def serialize_metric_ts(self, value: Any) -> str | None:
        if isinstance(value, self._ports.datetime_type()):
            normalized = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
            return normalized.isoformat()
        return None

    async def maybe_emit_pid_output_zone_event(
        self,
        *,
        zone_id: int,
        corr_step: str,
        dose_plan: DosePlan,
        pid_state_before: Mapping[str, Any],
        current_ph: float,
        current_ec: float,
        target_ph: float,
        target_ec: float,
        now: datetime,
    ) -> None:
        """Пишет PID_OUTPUT в zone_events для вкладки «Логи PID» в UI."""
        try:
            detail = build_pid_output_detail(
                corr_step=corr_step,
                dose_plan=dose_plan,
                pid_state_before=pid_state_before,
                current_ph=current_ph,
                current_ec=current_ec,
                target_ph=target_ph,
                target_ec=target_ec,
                now=now,
            )
            if detail is None:
                return
            payload = with_runtime_event_contract({k: v for k, v in detail.items() if v is not None})
            await self._ports.create_zone_event(zone_id, "PID_OUTPUT", payload)
        except Exception:
            _logger.debug("Не удалось записать PID_OUTPUT zone event", exc_info=True)

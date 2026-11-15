"""interrupt safety verification: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from ae3lite.application.services.interrupt_safety_records import (
    CorrectionInterruptPendingCheck,
    CorrectionInterruptSafetyVerdict,
)


@dataclass(frozen=True)
class InterruptSafetyVerificationPorts:
    pending_or_unsafe_after_grace: Callable[..., Any]
    assess_dose_path_risk: Callable[..., Any]
    flow_snapshot_is_safe: Callable[..., Any]
    read_workflow_phase: Callable[..., Any]
    required_nodes_online: Callable[..., Any]
    zone_has_active_ae_task: Callable[..., Any]


class InterruptSafetyVerification:
    def __init__(self, ports: InterruptSafetyVerificationPorts) -> None:
        self._ports = ports

    async def evaluate_correction_interrupt_safety(
        self, *, check: CorrectionInterruptPendingCheck, now: datetime, runtime_monitor: Any, irr_state_max_age_sec: int
    ) -> CorrectionInterruptSafetyVerdict:
        """Оценивает, можно ли считать железо безопасным после interrupt.

        Safe только при: нет active task, required nodes online, свежий irrig OFF
        snapshot **и** отсутствие dose-risk (для dose/wait — сейчас всегда risk,
        т.к. EC/pH pump channels через irr_state не probe'ятся).
        """
        dose_risk = self._ports.assess_dose_path_risk(corr_step=check.corr_step)

        if await self._ports.zone_has_active_ae_task(zone_id=check.zone_id):
            return CorrectionInterruptSafetyVerdict(
                status="pending",
                reason="zone_has_active_task",
                nodes_online=True,
                dose_risk=dose_risk,
            )

        nodes_ok, missing = await self._ports.required_nodes_online(zone_id=check.zone_id)
        if not nodes_ok:
            return self._ports.pending_or_unsafe_after_grace(
                now=now,
                deadline_at=check.deadline_at,
                pending_reason=f"waiting_nodes:{','.join(missing)}",
                unsafe_reason=f"required_nodes_offline:{','.join(missing)}",
                nodes_online=False,
                dose_risk=dose_risk,
            )

        state = await runtime_monitor.read_latest_irr_state(
            zone_id=check.zone_id,
            max_age_sec=max(5, int(irr_state_max_age_sec)),
        )
        snapshot = state.get("snapshot") if isinstance(state, Mapping) else None
        has_snapshot = bool(isinstance(state, Mapping) and state.get("has_snapshot"))
        is_stale = bool(isinstance(state, Mapping) and state.get("is_stale"))
        workflow_phase = await self._ports.read_workflow_phase(zone_id=check.zone_id)
        snap_map = snapshot if isinstance(snapshot, Mapping) else None

        # ready/idle + missing/stale — НЕ auto-safe (fail-closed): без свежего
        # OFF snapshot нельзя скрыть потенциально активные актуаторы.
        if not has_snapshot or is_stale or snap_map is None:
            phase_suffix = f"_in_{workflow_phase}" if workflow_phase in {"ready", "idle"} else ""
            return self._ports.pending_or_unsafe_after_grace(
                now=now,
                deadline_at=check.deadline_at,
                pending_reason=f"waiting_fresh_irr_state{phase_suffix}",
                unsafe_reason=f"irr_state_unavailable_after_grace{phase_suffix}",
                snapshot=snap_map,
                nodes_online=True,
                dose_risk=dose_risk,
            )

        if not self._ports.flow_snapshot_is_safe(stage=check.stage, snapshot=snap_map):
            # Свежий ON — stuck actuators; в ready/idle особенно опасно.
            if workflow_phase in {"ready", "idle"}:
                return self._ports.pending_or_unsafe_after_grace(
                    now=now,
                    deadline_at=check.deadline_at,
                    pending_reason="waiting_actuators_off_in_ready",
                    unsafe_reason="irr_state_actuators_active_in_ready",
                    snapshot=dict(snap_map),
                    nodes_online=True,
                    dose_risk=dose_risk,
                )
            return self._ports.pending_or_unsafe_after_grace(
                now=now,
                deadline_at=check.deadline_at,
                pending_reason="waiting_actuators_off",
                unsafe_reason="irr_state_actuators_active_after_grace",
                snapshot=dict(snap_map),
                nodes_online=True,
                dose_risk=dose_risk,
            )

        # Irrig OFF подтверждён — необходимое условие. Для dose/wait без probe
        # dose actuators всё ещё не safe.
        if dose_risk is not None:
            return self._ports.pending_or_unsafe_after_grace(
                now=now,
                deadline_at=check.deadline_at,
                pending_reason=dose_risk,
                unsafe_reason=f"{dose_risk}_after_grace",
                snapshot=dict(snap_map),
                nodes_online=True,
                dose_risk=dose_risk,
            )

        return CorrectionInterruptSafetyVerdict(
            status="safe",
            reason="irr_state_off_confirmed",
            snapshot=dict(snap_map),
            nodes_online=True,
            dose_risk=None,
        )

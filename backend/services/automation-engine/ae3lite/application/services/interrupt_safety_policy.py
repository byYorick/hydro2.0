"""interrupt safety policy: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from ae3lite.application.handlers.flow_path_guard import (
    CORRECTION_DOSE_STEPS,
    flow_path_stage_config,
)
from ae3lite.application.services.interrupt_safety_records import (
    CorrectionInterruptPendingCheck,
    CorrectionInterruptSafetyVerdict,
)


@dataclass(frozen=True)
class InterruptSafetyPolicyPorts:
    default_verify_grace_sec: Callable[..., Any]
    dose_actuators_unverifiable_reason: Callable[..., Any]
    is_dose_correction_step: Callable[..., Any]


class InterruptSafetyPolicy:
    def __init__(self, ports: InterruptSafetyPolicyPorts) -> None:
        self._ports = ports

    def is_dose_correction_step(self, corr_step: object) -> bool:
        return str(corr_step or "").strip().lower() in CORRECTION_DOSE_STEPS

    def assess_dose_path_risk(self, *, corr_step: object) -> str | None:
        """Оценка риска dose-path для interrupt safety.

        Для ``corr_dose_*`` / ``corr_wait_*`` probe каналов дозирующих насосов EC/pH
        через irrig ``IRR_STATE_SNAPSHOT`` пока недоступен → fail-closed
        (возвращает reason, не None). Без подтверждения dose actuators нельзя
        считать железо safe и нельзя разрешать HARDWARE_SAFE / replay.

        Returns:
            None — dose-path не применим (не dose/wait step) или подтверждён.
            str  — reason, почему dose-path нельзя считать безопасным.
        """
        if not self._ports.is_dose_correction_step(corr_step):
            return None
        # Planned: отдельный probe EC/pH pump channels (telemetry/command status).
        # До появления probe — всегда fail-closed.
        return self._ports.dose_actuators_unverifiable_reason()

    def parse_deadline_at(self, raw: object, *, fallback_now: datetime) -> datetime:
        if isinstance(raw, datetime):
            return raw if raw.tzinfo is not None else raw.replace(tzinfo=timezone.utc)
        text = str(raw or "").strip()
        if text:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return fallback_now + timedelta(seconds=self._ports.default_verify_grace_sec())

    def build_pending_check_from_task(
        self, *, task: Any, now: datetime, recovery_source: str, verify_grace_sec: int
    ) -> CorrectionInterruptPendingCheck | None:
        correction = getattr(task, "correction", None)
        if correction is None:
            return None
        corr_step = str(getattr(correction, "corr_step", "") or "").strip().lower()
        if not self._ports.is_dose_correction_step(corr_step):
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

    def flow_snapshot_is_safe(self, *, stage: str, snapshot: Mapping[str, Any] | None) -> bool:
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

    def node_is_fresh_online(self, *, status: str, last_seen_age_sec: int | None, max_age_sec: int) -> bool:
        if str(status or "").strip().lower() != "online":
            return False
        if last_seen_age_sec is None:
            # Нет timestamp активности — fail-closed (не считаем online).
            return False
        return int(last_seen_age_sec) < int(max_age_sec)

    def pending_or_unsafe_after_grace(
        self,
        *,
        now: datetime,
        deadline_at: datetime,
        pending_reason: str,
        unsafe_reason: str,
        snapshot: Mapping[str, Any] | None,
        nodes_online: bool,
        dose_risk: str | None,
    ) -> CorrectionInterruptSafetyVerdict:
        if now >= deadline_at:
            return CorrectionInterruptSafetyVerdict(
                status="unsafe",
                reason=unsafe_reason,
                snapshot=snapshot,
                nodes_online=nodes_online,
                dose_risk=dose_risk,
            )
        return CorrectionInterruptSafetyVerdict(
            status="pending",
            reason=pending_reason,
            snapshot=snapshot,
            nodes_online=nodes_online,
            dose_risk=dose_risk,
        )

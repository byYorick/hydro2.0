"""Typed records shared by the component boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


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
    """Итог одной попытки verify: pending | safe | unsafe.

    ``dose_risk`` — явная оценка dose-path: None если шаг не dose/wait или
    риск снят; иначе reason, почему dose actuators нельзя считать подтверждённо
    безопасными (сейчас всегда unverifiable через irr_state).
    """

    status: str  # pending | safe | unsafe
    reason: str
    snapshot: Mapping[str, Any] | None = None
    nodes_online: bool = False
    dose_risk: str | None = None


@dataclass(frozen=True)
class CorrectionInterruptFailSafeStopResult:
    """Итог попытки fail-safe stop перед escalate.

    ``success`` — транспорт принял publish-only batch. Это не подтверждённый OFF.
    ``confirmed`` остаётся False, пока нет probe: HTTP accept, пустой snapshot
    и пропущенный probe confirmed не ставят.
    """

    attempted: bool
    success: bool
    reason: str
    commands_total: int = 0
    confirmed: bool = False


class _FakeTaskForAlert:
    """Минимальный task-like для emit_correction_interrupted_hardware_risk."""

    def __init__(self, check: CorrectionInterruptPendingCheck) -> None:
        self.id = check.task_id
        self.zone_id = check.zone_id
        self.current_stage = check.stage
        self.correction = type("C", (), {"corr_step": check.corr_step})()
        self.workflow = type("W", (), {"control_mode": "auto"})()


class _FakeTaskForFailSafe:
    """Task-like для publish-only fail-safe batch (без corr_step в planner_step)."""

    def __init__(self, check: CorrectionInterruptPendingCheck) -> None:
        self.id = check.task_id
        self.zone_id = check.zone_id
        self.current_stage = check.stage or "correction_interrupt_fail_safe"
        self.topology = check.topology
        self.claimed_by = "ae3-correction-interrupt-fail-safe"
        self.correction = None
        self.workflow = type(
            "W",
            (),
            {
                "control_mode": "auto",
                "workflow_phase": check.workflow_phase,
                "stage_entered_at": None,
                "corr_step": None,
            },
        )()

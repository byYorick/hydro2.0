"""GetZoneAutomationStateUseCase presentation: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from ae3lite.application.services.zone_state_shared import (
    _CYCLE_START_STAGE_ORDER,
    _IRRIGATION_STAGE_PREFIX,
    _STAGE_LABELS,
    _STATE_LABELS,
    _TERMINAL_COMPLETED_STAGES,
    _WORKFLOW_PHASE_PROGRESS,
    logger,
)
from ae3lite.application.use_cases.manual_control_contract import (
    AVAILABLE_CONTROL_MODES,
    allowed_manual_steps_for_task,
    normalize_control_mode,
)


@dataclass(frozen=True)
class ZoneStatePresentationPorts:
    fetch_fn: Callable[..., Any]
    iso_or_none: Callable[..., Any]
    normalize_utc_naive: Callable[..., Any]
    now: Callable[..., Any]


class ZoneStatePresentation:
    def __init__(self, ports: ZoneStatePresentationPorts) -> None:
        self._ports = ports

    def primary_automation_state_label(
        self,
        *,
        workflow_phase: str,
        mapped_macro_state: str,
        current_stage: str,
        is_terminal_failed: bool,
    ) -> str:
        """Человекочитаемый заголовок для UI: не показывать «Раствор готов», если идёт подэтап полива."""
        cs_key = str(current_stage or "").strip().lower()

        if is_terminal_failed:
            stage_line = _STAGE_LABELS.get(cs_key)
            return f"{stage_line} — сбой" if stage_line else "Сбой автоматики"

        if workflow_phase == "idle" and cs_key == "startup":
            return "Инициализация"

        if mapped_macro_state == "READY" and cs_key and cs_key != "complete_ready":
            stage_line = _STAGE_LABELS.get(cs_key)
            if stage_line:
                return stage_line

        return _STATE_LABELS.get(mapped_macro_state, "Ожидание")

    def estimate_progress_percent(self, *, current_stage: str, workflow_phase: str) -> int:
        """Оценка прогресса для UI: подэтап в cycle_start, иначе macro workflow_phase."""
        cs_key = str(current_stage or "").strip().lower()
        if cs_key in _CYCLE_START_STAGE_ORDER:
            idx = _CYCLE_START_STAGE_ORDER.index(cs_key)
            return min(99, int(((idx + 1) / len(_CYCLE_START_STAGE_ORDER)) * 100))

        phase_key = str(workflow_phase or "").strip().lower()
        return int(_WORKFLOW_PHASE_PROGRESS.get(phase_key, 0))

    def timed_irrigation_metrics(
        self,
        *,
        stage_entered_at: datetime | None,
        stage_deadline_at: datetime | None,
        irrigation_requested_duration_sec: Any,
        current_stage: str,
        task_created_at: datetime | None = None,
        task_type: str = "",
    ) -> tuple[int | None, int | None]:
        """Прогресс полива по elapsed/deadline вместо индекса workflow (82% на irrigation_check)."""
        cs_key = str(current_stage or "").strip().lower()
        if not cs_key.startswith(_IRRIGATION_STAGE_PREFIX):
            return None, None

        anchor = stage_entered_at
        if (
            cs_key == "irrigation_check"
            and str(task_type or "").strip().lower() == "irrigation_start"
            and isinstance(task_created_at, datetime)
        ):
            anchor = task_created_at
        if not isinstance(anchor, datetime):
            return None, None

        entered_naive = self._ports.normalize_utc_naive(anchor)
        now = self._ports.normalize_utc_naive(self._ports.now())
        elapsed = max(0, int((now - entered_naive).total_seconds()))

        total_sec: int | None = None
        if isinstance(stage_deadline_at, datetime):
            deadline_naive = self._ports.normalize_utc_naive(stage_deadline_at)
            total_sec = max(1, int((deadline_naive - entered_naive).total_seconds()))
        else:
            try:
                requested = int(irrigation_requested_duration_sec)
            except (TypeError, ValueError):
                requested = 0
            if requested > 0:
                total_sec = max(1, requested)

        if total_sec is None:
            return None, None

        remaining = max(0, total_sec - elapsed)
        progress = min(99, max(0, int((elapsed / total_sec) * 100)))
        return progress, remaining

    def elapsed_sec_since(self, entered_at: datetime | None) -> int:
        if not isinstance(entered_at, datetime):
            return 0
        entered_naive = self._ports.normalize_utc_naive(entered_at)
        now = self._ports.now()
        if not isinstance(now, datetime):
            return 0
        return max(0, int((now - entered_naive).total_seconds()))

    def build_state_details(
        self,
        *,
        is_failed: bool,
        error_code: Any = None,
        error_message: Any = None,
        stage_entered_at: datetime | None = None,
        task_created_at: datetime | None = None,
        current_stage: str = "",
        workflow_phase: str = "idle",
        workflow_started_at: datetime | None = None,
        stage_deadline_at: datetime | None = None,
        irrigation_requested_duration_sec: Any = None,
        task_status: str = "",
        task_type: str = "",
        completed_at: datetime | None = None,
    ) -> dict[str, Any]:
        status_key = str(task_status or "").strip().lower()
        cs_key = str(current_stage or "").strip().lower()

        if not is_failed and status_key == "completed" and cs_key in _TERMINAL_COMPLETED_STAGES:
            started = task_created_at or stage_entered_at or workflow_started_at
            finished = completed_at if isinstance(completed_at, datetime) else None
            elapsed = 0
            if isinstance(started, datetime) and isinstance(finished, datetime):
                elapsed = max(
                    0,
                    int(
                        (
                            self._ports.normalize_utc_naive(finished) - self._ports.normalize_utc_naive(started)
                        ).total_seconds()
                    ),
                )
            elif isinstance(started, datetime):
                elapsed = self.elapsed_sec_since(started)
            return {
                "started_at": self._ports.iso_or_none(started),
                "stage_entered_at": self._ports.iso_or_none(stage_entered_at),
                "elapsed_sec": elapsed,
                "progress_percent": 0,
                "progress_basis": "terminal_completed",
                "failed": False,
                "error_code": None,
                "error_message": None,
            }

        anchor = stage_entered_at or task_created_at or workflow_started_at
        if (
            cs_key == "irrigation_check"
            and str(task_type or "").strip().lower() == "irrigation_start"
            and isinstance(task_created_at, datetime)
        ):
            anchor = task_created_at
        timed_progress, remaining_sec = self.timed_irrigation_metrics(
            stage_entered_at=stage_entered_at,
            stage_deadline_at=stage_deadline_at,
            irrigation_requested_duration_sec=irrigation_requested_duration_sec,
            current_stage=current_stage,
            task_created_at=task_created_at,
            task_type=task_type,
        )
        if is_failed:
            progress_percent = 0
        elif timed_progress is not None:
            progress_percent = timed_progress
        else:
            progress_percent = self.estimate_progress_percent(
                current_stage=current_stage,
                workflow_phase=workflow_phase,
            )

        details: dict[str, Any] = {
            "started_at": self._ports.iso_or_none(anchor),
            "stage_entered_at": self._ports.iso_or_none(stage_entered_at),
            "elapsed_sec": self.elapsed_sec_since(anchor),
            "progress_percent": progress_percent,
            "failed": is_failed,
            "error_code": error_code if is_failed else None,
            "error_message": error_message if is_failed else None,
        }
        if timed_progress is not None:
            details["progress_basis"] = "irrigation_deadline"
            details["stage_deadline_at"] = self._ports.iso_or_none(stage_deadline_at)
            details["stage_deadline_remaining_sec"] = remaining_sec
        return details

    async def control_mode_context(
        self,
        *,
        zone_id: int,
        current_stage: str | None,
        task_type: str | None = None,
        pending_manual_step: str | None = None,
    ) -> dict[str, Any]:
        """control_mode из zones — тот же source of truth, что и GET /control-mode."""
        control_mode = "auto"
        if self._ports.fetch_fn is not None:
            try:
                rows = await self._ports.fetch_fn(
                    "SELECT control_mode FROM zones WHERE id = $1",
                    zone_id,
                )
                if rows:
                    row = rows[0]
                    raw = row.get("control_mode") if isinstance(row, Mapping) else getattr(row, "control_mode", None)
                    control_mode = normalize_control_mode(raw)
            except Exception:
                logger.warning(
                    "AE3 automation state: control_mode read failed for zone_id=%s",
                    zone_id,
                    exc_info=True,
                )

        stage_key = str(current_stage or "").strip()
        allowed_manual_steps: list[str] = []
        if stage_key:
            # solution_change gate steps must be exposed even in control_mode=auto
            # (same contract as GetZoneControlStateUseCase / allowed_manual_steps_for_task).
            allowed_manual_steps = allowed_manual_steps_for_task(
                task_type=task_type or "",
                control_mode=control_mode,
                current_stage=stage_key,
                pending_manual_step=pending_manual_step,
            )

        return {
            "control_mode": control_mode,
            "control_mode_available": list(AVAILABLE_CONTROL_MODES),
            "allowed_manual_steps": allowed_manual_steps,
        }

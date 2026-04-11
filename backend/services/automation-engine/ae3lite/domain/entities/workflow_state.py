"""Объекты-значения workflow state и correction state для AE3-Lite v2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class WorkflowState:
    """Неизменяемый snapshot прогресса workflow по stage."""

    current_stage: str
    workflow_phase: str
    stage_deadline_at: Optional[datetime]
    stage_retry_count: int
    stage_entered_at: Optional[datetime]
    clean_fill_cycle: int
    # Поля control mode читаются из zones.control_mode + ae_tasks.pending_manual_step
    control_mode: str = "auto"
    pending_manual_step: Optional[str] = None


@dataclass(frozen=True)
class CorrectionState:
    """Неизменяемый snapshot состояния цикла коррекции.

    Все поля заполнены, когда коррекция активна;
    на уровне repository весь объект равен ``None``, когда она неактивна.
    """

    corr_step: str
    attempt: int
    max_attempts: int
    ec_attempt: int
    ec_max_attempts: int
    ph_attempt: int
    ph_max_attempts: int
    activated_here: bool
    stabilization_sec: int
    return_stage_success: str
    return_stage_fail: str
    outcome_success: Optional[bool]
    needs_ec: bool
    ec_node_uid: Optional[str]
    ec_channel: Optional[str]
    ec_duration_ms: Optional[int]
    needs_ph_up: bool
    needs_ph_down: bool
    ph_node_uid: Optional[str]
    ph_channel: Optional[str]
    ph_duration_ms: Optional[int]
    wait_until: Optional[datetime]
    ec_component: Optional[str] = None
    ec_amount_ml: Optional[float] = None
    ec_dose_sequence_json: Optional[str] = None
    ec_current_seq_index: int = 0
    ph_amount_ml: Optional[float] = None
    snapshot_event_id: Optional[int] = None
    snapshot_created_at: Optional[datetime] = None
    snapshot_cmd_id: Optional[str] = None
    snapshot_source_event_type: Optional[str] = None
    limit_policy_logged: bool = False

    @classmethod
    def build_default(
        cls,
        *,
        corr_step: str,
        max_attempts: int,
        ec_max_attempts: int,
        ph_max_attempts: int,
        activated_here: bool,
        stabilization_sec: int,
        return_stage_success: str,
        return_stage_fail: str,
    ) -> "CorrectionState":
        """Factory for a fresh correction window with all transient fields zeroed.

        Extracted from four handlers (solution_fill / prepare_recirc /
        irrigation_check / irrigation_recovery) per audit F3: every handler
        that opens a correction window previously duplicated the identical
        20-line initialization boilerplate. Any protocol change to ``CorrectionState``
        required editing four sites in lockstep.

        Only the nine varying fields remain as caller arguments; all dose/retry
        tracking state is reset to its pristine "no action yet" defaults.
        """
        return cls(
            corr_step=corr_step,
            attempt=0,
            max_attempts=max_attempts,
            ec_attempt=0,
            ec_max_attempts=ec_max_attempts,
            ph_attempt=0,
            ph_max_attempts=ph_max_attempts,
            activated_here=activated_here,
            stabilization_sec=stabilization_sec,
            return_stage_success=return_stage_success,
            return_stage_fail=return_stage_fail,
            outcome_success=None,
            needs_ec=False,
            ec_node_uid=None,
            ec_channel=None,
            ec_duration_ms=None,
            needs_ph_up=False,
            needs_ph_down=False,
            ph_node_uid=None,
            ph_channel=None,
            ph_duration_ms=None,
            wait_until=None,
            limit_policy_logged=False,
        )

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

"""Workflow and correction state value objects for AE3-Lite v2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class WorkflowState:
    """Immutable snapshot of workflow stage progression."""

    current_stage: str
    workflow_phase: str
    stage_deadline_at: Optional[datetime]
    stage_retry_count: int
    stage_entered_at: Optional[datetime]
    clean_fill_cycle: int


@dataclass(frozen=True)
class CorrectionState:
    """Immutable snapshot of correction cycle state.

    All fields are populated when correction is active;
    the entire object is ``None`` at the repository level when inactive.
    """

    corr_step: str
    attempt: int
    max_attempts: int
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

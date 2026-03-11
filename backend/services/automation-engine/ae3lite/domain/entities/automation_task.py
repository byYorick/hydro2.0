"""AutomationTask entity for AE3-Lite v2.

Replaces the monolithic ``payload JSONB`` column with explicit typed fields
for intent metadata, workflow state, and correction state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional


def _naive(dt: Any) -> Any:
    """Strip timezone from a datetime if present, return None as-is."""
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

from ae3lite.domain.entities.workflow_state import CorrectionState, WorkflowState


ACTIVE_TASK_STATUSES = frozenset({"pending", "claimed", "running", "waiting_command"})


@dataclass(frozen=True)
class AutomationTask:
    """Canonical task entity with explicit typed state columns."""

    # ── Identity ────────────────────────────────────────────────────
    id: int
    zone_id: int
    task_type: str
    status: str
    idempotency_key: str

    # ── Scheduling ──────────────────────────────────────────────────
    scheduled_for: datetime
    due_at: datetime

    # ── Claim ───────────────────────────────────────────────────────
    claimed_by: Optional[str]
    claimed_at: Optional[datetime]

    # ── Error ───────────────────────────────────────────────────────
    error_code: Optional[str]
    error_message: Optional[str]

    # ── Timestamps ──────────────────────────────────────────────────
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]

    # ── Intent metadata (write-once) ────────────────────────────────
    topology: str
    intent_source: Optional[str]
    intent_trigger: Optional[str]
    intent_id: Optional[int]
    intent_meta: Mapping[str, Any]

    # ── Workflow state (mutable per stage transition) ───────────────
    workflow: WorkflowState

    # ── Correction state (None when correction inactive) ────────────
    correction: Optional[CorrectionState]

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> AutomationTask:
        """Construct from an asyncpg Record or dict-like row."""
        # control_mode_snapshot takes priority (task-level snapshot);
        # pending_manual_step is always from ae_tasks (set via POST /manual-step).
        raw_control_mode = (
            row.get("control_mode_snapshot")
            if row.get("control_mode_snapshot") is not None
            else row.get("control_mode") or "auto"
        )
        workflow = WorkflowState(
            current_stage=str(row.get("current_stage") or "startup"),
            workflow_phase=str(row.get("workflow_phase") or "idle"),
            stage_deadline_at=_naive(row.get("stage_deadline_at")),
            stage_retry_count=int(row.get("stage_retry_count") or 0),
            stage_entered_at=_naive(row.get("stage_entered_at")),
            clean_fill_cycle=int(row.get("clean_fill_cycle") or 0),
            control_mode=str(raw_control_mode).strip() or "auto",
            pending_manual_step=str(row["pending_manual_step"]) if row.get("pending_manual_step") is not None else None,
        )

        correction: Optional[CorrectionState] = None
        if row.get("corr_step") is not None:
            correction = CorrectionState(
                corr_step=str(row["corr_step"]),
                attempt=int(row.get("corr_attempt") or 0),
                max_attempts=int(row.get("corr_max_attempts") or 0),
                ec_attempt=int(row.get("corr_ec_attempt") or 0),
                ec_max_attempts=int(row.get("corr_ec_max_attempts") or 0),
                ph_attempt=int(row.get("corr_ph_attempt") or 0),
                ph_max_attempts=int(row.get("corr_ph_max_attempts") or 0),
                activated_here=bool(row.get("corr_activated_here")),
                stabilization_sec=int(row.get("corr_stabilization_sec") or 0),
                return_stage_success=str(row.get("corr_return_stage_success") or ""),
                return_stage_fail=str(row.get("corr_return_stage_fail") or ""),
                outcome_success=row.get("corr_outcome_success"),
                needs_ec=bool(row.get("corr_needs_ec")),
                ec_node_uid=row.get("corr_ec_node_uid"),
                ec_channel=row.get("corr_ec_channel"),
                ec_duration_ms=int(row["corr_ec_duration_ms"]) if row.get("corr_ec_duration_ms") is not None else None,
                needs_ph_up=bool(row.get("corr_needs_ph_up")),
                needs_ph_down=bool(row.get("corr_needs_ph_down")),
                ph_node_uid=row.get("corr_ph_node_uid"),
                ph_channel=row.get("corr_ph_channel"),
                ph_duration_ms=int(row["corr_ph_duration_ms"]) if row.get("corr_ph_duration_ms") is not None else None,
                wait_until=_naive(row.get("corr_wait_until")),
                ec_component=str(row["corr_ec_component"]) if row.get("corr_ec_component") is not None else None,
                ec_amount_ml=float(row["corr_ec_amount_ml"]) if row.get("corr_ec_amount_ml") is not None else None,
                ph_amount_ml=float(row["corr_ph_amount_ml"]) if row.get("corr_ph_amount_ml") is not None else None,
            )

        intent_meta = row.get("intent_meta")

        return cls(
            id=int(row["id"]),
            zone_id=int(row["zone_id"]),
            task_type=str(row.get("task_type") or "").strip().lower(),
            status=str(row.get("status") or "").strip().lower(),
            idempotency_key=str(row.get("idempotency_key") or ""),
            scheduled_for=_naive(row["scheduled_for"]),
            due_at=_naive(row["due_at"]),
            claimed_by=str(row["claimed_by"]) if row.get("claimed_by") is not None else None,
            claimed_at=_naive(row.get("claimed_at")),
            error_code=str(row["error_code"]) if row.get("error_code") is not None else None,
            error_message=str(row["error_message"]) if row.get("error_message") is not None else None,
            created_at=_naive(row["created_at"]),
            updated_at=_naive(row["updated_at"]),
            completed_at=_naive(row.get("completed_at")),
            topology=str(row.get("topology") or "two_tank"),
            intent_source=str(row["intent_source"]) if row.get("intent_source") is not None else None,
            intent_trigger=str(row["intent_trigger"]) if row.get("intent_trigger") is not None else None,
            intent_id=int(row["intent_id"]) if row.get("intent_id") is not None else None,
            intent_meta=intent_meta if isinstance(intent_meta, Mapping) else {},
            workflow=workflow,
            correction=correction,
        )

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_TASK_STATUSES

    @property
    def can_be_claimed(self) -> bool:
        return self.status == "pending"

    @property
    def current_stage(self) -> str:
        return self.workflow.current_stage

    @property
    def workflow_phase(self) -> str:
        return self.workflow.workflow_phase

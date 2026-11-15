"""Shared records and immutable policy values for PgAutomationTaskRepository."""

from __future__ import annotations

import logging

logger = logging.getLogger('ae3lite.infrastructure.repositories.automation_task_repository')


class _ZoneLeaseNotAcquired(Exception):
    """Lease не захвачена внутри транзакции claim. Транзакция откатывается."""


ACTIVE_TASK_STATUSES = ("pending", "claimed", "running", "waiting_command")

RUNNING_TASK_STATUSES = ("claimed", "running", "waiting_command")

CORRECTION_OPTIONAL_FIELDS = (
    "corr_step",
    "attempt",
    "max_attempts",
    "ec_attempt",
    "ec_max_attempts",
    "ph_attempt",
    "ph_max_attempts",
    "activated_here",
    "stabilization_sec",
    "return_stage_success",
    "return_stage_fail",
    "outcome_success",
    "needs_ec",
    "ec_node_uid",
    "ec_channel",
    "ec_duration_ms",
    "needs_ph_up",
    "needs_ph_down",
    "ph_node_uid",
    "ph_channel",
    "ph_duration_ms",
    "wait_until",
    "ec_component",
    "ec_amount_ml",
    "ec_dose_sequence_json",
    "ec_current_seq_index",
    "ph_amount_ml",
    "snapshot_event_id",
    "snapshot_created_at",
    "snapshot_cmd_id",
    "snapshot_source_event_type",
    "pipeline_phase",
    "active_component",
    "water_ec",
    "water_ph",
    "nutrient_budget",
    "component_targets_json",
    "dilute_attempts",
    "ec_pid_frozen",
    "baseline_id",
)

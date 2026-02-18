"""Observability contract payload helpers for scheduler cutover."""

from __future__ import annotations

from typing import Any, Dict


def build_scheduler_observability_contract_payload() -> Dict[str, Any]:
    return {
        "contract_version": "s11-observability-v1",
        "required_metrics": [
            "scheduler_bootstrap_status_total{status,rollout_profile}",
            "scheduler_dedupe_decisions_total{outcome}",
            "decision_retry_enqueue_total{outcome}",
            "task_recovery_success_rate",
            "command_effect_confirm_rate{task_type}",
        ],
        "required_alert_codes": [
            "infra_scheduler_bootstrap_denied",
            "infra_unknown_error",
            "infra_scheduler_task_recovery_persist_failed",
            "infra_scheduler_task_recovery_event_failed",
            "infra_workflow_state_recovery_enqueue_failed",
            "infra_workflow_state_recovery_row_failed",
        ],
        "required_events": [
            "SCHEDULE_TASK_ACCEPTED",
            "SCHEDULE_TASK_FAILED",
            "WORKFLOW_RECOVERY_ENQUEUED",
            "WORKFLOW_RECOVERY_STALE_STOPPED",
            "WORKFLOW_RECOVERY_WORKFLOW_FALLBACK",
        ],
    }


__all__ = ["build_scheduler_observability_contract_payload"]

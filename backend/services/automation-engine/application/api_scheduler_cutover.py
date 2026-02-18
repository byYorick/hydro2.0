"""Cutover/rollout state payload helpers for scheduler observability."""

from __future__ import annotations

from typing import Any, Dict


def build_scheduler_cutover_state_payload(
    *,
    rollout_profile: str,
    tier2_capabilities: Dict[str, bool],
    scheduler_bootstrap_enforce: bool,
    scheduler_security_baseline_enforce: bool,
    scheduler_require_trace_id: bool,
    scheduler_dedupe_window_sec: int,
    scheduler_bootstrap_lease_ttl_sec: int,
    scheduler_bootstrap_poll_interval_sec: int,
    scheduler_bootstrap_task_timeout_sec: int,
) -> Dict[str, Any]:
    return {
        "rollout_profile": str(rollout_profile or "").strip().lower() or "canary-first",
        "tier2_capabilities": {
            "gdd_phase_transitions": bool(tier2_capabilities.get("gdd_phase_transitions")),
            "mobile_approvals": bool(tier2_capabilities.get("mobile_approvals")),
            "daily_health_digest": bool(tier2_capabilities.get("daily_health_digest")),
        },
        "scheduler_ingress": {
            "bootstrap_enforce": bool(scheduler_bootstrap_enforce),
            "security_baseline_enforce": bool(scheduler_security_baseline_enforce),
            "require_trace_id": bool(scheduler_require_trace_id),
            "dedupe_window_sec": int(scheduler_dedupe_window_sec),
            "bootstrap_lease_ttl_sec": int(scheduler_bootstrap_lease_ttl_sec),
            "bootstrap_poll_interval_sec": int(scheduler_bootstrap_poll_interval_sec),
            "bootstrap_task_timeout_sec": int(scheduler_bootstrap_task_timeout_sec),
        },
    }


__all__ = ["build_scheduler_cutover_state_payload"]

"""Tier2 integration contract payload helpers for scheduler cutover."""

from __future__ import annotations

from typing import Any, Dict


def build_scheduler_integration_contract_payload(
    *,
    rollout_profile: str,
    tier2_capabilities: Dict[str, bool],
) -> Dict[str, Any]:
    profile = str(rollout_profile or "").strip().lower() or "canary-first"
    gdd_enabled = bool(tier2_capabilities.get("gdd_phase_transitions"))
    approvals_enabled = bool(tier2_capabilities.get("mobile_approvals"))
    digest_enabled = bool(tier2_capabilities.get("daily_health_digest"))

    return {
        "contract_version": "s11-v1",
        "rollout_profile": profile,
        "integrations": {
            "gdd_phase_transitions": {
                "enabled": gdd_enabled,
                "signal": "gdd_phase_transition_request",
                "result_signal": "gdd_phase_transition_result",
            },
            "mobile_approvals": {
                "enabled": approvals_enabled,
                "signal": "mobile_approval_request",
                "result_signal": "mobile_approval_result",
            },
            "daily_health_digest": {
                "enabled": digest_enabled,
                "signal": "daily_health_digest_request",
                "result_signal": "daily_health_digest_result",
            },
        },
    }


__all__ = ["build_scheduler_integration_contract_payload"]

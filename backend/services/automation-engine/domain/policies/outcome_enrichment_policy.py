"""Extended outcome enrichment helpers for scheduler execution results."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence

from domain.models.decision_models import DecisionOutcome


def ensure_extended_outcome(
    *,
    task_type: str,
    payload: Dict[str, Any],
    decision: DecisionOutcome,
    result: Dict[str, Any],
    extract_next_due_at: Callable[[DecisionOutcome, Dict[str, Any]], str | None],
    safe_int: Callable[[Any], int | None],
    extract_topology: Callable[[Dict[str, Any]], str],
    extract_two_tank_chemistry_orchestration: Callable[[Dict[str, Any]], Dict[str, Any]],
    wind_blocked_reason: str,
    outside_temp_blocked_reason: str,
) -> Dict[str, Any]:
    enriched = dict(result)

    if not isinstance(enriched.get("executed_steps"), list):
        step_name = str(enriched.get("workflow") or enriched.get("mode") or task_type).strip() or task_type
        decision_state = str(enriched.get("decision") or "").strip().lower()
        if decision_state == "skip":
            step_status = "skipped"
        elif decision_state == "retry":
            step_status = "retry_scheduled"
        elif bool(enriched.get("success")):
            step_status = "completed"
        else:
            step_status = "failed"
        enriched["executed_steps"] = [{"step": step_name, "status": step_status}]

    safety_flags: List[str] = []
    raw_flags = enriched.get("safety_flags")
    if isinstance(raw_flags, Sequence) and not isinstance(raw_flags, (str, bytes, bytearray)):
        for item in raw_flags:
            value = str(item).strip()
            if value and value not in safety_flags:
                safety_flags.append(value)
    if isinstance(decision.details, dict):
        details_flags = decision.details.get("safety_flags")
        if isinstance(details_flags, Sequence) and not isinstance(details_flags, (str, bytes, bytearray)):
            for item in details_flags:
                value = str(item).strip()
                if value and value not in safety_flags:
                    safety_flags.append(value)
    reason_code = str(enriched.get("reason_code") or "").strip().lower()
    if reason_code in {
        "low_water",
        "nodes_unavailable",
        wind_blocked_reason,
        outside_temp_blocked_reason,
        "climate_external_nodes_unavailable",
    } and reason_code not in safety_flags:
        safety_flags.append(reason_code)
    enriched["safety_flags"] = safety_flags

    next_due_at = extract_next_due_at(decision, enriched)
    enriched["next_due_at"] = next_due_at

    if isinstance(enriched.get("measurements_before_after"), dict):
        measurements = enriched.get("measurements_before_after")
    elif isinstance(decision.details, dict) and isinstance(decision.details.get("sensor_snapshot"), dict):
        measurements = {"before": decision.details.get("sensor_snapshot"), "after": None}
    elif isinstance(enriched.get("targets_state"), dict):
        targets_state = enriched.get("targets_state") if isinstance(enriched.get("targets_state"), dict) else {}
        ph_state = targets_state.get("ph") if isinstance(targets_state.get("ph"), dict) else {}
        ec_state = targets_state.get("ec") if isinstance(targets_state.get("ec"), dict) else {}
        measurements = {"before": {"ph": ph_state.get("value"), "ec": ec_state.get("value")}, "after": None}
    else:
        measurements = {"before": None, "after": None}
    enriched["measurements_before_after"] = measurements

    if isinstance(decision.details, dict):
        run_mode = decision.details.get("run_mode")
        if isinstance(run_mode, str) and run_mode.strip():
            enriched.setdefault("run_mode", run_mode.strip())
        retry_attempt = safe_int(decision.details.get("retry_attempt"))
        retry_max_attempts = safe_int(decision.details.get("retry_max_attempts"))
        retry_backoff_sec = safe_int(decision.details.get("retry_backoff_sec"))
        if retry_attempt is not None:
            enriched.setdefault("retry_attempt", max(0, retry_attempt))
        if retry_max_attempts is not None:
            enriched.setdefault("retry_max_attempts", max(1, retry_max_attempts))
        if retry_backoff_sec is not None:
            enriched.setdefault("retry_backoff_sec", max(0, retry_backoff_sec))

    if extract_topology(payload) == "two_tank_drip_substrate_trays":
        orchestration = extract_two_tank_chemistry_orchestration(payload)
        if orchestration:
            enriched.setdefault("chemistry_orchestration", orchestration)

    return enriched


__all__ = ["ensure_extended_outcome"]

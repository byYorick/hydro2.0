"""Execution flow payload/result helpers for scheduler task executor."""

from __future__ import annotations

from typing import Any, Dict, Optional

from domain.models.decision_models import DecisionOutcome


def build_task_received_payload(*, payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "payload": payload,
        "scheduled_for": context.get("scheduled_for"),
    }


def build_execution_started_zone_event_payload(
    *,
    task_type: str,
    payload: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "task_type": task_type,
        "payload": payload,
        "task_id": context.get("task_id") or None,
        "correlation_id": context.get("correlation_id") or None,
    }


def build_decision_payload(decision: DecisionOutcome) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "action_required": decision.action_required,
        "decision": decision.decision,
        "reason_code": decision.reason_code,
        "reason": decision.reason,
    }
    if isinstance(decision.details, dict) and decision.details:
        result["decision_details"] = decision.details
    return result


def build_no_action_result(
    *,
    task_type: str,
    decision: DecisionOutcome,
    retry_enqueue: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    success = decision.decision != "fail"
    result: Dict[str, Any] = {
        "success": success,
        "task_type": task_type,
        "mode": f"decision_{decision.decision}",
        "commands_total": 0,
        "commands_failed": 0,
        "action_required": False,
        "decision": decision.decision,
        "reason_code": decision.reason_code,
        "reason": decision.reason,
    }
    if not success:
        result["error"] = decision.reason_code
        result["error_code"] = decision.reason_code
    if isinstance(decision.details, dict) and decision.details:
        result["decision_details"] = decision.details
    if retry_enqueue is not None:
        result["retry_enqueued"] = retry_enqueue
    return result


def apply_decision_defaults(*, result: Dict[str, Any], decision: DecisionOutcome) -> Dict[str, Any]:
    patched = dict(result)
    patched.setdefault("action_required", decision.action_required)
    patched.setdefault("decision", decision.decision)
    patched.setdefault("reason_code", decision.reason_code)
    patched.setdefault("reason", decision.reason)
    if isinstance(decision.details, dict) and decision.details:
        patched.setdefault("decision_details", decision.details)
    return patched


def build_task_finished_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "success": bool(result.get("success")),
        "result": result,
        "action_required": bool(result.get("action_required")),
        "decision": str(result.get("decision") or "unknown"),
        "reason_code": str(result.get("reason_code") or "unknown"),
    }


def build_execution_finished_zone_event_payload(
    *,
    task_type: str,
    result: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "task_type": task_type,
        "success": bool(result.get("success")),
        "result": result,
        "task_id": context.get("task_id") or None,
        "correlation_id": context.get("correlation_id") or None,
    }


__all__ = [
    "apply_decision_defaults",
    "build_decision_payload",
    "build_execution_finished_zone_event_payload",
    "build_execution_started_zone_event_payload",
    "build_no_action_result",
    "build_task_finished_payload",
    "build_task_received_payload",
]

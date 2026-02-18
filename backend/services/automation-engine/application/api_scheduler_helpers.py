"""Pure helpers for scheduler API request/result normalization."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

from services.resilience_contract import (
    SCHEDULER_MODE_DEADLINE_REJECTED,
    SCHEDULER_MODE_EXECUTION_FAILED,
)


def new_scheduler_task_id() -> str:
    return f"st-{uuid4().hex}"


def new_scheduler_lease_id() -> str:
    return f"lease-{uuid4().hex}"


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def task_payload_fingerprint(req: Any) -> str:
    raw = {
        "zone_id": req.zone_id,
        "task_type": req.task_type,
        "payload": req.payload or {},
        "scheduled_for": req.scheduled_for,
        "due_at": req.due_at,
        "expires_at": req.expires_at,
    }
    return hashlib.sha256(canonical_json(raw).encode("utf-8")).hexdigest()


def task_payload_matches(req: Any, existing_task: Dict[str, Any], expected_fingerprint: str) -> bool:
    existing_fingerprint = existing_task.get("payload_fingerprint")
    if isinstance(existing_fingerprint, str) and existing_fingerprint:
        return existing_fingerprint == expected_fingerprint

    if int(existing_task.get("zone_id") or 0) != int(req.zone_id):
        return False
    if str(existing_task.get("task_type") or "").strip().lower() != str(req.task_type).strip().lower():
        return False
    if (existing_task.get("scheduled_for") or None) != (req.scheduled_for or None):
        return False
    if (existing_task.get("due_at") or None) != (req.due_at or None):
        return False
    if (existing_task.get("expires_at") or None) != (req.expires_at or None):
        return False
    return canonical_json(existing_task.get("payload") or {}) == canonical_json(req.payload or {})


def build_deadline_terminal_result(
    *,
    status: str,
    now: datetime,
    due_at: datetime,
    expires_at: datetime,
    err_task_expired: str,
    err_task_due_deadline_exceeded: str,
) -> Dict[str, Any]:
    if status == "expired":
        reason_code = err_task_expired
        reason = "Задача получена после expires_at и не может быть исполнена"
        error_code = err_task_expired
    else:
        reason_code = err_task_due_deadline_exceeded
        reason = "Задача получена позже due_at и отклонена без запуска исполнения"
        error_code = err_task_due_deadline_exceeded

    return {
        "success": False,
        "mode": SCHEDULER_MODE_DEADLINE_REJECTED,
        "action_required": False,
        "decision": "skip",
        "reason_code": reason_code,
        "reason": reason,
        "received_at": now.isoformat(),
        "due_at": due_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "error": error_code,
        "error_code": error_code,
    }


def build_execution_terminal_result(
    *,
    error_code: str,
    reason: str,
    mode: str,
    action_required: bool = True,
    decision: str = "fail",
    reason_code: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "success": False,
        "mode": mode,
        "action_required": action_required,
        "decision": decision,
        "reason_code": reason_code or error_code,
        "reason": reason,
        "error": error_code,
        "error_code": error_code,
    }
    if isinstance(extra, dict):
        result.update(extra)
    return result


def normalize_failed_execution_result(
    result: Dict[str, Any],
    *,
    err_task_execution_failed: str,
) -> Dict[str, Any]:
    normalized = dict(result) if isinstance(result, dict) else {}
    error_code_raw = normalized.get("error_code") or normalized.get("error")
    error_code = str(error_code_raw or err_task_execution_failed)

    action_required = normalized.get("action_required")
    if not isinstance(action_required, bool):
        action_required = True

    decision = normalized.get("decision")
    if not isinstance(decision, str) or not decision.strip():
        decision = "fail"
    else:
        decision = decision.strip().lower()
        if decision == "execute":
            decision = "run"
        if decision == "run":
            decision = "fail"
        elif decision not in {"skip", "retry", "fail"}:
            decision = "fail"

    reason_code = normalized.get("reason_code")
    if not isinstance(reason_code, str) or not reason_code.strip():
        reason_code = error_code

    reason = normalized.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = "Задача завершилась ошибкой в automation-engine"

    error = normalized.get("error")
    if not isinstance(error, str) or not error.strip():
        error = error_code

    normalized["error"] = error
    normalized["error_code"] = error_code
    normalized["action_required"] = action_required
    normalized["decision"] = decision
    normalized["reason_code"] = reason_code
    normalized["reason"] = reason
    normalized.setdefault("mode", SCHEDULER_MODE_EXECUTION_FAILED)
    normalized["success"] = False
    return normalized


__all__ = [
    "build_deadline_terminal_result",
    "build_execution_terminal_result",
    "canonical_json",
    "new_scheduler_lease_id",
    "new_scheduler_task_id",
    "normalize_failed_execution_result",
    "task_payload_fingerprint",
    "task_payload_matches",
]

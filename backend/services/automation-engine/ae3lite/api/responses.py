"""Вспомогательные функции HTTP-ответов для compat-ingress AE3-Lite."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ae3lite.api.contracts import StartCycleRequest


def build_start_cycle_response(
    *,
    zone_id: int,
    req: StartCycleRequest,
    is_duplicate: bool,
    task_id: str,
    accepted: bool = True,
    runner_state: str = "active",
    task_status: Optional[str] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "zone_id": zone_id,
        "accepted": bool(accepted),
        "runner_state": str(runner_state or "active"),
        "deduplicated": is_duplicate,
        "task_id": task_id,
        "idempotency_key": req.idempotency_key,
    }
    normalized_task_status = str(task_status or "").strip().lower()
    if normalized_task_status:
        data["task_status"] = normalized_task_status
    normalized_reason = str(reason or "").strip()
    if normalized_reason:
        data["reason"] = normalized_reason

    return {
        "status": "ok",
        "data": data,
    }


__all__ = ["build_start_cycle_response"]

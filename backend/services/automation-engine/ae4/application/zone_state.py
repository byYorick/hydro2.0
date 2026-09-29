"""Оверлей ответа состояния зоны для экрана (planting_decision + unattended)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ae4.application.unattended_ready import assess_zone_unattended, assessment_to_payload
from ae4.infrastructure.failure_report import (
    load_latest_planting_decision,
    load_latest_state_overlay,
)
from common.db import fetch


async def enrich_zone_automation_state(
    *,
    zone_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Добавляет state_details, решение посадки и unattended_ready §11.7."""
    overlay = await load_latest_state_overlay(zone_id=zone_id)
    decision = await load_latest_planting_decision(zone_id=zone_id)
    result = dict(payload)

    details = dict(result.get("state_details") or {})
    if overlay:
        if overlay.get("failed") is True:
            details["failed"] = True
            details["error_code"] = overlay.get("error_code")
            details["human_error_message"] = overlay.get("human_error_message")
            if overlay.get("task_id") is not None:
                details["failed_task_id"] = overlay.get("task_id")
        elif details.get("failed") is not True:
            details.setdefault("failed", False)
            planting = overlay.get("planting_decision")
            if isinstance(planting, dict):
                decision = {
                    "reason_code": str(planting.get("reason_code") or ""),
                    "human_message": str(planting.get("human_message") or ""),
                    "failed": False,
                }
    result["state_details"] = details
    if decision is not None:
        result["planting_decision"] = decision

    if await _is_current_runtime(zone_id=zone_id):
        assessment = await assess_zone_unattended(
            zone_id=zone_id,
            now=datetime.now(timezone.utc),
            emit_regression_alerts=True,
        )
        result.update(assessment_to_payload(assessment))

    return result


async def _is_current_runtime(*, zone_id: int) -> bool:
    """После сноса обслуживается любой runtime, кроме явного старого ae3."""
    rows = await fetch(
        "SELECT automation_runtime FROM zones WHERE id = $1",
        zone_id,
    )
    if not rows:
        return False
    runtime = str(rows[0].get("automation_runtime") or "").strip().lower()
    return runtime != "ae3"


__all__ = ["enrich_zone_automation_state"]

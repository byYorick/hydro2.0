"""Публикация biz-алерта при терминальном сбое AE3-задачи."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from ae3lite.infrastructure.metrics import inc_observability_write_failed

logger = logging.getLogger(__name__)

_RECOVERY_ALERT_DEDUPE_SOURCES = frozenset({"startup_recovery", "waiting_command_reconcile"})


def recovery_task_failed_dedupe_key(
    *,
    alert_code: str,
    zone_id: int,
    task_id: int,
    recovery_source: str,
) -> str | None:
    """Стабильный dedupe_key для fail-closed recovery без дублей при multi-instance."""
    source = str(recovery_source or "").strip().lower()
    if source not in _RECOVERY_ALERT_DEDUPE_SOURCES:
        return None
    if zone_id <= 0 or task_id <= 0:
        return None
    code = str(alert_code or "").strip() or "biz_ae3_task_failed"
    return f"{code}:{zone_id}:{task_id}:{source}"


async def emit_task_failed_alert(
    *,
    alert_repository: Any | None,
    task: Any,
    error_code: str,
    error_message: str,
    now: datetime,
    extra_details: Mapping[str, Any] | None = None,
) -> None:
    """Записывает alert о сбое задачи; ошибки публикации не пробрасываются."""
    if alert_repository is None:
        return

    try:
        task_status = "failed"
        task_id = int(getattr(task, "id", 0) or 0)
        zone_id = int(getattr(task, "zone_id", 0) or 0)
        workflow = getattr(task, "workflow", None)
        now_utc = now.astimezone(timezone.utc) if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        details: dict[str, Any] = {
            "task_id": task_id,
            "task_type": str(getattr(task, "task_type", "") or "").strip().lower(),
            "task_status": task_status,
            "error_code": str(error_code),
            "error_message": str(error_message),
            "message": str(error_message),
            "stage": str(getattr(task, "current_stage", "") or "").strip(),
            "workflow_phase": str(getattr(task, "workflow_phase", "") or "").strip(),
            "stage_retry_count": int(getattr(workflow, "stage_retry_count", 0) or 0),
            "topology": str(getattr(task, "topology", "") or "").strip().lower(),
            "failed_at": now_utc.isoformat(),
        }
        corr = getattr(task, "correction", None)
        if corr is not None:
            details["corr_step"] = str(getattr(corr, "corr_step", "") or "").strip()
        if extra_details:
            details.update(dict(extra_details))

        recovery_source = str(details.get("recovery_source") or "").strip()
        recovery_dedupe = recovery_task_failed_dedupe_key(
            alert_code="biz_ae3_task_failed",
            zone_id=zone_id,
            task_id=task_id,
            recovery_source=recovery_source,
        )
        if recovery_dedupe is not None:
            details["dedupe_key"] = recovery_dedupe

        alert_code = "biz_ae3_task_failed"
        alert_severity = "error"
        if str(error_code).strip().lower() == "zone_correction_config_missing_critical":
            alert_code = "biz_zone_correction_config_missing"
            alert_severity = "critical"
        if str(error_code).strip().lower() == "zone_dosing_calibration_missing_critical":
            alert_code = "biz_zone_dosing_calibration_missing"
            alert_severity = "critical"
        if str(error_code).strip().lower() == "zone_pid_config_missing_critical":
            alert_code = "biz_zone_pid_config_missing"
            alert_severity = "critical"
        if str(error_code).strip().lower() == "zone_recipe_phase_targets_missing_critical":
            alert_code = "biz_zone_recipe_phase_targets_missing"
            alert_severity = "critical"
        normalized_error_code = str(error_code).strip().lower()
        if normalized_error_code in {
            "ae3_required_node_offline",
            "ae3_snapshot_required_node_persistently_offline",
            "irr_state_unavailable",
            "irr_state_stale",
            "command_timeout",
        }:
            if isinstance(extra_details, Mapping):
                offline_nodes = extra_details.get("offline_required_nodes")
                if isinstance(offline_nodes, list) and offline_nodes:
                    first = offline_nodes[0]
                    if isinstance(first, Mapping) and first.get("uid"):
                        details.setdefault("node_uid", first.get("uid"))
                details.setdefault("node_uid", extra_details.get("node_uid"))
            if not details.get("node_uid") and normalized_error_code == "irr_state_unavailable":
                details["message"] = (
                    str(error_message)
                    + " Проверьте связь с IRR-нодой (питание, Wi‑Fi, MQTT)."
                )
            details.setdefault(
                "node_uid",
                details.get("node_uid")
                or (extra_details.get("node_uid") if isinstance(extra_details, Mapping) else None),
            )

        await alert_repository.raise_active(
            zone_id=zone_id,
            code=alert_code,
            details=details,
            now=now,
            category="operations",
            severity=alert_severity,
        )
    except Exception:
        inc_observability_write_failed(kind="biz_alert")
        logger.warning(
            "AE3 не смог записать alert task-failed: task_id=%s zone_id=%s code=%s",
            getattr(task, "id", None),
            getattr(task, "zone_id", None),
            error_code,
            exc_info=True,
        )

"""Startup-initial branch handlers for two-tank startup workflow."""

from __future__ import annotations

import logging
from typing import Any, Dict

from executor.executor_constants import (
    ERR_SENSOR_STATE_INCONSISTENT,
    ERR_TWO_TANK_LEVEL_STALE,
    ERR_TWO_TANK_LEVEL_UNAVAILABLE,
    REASON_SENSOR_LEVEL_UNAVAILABLE,
    REASON_SENSOR_STALE_DETECTED,
    REASON_SENSOR_STATE_INCONSISTENT,
    REASON_TANK_LEVEL_CHECKED,
)

logger = logging.getLogger(__name__)


def build_sensor_state_inconsistent_result(
    *,
    workflow: str,
    reason: str,
    clean_level_max: bool,
    clean_level_min: bool,
) -> Dict[str, Any]:
    return {
        "success": False,
        "task_type": "diagnostics",
        "mode": "two_tank_sensor_state_inconsistent",
        "workflow": workflow,
        "commands_total": 0,
        "commands_failed": 0,
        "action_required": True,
        "decision": "run",
        "reason_code": REASON_SENSOR_STATE_INCONSISTENT,
        "reason": reason,
        "error": ERR_SENSOR_STATE_INCONSISTENT,
        "error_code": ERR_SENSOR_STATE_INCONSISTENT,
        "sensor_state": {
            "clean_level_max": clean_level_max,
            "clean_level_min": clean_level_min,
        },
    }


async def handle_two_tank_startup_initial(
    self,
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    workflow: str,
) -> Dict[str, Any]:
    clean_level = await self._read_level_switch(
        zone_id=zone_id,
        sensor_labels=runtime_cfg["clean_max_labels"],
        threshold=runtime_cfg["level_switch_on_threshold"],
    )
    await self._emit_task_event(
        zone_id=zone_id,
        task_type="diagnostics",
        context=context,
        event_type="TANK_LEVEL_CHECKED",
        payload={
            "tank": "clean",
            "sensor_id": clean_level["sensor_id"],
            "sensor_label": clean_level["sensor_label"],
            "level": clean_level["level"],
            "is_triggered": clean_level["is_triggered"],
            "sample_ts": clean_level["sample_ts"],
            "sample_age_sec": clean_level["sample_age_sec"],
            "is_stale": clean_level["is_stale"],
            "reason_code": REASON_TANK_LEVEL_CHECKED,
        },
    )
    if not clean_level["has_level"]:
        logger.warning(
            "Zone %s: two_tank clean level unavailable (startup), expected=%s available=%s source=%s",
            zone_id,
            clean_level.get("expected_labels", runtime_cfg["clean_max_labels"]),
            clean_level.get("available_sensor_labels", []),
            clean_level.get("level_source", "none"),
        )
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_clean_level_unavailable",
            "workflow": workflow,
            "commands_total": 0,
            "commands_failed": 0,
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_SENSOR_LEVEL_UNAVAILABLE,
            "reason": "Нет данных датчика верхнего уровня чистого бака",
            "error": ERR_TWO_TANK_LEVEL_UNAVAILABLE,
            "error_code": ERR_TWO_TANK_LEVEL_UNAVAILABLE,
            "expected_sensor_labels": clean_level.get("expected_labels", runtime_cfg["clean_max_labels"]),
            "available_sensor_labels": clean_level.get("available_sensor_labels", []),
            "level_source": clean_level.get("level_source", "none"),
        }
    if self._telemetry_freshness_enforce() and clean_level["is_stale"]:
        return {
            "success": False,
            "task_type": "diagnostics",
            "mode": "two_tank_clean_level_stale",
            "workflow": workflow,
            "commands_total": 0,
            "commands_failed": 0,
            "action_required": True,
            "decision": "run",
            "reason_code": REASON_SENSOR_STALE_DETECTED,
            "reason": "Телеметрия датчика верхнего уровня чистого бака устарела",
            "error": ERR_TWO_TANK_LEVEL_STALE,
            "error_code": ERR_TWO_TANK_LEVEL_STALE,
        }
    if clean_level["is_triggered"]:
        clean_min_level = await self._read_level_switch(
            zone_id=zone_id,
            sensor_labels=runtime_cfg["clean_min_labels"],
            threshold=runtime_cfg["level_switch_on_threshold"],
        )
        if not clean_min_level["has_level"]:
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_clean_min_level_unavailable",
                "workflow": workflow,
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_SENSOR_LEVEL_UNAVAILABLE,
                "reason": "Нет данных датчика нижнего уровня чистого бака",
                "error": ERR_TWO_TANK_LEVEL_UNAVAILABLE,
                "error_code": ERR_TWO_TANK_LEVEL_UNAVAILABLE,
                "expected_sensor_labels": clean_min_level.get("expected_labels", runtime_cfg["clean_min_labels"]),
                "available_sensor_labels": clean_min_level.get("available_sensor_labels", []),
                "level_source": clean_min_level.get("level_source", "none"),
            }
        if self._telemetry_freshness_enforce() and clean_min_level["is_stale"]:
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_clean_min_level_stale",
                "workflow": workflow,
                "commands_total": 0,
                "commands_failed": 0,
                "action_required": True,
                "decision": "run",
                "reason_code": REASON_SENSOR_STALE_DETECTED,
                "reason": "Телеметрия датчика нижнего уровня чистого бака устарела",
                "error": ERR_TWO_TANK_LEVEL_STALE,
                "error_code": ERR_TWO_TANK_LEVEL_STALE,
            }
        if not clean_min_level["is_triggered"]:
            return build_sensor_state_inconsistent_result(
                workflow=workflow,
                reason="Несогласованность датчиков чистого бака: max=1 и min=0",
                clean_level_max=True,
                clean_level_min=False,
            )
        return await self._start_two_tank_solution_fill(
            zone_id=zone_id,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
        )

    return await self._start_two_tank_clean_fill(
        zone_id=zone_id,
        payload=payload,
        context=context,
        runtime_cfg=runtime_cfg,
        cycle=1,
    )


__all__ = [
    "build_sensor_state_inconsistent_result",
    "handle_two_tank_startup_initial",
]

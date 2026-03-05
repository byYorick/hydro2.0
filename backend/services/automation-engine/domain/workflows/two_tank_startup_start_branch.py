"""Startup-initial branch handlers for two-tank startup workflow."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from domain.workflows.two_tank_deps import TwoTankDeps
from domain.workflows.two_tank_result import two_tank_error
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
    tank: str = "clean",
) -> Dict[str, Any]:
    normalized_tank = str(tank or "clean").strip().lower()
    if normalized_tank not in {"clean", "solution"}:
        normalized_tank = "clean"
    sensor_state = {
        "tank": normalized_tank,
        "level_max": clean_level_max,
        "level_min": clean_level_min,
    }
    if normalized_tank == "solution":
        sensor_state["solution_level_max"] = clean_level_max
        sensor_state["solution_level_min"] = clean_level_min
    else:
        sensor_state["clean_level_max"] = clean_level_max
        sensor_state["clean_level_min"] = clean_level_min

    return two_tank_error(
        mode="two_tank_sensor_state_inconsistent",
        workflow=workflow,
        reason_code=REASON_SENSOR_STATE_INCONSISTENT,
        reason=reason,
        error_code=ERR_SENSOR_STATE_INCONSISTENT,
        sensor_state=sensor_state,
    )


async def _read_clean_level_with_startup_retries(
    deps: TwoTankDeps,
    *,
    zone_id: int,
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    clean_level = await deps._read_level_switch(
        zone_id=zone_id,
        sensor_labels=runtime_cfg["clean_max_labels"],
        threshold=runtime_cfg["level_switch_on_threshold"],
    )
    if clean_level["has_level"]:
        return clean_level

    retry_attempts = max(0, int(runtime_cfg.get("startup_clean_level_retry_attempts") or 0))
    retry_delay_sec = max(0.0, float(runtime_cfg.get("startup_clean_level_retry_delay_sec") or 0.0))
    if retry_attempts == 0:
        return clean_level

    for attempt in range(1, retry_attempts + 1):
        if retry_delay_sec > 0:
            await asyncio.sleep(retry_delay_sec)
        clean_level = await deps._read_level_switch(
            zone_id=zone_id,
            sensor_labels=runtime_cfg["clean_max_labels"],
            threshold=runtime_cfg["level_switch_on_threshold"],
        )
        if clean_level["has_level"]:
            logger.info(
                "Zone %s: two_tank clean level recovered during startup retry (%s/%s), source=%s",
                zone_id,
                attempt,
                retry_attempts,
                clean_level.get("level_source", "unknown"),
            )
            return clean_level

    logger.warning(
        "Zone %s: two_tank clean level still unavailable after startup retries (%s attempts, delay=%.2fs)",
        zone_id,
        retry_attempts,
        retry_delay_sec,
    )
    return clean_level


async def handle_two_tank_startup_initial(
    deps: TwoTankDeps,
    *,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
    workflow: str,
) -> Dict[str, Any]:
    zone_id = deps.zone_id
    clean_level = await _read_clean_level_with_startup_retries(
        deps,
        zone_id=zone_id,
        runtime_cfg=runtime_cfg,
    )
    await deps._emit_task_event(
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
        return two_tank_error(
            mode="two_tank_clean_level_unavailable",
            workflow=workflow,
            reason_code=REASON_SENSOR_LEVEL_UNAVAILABLE,
            reason="Нет данных датчика верхнего уровня чистого бака",
            error_code=ERR_TWO_TANK_LEVEL_UNAVAILABLE,
            expected_sensor_labels=clean_level.get("expected_labels", runtime_cfg["clean_max_labels"]),
            available_sensor_labels=clean_level.get("available_sensor_labels", []),
            level_source=clean_level.get("level_source", "none"),
            startup_retry_attempts=max(0, int(runtime_cfg.get("startup_clean_level_retry_attempts") or 0)),
            startup_retry_delay_sec=max(0.0, float(runtime_cfg.get("startup_clean_level_retry_delay_sec") or 0.0)),
        )
    if deps._telemetry_freshness_enforce() and clean_level["is_stale"]:
        return two_tank_error(
            mode="two_tank_clean_level_stale",
            workflow=workflow,
            reason_code=REASON_SENSOR_STALE_DETECTED,
            reason="Телеметрия датчика верхнего уровня чистого бака устарела",
            error_code=ERR_TWO_TANK_LEVEL_STALE,
        )
    if clean_level["is_triggered"]:
        clean_min_level = await deps._read_level_switch(
            zone_id=zone_id,
            sensor_labels=runtime_cfg["clean_min_labels"],
            threshold=runtime_cfg["level_switch_on_threshold"],
        )
        if not clean_min_level["has_level"]:
            return two_tank_error(
                mode="two_tank_clean_min_level_unavailable",
                workflow=workflow,
                reason_code=REASON_SENSOR_LEVEL_UNAVAILABLE,
                reason="Нет данных датчика нижнего уровня чистого бака",
                error_code=ERR_TWO_TANK_LEVEL_UNAVAILABLE,
                expected_sensor_labels=clean_min_level.get("expected_labels", runtime_cfg["clean_min_labels"]),
                available_sensor_labels=clean_min_level.get("available_sensor_labels", []),
                level_source=clean_min_level.get("level_source", "none"),
            )
        if deps._telemetry_freshness_enforce() and clean_min_level["is_stale"]:
            return two_tank_error(
                mode="two_tank_clean_min_level_stale",
                workflow=workflow,
                reason_code=REASON_SENSOR_STALE_DETECTED,
                reason="Телеметрия датчика нижнего уровня чистого бака устарела",
                error_code=ERR_TWO_TANK_LEVEL_STALE,
            )
        if not clean_min_level["is_triggered"]:
            return build_sensor_state_inconsistent_result(
                workflow=workflow,
                reason="Несогласованность датчиков чистого бака: max=1 и min=0",
                clean_level_max=True,
                clean_level_min=False,
            )
        return await deps._start_two_tank_solution_fill(
            zone_id=zone_id,
            payload=payload,
            context=context,
            runtime_cfg=runtime_cfg,
        )

    return await deps._start_two_tank_clean_fill(
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

"""Защищает AE3 ready-state, когда бак раствора опустел."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from ae3lite.application.level_monitor import load_zone_level_monitor_config, solution_tank_is_depleted
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.infrastructure.metrics import CORRECTION_NO_EFFECT_RESET_FAILED

_logger = logging.getLogger(__name__)


class GuardSolutionTankStartupResetUseCase:
    """Сбрасывает `ready`-зоны обратно в startup-required, когда бак раствора пуст.

    В AE3-Lite «режим startup» кодируется так:
    - `zone_workflow_state.workflow_phase = 'idle'`
    - `zone_workflow_state.payload.ae3_cycle_start_stage = 'startup'`

    Также снимает correction no-effect block, чтобы следующий cycle_start
    мог выполнить обычную подготовку раствора.
    """

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        workflow_repository: Any,
        fetch_fn: Any,
        pid_state_repository: Any = None,
    ) -> None:
        self._runtime_monitor = runtime_monitor
        self._workflow_repository = workflow_repository
        self._fetch_fn = fetch_fn
        self._pid_state_repository = pid_state_repository

    async def run(self, *, zone_id: int, now: datetime) -> dict[str, Any]:
        workflow = await self._workflow_repository.get(zone_id=zone_id)
        if workflow is None:
            return {"reset": False, "reason": "workflow_missing"}

        current_stage = self._extract_stage(getattr(workflow, "payload", None))
        if not self._is_ready_state(workflow_phase=workflow.workflow_phase, current_stage=current_stage):
            return {
                "reset": False,
                "reason": "workflow_not_ready",
                "workflow_phase": workflow.workflow_phase,
                "current_stage": current_stage,
            }

        sensor_cfg = await self._load_solution_min_sensor_cfg(zone_id=zone_id)
        level = await self._runtime_monitor.read_level_switch(
            zone_id=zone_id,
            sensor_labels=sensor_cfg["labels"],
            threshold=sensor_cfg["threshold"],
            telemetry_max_age_sec=sensor_cfg["telemetry_max_age_sec"],
            allow_initial_event=True,
        )

        if not bool(level.get("has_level")):
            return {"reset": False, "reason": "solution_min_unavailable", "level": dict(level)}
        if bool(level.get("is_stale")):
            return {"reset": False, "reason": "solution_min_stale", "level": dict(level)}
        if not solution_tank_is_depleted(level):
            return {"reset": False, "reason": "solution_tank_has_solution", "level": dict(level)}

        payload = {
            "ae3_cycle_start_stage": "startup",
            "guard_reason": "solution_tank_depleted",
            "guard_sensor_label": level.get("sensor_label"),
            "guard_sample_ts": level.get("sample_ts").isoformat() if hasattr(level.get("sample_ts"), "isoformat") else None,
        }
        await self._workflow_repository.upsert_phase(
            zone_id=zone_id,
            workflow_phase="idle",
            payload=payload,
            scheduler_task_id=workflow.scheduler_task_id,
            now=now,
        )
        await self._clear_correction_blocks(zone_id=zone_id)
        return {
            "reset": True,
            "reason": "solution_tank_depleted",
            "workflow_phase": "idle",
            "current_stage": "startup",
            "level": dict(level),
        }

    async def _clear_correction_blocks(self, *, zone_id: int) -> None:
        if self._pid_state_repository is None:
            return
        zone_id = int(zone_id)
        last_exc: Exception | None = None
        for attempt in (1, 2):
            try:
                await self._pid_state_repository.reset_no_effect_counts(zone_id=zone_id)
                _logger.info(
                    "solution tank guard: сброшен no_effect block zone_id=%s reason=solution_tank_depleted",
                    zone_id,
                )
                return
            except Exception as exc:
                last_exc = exc
                _logger.warning(
                    "solution tank guard: не удалось сбросить no_effect_count zone_id=%s attempt=%s",
                    zone_id,
                    attempt,
                    exc_info=True,
                )
        CORRECTION_NO_EFFECT_RESET_FAILED.inc()
        raise TaskExecutionError(
            "corr_no_effect_reset_failed",
            f"Не удалось сбросить no_effect_count для зоны {zone_id} (solution_tank_depleted): {last_exc}",
        )

    async def _load_solution_min_sensor_cfg(self, *, zone_id: int) -> dict[str, Any]:
        level_cfg = await load_zone_level_monitor_config(zone_id=zone_id, fetch_fn=self._fetch_fn)
        return {
            "labels": level_cfg["solution_min_sensor_labels"],
            "threshold": level_cfg["level_switch_on_threshold"],
            "telemetry_max_age_sec": level_cfg["telemetry_max_age_sec"],
        }

    def _extract_stage(self, payload: Any) -> str | None:
        if not isinstance(payload, Mapping):
            return None
        raw = payload.get("ae3_cycle_start_stage")
        normalized = str(raw or "").strip().lower()
        return normalized or None

    def _is_ready_state(self, *, workflow_phase: str, current_stage: str | None) -> bool:
        normalized_phase = str(workflow_phase or "").strip().lower()
        normalized_stage = str(current_stage or "").strip().lower()
        return normalized_phase == "ready" or normalized_stage == "complete_ready"

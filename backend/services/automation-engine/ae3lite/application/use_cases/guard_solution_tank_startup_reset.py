"""Guard AE3 ready-state when the solution tank is depleted."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from ae3lite.infrastructure.read_models.active_grow_cycle_order_sql import SQL_ACTIVE_GROW_CYCLE_ORDER_BY


_DEFAULT_SOLUTION_MIN_LABELS: tuple[str, ...] = (
    "level_solution_min",
    "solution_level_min",
    "solution_min",
)


class GuardSolutionTankStartupResetUseCase:
    """Resets `ready` zones back to startup-required when solution tank is empty.

    AE3-Lite encodes "startup mode" as:
    - `zone_workflow_state.workflow_phase = 'idle'`
    - `zone_workflow_state.payload.ae3_cycle_start_stage = 'startup'`
    """

    def __init__(
        self,
        *,
        runtime_monitor: Any,
        workflow_repository: Any,
        fetch_fn: Any,
    ) -> None:
        self._runtime_monitor = runtime_monitor
        self._workflow_repository = workflow_repository
        self._fetch_fn = fetch_fn

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
        )

        if not bool(level.get("has_level")):
            return {"reset": False, "reason": "solution_min_unavailable", "level": dict(level)}
        if bool(level.get("is_stale")):
            return {"reset": False, "reason": "solution_min_stale", "level": dict(level)}
        if not bool(level.get("is_triggered")):
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
        return {
            "reset": True,
            "reason": "solution_tank_depleted",
            "workflow_phase": "idle",
            "current_stage": "startup",
            "level": dict(level),
        }

    async def _load_solution_min_sensor_cfg(self, *, zone_id: int) -> dict[str, Any]:
        rows = await self._fetch_fn(
            f"""
            SELECT aeb.config
            FROM grow_cycles gc
            JOIN automation_effective_bundles aeb
              ON aeb.scope_type = 'grow_cycle'
             AND aeb.scope_id = gc.id
            WHERE gc.zone_id = $1
              AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
            {SQL_ACTIVE_GROW_CYCLE_ORDER_BY.strip()}
            LIMIT 1
            """,
            zone_id,
        )
        config = rows[0].get("config") if rows else None
        zone_bundle = config.get("zone") if isinstance(config, Mapping) else None
        logic_profile = zone_bundle.get("logic_profile") if isinstance(zone_bundle, Mapping) else None
        active_profile = logic_profile.get("active_profile") if isinstance(logic_profile, Mapping) else None
        subsystems = active_profile.get("subsystems") if isinstance(active_profile, Mapping) else None
        diagnostics = self._mapping_get(subsystems, "diagnostics")
        execution = self._mapping_get(diagnostics, "execution")
        startup = self._mapping_get(execution, "startup")

        labels = self._coerce_labels(
            startup.get("solution_min_sensor_labels"),
            startup.get("solution_min_sensor_label"),
        )
        threshold = self._coerce_float(startup.get("level_switch_on_threshold"), default=0.5)
        telemetry_max_age_sec = self._coerce_int(startup.get("telemetry_max_age_sec"), default=60)
        return {
            "labels": labels,
            "threshold": threshold,
            "telemetry_max_age_sec": telemetry_max_age_sec,
        }

    def _mapping_get(self, value: Any, key: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            return {}
        nested = value.get(key)
        return nested if isinstance(nested, Mapping) else {}

    def _coerce_labels(self, *values: Any) -> Sequence[str]:
        for value in values:
            if isinstance(value, str) and value.strip() != "":
                return (value.strip(),)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                labels = [str(item).strip() for item in value if str(item).strip() != ""]
                if labels:
                    return tuple(labels)
        return _DEFAULT_SOLUTION_MIN_LABELS

    def _coerce_float(self, value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _coerce_int(self, value: Any, *, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

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

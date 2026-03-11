"""Get full automation state for a zone — for /zones/{id}/state endpoint."""

from __future__ import annotations

from typing import Any, Callable, Optional


_WORKFLOW_PHASE_TO_STATE: dict[str, str] = {
    "tank_filling": "TANK_FILLING",
    "tank_recirc": "TANK_RECIRC",
    "ready": "READY",
    "irrigating": "IRRIGATING",
    "irrig_recirc": "IRRIG_RECIRC",
    "error": "IDLE",
}

_STATE_LABELS: dict[str, str] = {
    "TANK_FILLING": "Наполнение баков",
    "TANK_RECIRC": "Рециркуляция раствора",
    "READY": "Раствор готов",
    "IRRIGATING": "Полив",
    "IRRIG_RECIRC": "Рециркуляция после полива",
    "IDLE": "Ожидание",
}

_STAGE_LABELS: dict[str, str] = {
    "startup": "Инициализация",
    "clean_fill_start": "Запуск наполнения чистой водой",
    "clean_fill_check": "Наполнение чистой водой",
    "clean_fill_stop_to_solution": "Остановка наполнения чистой водой",
    "solution_fill_start": "Запуск наполнения раствором",
    "solution_fill_check": "Наполнение раствором",
    "solution_fill_stop_to_prepare": "Остановка наполнения раствором",
    "prepare_recirculation_start": "Запуск рециркуляции",
    "prepare_recirculation_check": "Подготовка рециркуляции",
    "complete_ready": "Готов к поливу",
}

# Maps (from_stage, to_stage) → (event_code, human label)
_TRANSITION_EVENT_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("startup", "clean_fill_start"): ("CLEAN_FILL_STARTED", "Запуск наполнения чистой водой"),
    ("clean_fill_start", "clean_fill_check"): ("CLEAN_FILL_IN_PROGRESS", "Наполнение чистой водой"),
    ("clean_fill_check", "clean_fill_stop_to_solution"): ("CLEAN_FILL_COMPLETED", "Чистая вода заполнена"),
    ("clean_fill_stop_to_solution", "solution_fill_start"): ("SOLUTION_FILL_STARTED", "Запуск наполнения раствором"),
    ("solution_fill_start", "solution_fill_check"): ("SOLUTION_FILL_IN_PROGRESS", "Наполнение раствором"),
    ("solution_fill_check", "solution_fill_stop_to_prepare"): ("SOLUTION_FILL_COMPLETED", "Раствор заполнен"),
    ("solution_fill_stop_to_prepare", "prepare_recirculation_start"): ("RECIRC_STARTED", "Запуск рециркуляции"),
    ("prepare_recirculation_start", "prepare_recirculation_check"): ("RECIRC_IN_PROGRESS", "Рециркуляция"),
    ("prepare_recirculation_check", "prepare_recirculation_stop_to_ready"): ("RECIRC_COMPLETED", "Рециркуляция завершена"),
    ("prepare_recirculation_stop_to_ready", "complete_ready"): ("READY", "Готов к поливу"),
    ("prepare_recirculation_check", "complete_ready"): ("READY", "Готов к поливу"),
    ("complete_ready", "irrigation_start"): ("IRRIGATION_STARTED", "Запуск полива"),
}

# Telemetry sensor labels that carry pH/EC/level data
_PH_LABELS = frozenset({"ph_sensor", "ph"})
_EC_LABELS = frozenset({"ec_sensor", "ec"})
_CLEAN_MAX_LABELS = frozenset({"level_clean_max", "clean_level_max", "clean_max"})
_SOLUTION_MAX_LABELS = frozenset({"level_solution_max", "solution_level_max", "solution_max"})


class GetZoneAutomationStateUseCase:
    """Returns full AutomationState-compatible payload for a zone.

    Reads the last task (including failed/completed) and maps it to the
    AutomationState structure expected by the Laravel frontend.
    Enriches with stage transitions (timeline) and live telemetry (current_levels).
    """

    def __init__(self, *, task_repository: Any, fetch_fn: Callable) -> None:
        self._task_repository = task_repository
        self._fetch_fn = fetch_fn

    async def run(self, *, zone_id: int) -> dict[str, Any]:
        # Try active task first, then last terminal task
        task: Optional[Any] = await self._task_repository.get_active_for_zone(zone_id=zone_id)
        if task is None:
            task = await self._task_repository.get_last_for_zone(zone_id=zone_id)

        # Fetch enrichment data in parallel-ish (sequential is fine — both are fast)
        transitions: list[dict] = []
        if task is not None:
            try:
                transitions = await self._task_repository.get_transitions_for_task(task_id=task.id)
            except Exception:
                pass

        telemetry = await self._fetch_zone_telemetry(zone_id=zone_id)

        return self._build_state(zone_id=zone_id, task=task, transitions=transitions, telemetry=telemetry)

    async def _fetch_zone_telemetry(self, *, zone_id: int) -> dict[str, Any]:
        """Query telemetry_last for pH, EC and water level sensors of this zone."""
        try:
            rows = await self._fetch_fn(
                """
                SELECT s.label, s.type, tl.last_value, tl.last_ts, tl.last_quality
                FROM sensors s
                JOIN telemetry_last tl ON tl.sensor_id = s.id
                WHERE s.zone_id = $1
                  AND s.is_active = TRUE
                  AND s.type IN ('PH', 'EC', 'WATER_LEVEL')
                ORDER BY s.type, s.label
                """,
                zone_id,
            )
        except Exception:
            return {}

        result: dict[str, Any] = {}
        for row in rows:
            label = str(row["label"] or "").strip().lower()
            value = float(row["last_value"]) if row["last_value"] is not None else None
            if label in _PH_LABELS:
                result["ph"] = value
            elif label in _EC_LABELS:
                result["ec"] = value
            elif label in _CLEAN_MAX_LABELS:
                result["clean_tank_level_percent"] = 100 if value == 1.0 else 0
            elif label in _SOLUTION_MAX_LABELS:
                result["nutrient_tank_level_percent"] = 100 if value == 1.0 else 0
        return result

    def _build_timeline(self, transitions: list[dict]) -> list[dict]:
        events = []
        for t in transitions:
            from_s = str(t.get("from_stage") or "")
            to_s = str(t.get("to_stage") or "")
            key = (from_s, to_s)
            event_code, label = _TRANSITION_EVENT_MAP.get(key, (f"{from_s}→{to_s}", f"{from_s} → {to_s}"))
            ts = t.get("triggered_at")
            events.append({
                "event": event_code,
                "label": label,
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "active": False,
            })
        # Mark the last event as active
        if events:
            events[-1]["active"] = True
        return events

    def _build_state(
        self,
        *,
        zone_id: int,
        task: Optional[Any],
        transitions: list[dict],
        telemetry: dict[str, Any],
    ) -> dict[str, Any]:
        if task is None:
            return self._idle_state(zone_id=zone_id)

        status = str(getattr(task, "status", "") or "").strip().lower()
        wf = getattr(task, "workflow", None)
        workflow_phase = str(getattr(wf, "workflow_phase", None) or "idle").strip().lower()
        current_stage = getattr(wf, "current_stage", None)
        error_code = getattr(task, "error_code", None)
        error_message = getattr(task, "error_message", None)

        is_failed = status == "failed"
        is_active = status in ("pending", "claimed", "running", "waiting_command")

        state = _WORKFLOW_PHASE_TO_STATE.get(workflow_phase, "IDLE")
        if is_failed:
            state = "IDLE"

        timeline = self._build_timeline(transitions)

        return {
            "zone_id": zone_id,
            "state": state,
            "state_label": _STATE_LABELS.get(state, "Ожидание"),
            "state_details": {
                "started_at": None,
                "elapsed_sec": 0,
                "progress_percent": 0,
                "failed": is_failed,
                "error_code": error_code if is_failed else None,
                "error_message": error_message if is_failed else None,
            },
            "workflow_phase": workflow_phase,
            "current_stage": current_stage,
            "current_stage_label": _STAGE_LABELS.get(str(current_stage or ""), None),
            "system_config": {
                "tanks_count": 2,
                "system_type": "drip",
                "clean_tank_capacity_l": None,
                "nutrient_tank_capacity_l": None,
            },
            "current_levels": {
                "clean_tank_level_percent": telemetry.get("clean_tank_level_percent", 0),
                "nutrient_tank_level_percent": telemetry.get("nutrient_tank_level_percent", 0),
                "buffer_tank_level_percent": None,
                "ph": telemetry.get("ph"),
                "ec": telemetry.get("ec"),
            },
            "active_processes": {
                "pump_in": is_active and workflow_phase == "tank_filling",
                "circulation_pump": is_active and workflow_phase == "tank_recirc",
                "ph_correction": False,
                "ec_correction": False,
            },
            "timeline": timeline,
            "next_state": None,
            "estimated_completion_sec": None,
            "irr_node_state": None,
        }

    def _idle_state(self, *, zone_id: int) -> dict[str, Any]:
        return {
            "zone_id": zone_id,
            "state": "IDLE",
            "state_label": "Ожидание",
            "state_details": {
                "started_at": None,
                "elapsed_sec": 0,
                "progress_percent": 0,
                "failed": False,
                "error_code": None,
                "error_message": None,
            },
            "workflow_phase": "idle",
            "current_stage": None,
            "current_stage_label": None,
            "system_config": {
                "tanks_count": 2,
                "system_type": "drip",
                "clean_tank_capacity_l": None,
                "nutrient_tank_capacity_l": None,
            },
            "current_levels": {
                "clean_tank_level_percent": 0,
                "nutrient_tank_level_percent": 0,
                "buffer_tank_level_percent": None,
                "ph": None,
                "ec": None,
            },
            "active_processes": {
                "pump_in": False,
                "circulation_pump": False,
                "ph_correction": False,
                "ec_correction": False,
            },
            "timeline": [],
            "next_state": None,
            "estimated_completion_sec": None,
            "irr_node_state": None,
        }

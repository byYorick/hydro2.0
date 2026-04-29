"""Собирает полное automation state зоны для endpoint'а /zones/{id}/state."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional

from ae3lite.application.level_monitor import (
    coarse_clean_tank_level_percent,
    coarse_solution_tank_level_percent,
    load_zone_level_monitor_config,
    summarize_zone_telemetry_rows,
)

logger = logging.getLogger(__name__)


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
    "clean_fill_source_empty_stop": "Остановка наполнения: источник чистой воды пуст",
    "solution_fill_start": "Запуск наполнения раствором",
    "solution_fill_check": "Наполнение раствором",
    "solution_fill_source_empty_stop": "Остановка наполнения раствором: источник пуст",
    "solution_fill_leak_stop": "Остановка наполнения раствором: обнаружена утечка/низкий уровень",
    "solution_fill_stop_to_prepare": "Остановка наполнения раствором",
    "prepare_recirculation_start": "Запуск рециркуляции",
    "prepare_recirculation_check": "Подготовка рециркуляции",
    "prepare_recirculation_solution_low_stop": "Остановка рециркуляции: низкий уровень раствора",
    "complete_ready": "Готов к поливу",
    "await_ready": "Ожидание готового раствора",
    "decision_gate": "Принятие решения о поливе",
    "irrigation_start": "Запуск полива",
    "irrigation_check": "Полив",
    "irrigation_recovery_start": "Запуск рециркуляции после полива",
    "irrigation_recovery_check": "Рециркуляция после полива",
    "completed_run": "Полив завершён",
    "completed_skip": "Полив пропущен",
    "apply": "Свет (scheduler tick)",
}

# Соответствие (from_stage, to_stage) → (event_code, human label)
_TRANSITION_EVENT_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("startup", "clean_fill_start"): ("CLEAN_FILL_STARTED", "Запуск наполнения чистой водой"),
    ("clean_fill_start", "clean_fill_check"): ("CLEAN_FILL_IN_PROGRESS", "Наполнение чистой водой"),
    ("clean_fill_check", "clean_fill_retry_stop"): ("CLEAN_FILL_SOURCE_EMPTY", "Источник чистой воды пуст, выполняется безопасная остановка и повтор"),
    ("clean_fill_check", "clean_fill_source_empty_stop"): ("CLEAN_FILL_SOURCE_EMPTY", "Наполнение остановлено: источник чистой воды пуст"),
    ("clean_fill_check", "clean_fill_stop_to_solution"): ("CLEAN_FILL_COMPLETED", "Чистая вода заполнена"),
    ("clean_fill_stop_to_solution", "solution_fill_start"): ("SOLUTION_FILL_STARTED", "Запуск наполнения раствором"),
    ("solution_fill_start", "solution_fill_check"): ("SOLUTION_FILL_IN_PROGRESS", "Наполнение раствором"),
    ("solution_fill_check", "solution_fill_check"): ("SOLUTION_FILL_CORRECTION", "Коррекция раствора при наполнении"),
    ("solution_fill_check", "solution_fill_source_empty_stop"): ("SOLUTION_FILL_SOURCE_EMPTY", "Наполнение раствором остановлено: источник чистой воды пуст"),
    ("solution_fill_check", "solution_fill_leak_stop"): ("SOLUTION_FILL_LEAK_DETECTED", "Наполнение раствором остановлено: нижний уровень раствора пропал"),
    ("solution_fill_check", "solution_fill_stop_to_prepare"): ("SOLUTION_FILL_COMPLETED", "Раствор заполнен"),
    ("solution_fill_stop_to_prepare", "prepare_recirculation_start"): ("RECIRC_STARTED", "Запуск рециркуляции"),
    ("prepare_recirculation_start", "prepare_recirculation_check"): ("RECIRC_IN_PROGRESS", "Рециркуляция"),
    ("prepare_recirculation_check", "prepare_recirculation_solution_low_stop"): ("RECIRCULATION_SOLUTION_LOW", "Рециркуляция остановлена по низкому уровню раствора"),
    ("prepare_recirculation_check", "prepare_recirculation_stop_to_ready"): ("RECIRC_COMPLETED", "Рециркуляция завершена"),
    ("prepare_recirculation_stop_to_ready", "complete_ready"): ("READY", "Готов к поливу"),
    ("prepare_recirculation_check", "complete_ready"): ("READY", "Готов к поливу"),
    ("complete_ready", "irrigation_start"): ("IRRIGATION_STARTED", "Запуск полива"),
    ("await_ready", "decision_gate"): ("IRRIGATION_READY", "Раствор готов для полива"),
    ("decision_gate", "completed_skip"): ("IRRIGATION_SKIPPED", "Полив пропущен по decision-controller"),
    ("decision_gate", "irrigation_start"): ("IRRIGATION_APPROVED", "Полив разрешён"),
    ("irrigation_start", "irrigation_check"): ("IRRIGATION_STARTED", "Полив"),
    ("irrigation_check", "irrigation_stop_to_recovery"): ("IRRIGATION_STOPPED", "Полив остановлен, запуск recovery"),
    ("irrigation_check", "irrigation_stop_to_ready"): ("IRRIGATION_STOPPED", "Полив завершён"),
    ("irrigation_check", "irrigation_stop_to_setup"): ("IRRIGATION_LOW_SOLUTION", "Остановка полива из-за низкого уровня раствора"),
    ("irrigation_recovery_start", "irrigation_recovery_check"): ("IRRIGATION_RECOVERY_STARTED", "Запуск recovery после полива"),
    ("irrigation_recovery_check", "irrigation_recovery_stop_to_ready"): ("IRRIGATION_RECOVERY_COMPLETED", "Recovery после полива завершён"),
}

_EC_CORRECTION_STEPS = frozenset({"corr_dose_ec", "corr_wait_ec"})
_PH_CORRECTION_STEPS = frozenset({"corr_dose_ph", "corr_wait_ph"})
_TIMELINE_NODE_EVENT_TYPES = (
    "LEVEL_SWITCH_CHANGED",
    "CLEAN_FILL_SOURCE_EMPTY",
    "CLEAN_FILL_COMPLETED",
    "SOLUTION_FILL_SOURCE_EMPTY",
    "SOLUTION_FILL_LEAK_DETECTED",
    "SOLUTION_FILL_COMPLETED",
    "SOLUTION_FILL_TIMEOUT",
    "PREPARE_RECIRCULATION_TIMEOUT",
    "RECIRCULATION_SOLUTION_LOW",
    "IRRIGATION_SOLUTION_LOW",
    "EMERGENCY_STOP_ACTIVATED",
)
_LEVEL_CHANNEL_LABELS = {
    "level_clean_min": "Нижний уровень чистой воды",
    "clean_level_min": "Нижний уровень чистой воды",
    "level_clean_max": "Верхний уровень чистой воды",
    "clean_level_max": "Верхний уровень чистой воды",
    "level_solution_min": "Нижний уровень раствора",
    "solution_level_min": "Нижний уровень раствора",
    "level_solution_max": "Верхний уровень раствора",
    "solution_level_max": "Верхний уровень раствора",
}
_NODE_EVENT_LABELS = {
    "CLEAN_FILL_SOURCE_EMPTY": "Событие ноды: источник чистой воды пуст",
    "CLEAN_FILL_COMPLETED": "Событие ноды: чистая вода заполнена",
    "SOLUTION_FILL_SOURCE_EMPTY": "Событие ноды: источник чистой воды пуст при наполнении раствором",
    "SOLUTION_FILL_LEAK_DETECTED": "Событие ноды: обнаружен провал нижнего уровня раствора",
    "SOLUTION_FILL_COMPLETED": "Событие ноды: раствор заполнен",
    "SOLUTION_FILL_TIMEOUT": "Событие ноды: таймаут наполнения раствора",
    "PREPARE_RECIRCULATION_TIMEOUT": "Событие ноды: таймаут подготовки рециркуляции",
    "RECIRCULATION_SOLUTION_LOW": "Событие ноды: рециркуляция остановлена по низкому уровню раствора",
    "IRRIGATION_SOLUTION_LOW": "Событие ноды: полив остановлен по низкому уровню раствора",
    "EMERGENCY_STOP_ACTIVATED": "Событие ноды: активирован аварийный стоп",
}
_IDLE_NODE_EVENT_LOOKBACK_SEC = 15 * 60


class GetZoneAutomationStateUseCase:
    """Возвращает полный payload зоны в формате AutomationState.

    Читает последнюю задачу, включая failed/completed, и маппит её в структуру,
    которую ожидает Laravel frontend. Дополняет ответ переходами между stage
    и живой телеметрией.
    """

    def __init__(
        self,
        *,
        task_repository: Any,
        workflow_repository: Any | None = None,
        fetch_fn: Callable | None = None,
        startup_reset_guard_use_case: Any | None = None,
    ) -> None:
        self._task_repository = task_repository
        self._fetch_fn = fetch_fn
        self._workflow_repository = workflow_repository
        self._startup_reset_guard_use_case = startup_reset_guard_use_case

    async def run(self, *, zone_id: int) -> dict[str, Any]:
        # Сначала пробуем активную задачу, затем последнюю terminal-задачу
        task: Optional[Any] = await self._task_repository.get_active_for_zone(zone_id=zone_id)
        workflow_state: Optional[Any] = None
        last_task: Optional[Any] = None
        solution_tank_guard = None
        if task is None and self._startup_reset_guard_use_case is not None:
            try:
                guard_result = await self._startup_reset_guard_use_case.run(zone_id=zone_id, now=self._now())
                solution_tank_guard = self._normalize_solution_tank_guard(
                    guard_result
                )
            except Exception:
                logger.warning(
                    "AE3 automation state: startup reset guard failed for zone_id=%s",
                    zone_id,
                    exc_info=True,
                )
        if task is None and self._workflow_repository is not None:
            try:
                workflow_state = await self._workflow_repository.get(zone_id=zone_id)
            except Exception:
                logger.warning(
                    "AE3 automation state: workflow read failed for zone_id=%s",
                    zone_id,
                    exc_info=True,
                )
                workflow_state = None
        if task is None:
            last_task = await self._task_repository.get_last_for_zone(zone_id=zone_id)

        # Подтянуть дополнительные данные; последовательного чтения здесь достаточно
        transitions: list[dict] = []
        if task is not None:
            try:
                transitions = await self._task_repository.get_transitions_for_task(task_id=task.id)
            except Exception:
                logger.warning(
                    "AE3 automation state: transition read failed for zone_id=%s task_id=%s",
                    zone_id,
                    getattr(task, "id", None),
                    exc_info=True,
                )

        telemetry, telemetry_fetch_ok = await self._fetch_zone_telemetry(zone_id=zone_id)
        if task is None and self._should_prefer_workflow_state(workflow_state) and not self._workflow_state_is_stale(
            workflow_state=workflow_state,
            last_task=last_task,
        ):
            built = await self._build_workflow_state(
                zone_id=zone_id,
                workflow_state=workflow_state,
                telemetry=telemetry,
                telemetry_fetch_ok=telemetry_fetch_ok,
                solution_tank_guard=solution_tank_guard,
            )
            return self._merge_last_failed_task_into_workflow_view(built, last_task)
        if task is None:
            task = last_task

        return await self._build_state(
            zone_id=zone_id,
            task=task,
            transitions=transitions,
            telemetry=telemetry,
            telemetry_fetch_ok=telemetry_fetch_ok,
            solution_tank_guard=solution_tank_guard,
        )

    async def _fetch_zone_telemetry(self, *, zone_id: int) -> tuple[dict[str, Any], bool]:
        """Читает ``telemetry_last`` для pH, EC и датчиков уровня этой зоны.

        Возвращает ``(levels_dict, ok)``, где ``ok`` равно ``False``, если SQL-чтение не удалось.
        """
        try:
            level_cfg = await load_zone_level_monitor_config(zone_id=zone_id, fetch_fn=self._fetch_fn)
            rows = await self._fetch_fn(
                """
                SELECT s.label, s.type, tl.last_value, tl.last_ts, tl.last_quality
                FROM sensors s
                JOIN telemetry_last tl ON tl.sensor_id = s.id
                WHERE s.zone_id = $1
                  AND s.is_active = TRUE
                  AND s.type IN ('PH', 'EC', 'WATER_LEVEL', 'WATER_LEVEL_SWITCH')
                ORDER BY s.type, s.label
                """,
                zone_id,
            )
        except Exception:
            logger.warning(
                "AE3 automation state: telemetry fetch failed for zone_id=%s",
                zone_id,
                exc_info=True,
            )
            return {}, False

        return summarize_zone_telemetry_rows(rows, config=level_cfg), True

    async def _fetch_recent_node_runtime_events(self, *, zone_id: int, since_ts: datetime | None) -> list[dict[str, Any]]:
        if self._fetch_fn is None:
            return []
        try:
            rows = await self._fetch_fn(
                """
                SELECT type, created_at, COALESCE(details, payload_json) AS payload
                FROM zone_events
                WHERE zone_id = $1
                  AND type = ANY($2::text[])
                  AND ($3::timestamp IS NULL OR created_at >= $3)
                ORDER BY created_at ASC, id ASC
                LIMIT 32
                """,
                zone_id,
                list(_TIMELINE_NODE_EVENT_TYPES),
                since_ts,
            )
        except Exception:
            logger.warning(
                "AE3 automation state: node runtime events fetch failed for zone_id=%s",
                zone_id,
                exc_info=True,
            )
            return []

        events: list[dict[str, Any]] = []
        for row in rows:
            event = self._build_node_runtime_timeline_event(row)
            if event is not None:
                events.append(event)
        return events

    def _build_node_runtime_timeline_event(self, row: Mapping[str, Any]) -> dict[str, Any] | None:
        event_type = str(row.get("type") or "").strip().upper()
        payload = row.get("payload")
        payload_map = payload if isinstance(payload, Mapping) else {}
        ts = row.get("created_at")

        if event_type == "LEVEL_SWITCH_CHANGED":
            channel = str(payload_map.get("channel") or "").strip().lower()
            state = payload_map.get("state")
            initial = payload_map.get("initial")
            channel_label = _LEVEL_CHANNEL_LABELS.get(channel, channel or "датчик уровня")
            normalized_state = state if isinstance(state, bool) else str(state).strip().lower() in {"1", "true", "yes", "on"}
            normalized_initial = initial if isinstance(initial, bool) else str(initial).strip().lower() in {"1", "true", "yes", "on"}
            state_label = "сработал" if normalized_state else "отпущен"
            prefix = "Начальное состояние ноды" if normalized_initial else "Сигнал датчика"
            label = f"{prefix}: {channel_label} {state_label}"
        else:
            label = _NODE_EVENT_LABELS.get(event_type, event_type)

        return {
            "event": event_type,
            "label": label,
            "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "active": False,
            "source": "node_event",
        }

    async def _build_timeline(
        self,
        *,
        zone_id: int,
        transitions: list[dict],
        since_ts: datetime | None,
    ) -> list[dict]:
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
                "source": "transition",
            })
        events.extend(await self._fetch_recent_node_runtime_events(zone_id=zone_id, since_ts=since_ts))
        events.sort(key=lambda item: str(item.get("timestamp") or ""))
        # Пометить последнее событие как активное
        if events:
            events[-1]["active"] = True
        return events

    def _primary_automation_state_label(
        self,
        *,
        workflow_phase: str,
        mapped_macro_state: str,
        current_stage: str,
        is_terminal_failed: bool,
    ) -> str:
        """Человекочитаемый заголовок для UI: не показывать «Раствор готов», если идёт подэтап полива."""
        cs_key = str(current_stage or "").strip().lower()

        if is_terminal_failed:
            stage_line = _STAGE_LABELS.get(cs_key)
            return f"{stage_line} — сбой" if stage_line else "Сбой автоматики"

        if workflow_phase == "idle" and cs_key == "startup":
            return "Инициализация"

        if mapped_macro_state == "READY" and cs_key and cs_key != "complete_ready":
            stage_line = _STAGE_LABELS.get(cs_key)
            if stage_line:
                return stage_line

        return _STATE_LABELS.get(mapped_macro_state, "Ожидание")

    def _merge_last_failed_task_into_workflow_view(self, payload: dict[str, Any], last_task: Optional[Any]) -> dict[str, Any]:
        """Снимок workflow в БД может оставаться ready, пока последняя ae_task уже failed — не маскируем сбой."""
        if last_task is None:
            return payload
        status = str(getattr(last_task, "status", "") or "").strip().lower()
        if status != "failed":
            return payload

        details = dict(payload.get("state_details") or {})
        details["failed"] = True
        details["error_code"] = getattr(last_task, "error_code", None)
        details["error_message"] = getattr(last_task, "error_message", None)
        payload["state_details"] = details

        wf = getattr(last_task, "workflow", None)
        failed_stage = str(getattr(wf, "current_stage", "") or "").strip() if wf is not None else ""
        wf_phase = (
            str(getattr(wf, "workflow_phase", "") or "").strip().lower()
            if wf is not None
            else str(payload.get("workflow_phase") or "").strip().lower()
        )

        payload["state_label"] = self._primary_automation_state_label(
            workflow_phase=wf_phase,
            mapped_macro_state=str(payload.get("state") or "IDLE"),
            current_stage=failed_stage,
            is_terminal_failed=True,
        )
        return payload

    async def _build_state(
        self,
        *,
        zone_id: int,
        task: Optional[Any],
        transitions: list[dict],
        telemetry: dict[str, Any],
        telemetry_fetch_ok: bool = True,
        solution_tank_guard: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if task is None:
            return await self._idle_state(
                zone_id=zone_id,
                telemetry_fetch_ok=telemetry_fetch_ok,
                solution_tank_guard=solution_tank_guard,
            )

        status = str(getattr(task, "status", "") or "").strip().lower()
        wf = getattr(task, "workflow", None)
        workflow_phase = str(getattr(wf, "workflow_phase", None) or "idle").strip().lower()
        current_stage = getattr(wf, "current_stage", None)
        error_code = getattr(task, "error_code", None)
        error_message = getattr(task, "error_message", None)

        is_failed = status == "failed"
        is_active = status in ("pending", "claimed", "running", "waiting_command")

        mapped_macro = _WORKFLOW_PHASE_TO_STATE.get(workflow_phase, "IDLE")
        state = "IDLE" if is_failed else mapped_macro

        timeline = await self._build_timeline(
            zone_id=zone_id,
            transitions=transitions,
            since_ts=self._timeline_since(task=task),
        )
        active_processes = self._build_active_processes(
            workflow_phase=workflow_phase,
            is_active=is_active,
            correction=getattr(task, "correction", None),
        )

        return {
            "zone_id": zone_id,
            "state": state,
            "state_label": self._primary_automation_state_label(
                workflow_phase=workflow_phase,
                mapped_macro_state=mapped_macro,
                current_stage=str(current_stage) if current_stage is not None else "",
                is_terminal_failed=is_failed,
            ),
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
                "clean_tank_level_percent": telemetry.get(
                    "clean_tank_level_percent",
                    coarse_clean_tank_level_percent(clean_max_triggered=False) or 0,
                ),
                "nutrient_tank_level_percent": telemetry.get(
                    "nutrient_tank_level_percent",
                    coarse_solution_tank_level_percent(
                        solution_max_triggered=False,
                        solution_min_triggered=False,
                    )
                    or 0,
                ),
                "buffer_tank_level_percent": None,
                "ph": telemetry.get("ph"),
                "ec": telemetry.get("ec"),
            },
            "active_processes": active_processes,
            "timeline": timeline,
            "next_state": None,
            "estimated_completion_sec": None,
            "irr_node_state": None,
            "solution_tank_guard": solution_tank_guard,
            "decision": self._build_decision(task),
            "telemetry_fetch_ok": telemetry_fetch_ok,
        }

    async def _build_workflow_state(
        self,
        *,
        zone_id: int,
        workflow_state: Any,
        telemetry: dict[str, Any],
        telemetry_fetch_ok: bool = True,
        solution_tank_guard: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        workflow_phase = str(getattr(workflow_state, "workflow_phase", None) or "idle").strip().lower()
        payload = getattr(workflow_state, "payload", None)
        normalized_payload = payload if isinstance(payload, Mapping) else {}
        current_stage = str(normalized_payload.get("ae3_cycle_start_stage") or "").strip() or None
        workflow_guard = self._solution_tank_guard_from_payload(normalized_payload)
        if solution_tank_guard is None:
            solution_tank_guard = workflow_guard
        elif workflow_guard is not None:
            solution_tank_guard = {
                **workflow_guard,
                **{k: v for k, v in solution_tank_guard.items() if v is not None},
            }
        state = _WORKFLOW_PHASE_TO_STATE.get(workflow_phase, "IDLE")
        state_label = self._primary_automation_state_label(
            workflow_phase=workflow_phase,
            mapped_macro_state=state,
            current_stage=str(current_stage or ""),
            is_terminal_failed=False,
        )
        timeline = await self._build_timeline(
            zone_id=zone_id,
            transitions=[],
            since_ts=self._timeline_since_workflow(workflow_state=workflow_state),
        )

        return {
            "zone_id": zone_id,
            "state": state,
            "state_label": state_label,
            "state_details": {
                "started_at": getattr(workflow_state, "started_at", None),
                "elapsed_sec": 0,
                "progress_percent": 0,
                "failed": False,
                "error_code": None,
                "error_message": None,
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
                "clean_tank_level_percent": telemetry.get(
                    "clean_tank_level_percent",
                    coarse_clean_tank_level_percent(clean_max_triggered=False) or 0,
                ),
                "nutrient_tank_level_percent": telemetry.get(
                    "nutrient_tank_level_percent",
                    coarse_solution_tank_level_percent(
                        solution_max_triggered=False,
                        solution_min_triggered=False,
                    )
                    or 0,
                ),
                "buffer_tank_level_percent": None,
                "ph": telemetry.get("ph"),
                "ec": telemetry.get("ec"),
            },
            "active_processes": {
                "pump_in": workflow_phase == "tank_filling",
                "circulation_pump": workflow_phase == "tank_recirc",
                "ph_correction": False,
                "ec_correction": False,
            },
            "timeline": timeline,
            "next_state": None,
            "estimated_completion_sec": None,
            "irr_node_state": None,
            "solution_tank_guard": solution_tank_guard,
            "decision": None,
            "telemetry_fetch_ok": telemetry_fetch_ok,
        }

    async def _idle_state(
        self,
        *,
        zone_id: int,
        telemetry_fetch_ok: bool = True,
        solution_tank_guard: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        timeline = await self._build_timeline(
            zone_id=zone_id,
            transitions=[],
            since_ts=self._idle_timeline_since(),
        )
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
            "timeline": timeline,
            "next_state": None,
            "estimated_completion_sec": None,
            "irr_node_state": None,
            "solution_tank_guard": solution_tank_guard,
            "decision": None,
            "telemetry_fetch_ok": telemetry_fetch_ok,
        }

    def _build_active_processes(
        self,
        *,
        workflow_phase: str,
        is_active: bool,
        correction: Any | None,
    ) -> dict[str, bool]:
        corr_step = str(getattr(correction, "corr_step", "") or "").strip().lower()
        return {
            "pump_in": is_active and workflow_phase == "tank_filling",
            "circulation_pump": is_active and workflow_phase == "tank_recirc",
            "ph_correction": is_active and corr_step in _PH_CORRECTION_STEPS,
            "ec_correction": is_active and corr_step in _EC_CORRECTION_STEPS,
        }

    def _should_prefer_workflow_state(self, workflow_state: Optional[Any]) -> bool:
        if workflow_state is None:
            return False
        workflow_phase = str(getattr(workflow_state, "workflow_phase", None) or "idle").strip().lower()
        payload = getattr(workflow_state, "payload", None)
        normalized_payload = payload if isinstance(payload, Mapping) else {}
        current_stage = str(normalized_payload.get("ae3_cycle_start_stage") or "").strip().lower()
        return workflow_phase in {"tank_filling", "tank_recirc", "ready", "irrigating", "irrig_recirc"} or current_stage == "startup"

    def _workflow_state_is_stale(self, *, workflow_state: Optional[Any], last_task: Optional[Any]) -> bool:
        if workflow_state is None or last_task is None:
            return False
        if bool(getattr(last_task, "is_active", False)):
            return False

        scheduler_task_id = str(getattr(workflow_state, "scheduler_task_id", "") or "").strip()
        if scheduler_task_id and scheduler_task_id == str(getattr(last_task, "id", "") or ""):
            return True

        workflow_updated_at = getattr(workflow_state, "updated_at", None)
        task_updated_at = getattr(last_task, "updated_at", None)
        if workflow_updated_at is None or task_updated_at is None:
            return False

        workflow_cmp = self._normalize_utc_naive(workflow_updated_at)
        task_cmp = self._normalize_utc_naive(task_updated_at)
        return task_cmp >= workflow_cmp

    def _timeline_since(self, *, task: Any | None) -> datetime | None:
        if task is None:
            return None
        for field_name in ("created_at", "updated_at"):
            value = getattr(task, field_name, None)
            if isinstance(value, datetime):
                return self._normalize_utc_naive(value)
        workflow = getattr(task, "workflow", None)
        entered = getattr(workflow, "stage_entered_at", None)
        if isinstance(entered, datetime):
            return self._normalize_utc_naive(entered)
        return None

    def _timeline_since_workflow(self, *, workflow_state: Any | None) -> datetime | None:
        if workflow_state is None:
            return self._idle_timeline_since()
        for field_name in ("updated_at", "started_at"):
            value = getattr(workflow_state, field_name, None)
            if isinstance(value, datetime):
                return self._normalize_utc_naive(value)
        return self._idle_timeline_since()

    def _idle_timeline_since(self) -> datetime:
        return self._now() - timedelta(seconds=_IDLE_NODE_EVENT_LOOKBACK_SEC)

    def _now(self) -> Any:
        from common.utils.time import utcnow_naive

        return utcnow_naive()

    def _normalize_utc_naive(self, value: Any) -> Any:
        if not isinstance(value, datetime):
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value

    def _normalize_solution_tank_guard(self, guard_result: Any) -> dict[str, Any] | None:
        if not isinstance(guard_result, Mapping):
            return None
        level = guard_result.get("level")
        normalized_level = level if isinstance(level, Mapping) else {}
        sensor_label = (
            guard_result.get("sensor_label")
            or normalized_level.get("sensor_label")
            or guard_result.get("guard_sensor_label")
        )
        sample_ts = (
            guard_result.get("sample_ts")
            or normalized_level.get("sample_ts")
            or guard_result.get("guard_sample_ts")
        )
        normalized_sample_ts = sample_ts.isoformat() if hasattr(sample_ts, "isoformat") else sample_ts
        return {
            "checked": True,
            "reset": bool(guard_result.get("reset")),
            "reason": guard_result.get("reason"),
            "sensor_label": sensor_label,
            "sample_ts": normalized_sample_ts,
        }

    def _solution_tank_guard_from_payload(self, payload: Mapping[str, Any]) -> dict[str, Any] | None:
        reason = payload.get("guard_reason")
        sensor_label = payload.get("guard_sensor_label")
        sample_ts = payload.get("guard_sample_ts")
        if reason is None and sensor_label is None and sample_ts is None:
            return None
        return {
            "checked": True,
            "reset": True,
            "reason": reason,
            "sensor_label": sensor_label,
            "sample_ts": sample_ts,
        }

    def _build_decision(self, task: Any) -> dict[str, Any] | None:
        outcome = getattr(task, "irrigation_decision_outcome", None)
        reason_code = getattr(task, "irrigation_decision_reason_code", None)
        strategy = getattr(task, "irrigation_decision_strategy", None)
        config = getattr(task, "irrigation_decision_config", None)
        bundle_revision = getattr(task, "irrigation_bundle_revision", None)
        degraded = getattr(task, "irrigation_decision_degraded", None)

        if outcome is None and reason_code is None and strategy is None and config is None and bundle_revision is None and degraded is None:
            return None

        return {
            "outcome": str(outcome).strip().lower() if outcome is not None else None,
            "reason_code": str(reason_code).strip() if reason_code is not None else None,
            "strategy": str(strategy).strip().lower() if strategy is not None else None,
            "config": dict(config) if isinstance(config, Mapping) else None,
            "bundle_revision": str(bundle_revision).strip() if bundle_revision is not None else None,
            "degraded": bool(degraded) if degraded is not None else None,
        }

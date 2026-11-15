"""Shared records and immutable policy values for GetZoneAutomationStateUseCase."""

from __future__ import annotations

import logging

logger = logging.getLogger('ae3lite.application.use_cases.get_zone_automation_state')

_WORKFLOW_PHASE_TO_STATE: dict[str, str] = {
    "tank_filling": "TANK_FILLING",
    "tank_recirc": "TANK_RECIRC",
    "ready": "READY",
    "irrigating": "IRRIGATING",
    # Legacy DB rows only — post-irrigation chemistry phase removed from topology.
    "irrig_recirc": "IRRIG_RECIRC",
    "error": "IDLE",
}

_STATE_LABELS: dict[str, str] = {
    "TANK_FILLING": "Наполнение баков",
    "TANK_RECIRC": "Рециркуляция раствора",
    "READY": "Раствор готов",
    "IRRIGATING": "Полив",
    "IRRIG_RECIRC": "Рециркуляция после полива (deprecated)",
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
    "prepare_recirculation_solution_low_stop": "Остановка рециркуляции: раствор закончился → подготовка",
    "complete_ready": "Готов к поливу",
    "await_ready": "Ожидание готового раствора",
    "decision_gate": "Принятие решения о поливе",
    "irrigation_start": "Запуск полива",
    "irrigation_check": "Полив",
    # Deprecated recovery stages (removed from topology; kept for historical timeline labels).
    "irrigation_recovery_start": "Запуск рециркуляции после полива (deprecated)",
    "irrigation_recovery_check": "Рециркуляция после полива (deprecated)",
    "completed_run": "Полив завершён",
    "completed_skip": "Полив пропущен",
    "apply": "Свет (scheduler tick)",
}

_TRANSITION_EVENT_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("startup", "clean_fill_start"): ("CLEAN_FILL_STARTED", "Запуск наполнения чистой водой"),
    ("clean_fill_start", "clean_fill_check"): ("CLEAN_FILL_IN_PROGRESS", "Наполнение чистой водой"),
    ("clean_fill_check", "clean_fill_retry_stop"): (
        "CLEAN_FILL_SOURCE_EMPTY",
        "Источник чистой воды пуст, выполняется безопасная остановка и повтор",
    ),
    ("clean_fill_check", "clean_fill_source_empty_stop"): (
        "CLEAN_FILL_SOURCE_EMPTY",
        "Наполнение остановлено: источник чистой воды пуст",
    ),
    ("clean_fill_check", "clean_fill_stop_to_solution"): ("CLEAN_FILL_COMPLETED", "Чистая вода заполнена"),
    ("clean_fill_stop_to_solution", "solution_fill_start"): ("SOLUTION_FILL_STARTED", "Запуск наполнения раствором"),
    ("solution_fill_start", "solution_fill_check"): ("SOLUTION_FILL_IN_PROGRESS", "Наполнение раствором"),
    ("solution_fill_check", "solution_fill_check"): ("SOLUTION_FILL_CORRECTION", "Коррекция раствора при наполнении"),
    ("solution_fill_check", "solution_fill_source_empty_stop"): (
        "SOLUTION_FILL_SOURCE_EMPTY",
        "Наполнение раствором остановлено: источник чистой воды пуст",
    ),
    ("solution_fill_check", "solution_fill_leak_stop"): (
        "SOLUTION_FILL_LEAK_DETECTED",
        "Наполнение раствором остановлено: нижний уровень раствора пропал",
    ),
    ("solution_fill_check", "solution_fill_stop_to_prepare"): ("SOLUTION_FILL_COMPLETED", "Раствор заполнен"),
    ("solution_fill_stop_to_prepare", "prepare_recirculation_start"): ("RECIRC_STARTED", "Запуск рециркуляции"),
    ("prepare_recirculation_start", "prepare_recirculation_check"): ("RECIRC_IN_PROGRESS", "Рециркуляция"),
    ("prepare_recirculation_check", "prepare_recirculation_solution_low_stop"): (
        "RECIRCULATION_SOLUTION_LOW",
        "Рециркуляция остановлена: раствор закончился",
    ),
    ("prepare_recirculation_solution_low_stop", "startup"): (
        "RECIRCULATION_SOLUTION_LOW_TO_SETUP",
        "Переход к обычной подготовке раствора",
    ),
    ("prepare_recirculation_check", "prepare_recirculation_stop_to_ready"): (
        "RECIRC_COMPLETED",
        "Рециркуляция завершена",
    ),
    ("prepare_recirculation_stop_to_ready", "complete_ready"): ("READY", "Готов к поливу"),
    ("prepare_recirculation_check", "complete_ready"): ("READY", "Готов к поливу"),
    ("complete_ready", "irrigation_start"): ("IRRIGATION_STARTED", "Запуск полива"),
    ("await_ready", "decision_gate"): ("IRRIGATION_READY", "Раствор готов для полива"),
    ("decision_gate", "completed_skip"): ("IRRIGATION_SKIPPED", "Полив пропущен по decision-controller"),
    ("decision_gate", "irrigation_start"): ("IRRIGATION_APPROVED", "Полив разрешён"),
    ("irrigation_start", "irrigation_check"): ("IRRIGATION_STARTED", "Полив"),
    ("irrigation_check", "irrigation_stop_to_ready"): ("IRRIGATION_STOPPED", "Полив завершён"),
    ("irrigation_check", "irrigation_stop_to_setup"): (
        "IRRIGATION_LOW_SOLUTION",
        "Остановка полива из-за низкого уровня раствора",
    ),
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

_CYCLE_START_STAGE_ORDER: tuple[str, ...] = (
    "startup",
    "clean_fill_start",
    "clean_fill_check",
    "clean_fill_stop_to_solution",
    "solution_fill_start",
    "solution_fill_check",
    "solution_fill_stop_to_prepare",
    "prepare_recirculation_start",
    "prepare_recirculation_check",
    "complete_ready",
    "await_ready",
    "decision_gate",
    "irrigation_start",
    "irrigation_check",
    "completed_run",
)

_WORKFLOW_PHASE_PROGRESS: dict[str, int] = {
    "tank_filling": 20,
    "tank_recirc": 45,
    "ready": 65,
    "irrigating": 85,
    # Legacy DB rows only — not a live topology phase.
    "irrig_recirc": 95,
}

_IRRIGATION_STAGE_PREFIX = "irrigation_"

_TERMINAL_COMPLETED_STAGES = frozenset(
    {
        "completed_run",
        "completed_skip",
        "complete_ready",
    }
)

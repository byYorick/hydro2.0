"""Constants for automation state/timeline API payloads."""

from __future__ import annotations

from typing import Dict, Optional

AUTOMATION_STATE_IDLE = "IDLE"
AUTOMATION_STATE_TANK_FILLING = "TANK_FILLING"
AUTOMATION_STATE_TANK_RECIRC = "TANK_RECIRC"
AUTOMATION_STATE_READY = "READY"
AUTOMATION_STATE_IRRIGATING = "IRRIGATING"
AUTOMATION_STATE_IRRIG_RECIRC = "IRRIG_RECIRC"

AUTOMATION_STATE_LABELS: Dict[str, str] = {
    AUTOMATION_STATE_IDLE: "Система в ожидании",
    AUTOMATION_STATE_TANK_FILLING: "Набор бака с раствором",
    AUTOMATION_STATE_TANK_RECIRC: "Рециркуляция бака",
    AUTOMATION_STATE_READY: "Раствор готов к поливу",
    AUTOMATION_STATE_IRRIGATING: "Полив",
    AUTOMATION_STATE_IRRIG_RECIRC: "Рециркуляция после полива",
}

AUTOMATION_STATE_NEXT: Dict[str, Optional[str]] = {
    AUTOMATION_STATE_IDLE: AUTOMATION_STATE_TANK_FILLING,
    AUTOMATION_STATE_TANK_FILLING: AUTOMATION_STATE_TANK_RECIRC,
    AUTOMATION_STATE_TANK_RECIRC: AUTOMATION_STATE_READY,
    AUTOMATION_STATE_READY: AUTOMATION_STATE_IRRIGATING,
    AUTOMATION_STATE_IRRIGATING: AUTOMATION_STATE_IRRIG_RECIRC,
    AUTOMATION_STATE_IRRIG_RECIRC: AUTOMATION_STATE_IDLE,
}

AUTOMATION_TIMELINE_EVENT_LABELS: Dict[str, str] = {
    "SCHEDULE_TASK_ACCEPTED": "Scheduler: задача принята",
    "SCHEDULE_TASK_COMPLETED": "Scheduler: задача завершена",
    "SCHEDULE_TASK_FAILED": "Scheduler: задача с ошибкой",
    "TASK_RECEIVED": "Automation-engine: задача получена",
    "TASK_STARTED": "Automation-engine: выполнение начато",
    "DECISION_MADE": "Automation-engine: принято решение",
    "COMMAND_DISPATCHED": "Отправлена команда узлу",
    "COMMAND_FAILED": "Ошибка отправки команды",
    "TASK_FINISHED": "Automation-engine: выполнение завершено",
    "CLEAN_FILL_COMPLETED": "Бак чистой воды заполнен",
    "SOLUTION_FILL_COMPLETED": "Бак рабочего раствора заполнен",
    "CLEAN_FILL_RETRY_STARTED": "Запущен повторный цикл clean-fill",
    "PREPARE_TARGETS_REACHED": "Целевые pH/EC достигнуты",
    "TWO_TANK_STARTUP_INITIATED": "Запущен старт 2-баковой схемы",
    "SCHEDULE_TASK_EXECUTION_STARTED": "Старт исполнения scheduler-task",
    "SCHEDULE_TASK_EXECUTION_FINISHED": "Финиш исполнения scheduler-task",
    "AUTOMATION_CONTROL_MODE_UPDATED": "Режим управления автоматикой обновлён",
    "MANUAL_STEP_ACCEPTED": "Ручной шаг принят",
    "MANUAL_STEP_REQUESTED": "Ручной шаг запрошен",
    "MANUAL_STEP_EXECUTED": "Ручной шаг выполнен",
}


__all__ = [
    "AUTOMATION_STATE_IDLE",
    "AUTOMATION_STATE_IRRIGATING",
    "AUTOMATION_STATE_IRRIG_RECIRC",
    "AUTOMATION_STATE_LABELS",
    "AUTOMATION_STATE_NEXT",
    "AUTOMATION_STATE_READY",
    "AUTOMATION_STATE_TANK_FILLING",
    "AUTOMATION_STATE_TANK_RECIRC",
    "AUTOMATION_TIMELINE_EVENT_LABELS",
]

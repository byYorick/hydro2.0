"""Какая гидравлическая система владеет стадией графа two_tank.

Исполнитель один. Модули не вызывают друг друга: переход между ними
делает только он. Коррекция — вложенная машина, своих стадий в графе нет.
"""

from __future__ import annotations

SOLUTION = "solution"
IRRIGATION = "irrigation"
CORRECTION = "correction"
EXECUTOR = "executor"

SOLUTION_STAGES: frozenset[str] = frozenset(
    {
        "startup",
        "await_operator_drain_confirm",
        "solution_drain_start",
        "solution_drain_check",
        "solution_drain_stop_to_clean_fill",
        "solution_drain_timeout_stop",
        "solution_fill_stop_to_refill_confirm",
        "await_operator_refill_confirm",
        "solution_change_operator_timeout_stop",
        "solution_change_abort_stop",
        "clean_fill_start",
        "clean_fill_check",
        "clean_fill_stop_to_solution",
        "clean_fill_retry_stop",
        "clean_fill_source_empty_stop",
        "clean_fill_timeout_stop",
        "solution_fill_start",
        "solution_fill_check",
        "solution_fill_stop_to_ready",
        "solution_fill_stop_to_prepare",
        "solution_fill_source_empty_stop",
        "solution_fill_leak_stop",
        "solution_fill_timeout_stop",
        "prepare_recirculation_start",
        "prepare_recirculation_check",
        "prepare_recirculation_window_exhausted",
        "prepare_recirculation_stop_to_ready",
        "prepare_recirculation_solution_low_stop",
        "solution_topup_guard",
        "solution_topup_start",
        "solution_topup_check",
        "solution_topup_stop",
        "solution_topup_complete",
        "solution_topup_source_empty_stop",
        "solution_topup_leak_stop",
        "solution_topup_timeout_stop",
        "complete_ready",
    }
)

IRRIGATION_STAGES: frozenset[str] = frozenset(
    {
        "await_ready",
        "decision_gate",
        "irrigation_start",
        "irrigation_check",
        "irrigation_pump_stop",
        "irrigation_stop_to_ready",
        "irrigation_stop_to_setup",
        "completed_run",
        "completed_skip",
    }
)

# Пауза потока — политика исполнителя, не отдельная установка.
EXECUTOR_STAGES: frozenset[str] = frozenset({"manual_hold"})

CORRECTION_HOST_STAGES: frozenset[str] = frozenset(
    {
        "solution_fill_check",
        "prepare_recirculation_check",
        "irrigation_check",
    }
)

_STAGE_SYSTEM: dict[str, str] = {
    **{name: SOLUTION for name in SOLUTION_STAGES},
    **{name: IRRIGATION for name in IRRIGATION_STAGES},
    **{name: EXECUTOR for name in EXECUTOR_STAGES},
}


def system_for_stage(stage: str) -> str | None:
    return _STAGE_SYSTEM.get(stage)

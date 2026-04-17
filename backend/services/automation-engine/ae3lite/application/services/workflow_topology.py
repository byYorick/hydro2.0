"""Canonical workflow topology graph for AE3 runtime routing/recovery.

Каждая topology, например ``two_tank_drip_substrate_trays``, задаёт
отображение имени stage в :class:`StageDef`. :class:`TopologyRegistry`
предоставляет lookup по ``(topology, stage_name)`` и проверку целостности графа.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


# ---------------------------------------------------------------------------
# StageDef
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StageDef:
    """Декларативное описание одного stage внутри workflow-topology.

    Атрибуты:
        name: Уникальный идентификатор stage, например ``"clean_fill_start"``.
        handler: Ключ handler-класса, который :class:`WorkflowRouter` использует для dispatch.
        workflow_phase: Фаза зоны, которую видят внешние наблюдатели.
        command_plans: Кортеж имён plan-ключей, выполняемых ``CommandHandler``.
        next_stage: Статический stage-приёмник после успешного выполнения команды.
        terminal_error: ``(error_code, error_message)``; если задан, stage терминально падает.
        timeout_key: Ключ runtime-конфига для вычисления ``stage_deadline_at``.
        has_correction: Может ли этот check-stage запускать цикл коррекции.
        on_corr_success: Stage перехода при успешной коррекции.
        on_corr_fail: Stage перехода при неуспешной коррекции.
    """

    name: str
    handler: str
    workflow_phase: str = "idle"

    # Командные stage
    command_plans: Tuple[str, ...] = ()
    next_stage: Optional[str] = None

    # Терминальная ошибка
    terminal_error: Optional[Tuple[str, str]] = None

    # Проверочные stage
    timeout_key: Optional[str] = None
    has_correction: bool = False
    on_corr_success: Optional[str] = None
    on_corr_fail: Optional[str] = None


# ---------------------------------------------------------------------------
# Topology two-tank drip substrate trays (полный граф)
# ---------------------------------------------------------------------------

TWO_TANK: Mapping[str, StageDef] = {
    # === Startup ===
    "startup": StageDef("startup", "startup"),

    # === Clean fill path ===
    "clean_fill_start": StageDef(
        "clean_fill_start", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_start",),
        next_stage="clean_fill_check",
    ),
    "clean_fill_check": StageDef(
        "clean_fill_check", "clean_fill",
        workflow_phase="tank_filling",
        timeout_key="clean_fill_timeout_sec",
    ),
    "clean_fill_stop_to_solution": StageDef(
        "clean_fill_stop_to_solution", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_stop",),
        next_stage="solution_fill_start",
    ),
    "clean_fill_retry_stop": StageDef(
        "clean_fill_retry_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_stop",),
        next_stage="clean_fill_start",
    ),
    "clean_fill_source_empty_stop": StageDef(
        "clean_fill_source_empty_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_stop",),
        terminal_error=(
            "clean_fill_source_empty",
            "Source tank became empty during clean fill",
        ),
    ),
    "clean_fill_timeout_stop": StageDef(
        "clean_fill_timeout_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_stop",),
        terminal_error=(
            "clean_tank_not_filled_timeout",
            "Clean fill timeout exceeded",
        ),
    ),

    # === Solution fill path ===
    "solution_fill_start": StageDef(
        "solution_fill_start", "command",
        workflow_phase="tank_filling",
        command_plans=("sensor_mode_activate", "solution_fill_start"),
        next_stage="solution_fill_check",
    ),
    "solution_fill_check": StageDef(
        "solution_fill_check", "solution_fill",
        workflow_phase="tank_filling",
        timeout_key="solution_fill_timeout_sec",
        has_correction=True,
        on_corr_success="solution_fill_check",
        on_corr_fail="solution_fill_check",
    ),
    "solution_fill_stop_to_ready": StageDef(
        "solution_fill_stop_to_ready", "command",
        workflow_phase="ready",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        next_stage="complete_ready",
    ),
    "solution_fill_stop_to_prepare": StageDef(
        "solution_fill_stop_to_prepare", "command",
        workflow_phase="tank_recirc",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        next_stage="prepare_recirculation_start",
    ),
    "solution_fill_source_empty_stop": StageDef(
        "solution_fill_source_empty_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        terminal_error=(
            "solution_fill_source_empty",
            "Clean source became empty during solution fill",
        ),
    ),
    "solution_fill_leak_stop": StageDef(
        "solution_fill_leak_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        terminal_error=(
            "solution_fill_leak_detected",
            "Solution minimum level dropped during solution fill",
        ),
    ),
    "solution_fill_timeout_stop": StageDef(
        "solution_fill_timeout_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        terminal_error=(
            "solution_tank_not_filled_timeout",
            "Solution fill timeout exceeded",
        ),
    ),

    # === Prepare recirculation path ===
    "prepare_recirculation_start": StageDef(
        "prepare_recirculation_start", "command",
        workflow_phase="tank_recirc",
        command_plans=("sensor_mode_activate", "prepare_recirculation_start"),
        next_stage="prepare_recirculation_check",
    ),
    "prepare_recirculation_check": StageDef(
        "prepare_recirculation_check", "prepare_recirc",
        workflow_phase="tank_recirc",
        timeout_key="prepare_recirculation_timeout_sec",
        has_correction=True,
        on_corr_success="prepare_recirculation_stop_to_ready",
        on_corr_fail="prepare_recirculation_window_exhausted",
    ),
    "prepare_recirculation_window_exhausted": StageDef(
        "prepare_recirculation_window_exhausted", "prepare_recirc_window",
        workflow_phase="tank_recirc",
    ),
    "prepare_recirculation_stop_to_ready": StageDef(
        "prepare_recirculation_stop_to_ready", "command",
        workflow_phase="ready",
        command_plans=("prepare_recirculation_stop", "sensor_mode_deactivate"),
        next_stage="complete_ready",
    ),
    "prepare_recirculation_solution_low_stop": StageDef(
        "prepare_recirculation_solution_low_stop", "command",
        workflow_phase="tank_recirc",
        command_plans=("prepare_recirculation_stop", "sensor_mode_deactivate"),
        terminal_error=(
            "recirculation_solution_low",
            "Solution minimum level dropped during prepare recirculation",
        ),
    ),
    # === Irrigation path ===
    "await_ready": StageDef("await_ready", "await_ready", workflow_phase="ready"),
    "decision_gate": StageDef("decision_gate", "decision_gate", workflow_phase="ready"),
    "irrigation_start": StageDef(
        "irrigation_start", "command",
        workflow_phase="irrigating",
        command_plans=("sensor_mode_activate", "irrigation_start"),
        next_stage="irrigation_check",
    ),
    "irrigation_check": StageDef(
        "irrigation_check", "irrigation_check",
        workflow_phase="irrigating",
        has_correction=True,
        on_corr_success="irrigation_check",
        on_corr_fail="irrigation_check",
    ),
    "irrigation_stop_to_ready": StageDef(
        "irrigation_stop_to_ready", "command",
        workflow_phase="ready",
        command_plans=("irrigation_stop", "sensor_mode_deactivate"),
        next_stage="completed_run",
    ),
    "irrigation_stop_to_recovery": StageDef(
        "irrigation_stop_to_recovery", "command",
        workflow_phase="irrig_recirc",
        command_plans=("irrigation_stop", "sensor_mode_deactivate"),
        next_stage="irrigation_recovery_start",
    ),
    "irrigation_stop_to_setup": StageDef(
        "irrigation_stop_to_setup", "command",
        workflow_phase="tank_filling",
        command_plans=("irrigation_stop", "sensor_mode_deactivate"),
        next_stage="startup",
    ),
    "irrigation_recovery_start": StageDef(
        "irrigation_recovery_start", "command",
        workflow_phase="irrig_recirc",
        command_plans=("sensor_mode_activate", "irrigation_recovery_start"),
        next_stage="irrigation_recovery_check",
    ),
    "irrigation_recovery_check": StageDef(
        "irrigation_recovery_check", "irrigation_recovery",
        workflow_phase="irrig_recirc",
        timeout_key="prepare_recirculation_timeout_sec",
        has_correction=True,
        on_corr_success="irrigation_recovery_stop_to_ready",
        on_corr_fail="irrigation_recovery_stop_failed",
    ),
    "irrigation_recovery_stop_to_ready": StageDef(
        "irrigation_recovery_stop_to_ready", "command",
        workflow_phase="ready",
        command_plans=("irrigation_recovery_stop", "sensor_mode_deactivate"),
        next_stage="completed_run",
    ),
    "irrigation_recovery_stop_failed": StageDef(
        "irrigation_recovery_stop_failed", "command",
        workflow_phase="irrig_recirc",
        command_plans=("irrigation_recovery_stop", "sensor_mode_deactivate"),
        terminal_error=(
            "irrigation_recovery_targets_not_restored",
            "Irrigation recovery correction failed to restore targets",
        ),
    ),
    # === Terminal ===
    "complete_ready": StageDef("complete_ready", "ready", workflow_phase="ready"),
    "completed_run": StageDef("completed_run", "ready", workflow_phase="ready"),
    "completed_skip": StageDef("completed_skip", "ready", workflow_phase="ready"),
}


# ---------------------------------------------------------------------------
# Topology generic_cycle_start (simple single-batch diagnostics)
# ---------------------------------------------------------------------------

GENERIC_CYCLE_START: Mapping[str, StageDef] = {
    # startup: единственный stage для simple single-batch workflow.
    # При DONE команды startup recovery завершает задачу (нет next_stage/terminal_error).
    "startup": StageDef("startup", "command", workflow_phase="idle"),
}


# ---------------------------------------------------------------------------
# Реестр
# ---------------------------------------------------------------------------

# Каноническое имя topology → граф stage
_TOPOLOGIES: Mapping[str, Mapping[str, StageDef]] = {
    "two_tank_drip_substrate_trays": TWO_TANK,
    "two_tank": TWO_TANK,  # short alias used in legacy intents
    "generic_cycle_start": GENERIC_CYCLE_START,
}


class TopologyRegistry:
    """Сервис lookup для описаний stage внутри topology."""

    def __init__(
        self,
        topologies: Mapping[str, Mapping[str, StageDef]] | None = None,
    ) -> None:
        self._topologies = dict(topologies or _TOPOLOGIES)

    def get(self, topology: str, stage: str) -> StageDef:
        """Возвращает :class:`StageDef` для пары *topology* / *stage*.

        Выбрасывает :class:`KeyError`, если topology или stage неизвестны.
        """
        topo = self._topologies.get(topology)
        if topo is None:
            raise KeyError(f"Неизвестная topology: {topology!r}")
        stage_def = topo.get(stage)
        if stage_def is None:
            raise KeyError(
                f"Неизвестный stage {stage!r} в topology {topology!r}"
            )
        return stage_def

    def stages(self, topology: str) -> Mapping[str, StageDef]:
        """Возвращает полный граф stage для *topology*."""
        topo = self._topologies.get(topology)
        if topo is None:
            raise KeyError(f"Неизвестная topology: {topology!r}")
        return topo

    def has_topology(self, topology: str) -> bool:
        return topology in self._topologies

    def validate(self, topology: str) -> list[str]:
        """Возвращает список ошибок валидации, пустой при согласованном графе."""
        topo = self._topologies.get(topology)
        if topo is None:
            return [f"Неизвестная topology: {topology!r}"]
        errors: list[str] = []
        for name, sdef in topo.items():
            if sdef.name != name:
                errors.append(
                    f"Ключ stage {name!r} не совпадает с StageDef.name {sdef.name!r}"
                )
            if sdef.next_stage and sdef.next_stage not in topo:
                errors.append(
                    f"Stage {name!r} ссылается на неизвестный next_stage "
                    f"{sdef.next_stage!r}"
                )
            if sdef.on_corr_success and sdef.on_corr_success not in topo:
                errors.append(
                    f"Stage {name!r} ссылается на неизвестный on_corr_success "
                    f"{sdef.on_corr_success!r}"
                )
            if sdef.on_corr_fail and sdef.on_corr_fail not in topo:
                errors.append(
                    f"Stage {name!r} ссылается на неизвестный on_corr_fail "
                    f"{sdef.on_corr_fail!r}"
                )
            if sdef.has_correction and not (
                sdef.on_corr_success and sdef.on_corr_fail
            ):
                errors.append(
                    f"Stage {name!r} имеет has_correction=True, но отсутствуют "
                    f"on_corr_success/on_corr_fail"
                )
            if sdef.terminal_error and sdef.next_stage:
                errors.append(
                    f"Stage {name!r} одновременно содержит terminal_error и next_stage"
                )
        return errors


__all__ = ["GENERIC_CYCLE_START", "StageDef", "TopologyRegistry", "TWO_TANK"]

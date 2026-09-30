"""Canonical workflow topology graph for AE3 runtime routing/recovery.

Каждая topology, например ``two_tank_drip_substrate_trays``, задаёт
отображение имени stage в :class:`StageDef`. :class:`TopologyRegistry`
предоставляет lookup по ``(topology, stage_name)`` и проверку целостности графа.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Optional, Tuple

from ae3lite.application.services.topology_pack import (
    HYDRAULIC_ENTRY_BY_TASK_TYPE,
    SINGLE_TANK_COMMAND_PLAN_KEYS,
    TWO_TANK_COMMAND_PLAN_KEYS,
    TopologyPack,
)
from ae3lite.hydraulics.ownership import system_for_stage


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
        system: Модуль гидравлики, которому принадлежит стадия
            (``solution`` / ``irrigation`` / ``executor``).
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
    system: str = ""
    has_correction: bool = False
    on_corr_success: Optional[str] = None
    on_corr_fail: Optional[str] = None


# ---------------------------------------------------------------------------
# Topology two-tank drip substrate trays (полный граф)
# ---------------------------------------------------------------------------

_TWO_TANK_STAGES: Mapping[str, StageDef] = {
    # === Startup ===
    "startup": StageDef(
        "startup",
        "startup",
        timeout_key="startup_manual_hold_timeout_sec",
    ),

    # === Solution change path (semi-auto v1) ===
    "await_operator_drain_confirm": StageDef(
        "await_operator_drain_confirm", "solution_change_gate",
        workflow_phase="ready",
        timeout_key="solution_change_operator_confirm_timeout_sec",
    ),
    "solution_drain_start": StageDef(
        "solution_drain_start", "command",
        workflow_phase="tank_filling",
        command_plans=("solution_drain_start",),
        next_stage="solution_drain_check",
        timeout_key="solution_drain_timeout_sec",
    ),
    "solution_drain_check": StageDef(
        "solution_drain_check", "solution_drain_check",
        workflow_phase="tank_filling",
        timeout_key="solution_drain_timeout_sec",
    ),
    "solution_drain_stop_to_clean_fill": StageDef(
        "solution_drain_stop_to_clean_fill", "command",
        workflow_phase="tank_filling",
        command_plans=("solution_drain_stop",),
        next_stage="clean_fill_start",
    ),
    "solution_drain_timeout_stop": StageDef(
        "solution_drain_timeout_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("solution_drain_stop",),
        terminal_error=(
            "solution_drain_timeout_stop",
            "Слив раствора не завершился за отведённое время.",
        ),
    ),
    "solution_fill_stop_to_refill_confirm": StageDef(
        "solution_fill_stop_to_refill_confirm", "command",
        workflow_phase="tank_filling",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        next_stage="await_operator_refill_confirm",
    ),
    "await_operator_refill_confirm": StageDef(
        "await_operator_refill_confirm", "solution_change_gate",
        workflow_phase="tank_filling",
        timeout_key="solution_change_operator_confirm_timeout_sec",
    ),
    "solution_change_operator_timeout_stop": StageDef(
        "solution_change_operator_timeout_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("solution_drain_stop", "solution_fill_stop", "sensor_mode_deactivate"),
        terminal_error=(
            "solution_change_operator_timeout",
            "Истёк таймаут ожидания подтверждения оператора при подмене раствора.",
        ),
    ),
    "solution_change_abort_stop": StageDef(
        "solution_change_abort_stop", "command",
        workflow_phase="idle",
        command_plans=("solution_drain_stop", "solution_fill_stop", "sensor_mode_deactivate"),
        terminal_error=(
            "solution_change_aborted_by_operator",
            "Подмена раствора отменена оператором.",
        ),
    ),

    # === Clean fill path ===
    "clean_fill_start": StageDef(
        "clean_fill_start", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_start",),
        next_stage="clean_fill_check",
        timeout_key="clean_fill_timeout_sec",
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
            "Наполнение чистой водой остановлено: источник воды пуст или нижний уровень не подтверждает наличие воды.",
        ),
    ),
    "clean_fill_timeout_stop": StageDef(
        "clean_fill_timeout_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_stop",),
        terminal_error=(
            "clean_tank_not_filled_timeout",
            "За отведённое время бак чистой воды не достиг требуемого уровня.",
        ),
    ),

    # === Solution fill path ===
    "solution_fill_start": StageDef(
        "solution_fill_start", "command",
        workflow_phase="tank_filling",
        command_plans=("sensor_mode_activate", "solution_fill_start"),
        next_stage="solution_fill_check",
        timeout_key="solution_fill_timeout_sec",
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
            "Наполнение раствором остановлено: в баке чистой воды не осталось воды для подачи.",
        ),
    ),
    "solution_fill_leak_stop": StageDef(
        "solution_fill_leak_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        terminal_error=(
            "solution_fill_leak_detected",
            "Наполнение раствором остановлено: нижний уровень раствора пропал после guard-delay, возможна утечка или неправильная гидравлика.",
        ),
    ),
    "solution_fill_timeout_stop": StageDef(
        "solution_fill_timeout_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        terminal_error=(
            "solution_tank_not_filled_timeout",
            "Бак раствора не наполнился за отведённое время.",
        ),
    ),

    # === Prepare recirculation path ===
    "prepare_recirculation_start": StageDef(
        "prepare_recirculation_start", "command",
        workflow_phase="tank_recirc",
        command_plans=("sensor_mode_activate", "prepare_recirculation_start"),
        next_stage="prepare_recirculation_check",
        timeout_key="prepare_recirculation_timeout_sec",
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
        workflow_phase="tank_filling",
        command_plans=("prepare_recirculation_stop", "sensor_mode_deactivate"),
        # Раствор закончился → обычная подготовка (startup → clean/solution_fill → prepare),
        # а не terminal fail. Зеркало irrigation_stop_to_setup.
        next_stage="startup",
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
    "irrigation_pump_stop": StageDef(
        "irrigation_pump_stop", "command",
        workflow_phase="irrigating",
        command_plans=("irrigation_pump_stop",),
        next_stage="irrigation_check",
    ),
    "irrigation_stop_to_ready": StageDef(
        "irrigation_stop_to_ready", "command",
        workflow_phase="ready",
        command_plans=("irrigation_stop", "sensor_mode_deactivate"),
        next_stage="completed_run",
    ),
    "irrigation_stop_to_setup": StageDef(
        "irrigation_stop_to_setup", "command",
        workflow_phase="tank_filling",
        command_plans=("irrigation_stop", "sensor_mode_deactivate"),
        next_stage="startup",
    ),
    # === Solution topup path (ready autofill) ===
    "solution_topup_guard": StageDef(
        "solution_topup_guard", "solution_topup_guard",
        workflow_phase="ready",
    ),
    "solution_topup_start": StageDef(
        "solution_topup_start", "command",
        workflow_phase="ready",
        command_plans=("solution_topup_start",),
        next_stage="solution_topup_check",
        timeout_key="solution_topup_timeout_sec",
    ),
    "solution_topup_check": StageDef(
        "solution_topup_check", "solution_topup_check",
        workflow_phase="ready",
        timeout_key="solution_topup_timeout_sec",
    ),
    "solution_topup_stop": StageDef(
        "solution_topup_stop", "command",
        workflow_phase="ready",
        command_plans=("solution_topup_stop",),
        next_stage="solution_topup_complete",
    ),
    "solution_topup_complete": StageDef(
        "solution_topup_complete", "solution_topup_complete",
        workflow_phase="ready",
    ),
    "solution_topup_source_empty_stop": StageDef(
        "solution_topup_source_empty_stop", "command",
        workflow_phase="ready",
        command_plans=("solution_topup_stop",),
        terminal_error=(
            "solution_topup_source_empty",
            "Автодолив остановлен: в баке чистой воды не осталось воды для подачи.",
        ),
    ),
    "solution_topup_leak_stop": StageDef(
        "solution_topup_leak_stop", "command",
        workflow_phase="ready",
        command_plans=("solution_topup_stop",),
        terminal_error=(
            "solution_topup_leak_detected",
            "Автодолив остановлен: нижний уровень раствора пропал, возможна утечка.",
        ),
    ),
    "solution_topup_timeout_stop": StageDef(
        "solution_topup_timeout_stop", "command",
        workflow_phase="ready",
        command_plans=("solution_topup_stop",),
        terminal_error=(
            "solution_topup_timeout",
            "Автодолив не завершился за отведённое время.",
        ),
    ),

    # === Terminal ===
    "manual_hold": StageDef("manual_hold", "manual_hold"),
    "complete_ready": StageDef("complete_ready", "ready", workflow_phase="ready"),
    "completed_run": StageDef("completed_run", "ready", workflow_phase="ready"),
    "completed_skip": StageDef("completed_skip", "ready", workflow_phase="ready"),
}


def _bind_hydraulic_system(graph: Mapping[str, StageDef]) -> dict[str, StageDef]:
    """Проставляет владельца стадии из каталога модулей гидравлики."""
    bound: dict[str, StageDef] = {}
    for name, stage in graph.items():
        system = system_for_stage(name)
        if system is None:
            raise RuntimeError(f"Стадия {name} не назначена модулю гидравлики")
        bound[name] = replace(stage, system=system)
    return bound


TWO_TANK: Mapping[str, StageDef] = _bind_hydraulic_system(_TWO_TANK_STAGES)


# ---------------------------------------------------------------------------
# Topology generic_cycle_start (simple single-batch diagnostics)
# ---------------------------------------------------------------------------

GENERIC_CYCLE_START: Mapping[str, StageDef] = {
    # startup: единственный stage для simple single-batch workflow.
    # При DONE команды startup recovery завершает задачу (нет next_stage/terminal_error).
    "startup": StageDef("startup", "command", workflow_phase="idle"),
}


LIGHTING_TICK_STAGES: Mapping[str, StageDef] = {
    # Текущий intent пишет current_stage='apply'. Tick остаётся одним command batch.
    "apply": StageDef(
        "apply",
        "command",
        workflow_phase="ready",
        command_plans=("lighting_tick",),
    ),
}


def _without_clean_fill(graph: Mapping[str, StageDef]) -> dict[str, StageDef]:
    """Скомпилированный вариант графа: нет стадий чистого бака."""
    dropped = {name for name in graph if name.startswith("clean_fill_")}
    compiled: dict[str, StageDef] = {}
    for name, stage in graph.items():
        if name in dropped:
            continue
        next_stage = stage.next_stage
        if next_stage in dropped:
            next_stage = "solution_fill_start"
        if next_stage != stage.next_stage:
            stage = replace(stage, next_stage=next_stage)
        compiled[name] = stage
    return compiled


SINGLE_TANK: Mapping[str, StageDef] = _without_clean_fill(TWO_TANK)


def _hydraulic_pack(
    pack_id: str,
    *,
    stages: Mapping[str, StageDef],
    irrigation_binding: str,
    command_plan_keys: frozenset[str],
    plan_profile: str,
) -> TopologyPack:
    return TopologyPack(
        id=pack_id,
        stages=stages,
        required_node_types=frozenset({"irrig", "ph", "ec"}),
        required_subsystems=("solution", "irrigation", "correction"),
        optional_subsystems=("solution_change", "solution_topup"),
        entry_by_task_type=HYDRAULIC_ENTRY_BY_TASK_TYPE,
        command_plan_keys=command_plan_keys,
        irrigation_binding=irrigation_binding,
        scope="zone",
        plan_profile=plan_profile,
        execution_mode="workflow",
        check_stage_ownership=True,
        fail_safe_on_flow=True,
        tracks_correction_authority=True,
        retries_missing_actuators=True,
    )


TWO_TANK_PACK = _hydraulic_pack(
    "two_tank",
    stages=TWO_TANK,
    irrigation_binding="generic",
    command_plan_keys=TWO_TANK_COMMAND_PLAN_KEYS,
    plan_profile="two_tank",
)
DRIP_SUBSTRATE_TRAYS_PACK = _hydraulic_pack(
    "two_tank_drip_substrate_trays",
    stages=TWO_TANK,
    irrigation_binding="drip_substrate_trays",
    command_plan_keys=TWO_TANK_COMMAND_PLAN_KEYS,
    plan_profile="two_tank",
)
SINGLE_TANK_PACK = _hydraulic_pack(
    "single_tank",
    stages=SINGLE_TANK,
    irrigation_binding="single_tank",
    command_plan_keys=SINGLE_TANK_COMMAND_PLAN_KEYS,
    plan_profile="single_tank",
)
GENERIC_CYCLE_START_PACK = TopologyPack(
    id="generic_cycle_start",
    stages=GENERIC_CYCLE_START,
    required_node_types=frozenset({"irrig"}),
    required_subsystems=(),
    optional_subsystems=("diagnostics",),
    entry_by_task_type={"cycle_start": "startup"},
    command_plan_keys=frozenset(),
    plan_profile="diagnostics",
    execution_mode="command_batch",
    check_stage_ownership=False,
)
LIGHTING_TICK_PACK = TopologyPack(
    id="lighting_tick",
    stages=LIGHTING_TICK_STAGES,
    required_node_types=frozenset(),
    required_subsystems=("lighting",),
    optional_subsystems=(),
    entry_by_task_type={"lighting_tick": "apply"},
    command_plan_keys=frozenset({"lighting_tick"}),
    scope="zone",
    plan_profile="lighting",
    execution_mode="command_batch",
    check_stage_ownership=False,
)


# Каноническое имя topology → пакет
_PACKS: Mapping[str, TopologyPack] = {
    TWO_TANK_PACK.id: TWO_TANK_PACK,
    DRIP_SUBSTRATE_TRAYS_PACK.id: DRIP_SUBSTRATE_TRAYS_PACK,
    SINGLE_TANK_PACK.id: SINGLE_TANK_PACK,
    GENERIC_CYCLE_START_PACK.id: GENERIC_CYCLE_START_PACK,
    LIGHTING_TICK_PACK.id: LIGHTING_TICK_PACK,
}


def _pack_from_stages(pack_id: str, stages: Mapping[str, StageDef]) -> TopologyPack:
    """Тестовый граф без каталога модулей."""
    return TopologyPack(
        id=pack_id,
        stages=stages,
        required_node_types=frozenset(),
        required_subsystems=(),
        optional_subsystems=(),
        entry_by_task_type={},
        command_plan_keys=frozenset(),
        execution_mode="command_batch",
        check_stage_ownership=False,
    )


class TopologyRegistry:
    """Сервис lookup для пакетов topology и их stage."""

    def __init__(
        self,
        topologies: Mapping[str, TopologyPack | Mapping[str, StageDef]] | None = None,
    ) -> None:
        source = _PACKS if topologies is None else topologies
        packs: dict[str, TopologyPack] = {}
        for key, value in source.items():
            if isinstance(value, TopologyPack):
                packs[key] = value
            else:
                packs[key] = _pack_from_stages(key, value)
        self._packs = packs

    def pack(self, topology: str) -> TopologyPack:
        found = self._packs.get(topology)
        if found is None:
            raise KeyError(f"Неизвестная topology: {topology!r}")
        return found

    def try_pack(self, topology: str) -> Optional[TopologyPack]:
        return self._packs.get(str(topology or "").strip().lower())

    def ids(self) -> Tuple[str, ...]:
        return tuple(self._packs)

    def get(self, topology: str, stage: str) -> StageDef:
        """Возвращает :class:`StageDef` для пары *topology* / *stage*.

        Выбрасывает :class:`KeyError`, если topology или stage неизвестны.
        """
        topo = self.pack(topology).stages
        stage_def = topo.get(stage)
        if stage_def is None:
            raise KeyError(
                f"Неизвестный stage {stage!r} в topology {topology!r}"
            )
        return stage_def

    def stages(self, topology: str) -> Mapping[str, StageDef]:
        """Возвращает полный граф stage для *topology*."""
        return self.pack(topology).stages

    def has_topology(self, topology: str) -> bool:
        return topology in self._packs

    def validate(self, topology: str) -> list[str]:
        """Возвращает список ошибок валидации, пустой при согласованном графе."""
        found = self._packs.get(topology)
        if found is None:
            return [f"Неизвестная topology: {topology!r}"]
        topo = found.stages
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
            if found.check_stage_ownership:
                expected = system_for_stage(name)
                if expected is None or sdef.system != expected:
                    errors.append(
                        f"Stage {name!r} принадлежит системе {sdef.system!r}, "
                        f"каталог модулей ожидает {expected!r}"
                    )
        entry_targets = set(found.entry_by_task_type.values())
        missing_entries = sorted(entry_targets - set(topo))
        for missing in missing_entries:
            errors.append(
                f"Topology {topology!r} ссылается на неизвестный entry stage {missing!r}"
            )
        return errors


__all__ = [
    "DRIP_SUBSTRATE_TRAYS_PACK",
    "GENERIC_CYCLE_START",
    "GENERIC_CYCLE_START_PACK",
    "LIGHTING_TICK_PACK",
    "SINGLE_TANK",
    "SINGLE_TANK_PACK",
    "StageDef",
    "TWO_TANK",
    "TWO_TANK_PACK",
    "TopologyPack",
    "TopologyRegistry",
]

"""Один исполнитель гидравлики и три непересекающиеся системы."""

from ae3lite.application.services.workflow_topology import TWO_TANK
from ae3lite.application.use_cases.workflow_router import WorkflowRouter
from ae3lite.hydraulics.correction import CORRECTION_SYSTEM
from ae3lite.hydraulics.irrigation import IRRIGATION_SYSTEM
from ae3lite.hydraulics.ownership import (
    CORRECTION_HOST_STAGES,
    EXECUTOR_STAGES,
    IRRIGATION_STAGES,
    SOLUTION_STAGES,
)
from ae3lite.hydraulics.registry import EXECUTOR_HANDLERS, HYDRAULIC_SYSTEMS
from ae3lite.hydraulics.solution import SOLUTION_SYSTEM


def test_stage_partitions_cover_two_tank_without_overlap() -> None:
    covered = SOLUTION_STAGES | IRRIGATION_STAGES | EXECUTOR_STAGES
    assert covered == set(TWO_TANK)
    assert not (SOLUTION_STAGES & IRRIGATION_STAGES)
    assert not (SOLUTION_STAGES & EXECUTOR_STAGES)
    assert not (IRRIGATION_STAGES & EXECUTOR_STAGES)


def test_each_stage_records_its_system() -> None:
    for name, stage in TWO_TANK.items():
        if name in SOLUTION_STAGES:
            assert stage.system == "solution"
        elif name in IRRIGATION_STAGES:
            assert stage.system == "irrigation"
        else:
            assert stage.system == "executor"


def test_correction_has_no_graph_stages_and_hosts_only_check_stages() -> None:
    assert CORRECTION_SYSTEM.stages == frozenset()
    assert CORRECTION_SYSTEM.hosted_by_stages == CORRECTION_HOST_STAGES
    hosts = {name for name, stage in TWO_TANK.items() if stage.has_correction}
    assert hosts == set(CORRECTION_HOST_STAGES)


def test_handler_keys_belong_to_one_module() -> None:
    seen: dict[str, str] = {}
    for system in HYDRAULIC_SYSTEMS:
        for key in system.handlers:
            assert key not in seen
            assert key not in EXECUTOR_HANDLERS
            seen[key] = system.system_id
    assert set(WorkflowRouter.HANDLER_MAP) == set(seen) | set(EXECUTOR_HANDLERS)


def test_modules_declare_what_they_watch_and_control() -> None:
    assert SOLUTION_SYSTEM.watches
    assert SOLUTION_SYSTEM.controls
    assert IRRIGATION_SYSTEM.watches
    assert IRRIGATION_SYSTEM.controls
    assert CORRECTION_SYSTEM.watches
    assert CORRECTION_SYSTEM.controls
    assert "valve_clean_supply" in SOLUTION_SYSTEM.controls
    assert "valve_clean_supply" in CORRECTION_SYSTEM.borrows
    assert "valve_clean_supply" not in CORRECTION_SYSTEM.controls
    assert "dose_ec" not in SOLUTION_SYSTEM.controls
    assert "dose_ph" not in IRRIGATION_SYSTEM.controls

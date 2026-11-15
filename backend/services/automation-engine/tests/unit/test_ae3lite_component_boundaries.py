"""Architectural and ownership contracts for the decomposed AE3 components."""
from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from ae3lite.application.services.stage_config_schedule import StageConfigSchedule
from ae3lite.application.services.stage_runtime_config import StageRuntimeConfig
from ae3lite.infrastructure.read_models.zone_snapshot_read_model import PgZoneSnapshotReadModel
from ae3lite.runtime.worker_runtime_state import WorkerRuntimeState


def test_direct_component_import_graph_has_no_cycles() -> None:
    root = Path(__file__).resolve().parents[2] / "ae3lite"
    modules = {
        "ae3lite." + ".".join(path.relative_to(root).with_suffix("").parts): path
        for path in root.rglob("*.py")
    }
    edges: dict[str, set[str]] = {}
    for name, path in modules.items():
        edges[name] = set()
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.ImportFrom) and node.module in modules:
                edges[name].add(node.module)
            elif isinstance(node, ast.Import):
                edges[name].update(alias.name for alias in node.names if alias.name in modules)

    visited: set[str] = set()
    active: list[str] = []

    def visit(name: str) -> None:
        assert name not in active, " -> ".join([*active, name])
        if name in visited:
            return
        active.append(name)
        for target in sorted(edges[name]):
            visit(target)
        active.pop()
        visited.add(name)

    for name in sorted(modules):
        visit(name)


def test_lazy_snapshot_components_support_custom_subclass_constructor() -> None:
    class CustomSnapshot(PgZoneSnapshotReadModel):
        def __init__(self) -> None:
            self.fixture_name = "custom"

    first, second = CustomSnapshot(), CustomSnapshot()
    assert first._zone_snapshot_values_policy is first._zone_snapshot_values_policy
    assert first._zone_snapshot_values_policy is not second._zone_snapshot_values_policy
    assert first._as_mapping({"fresh": True}) == {"fresh": True}


def test_reused_config_component_reads_each_current_runtime_plan() -> None:
    config = StageRuntimeConfig()
    first = SimpleNamespace(target_ph=5.7, day_night_config=None)
    second = SimpleNamespace(target_ph=6.1, day_night_config=None)
    component = config._stage_config_targets
    assert config.effective_ph_target(task=None, runtime=first) == 5.7
    assert config.effective_ph_target(task=None, runtime=second) == 6.1
    assert config._stage_config_targets is component


def test_worker_lifecycle_mutations_are_isolated_per_instance() -> None:
    first, second = WorkerRuntimeState(), WorkerRuntimeState()
    first.lease_release_fail_zones.add(7)
    first.pending_correction_safety_checks.append({"zone_id": 7})
    first.pending_kicks += 1
    assert second.lease_release_fail_zones == set()
    assert second.pending_correction_safety_checks == []
    assert second.pending_kicks == 0


def test_schedule_clock_receives_greenhouse_timezone_on_every_call() -> None:
    calls: list[str] = []
    hour = 7

    def now(tz):
        calls.append(str(tz))
        return datetime(2026, 11, 15, hour, tzinfo=tz)

    settings = {"lighting": {"day_start_time": "06:00", "day_hours": 16, "timezone": "Europe/Moscow"}}
    assert StageConfigSchedule.is_day_now(settings, now_fn=now) is True
    hour = 23
    assert StageConfigSchedule.is_day_now(settings, now_fn=now) is False
    assert calls == ["Europe/Moscow", "Europe/Moscow"]

from __future__ import annotations

import builtins
import sys
from types import SimpleNamespace

import pytest

import ae2lite.main_runtime_cycle as cycle
import ae2lite.main_runtime_shared as shared


@pytest.fixture
def _restore_api_module():
    had_api_module = "api" in sys.modules
    original_api_module = sys.modules.get("api")
    try:
        yield
    finally:
        if had_api_module:
            sys.modules["api"] = original_api_module
        else:
            sys.modules.pop("api", None)


def _force_api_import_failure(monkeypatch):
    original_import = builtins.__import__

    def _patched_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name == "api":
            raise ModuleNotFoundError("forced missing api module for test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _patched_import)


@pytest.mark.asyncio
async def test_single_writer_probe_returns_false_when_enforcement_disabled(monkeypatch, _restore_api_module):
    monkeypatch.setattr(shared, "_AE2_RUNTIME_SINGLE_WRITER_ENFORCE", False)
    monkeypatch.setattr(shared, "_AE2_FALLBACK_LOOP_WRITER_ENABLED", False)

    assert await shared._is_scheduler_single_writer_active() is False


@pytest.mark.asyncio
async def test_single_writer_probe_fail_closed_when_api_probe_missing_and_fallback_disabled(monkeypatch, _restore_api_module):
    monkeypatch.setattr(shared, "_AE2_RUNTIME_SINGLE_WRITER_ENFORCE", True)
    monkeypatch.setattr(shared, "_AE2_FALLBACK_LOOP_WRITER_ENABLED", False)
    _force_api_import_failure(monkeypatch)

    assert await shared._is_scheduler_single_writer_active() is True


@pytest.mark.asyncio
async def test_single_writer_probe_fail_open_when_api_probe_missing_and_fallback_enabled(monkeypatch, _restore_api_module):
    monkeypatch.setattr(shared, "_AE2_RUNTIME_SINGLE_WRITER_ENFORCE", True)
    monkeypatch.setattr(shared, "_AE2_FALLBACK_LOOP_WRITER_ENABLED", True)
    _force_api_import_failure(monkeypatch)

    assert await shared._is_scheduler_single_writer_active() is False


@pytest.mark.asyncio
async def test_single_writer_probe_uses_api_result(monkeypatch, _restore_api_module):
    monkeypatch.setattr(shared, "_AE2_RUNTIME_SINGLE_WRITER_ENFORCE", True)
    monkeypatch.setattr(shared, "_AE2_FALLBACK_LOOP_WRITER_ENABLED", False)

    async def _probe() -> bool:
        return True

    sys.modules["api"] = SimpleNamespace(is_scheduler_single_writer_active=_probe)
    assert await shared._is_scheduler_single_writer_active() is True


@pytest.mark.asyncio
async def test_single_writer_probe_fail_closed_when_api_probe_raises_and_fallback_disabled(monkeypatch, _restore_api_module):
    monkeypatch.setattr(shared, "_AE2_RUNTIME_SINGLE_WRITER_ENFORCE", True)
    monkeypatch.setattr(shared, "_AE2_FALLBACK_LOOP_WRITER_ENABLED", False)

    async def _probe() -> bool:
        raise RuntimeError("probe_failed")

    sys.modules["api"] = SimpleNamespace(is_scheduler_single_writer_active=_probe)
    assert await shared._is_scheduler_single_writer_active() is True


@pytest.mark.asyncio
async def test_single_writer_probe_fail_open_when_api_probe_raises_and_fallback_enabled(monkeypatch, _restore_api_module):
    monkeypatch.setattr(shared, "_AE2_RUNTIME_SINGLE_WRITER_ENFORCE", True)
    monkeypatch.setattr(shared, "_AE2_FALLBACK_LOOP_WRITER_ENABLED", True)

    async def _probe() -> bool:
        raise RuntimeError("probe_failed")

    sys.modules["api"] = SimpleNamespace(is_scheduler_single_writer_active=_probe)
    assert await shared._is_scheduler_single_writer_active() is False


@pytest.mark.asyncio
async def test_single_writer_probe_passes_zone_id_to_api(monkeypatch, _restore_api_module):
    monkeypatch.setattr(shared, "_AE2_RUNTIME_SINGLE_WRITER_ENFORCE", True)
    monkeypatch.setattr(shared, "_AE2_FALLBACK_LOOP_WRITER_ENABLED", False)
    probe_calls = []

    async def _probe(*, zone_id=None) -> bool:
        probe_calls.append(zone_id)
        return zone_id == 42

    sys.modules["api"] = SimpleNamespace(is_scheduler_single_writer_active=_probe)

    assert await shared._is_scheduler_single_writer_active(zone_id=42) is True
    assert await shared._is_scheduler_single_writer_active(zone_id=43) is False
    assert probe_calls == [42, 43]


@pytest.mark.asyncio
async def test_partition_zones_by_single_writer_gates_only_claimed_zone(monkeypatch):
    monkeypatch.setattr(shared, "_AE2_RUNTIME_SINGLE_WRITER_ENFORCE", True)
    monkeypatch.setattr(shared, "_AE2_FALLBACK_LOOP_WRITER_ENABLED", False)
    monkeypatch.setattr(shared, "_SCHEDULER_WRITER_WATCHDOG_TIMEOUT_SEC", 600.0)
    monkeypatch.setattr(cycle.time, "monotonic", lambda: 1000.0)
    monkeypatch.setattr(shared, "_should_log_scheduler_single_writer_skip", lambda _now: False)
    shared._scheduler_writer_active_since.clear()
    probe_calls = []

    async def _probe(*, zone_id=None) -> bool:
        probe_calls.append(zone_id)
        return zone_id == 1

    monkeypatch.setattr(shared, "_is_scheduler_single_writer_active", _probe)

    zones_for_processing, gated_zone_ids = await cycle._partition_zones_by_single_writer([{"id": 1}, {"id": 2}])

    assert gated_zone_ids == [1]
    assert [int(zone["id"]) for zone in zones_for_processing] == [2]
    assert shared._scheduler_writer_active_since == {1: 1000.0}
    assert probe_calls == [1, 2]


@pytest.mark.asyncio
async def test_partition_zones_by_single_writer_watchdog_releases_zone(monkeypatch):
    monkeypatch.setattr(shared, "_AE2_RUNTIME_SINGLE_WRITER_ENFORCE", True)
    monkeypatch.setattr(shared, "_AE2_FALLBACK_LOOP_WRITER_ENABLED", False)
    monkeypatch.setattr(shared, "_SCHEDULER_WRITER_WATCHDOG_TIMEOUT_SEC", 10.0)
    monkeypatch.setattr(cycle.time, "monotonic", lambda: 20.0)
    monkeypatch.setattr(shared, "_should_log_scheduler_single_writer_skip", lambda _now: False)
    shared._scheduler_writer_active_since.clear()
    shared._scheduler_writer_active_since[1] = 0.0

    async def _probe(*, zone_id=None) -> bool:
        return zone_id == 1

    monkeypatch.setattr(shared, "_is_scheduler_single_writer_active", _probe)

    zones_for_processing, gated_zone_ids = await cycle._partition_zones_by_single_writer([{"id": 1}])

    assert gated_zone_ids == []
    assert [int(zone["id"]) for zone in zones_for_processing] == [1]
    assert shared._scheduler_writer_active_since == {}

"""Tests for runtime state snapshot store."""

from pathlib import Path

from infrastructure.runtime_state_store import RuntimeStateStore


def test_runtime_state_store_roundtrip(tmp_path: Path):
    store = RuntimeStateStore(str(tmp_path / "runtime_state.json"))
    payload = {"saved_at": "2026-02-18T12:00:00", "zone_service": {"zone_states": {"1": {"error_streak": 2}}}}
    assert store.save(payload) is True
    loaded = store.load()
    assert isinstance(loaded, dict)
    assert loaded["zone_service"]["zone_states"]["1"]["error_streak"] == 2
    assert loaded["schema_version"] == 1

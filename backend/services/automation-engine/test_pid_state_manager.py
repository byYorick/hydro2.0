from datetime import datetime, timedelta, timezone

import pytest

from services.pid_state_manager import PidStateManager
from utils.adaptive_pid import AdaptivePid, AdaptivePidConfig, PidZone, PidZoneCoeffs


def _build_pid() -> AdaptivePid:
    return AdaptivePid(
        AdaptivePidConfig(
            setpoint=1.8,
            dead_zone=0.2,
            close_zone=0.5,
            far_zone=1.0,
            zone_coeffs={
                PidZone.DEAD: PidZoneCoeffs(0.0, 0.0, 0.0),
                PidZone.CLOSE: PidZoneCoeffs(1.0, 0.0, 0.0),
                PidZone.FAR: PidZoneCoeffs(1.0, 0.0, 0.0),
            },
            max_output=200.0,
        )
    )


@pytest.mark.asyncio
async def test_restore_pid_state_reconstructs_last_output_from_last_dose_at(monkeypatch):
    manager = PidStateManager()
    pid = _build_pid()
    now_utc = datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc)
    last_dose_at = now_utc - timedelta(seconds=15)

    async def fake_load(_zone_id, _pid_type):
        return {
            "integral": 1.0,
            "prev_error": 0.1,
            "last_output_ms": 1771299192016,  # legacy поле, игнорируется при наличии last_dose_at
            "last_dose_at": last_dose_at,
            "prev_derivative": 0.7,
            "stats": {},
            "current_zone": "far",
        }

    monkeypatch.setattr(manager, "load_pid_state", fake_load)
    monkeypatch.setattr("services.pid_state_manager.utcnow", lambda: now_utc)
    monkeypatch.setattr("services.pid_state_manager.time.monotonic", lambda: 1000.0)

    restored = await manager.restore_pid_state(5, "ec", pid)

    assert restored is True
    assert pid.last_output_ms == 985_000
    assert pid.integral == 1.0
    assert pid.prev_error == 0.1
    assert pid.prev_derivative == 0.7


@pytest.mark.asyncio
async def test_restore_pid_state_resets_interval_when_min_interval_elapsed(monkeypatch):
    manager = PidStateManager()
    pid = _build_pid()
    now_utc = datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc)
    last_dose_at = now_utc - timedelta(seconds=120)

    async def fake_load(_zone_id, _pid_type):
        return {
            "integral": 2.0,
            "prev_error": 0.2,
            "last_output_ms": 999500,
            "last_dose_at": last_dose_at,
            "prev_derivative": 0.4,
            "stats": {},
            "current_zone": "close",
        }

    monkeypatch.setattr(manager, "load_pid_state", fake_load)
    monkeypatch.setattr("services.pid_state_manager.utcnow", lambda: now_utc)
    monkeypatch.setattr("services.pid_state_manager.time.monotonic", lambda: 1000.0)

    restored = await manager.restore_pid_state(5, "ec", pid)

    assert restored is True
    assert pid.last_output_ms == 0
    assert pid.integral == 2.0
    assert pid.prev_error == 0.2
    assert pid.prev_derivative == 0.4


@pytest.mark.asyncio
async def test_restore_pid_state_without_last_dose_at_resets_interval(monkeypatch):
    manager = PidStateManager()
    pid = _build_pid()
    now_utc = datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc)

    async def fake_load(_zone_id, _pid_type):
        return {
            "integral": 3.0,
            "prev_error": 0.3,
            "last_output_ms": 1_050_000,
            "last_dose_at": None,
            "prev_derivative": 0.0,
            "stats": {},
            "current_zone": "far",
        }

    monkeypatch.setattr(manager, "load_pid_state", fake_load)
    monkeypatch.setattr("services.pid_state_manager.utcnow", lambda: now_utc)
    monkeypatch.setattr("services.pid_state_manager.time.monotonic", lambda: 1000.0)

    restored = await manager.restore_pid_state(5, "ph", pid)

    assert restored is True
    assert pid.last_output_ms == 0
    assert pid.integral == 3.0
    assert pid.prev_error == 0.3


@pytest.mark.asyncio
async def test_restore_pid_state_restores_current_zone_and_stats(monkeypatch):
    manager = PidStateManager()
    pid = _build_pid()
    now_utc = datetime(2026, 3, 4, 12, 0, 0, tzinfo=timezone.utc)
    last_dose_at = now_utc - timedelta(seconds=10)

    async def fake_load(_zone_id, _pid_type):
        return {
            "integral": 4.0,
            "prev_error": 0.4,
            "last_output_ms": 0,
            "last_dose_at": last_dose_at,
            "prev_derivative": 0.2,
            "stats": {"corrections_count": 5, "total_output": 11.5},
            "current_zone": "close",
        }

    monkeypatch.setattr(manager, "load_pid_state", fake_load)
    monkeypatch.setattr("services.pid_state_manager.utcnow", lambda: now_utc)
    monkeypatch.setattr("services.pid_state_manager.time.monotonic", lambda: 1000.0)

    restored = await manager.restore_pid_state(5, "ec", pid)

    assert restored is True
    assert pid.last_output_ms == 990_000
    assert pid.integral == 4.0
    assert pid.prev_error == 0.4
    assert pid.current_zone == PidZone.CLOSE
    assert pid.stats.corrections_count == 5
    assert pid.stats.total_output == 11.5

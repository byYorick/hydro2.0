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
async def test_restore_pid_state_resets_incompatible_last_output_timestamp(monkeypatch):
    manager = PidStateManager()
    pid = _build_pid()

    async def fake_load(_zone_id, _pid_type):
        return {
            "integral": 1.0,
            "prev_error": 0.1,
            "last_output_ms": 1771299192016,  # epoch-like legacy value
            "stats": {},
            "current_zone": "far",
        }

    monkeypatch.setattr(manager, "load_pid_state", fake_load)
    monkeypatch.setattr("services.pid_state_manager.time.monotonic", lambda: 1000.0)

    restored = await manager.restore_pid_state(5, "ec", pid)

    assert restored is True
    assert pid.last_output_ms == 0
    assert pid.integral == 1.0
    assert pid.prev_error == 0.1


@pytest.mark.asyncio
async def test_restore_pid_state_keeps_valid_monotonic_last_output(monkeypatch):
    manager = PidStateManager()
    pid = _build_pid()

    async def fake_load(_zone_id, _pid_type):
        return {
            "integral": 2.0,
            "prev_error": 0.2,
            "last_output_ms": 999500,
            "stats": {},
            "current_zone": "close",
        }

    monkeypatch.setattr(manager, "load_pid_state", fake_load)
    monkeypatch.setattr("services.pid_state_manager.time.monotonic", lambda: 1000.0)

    restored = await manager.restore_pid_state(5, "ec", pid)

    assert restored is True
    assert pid.last_output_ms == 999500
    assert pid.integral == 2.0
    assert pid.prev_error == 0.2


@pytest.mark.asyncio
async def test_restore_pid_state_resets_negative_last_output(monkeypatch):
    manager = PidStateManager()
    pid = _build_pid()

    async def fake_load(_zone_id, _pid_type):
        return {
            "integral": 3.0,
            "prev_error": 0.3,
            "last_output_ms": -10,
            "stats": {},
            "current_zone": "far",
        }

    monkeypatch.setattr(manager, "load_pid_state", fake_load)
    monkeypatch.setattr("services.pid_state_manager.time.monotonic", lambda: 1000.0)

    restored = await manager.restore_pid_state(5, "ph", pid)

    assert restored is True
    assert pid.last_output_ms == 0
    assert pid.integral == 3.0
    assert pid.prev_error == 0.3


@pytest.mark.asyncio
async def test_restore_pid_state_keeps_small_future_offset_within_tolerance(monkeypatch):
    manager = PidStateManager()
    pid = _build_pid()

    async def fake_load(_zone_id, _pid_type):
        return {
            "integral": 4.0,
            "prev_error": 0.4,
            "last_output_ms": 1_050_000,  # now_mono=1_000_000, within +60s tolerance
            "stats": {},
            "current_zone": "close",
        }

    monkeypatch.setattr(manager, "load_pid_state", fake_load)
    monkeypatch.setattr("services.pid_state_manager.time.monotonic", lambda: 1000.0)

    restored = await manager.restore_pid_state(5, "ec", pid)

    assert restored is True
    assert pid.last_output_ms == 1_050_000
    assert pid.integral == 4.0
    assert pid.prev_error == 0.4

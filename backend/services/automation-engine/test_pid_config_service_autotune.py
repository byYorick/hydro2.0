import pytest

from services import pid_config_service
from utils.adaptive_pid import AdaptivePidConfig, PidZone, PidZoneCoeffs


@pytest.mark.asyncio
async def test_save_autotune_result_updates_zone_coeffs_invalidates_cache_and_emits_events(monkeypatch):
    captured = {}
    invalidated = []
    events = []

    async def fake_fetch(_query, zone_id, pid_type):
        assert zone_id == 12
        assert pid_type == "ph"
        return [
            {
                "config": {
                    "dead_zone": 0.05,
                    "close_zone": 0.3,
                    "far_zone": 1.0,
                    "max_output": 20.0,
                    "zone_coeffs": {
                        "close": {"kp": 5.0, "ki": 0.05, "kd": 0.0},
                        "far": {"kp": 8.0, "ki": 0.02, "kd": 0.0},
                    },
                }
            }
        ]

    async def fake_execute(_query, zone_id, pid_type, config_json):
        captured["zone_id"] = zone_id
        captured["pid_type"] = pid_type
        captured["config_json"] = config_json
        return "INSERT 0 1"

    async def fake_create_zone_event(zone_id, event_type, details):
        events.append((zone_id, event_type, details))
        return None

    monkeypatch.setattr(pid_config_service, "fetch", fake_fetch)
    monkeypatch.setattr(pid_config_service, "execute", fake_execute)
    monkeypatch.setattr(pid_config_service, "create_zone_event", fake_create_zone_event)
    monkeypatch.setattr(
        pid_config_service,
        "invalidate_cache",
        lambda zone_id, correction_type=None: invalidated.append((zone_id, correction_type)),
    )

    await pid_config_service.save_autotune_result(
        12,
        "ph",
        {
            "kp": 6.7,
            "ki": 0.11,
            "kd": 0.0,
            "ku": 14.2,
            "tu_sec": 95.0,
            "oscillation_amplitude": 0.15,
            "cycles_detected": 3,
            "duration_sec": 470.0,
            "tuned_at": "2026-03-04T12:00:00",
        },
    )

    assert captured["zone_id"] == 12
    assert captured["pid_type"] == "ph"
    assert captured["config_json"]["zone_coeffs"]["close"]["kp"] == pytest.approx(6.7)
    assert captured["config_json"]["zone_coeffs"]["close"]["ki"] == pytest.approx(0.11)
    assert captured["config_json"]["zone_coeffs"]["far"]["kp"] == pytest.approx(6.7)
    assert captured["config_json"]["zone_coeffs"]["far"]["ki"] == pytest.approx(0.11)
    assert "autotune" not in captured["config_json"]
    assert captured["config_json"]["autotune_meta"]["kp"] == pytest.approx(6.7)
    assert [event_type for _, event_type, _ in events] == [
        "PID_CONFIG_UPDATED",
        "RELAY_AUTOTUNE_COMPLETED",
    ]
    assert events[0][2]["autotune_meta"]["tu_sec"] == pytest.approx(95.0)
    assert events[1][2]["cycles_detected"] == 3
    assert invalidated == [(12, "ph")]


def test_json_to_pid_config_uses_legacy_autotune_and_fallbacks_non_positive_ki(monkeypatch):
    class _Settings:
        PH_PID_KP_CLOSE = 5.0
        PH_PID_KI_CLOSE = 0.05
        PH_PID_KD_CLOSE = 0.0
        PH_PID_KP_FAR = 8.0
        PH_PID_KI_FAR = 0.02
        PH_PID_KD_FAR = 0.0
        PH_PID_DEAD_ZONE = 0.05
        PH_PID_CLOSE_ZONE = 0.30
        PH_PID_FAR_ZONE = 1.0
        PH_PID_MAX_OUTPUT = 20.0
        PH_PID_MAX_INTEGRAL = 20.0
        PH_PID_MIN_INTERVAL_MS = 90000
        PH_PID_DERIVATIVE_FILTER_ALPHA = 0.35
        EC_PID_KP_CLOSE = 30.0
        EC_PID_KI_CLOSE = 0.3
        EC_PID_KD_CLOSE = 0.0
        EC_PID_KP_FAR = 50.0
        EC_PID_KI_FAR = 0.1
        EC_PID_KD_FAR = 0.0
        EC_PID_DEAD_ZONE = 0.1
        EC_PID_CLOSE_ZONE = 0.5
        EC_PID_FAR_ZONE = 1.5
        EC_PID_MAX_OUTPUT = 50.0
        EC_PID_MAX_INTEGRAL = 100.0
        EC_PID_MIN_INTERVAL_MS = 120000
        EC_PID_DERIVATIVE_FILTER_ALPHA = 0.35
        PID_ANTI_WINDUP_MODE = "conditional"
        PID_BACK_CALCULATION_GAIN = 0.2

    monkeypatch.setattr(pid_config_service, "get_settings", lambda: _Settings())

    config_json = {
        "zone_coeffs": {
            "close": {"kp": 4.2, "ki": 0.0, "kd": 0.0},
            "far": {"kp": 7.4, "ki": -0.1, "kd": 0.0},
        },
        "autotune": {
            "source": "relay_autotune",
            "kp": 4.2,
        },
    }

    config = pid_config_service._json_to_pid_config(config_json, setpoint=6.1, correction_type="ph")
    assert config.zone_coeffs[PidZone.CLOSE].ki == pytest.approx(0.05)
    assert config.zone_coeffs[PidZone.FAR].ki == pytest.approx(0.02)
    assert getattr(config, "autotune_meta", {}).get("source") == "relay_autotune"


def test_pid_config_to_json_keeps_autotune_meta():
    config = AdaptivePidConfig(
        setpoint=6.0,
        dead_zone=0.05,
        close_zone=0.3,
        far_zone=1.0,
        zone_coeffs={
            PidZone.DEAD: PidZoneCoeffs(0.0, 0.0, 0.0),
            PidZone.CLOSE: PidZoneCoeffs(5.0, 0.05, 0.0),
            PidZone.FAR: PidZoneCoeffs(8.0, 0.02, 0.0),
        },
        max_output=20.0,
        min_output=0.0,
        max_integral=20.0,
        anti_windup_mode="conditional",
        back_calculation_gain=0.2,
        derivative_filter_alpha=0.35,
        min_interval_ms=90000,
    )
    setattr(config, "autotune_meta", {"source": "relay_autotune", "ku": 12.3})

    payload = pid_config_service._pid_config_to_json(config)
    assert payload["autotune_meta"]["source"] == "relay_autotune"
    assert payload["autotune_meta"]["ku"] == pytest.approx(12.3)

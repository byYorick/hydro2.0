"""Unit-тесты SimWorld + Publisher (Phase C, без живого MQTT)."""
import json
from typing import Any, Dict, List, Tuple

import pytest

from live import (
    LevelSwitchEvent,
    NodeChannelSpec,
    Publisher,
    SensorSample,
    SimWorld,
)
from live.sim_world import resolve_metric_type


# --- resolve_metric_type --------------------------------------------------


@pytest.mark.parametrize(
    "channel,hint,expected",
    [
        ("ph_sensor", None, "PH"),
        ("ec_sensor", None, "EC"),
        ("temp_air", None, "TEMPERATURE"),
        ("solution_temp_c", None, "WATER_TEMPERATURE"),
        ("humidity", None, "HUMIDITY"),
        ("level_clean_max", None, "WATER_LEVEL"),
        ("level_solution_min", None, "WATER_LEVEL"),
        ("water_content", None, "WATER_CONTENT"),
        ("co2_sensor", None, "CO2"),
        ("custom", "PH", "PH"),         # hint имеет приоритет
        ("custom", "  ph  ", "PH"),     # нормализация
        ("garbage_xx", None, None),     # неизвестный
    ],
)
def test_resolve_metric_type_resolves_known_patterns(channel, hint, expected):
    assert resolve_metric_type(channel, hint) == expected


# --- helpers --------------------------------------------------------------


class _CapturedPublisher:
    """Фейковый publisher, складывающий сообщения в список для assertions."""

    def __init__(self) -> None:
        self.messages: List[Tuple[str, Dict[str, Any], int, bool]] = []

    async def __call__(self, topic: str, payload: bytes, qos: int, retain: bool) -> None:
        decoded = json.loads(payload.decode("utf-8"))
        self.messages.append((topic, decoded, qos, retain))


def _make_sim_world() -> SimWorld:
    channels = [
        NodeChannelSpec("nd-ph", "ph_sensor", "SENSOR", "PH"),
        NodeChannelSpec("nd-ec", "ec_sensor", "SENSOR", "EC"),
        NodeChannelSpec("nd-irr", "level_clean_max", "SENSOR", "WATER_LEVEL"),
        NodeChannelSpec("nd-irr", "level_solution_min", "SENSOR", "WATER_LEVEL"),
        NodeChannelSpec("nd-irr", "valve_clean_fill", "ACTUATOR", None),
        NodeChannelSpec("nd-ec", "pump_a", "ACTUATOR", None),
    ]
    return SimWorld(
        simulation_id=42,
        zone_id=7,
        gh_uid="gh-1",
        zone_uid="sim-zone-7",
        channels=channels,
        params_by_group={"actuator": {"channel_calibrations": {"pump_a": 2.0}}},
        initial_state={"ph": 6.0, "ec": 1.2},
        time_scale=1.0,
    )


# --- SimWorld basic ------------------------------------------------------


def test_sim_world_step_emits_sensor_samples():
    sw = _make_sim_world()
    samples, _ = sw.step(dt_real_seconds=10.0)
    metrics = sorted({s.metric_type for s in samples})
    assert "PH" in metrics
    assert "EC" in metrics
    # WATER_LEVEL тоже эмитится (для каждого level-канала)
    assert "WATER_LEVEL" in metrics


def test_sim_world_step_with_zero_dt_returns_empty():
    sw = _make_sim_world()
    samples, events = sw.step(dt_real_seconds=0.0)
    assert samples == []
    assert events == []


def test_sim_world_emit_initial_levels():
    sw = _make_sim_world()
    events = sw.emit_initial_levels()
    # Два level-канала → два initial event
    channels = sorted(e.channel for e in events)
    assert channels == ["level_clean_max", "level_solution_min"]
    assert all(e.initial is True for e in events)


def test_sim_world_apply_command_dose_changes_ec():
    sw = _make_sim_world()
    state_before = sw.state.chem.ec
    sw.apply_command("nd-ec", "pump_a", "dose", {"ml": 4.0})
    # 4 ml @ 2 ml/sec = 2 sec; шагнём 3 сек (при scale=1).
    sw.step(dt_real_seconds=3.0)
    assert sw.state.chem.ec > state_before


def test_sim_world_level_changes_emit_diff_events_only():
    sw = _make_sim_world()
    # Первый шаг — initial latches уже опубликованы; повторный step не должен
    # эмитить event если уровни не поменялись.
    _ = sw.emit_initial_levels()
    _, events = sw.step(dt_real_seconds=1.0)
    assert events == []  # state не поменялся

    # Запустим clean_fill — уровень clean_max сработает после наполнения.
    sw.apply_command("nd-irr", "valve_clean_fill", "set_relay", {"state": True})
    # Накачка с 100л до 180л при 60 l/час → ~80 минут реального времени.
    # Используем большой шаг для теста.
    _, events = sw.step(dt_real_seconds=3600 * 2)
    # Должен появиться event для level_clean_max
    triggered_channels = [e.channel for e in events if e.state == 1]
    assert "level_clean_max" in triggered_channels


def test_sim_world_time_scale_amplifies_dt():
    sw = SimWorld(
        simulation_id=1, zone_id=1, gh_uid="gh", zone_uid="z",
        channels=[NodeChannelSpec("nd-ec", "ec_sensor", "SENSOR", "EC")],
        initial_state={"ec": 1.0},
        time_scale=10.0,  # 1 sec real ≈ 10 sec sim
    )
    s_scaled, _ = sw.step(dt_real_seconds=1.0)
    sw2 = SimWorld(
        simulation_id=2, zone_id=1, gh_uid="gh", zone_uid="z",
        channels=[NodeChannelSpec("nd-ec", "ec_sensor", "SENSOR", "EC")],
        initial_state={"ec": 1.0},
        time_scale=1.0,
    )
    s_norm, _ = sw2.step(dt_real_seconds=1.0)
    # При scale=10 evaporation должен быть выше → EC выше
    assert s_scaled[0].value > s_norm[0].value


# --- Publisher ----------------------------------------------------------


@pytest.mark.asyncio
async def test_publisher_publishes_telemetry_with_correct_topic_and_format():
    captured = _CapturedPublisher()
    publisher = Publisher(publish_fn=captured)
    samples = [SensorSample(
        node_uid="nd-ph", channel="ph_sensor", metric_type="PH",
        value=6.234, ts_seconds=1714032000.0,
    )]
    await publisher.publish_samples("gh-1", "sim-z", samples)
    assert len(captured.messages) == 1
    topic, payload, qos, retain = captured.messages[0]
    assert topic == "hydro/gh-1/sim-z/nd-ph/ph_sensor/telemetry"
    assert payload["metric_type"] == "PH"
    assert payload["value"] == 6.234
    assert payload["ts"] == 1714032000
    assert payload["is_simulation"] is True
    assert qos == 1
    assert retain is False


@pytest.mark.asyncio
async def test_publisher_publishes_level_event():
    captured = _CapturedPublisher()
    publisher = Publisher(publish_fn=captured)
    events = [LevelSwitchEvent(
        node_uid="nd-irr", channel="level_clean_max",
        state=1, initial=False, ts_seconds=1714032000.0,
    )]
    await publisher.publish_level_events("gh-1", "sim-z", events)
    topic, payload, _, _ = captured.messages[0]
    assert topic == "hydro/gh-1/sim-z/nd-irr/event"
    assert payload["event_code"] == "level_switch_changed"
    assert payload["channel"] == "level_clean_max"
    assert payload["state"] == 1
    assert payload["initial"] is False


@pytest.mark.asyncio
async def test_publisher_publishes_command_response_in_milliseconds():
    captured = _CapturedPublisher()
    publisher = Publisher(publish_fn=captured)
    await publisher.publish_command_response(
        gh_uid="gh-1", zone_uid="sim-z", node_uid="nd", channel="pump_a",
        cmd_id="cmd-123", status="DONE", ts_seconds=1714032000.5,
    )
    topic, payload, _, _ = captured.messages[0]
    assert topic == "hydro/gh-1/sim-z/nd/pump_a/command_response"
    # ts должен быть в миллисекундах
    assert payload["ts"] == int(1714032000.5 * 1000)
    assert payload["cmd_id"] == "cmd-123"
    assert payload["status"] == "DONE"


@pytest.mark.asyncio
async def test_publisher_swallows_publish_error_doesnt_raise():
    async def failing(topic, payload, qos, retain):
        raise RuntimeError("network down")
    publisher = Publisher(publish_fn=failing)
    # не должно поднимать
    await publisher.publish_samples("gh", "z", [SensorSample(
        node_uid="n", channel="ch", metric_type="PH", value=6.0, ts_seconds=0,
    )])

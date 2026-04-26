"""Тесты WorldRegistry и MqttBridge parser (Phase C)."""
import asyncio
import json
from typing import Any, Dict, List, Tuple

import pytest

from live import (
    LiveOrchestrator,
    NodeChannelSpec,
    Publisher,
    SimWorld,
    WorldRegistry,
)
from live.mqtt_bridge import _parse_command_topic


# --- _parse_command_topic ------------------------------------------------


@pytest.mark.parametrize(
    "topic,expected",
    [
        ("hydro/gh-1/zn-1/nd-1/ch/command", ("gh-1", "zn-1", "nd-1", "ch")),
        ("hydro/gh-1/zn-1/nd-1/ch/telemetry", None),
        ("hydro/gh-1/zn-1/nd-1/command", None),                # 5 segments
        ("hydro/gh-1/zn-1/nd-1/ch/foo/command", None),         # 7 segments
        ("not_hydro/gh-1/zn-1/nd-1/ch/command", None),
        ("", None),
    ],
)
def test_parse_command_topic(topic, expected):
    assert _parse_command_topic(topic) == expected


# --- WorldRegistry ------------------------------------------------------


class _CapturedPublisher:
    def __init__(self) -> None:
        self.messages: List[Tuple[str, Dict[str, Any]]] = []

    async def __call__(self, topic: str, payload: bytes, qos: int, retain: bool) -> None:
        decoded = json.loads(payload.decode("utf-8"))
        self.messages.append((topic, decoded))


def _make_world(simulation_id: int = 1) -> SimWorld:
    channels = [
        NodeChannelSpec("nd-ph", "ph_sensor", "SENSOR", "PH"),
    ]
    return SimWorld(
        simulation_id=simulation_id,
        zone_id=1,
        gh_uid="gh-1",
        zone_uid=f"sim-{simulation_id}",
        channels=channels,
        initial_state={"ph": 6.0},
        time_scale=1.0,
    )


@pytest.mark.asyncio
async def test_registry_registers_and_publishes_initial_levels():
    captured = _CapturedPublisher()
    registry = WorldRegistry(publisher=Publisher(publish_fn=captured))
    sw = _make_world()
    await registry.register(sw, tick_seconds=10.0)  # большой tick — не успеет шагнуть
    try:
        # initial levels пусты для этого мира (нет water-level каналов), значит
        # сообщений быть не должно
        assert captured.messages == []
        assert registry.active_count == 1
        assert registry.get(sw.simulation_id) is sw
        assert registry.get_by_zone_uid("gh-1", "sim-1") is sw
    finally:
        await registry.unregister(sw.simulation_id)
        assert registry.active_count == 0


@pytest.mark.asyncio
async def test_registry_tick_loop_publishes_samples():
    captured = _CapturedPublisher()
    registry = WorldRegistry(publisher=Publisher(publish_fn=captured))
    sw = _make_world()
    # tick=0.1 → за 0.3 сек ~3 шага
    await registry.register(sw, tick_seconds=0.1)
    try:
        await asyncio.sleep(0.35)
        assert any("/ph_sensor/telemetry" in topic for topic, _ in captured.messages)
    finally:
        await registry.unregister(sw.simulation_id)


@pytest.mark.asyncio
async def test_registry_double_register_is_idempotent():
    captured = _CapturedPublisher()
    registry = WorldRegistry(publisher=Publisher(publish_fn=captured))
    sw1 = _make_world()
    sw2 = _make_world()  # тот же simulation_id=1
    await registry.register(sw1, tick_seconds=10.0)
    await registry.register(sw2, tick_seconds=10.0)
    try:
        assert registry.active_count == 1
        # Должен остаться первый
        assert registry.get(1) is sw1
    finally:
        await registry.unregister(1)


@pytest.mark.asyncio
async def test_registry_shutdown_all_cancels_tasks():
    captured = _CapturedPublisher()
    registry = WorldRegistry(publisher=Publisher(publish_fn=captured))
    await registry.register(_make_world(1), tick_seconds=10.0)
    await registry.register(_make_world(2), tick_seconds=10.0)
    assert registry.active_count == 2
    await registry.shutdown_all()
    assert registry.active_count == 0


# --- LiveOrchestrator handler (без живого MQTT) -------------------------


@pytest.mark.asyncio
async def test_live_orchestrator_handle_command_unknown_zone_is_noop():
    """Команда для неизвестной зоны не падает и не публикует ответ."""
    captured = _CapturedPublisher()
    orch = LiveOrchestrator(mqtt_host="dummy", mqtt_port=1)
    orch.publisher = Publisher(publish_fn=captured)
    await orch._handle_command(
        "gh-x", "zn-y", "nd-1", "pump_a",
        {"cmd": "dose", "params": {"ml": 1.0}},
    )
    assert captured.messages == []


@pytest.mark.asyncio
async def test_live_orchestrator_handle_command_publishes_done_response():
    """Известная sim-zone — DT применяет cmd и публикует DONE."""
    captured = _CapturedPublisher()
    orch = LiveOrchestrator(mqtt_host="dummy", mqtt_port=1)
    orch.publisher = Publisher(publish_fn=captured)

    sw = SimWorld(
        simulation_id=99, zone_id=99, gh_uid="gh-1", zone_uid="sim-99",
        channels=[
            NodeChannelSpec("nd-ec", "pump_a", "ACTUATOR", None),
            NodeChannelSpec("nd-ec", "ec_sensor", "SENSOR", "EC"),
        ],
        initial_state={"ec": 1.0},
        time_scale=1.0,
    )
    await orch.registry.register(sw, tick_seconds=10.0)
    try:
        await orch._handle_command(
            "gh-1", "sim-99", "nd-ec", "pump_a",
            {"cmd": "dose", "params": {"ml": 2.0}, "cmd_id": "C1"},
        )
        # Должен прийти command_response DONE
        cr = [m for m in captured.messages if "/command_response" in m[0]]
        assert len(cr) == 1
        topic, payload = cr[0]
        assert topic == "hydro/gh-1/sim-99/nd-ec/pump_a/command_response"
        assert payload["status"] == "DONE"
        assert payload["cmd_id"] == "C1"
    finally:
        await orch.registry.unregister(99)


@pytest.mark.asyncio
async def test_live_orchestrator_handle_command_skips_when_cmd_empty():
    captured = _CapturedPublisher()
    orch = LiveOrchestrator(mqtt_host="dummy", mqtt_port=1)
    orch.publisher = Publisher(publish_fn=captured)
    sw = _make_world(7)
    await orch.registry.register(sw, tick_seconds=10.0)
    try:
        await orch._handle_command(
            "gh-1", "sim-7", "nd", "ch", {"cmd": "", "params": {}},
        )
        assert captured.messages == []
    finally:
        await orch.registry.unregister(7)

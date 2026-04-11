import asyncio
import json

from node_sim.test_node_profile import (
    PendingCommand,
    CommandKind,
    TestNodeSimulator,
    VIRTUAL_NODE_BY_UID,
)
from node_sim.model import NodeType


class _DummyMqtt:
    def __init__(self):
        self.messages = []
        self.subscriptions = []
        self.connection_callback = None
        self.connected = True

    def publish_json(self, topic, payload, qos=1, retain=False):
        self.messages.append((topic, payload, qos, retain))
        return True

    def subscribe(self, topic, callback, qos=1):
        self.subscriptions.append((topic, callback, qos))

    def set_connection_callback(self, callback):
        self.connection_callback = callback

    def is_connected(self):
        return self.connected


def test_build_config_report_matches_test_node_channels():
    mqtt = _DummyMqtt()
    sim = TestNodeSimulator(mqtt)

    payload = sim.build_config_report_payload(VIRTUAL_NODE_BY_UID["nd-test-irrig-1"])

    assert payload["node_id"] == "nd-test-irrig-1"
    assert payload["type"] == "irrig"
    assert payload["wifi"]["configured"] is False
    assert len(payload["channels"]) == 10
    pump_main = next(item for item in payload["channels"] if item["name"] == "pump_main")
    assert pump_main["actuator_type"] == "PUMP"
    assert pump_main["safe_limits"]["max_duration_ms"] == 3600000
    level_clean_min = next(item for item in payload["channels"] if item["name"] == "level_clean_min")
    assert level_clean_min["metric"] == "WATER_LEVEL_SWITCH"
    assert level_clean_min["poll_interval_ms"] == 5000


def test_build_config_report_includes_soil_node_channels():
    mqtt = _DummyMqtt()
    sim = TestNodeSimulator(mqtt)

    payload = sim.build_config_report_payload(VIRTUAL_NODE_BY_UID["nd-test-soil-1"])

    assert payload["node_id"] == "nd-test-soil-1"
    assert payload["type"] == "water_sensor"
    soil_moisture = next(item for item in payload["channels"] if item["name"] == "soil_moisture")
    assert soil_moisture["metric"] == "SOIL_MOISTURE"
    system = next(item for item in payload["channels"] if item["name"] == "system")
    assert system["actuator_type"] == "RELAY"


def test_node_type_enum_accepts_water_sensor():
    assert NodeType("water_sensor") is NodeType.WATER_SENSOR


def test_staged_clean_fill_min_switch_after_delay():
    mqtt = _DummyMqtt()
    sim = TestNodeSimulator(mqtt)

    sim.state.clean_fill_stage_active = True
    sim.state.clean_fill_started_at = sim.get_timestamp_seconds() - 5

    assert sim.resolve_clean_min_switch_value() == 1.0


def test_staged_solution_fill_max_switch_after_three_minutes():
    mqtt = _DummyMqtt()
    sim = TestNodeSimulator(mqtt)

    sim.state.solution_fill_stage_active = True
    sim.state.solution_fill_started_at = sim.get_timestamp_seconds() - 179
    sim.apply_passive_drift()

    assert sim.state.solution_max_latched is False

    sim.state.solution_fill_stage_active = True
    sim.state.solution_fill_started_at = sim.get_timestamp_seconds() - 180
    sim.apply_passive_drift()

    assert sim.state.solution_max_latched is True


def test_state_query_includes_fault_modes_after_set_fault_mode():
    mqtt = _DummyMqtt()
    sim = TestNodeSimulator(mqtt)

    asyncio.run(
        sim.execute_pending_command(
            PendingCommand(
                node_uid="nd-test-irrig-1",
                channel="storage_state",
                cmd_id="cmd-fault-1",
                cmd="set_fault_mode",
                kind=CommandKind.ACTUATOR,
                params={
                    "sensor_conflict_clean": True,
                    "level_clean_max_override": True,
                    "sim_delay_ms": 50,
                },
                execute_delay_ms=0,
            )
        )
    )
    asyncio.run(
        sim.execute_pending_command(
            PendingCommand(
                node_uid="nd-test-irrig-1",
                channel="storage_state",
                cmd_id="cmd-state-1",
                cmd="state",
                kind=CommandKind.STATE_QUERY,
                params={},
                execute_delay_ms=0,
            )
        )
    )

    _, payload, _, _ = mqtt.messages[-1]
    assert payload["status"] == "DONE"
    assert payload["details"]["fault_modes"]["sensor_conflict_clean"] is True
    assert payload["details"]["fault_modes"]["level_clean_max_override"] == "on"
    assert payload["details"]["snapshot"]["clean_level_max"] is True


def test_reset_binding_applies_after_reboot():
    mqtt = _DummyMqtt()
    sim = TestNodeSimulator(mqtt, gh_uid="gh-live", zone_uid="zn-live")

    asyncio.run(
        sim.execute_pending_command(
            PendingCommand(
                node_uid="nd-test-irrig-1",
                channel="system",
                cmd_id="cmd-bind-reset",
                cmd="reset_binding",
                kind=CommandKind.ACTUATOR,
                params={},
                execute_delay_ms=0,
            )
        )
    )
    asyncio.run(
        sim.execute_pending_command(
            PendingCommand(
                node_uid="nd-test-irrig-1",
                channel="system",
                cmd_id="cmd-reboot",
                cmd="reboot",
                kind=CommandKind.RESTART,
                params={},
                execute_delay_ms=0,
            )
        )
    )

    assert sim.persisted_boot_namespace == ("gh-temp", "zn-temp")
    assert sim.get_node_namespace("nd-test-irrig-1").gh_uid == "gh-temp"
    assert sim.get_node_namespace("nd-test-ph-1").zone_uid == "zn-temp"
    restarting = [msg for msg in mqtt.messages if msg[1].get("status") == "RESTARTING"]
    assert restarting


def test_process_command_auto_binds_namespace_and_enables_ph_telemetry():
    mqtt = _DummyMqtt()
    sim = TestNodeSimulator(mqtt)

    async def _run():
        await sim.start()
        payload = {
            "cmd_id": "cmd-activate-ph",
            "cmd": "activate_sensor_mode",
            "params": {"sim_delay_ms": 50},
            "ts": 1_737_979_200,
            "sig": "a" * 64,
        }
        await sim.process_command_payload(
            "hydro/gh-live/zn-live/nd-test-ph-1/system/command",
            json.dumps(payload).encode("utf-8"),
        )
        await asyncio.sleep(0.1)
        sim.publish_virtual_telemetry_batch()
        await sim.stop()

    asyncio.run(_run())

    assert sim.get_node_namespace("nd-test-ph-1").gh_uid == "gh-live"
    responses = [msg for msg in mqtt.messages if msg[0].endswith("/system/command_response")]
    assert responses[0][1]["status"] == "ACK"
    assert responses[1][1]["status"] == "DONE"
    ph_telemetry = [msg for msg in mqtt.messages if msg[0].endswith("/ph_sensor/telemetry")]
    assert ph_telemetry
    assert ph_telemetry[-1][1]["corrections_allowed"] is True


def test_process_config_ignores_temp_topic_for_configured_node():
    mqtt = _DummyMqtt()
    sim = TestNodeSimulator(mqtt, gh_uid="gh-test-1", zone_uid="zn-test-1")

    async def _run():
        await sim.start()
        await sim.process_config_payload(
            "hydro/gh-temp/zn-temp/nd-test-irrig-1/config",
            json.dumps(
                {
                    "gh_uid": "gh-temp",
                    "zone_uid": "zn-temp",
                }
            ).encode("utf-8"),
        )
        await sim.stop()

    asyncio.run(_run())

    namespace = sim.get_node_namespace("nd-test-irrig-1")
    assert namespace.gh_uid == "gh-test-1"
    assert namespace.zone_uid == "zn-test-1"


def test_publish_virtual_telemetry_batch_can_skip_aux_telemetry():
    mqtt = _DummyMqtt()
    sim = TestNodeSimulator(mqtt, publish_aux_telemetry=False)

    sim.publish_virtual_telemetry_batch()

    telemetry_topics = [topic for topic, _, _, _ in mqtt.messages if topic.endswith("/telemetry")]
    assert any(topic.endswith("/level_clean_min/telemetry") for topic in telemetry_topics)
    assert any(topic.endswith("/soil_moisture/telemetry") for topic in telemetry_topics)
    assert not any("/nd-test-climate-1/" in topic for topic in telemetry_topics)
    assert not any("/nd-test-light-1/" in topic for topic in telemetry_topics)


def test_set_fault_mode_updates_soil_moisture_snapshot():
    mqtt = _DummyMqtt()
    sim = TestNodeSimulator(mqtt)

    asyncio.run(
        sim.execute_pending_command(
            PendingCommand(
                node_uid="nd-test-soil-1",
                channel="system",
                cmd_id="cmd-soil-fault-1",
                cmd="set_fault_mode",
                kind=CommandKind.ACTUATOR,
                params={"soil_moisture_pct": 31.5},
                execute_delay_ms=0,
            )
        )
    )

    _, payload, _, _ = mqtt.messages[-1]
    assert payload["status"] == "DONE"
    assert payload["details"]["soil_moisture_pct"] == 31.5
    assert sim.state.soil_moisture == 31.5


def test_soil_moisture_rises_during_irrigation_and_then_dries_back():
    mqtt = _DummyMqtt()
    sim = TestNodeSimulator(mqtt)
    sim.state.soil_moisture = 43.0

    sim.state.main_pump_on = True
    sim.state.valve_solution_supply_on = True
    sim.state.valve_irrigation_on = True
    for _ in range(6):
        sim.apply_passive_drift()
    raised = sim.state.soil_moisture

    sim.state.main_pump_on = False
    sim.state.valve_solution_supply_on = False
    sim.state.valve_irrigation_on = False
    for _ in range(12):
        sim.apply_passive_drift()
    dried = sim.state.soil_moisture

    assert raised > 43.0
    assert dried < raised


def test_soil_moisture_dynamics_scale_with_telemetry_interval():
    fast = TestNodeSimulator(_DummyMqtt(), telemetry_interval_ms=2000)
    slow = TestNodeSimulator(_DummyMqtt(), telemetry_interval_ms=5000)

    fast.state.soil_moisture = 43.0
    slow.state.soil_moisture = 43.0
    fast.state.main_pump_on = True
    fast.state.valve_solution_supply_on = True
    fast.state.valve_irrigation_on = True
    slow.state.main_pump_on = True
    slow.state.valve_solution_supply_on = True
    slow.state.valve_irrigation_on = True

    for _ in range(15):
        fast.apply_passive_drift()
    for _ in range(6):
        slow.apply_passive_drift()

    assert abs(fast.state.soil_moisture - slow.state.soil_moisture) < 1.5

    fast.state.main_pump_on = False
    fast.state.valve_solution_supply_on = False
    fast.state.valve_irrigation_on = False
    slow.state.main_pump_on = False
    slow.state.valve_solution_supply_on = False
    slow.state.valve_irrigation_on = False

    for _ in range(15):
        fast.apply_passive_drift()
    for _ in range(6):
        slow.apply_passive_drift()

    assert abs(fast.state.soil_moisture - slow.state.soil_moisture) < 1.5


def test_ec_correction_hold_prevents_fast_regression_during_observe_window():
    held = TestNodeSimulator(_DummyMqtt())
    released = TestNodeSimulator(_DummyMqtt())

    for sim in (held, released):
        sim.state.ec_value = 1.92
        sim.state.ec_sensor_mode_active = True
        sim.state.main_pump_on = True
        sim.state.valve_solution_supply_on = True
        sim.state.valve_solution_fill_on = True
        asyncio.run(
            sim.execute_pending_command(
                PendingCommand(
                    node_uid="nd-test-ec-1",
                    channel="pump_a",
                    cmd_id="cmd-ec-dose-1",
                    cmd="dose",
                    kind=CommandKind.ACTUATOR,
                    params={"ml": 6.0},
                    execute_delay_ms=0,
                )
            )
        )

    released.state.ec_drift_hold_ticks = 0

    for _ in range(20):
        held.apply_passive_drift()
        released.apply_passive_drift()

    assert held.state.ec_value > released.state.ec_value + 0.04


def test_set_fault_mode_updates_ph_and_ec_snapshot():
    mqtt = _DummyMqtt()
    sim = TestNodeSimulator(mqtt)

    asyncio.run(
        sim.execute_pending_command(
            PendingCommand(
                node_uid="nd-test-irrig-1",
                channel="storage_state",
                cmd_id="cmd-storage-fault-1",
                cmd="set_fault_mode",
                kind=CommandKind.ACTUATOR,
                params={"ph_value": 5.8, "ec_value": 1.4},
                execute_delay_ms=0,
            )
        )
    )

    _, payload, _, _ = mqtt.messages[-1]
    assert payload["status"] == "DONE"
    assert payload["details"]["ph_value"] == 5.8
    assert payload["details"]["ec_value"] == 1.4
    assert sim.state.ph_value == 5.8
    assert sim.state.ec_value == 1.4

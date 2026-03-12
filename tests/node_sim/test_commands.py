import pytest
import asyncio

from node_sim.commands import CommandHandler, CommandStatus
from node_sim.model import NodeModel, NodeType


def _make_node(node_type: NodeType) -> NodeModel:
    return NodeModel(
        gh_uid="gh-1",
        zone_uid="zn-1",
        node_uid="nd-1",
        hardware_id="hw-1",
        node_type=node_type,
    )


def test_dose_applies_ph_change():
    node = _make_node(NodeType.PH)
    handler = CommandHandler(node, mqtt_client=None)

    status, details = handler._handle_dose("dose", {"ml": 10, "type": "add_acid"})

    assert status == CommandStatus.DONE
    assert details["ph_before"] == pytest.approx(6.0)
    assert details["ph_after"] == pytest.approx(5.9)
    assert node.get_sensor_value("ph_sensor") == pytest.approx(5.9)


def test_dose_missing_ml_invalid():
    node = _make_node(NodeType.PH)
    handler = CommandHandler(node, mqtt_client=None)

    status, details = handler._handle_dose("dose", {"type": "add_acid"})

    assert status == CommandStatus.INVALID
    assert details["error"] == "Missing 'ml' parameter"


def test_run_pump_applies_ec_change():
    node = _make_node(NodeType.EC)
    handler = CommandHandler(node, mqtt_client=None)

    status, details = handler._handle_run(
        "run_pump",
        {"duration_ms": 0, "type": "add_nutrients", "ml": 5.0},
    )

    assert status == CommandStatus.DONE
    dose_details = details["dose"]
    assert dose_details["ec_before"] == pytest.approx(1.5)
    assert dose_details["ec_after"] == pytest.approx(1.6)
    assert node.get_sensor_value("ec_sensor") == pytest.approx(1.6)


def test_validate_command_payload_invalid_sig_is_hmac_error():
    node = _make_node(NodeType.PH)
    handler = CommandHandler(node, mqtt_client=None)

    payload = {
        "cmd_id": "cmd-123",
        "cmd": "dose",
        "params": {"ml": 1.2},
        "ts": 1737979200,
        "sig": "deadbeef",
    }

    assert handler._validate_command_payload(payload) == ("invalid_hmac_format", "Invalid sig")


def test_send_error_response_uses_unknown_cmd_id_when_missing():
    published = []

    class _DummyMqtt:
        def publish_json(self, topic, payload, qos=1):
            published.append((topic, payload, qos))

    node = _make_node(NodeType.PH)
    handler = CommandHandler(node, mqtt_client=_DummyMqtt())

    asyncio.run(
        handler._send_error_response(
            "ph_sensor",
            None,
            "ERROR",
            "Invalid command payload",
            error_code="invalid_command_format",
        )
    )

    assert len(published) == 1
    _, payload, _ = published[0]
    assert payload["cmd_id"] == "unknown"
    assert payload["status"] == "ERROR"
    assert payload["details"]["error_code"] == "invalid_command_format"


def test_handle_command_rejects_actuator_command_on_sensor_channel():
    published = []

    class _DummyMqtt:
        def publish_json(self, topic, payload, qos=1):
            published.append((topic, payload, qos))

    node = _make_node(NodeType.PH)
    handler = CommandHandler(node, mqtt_client=_DummyMqtt())

    asyncio.run(
        handler._handle_command(
            channel="ph_sensor",
            cmd_id="cmd-compat-1",
            cmd="set_relay",
            params={"state": True},
            exec_time_ms=100,
        )
    )

    assert len(published) == 1
    _, payload, _ = published[0]
    assert payload["status"] == "INVALID"
    assert payload["details"]["error_code"] == "unsupported_channel_cmd"


def test_sensor_mode_commands_toggle_flags_for_ph_node():
    node = _make_node(NodeType.PH)
    handler = CommandHandler(node, mqtt_client=None)

    status, details = handler._handle_activate_sensor_mode(
        "activate_sensor_mode",
        {"channel": "system"},
    )
    assert status == CommandStatus.DONE
    assert details["details"] == "sensor_mode_activated"
    assert node.ph_sensor_mode_active is True

    status, details = handler._handle_activate_sensor_mode(
        "activate_sensor_mode",
        {"channel": "system"},
    )
    assert status == CommandStatus.NO_EFFECT
    assert details["note"] == "sensor_mode_already_active"

    status, details = handler._handle_deactivate_sensor_mode(
        "deactivate_sensor_mode",
        {"channel": "system"},
    )
    assert status == CommandStatus.DONE
    assert details["details"] == "sensor_mode_deactivated"
    assert node.ph_sensor_mode_active is False


def test_state_command_returns_snapshot_for_storage_state_channel():
    node = NodeModel(
        gh_uid="gh-1",
        zone_uid="zn-1",
        node_uid="nd-irrig-1",
        hardware_id="hw-irrig-1",
        node_type=NodeType.IRRIG,
        actuators=["valve_clean_fill", "pump_main"],
        sensors=["level_clean_max"],
    )
    handler = CommandHandler(node, mqtt_client=None)

    node.set_actuator("valve_clean_fill", True)
    node.set_actuator("pump_main", False)
    node.set_sensor_value("level_clean_max", 1.0)

    status, details = handler._handle_state("state", {"channel": "storage_state"})

    assert status == CommandStatus.DONE
    assert details["snapshot"]["valve_clean_fill"] is True
    assert details["snapshot"]["pump_main"] is False
    assert details["snapshot"]["clean_level_max"] is True
    assert details["state"]["level_clean_max"] is True


def test_state_command_rejects_non_storage_state_channel():
    node = _make_node(NodeType.IRRIG)
    handler = CommandHandler(node, mqtt_client=None)

    error = handler._validate_command_channel_compatibility("pump_main", "state")
    assert error is not None
    assert "storage_state" in error

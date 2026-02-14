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

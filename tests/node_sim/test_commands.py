import pytest

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

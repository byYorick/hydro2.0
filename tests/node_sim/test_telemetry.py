import asyncio

from node_sim.model import NodeModel, NodeType
from node_sim.telemetry import TelemetryPublisher


class _DummyMqtt:
    def __init__(self):
        self.messages = []

    def publish_json(self, topic, payload, qos=1, retain=False):
        self.messages.append((topic, payload, qos, retain))


def _make_node(node_type: NodeType) -> NodeModel:
    return NodeModel(
        gh_uid="gh-1",
        zone_uid="zn-1",
        node_uid="nd-1",
        hardware_id="hw-1",
        node_type=node_type,
    )


def test_ph_telemetry_includes_sensor_mode_flags():
    node = _make_node(NodeType.PH)
    mqtt = _DummyMqtt()
    publisher = TelemetryPublisher(node=node, mqtt=mqtt, telemetry_interval_s=5.0)

    asyncio.run(publisher._publish_channel_telemetry("ph_sensor"))
    _, payload, _, _ = mqtt.messages[-1]
    assert payload["flow_active"] is False
    assert payload["stable"] is False
    assert payload["corrections_allowed"] is False

    node.ph_sensor_mode_active = True
    asyncio.run(publisher._publish_channel_telemetry("ph_sensor"))
    _, payload, _, _ = mqtt.messages[-1]
    assert payload["flow_active"] is True
    assert payload["stable"] is True
    assert payload["corrections_allowed"] is True

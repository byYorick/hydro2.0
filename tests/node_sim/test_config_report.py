from node_sim.config_report import build_config_report_payload
from node_sim.model import NodeModel, NodeType
from node_sim.mqtt_client import MqttClient
from node_sim.telemetry import TelemetryPublisher


def test_build_config_report_payload_maps_level_switch_channels_to_water_level_switch():
    node = NodeModel(
        gh_uid="gh-sim",
        zone_uid="zn-sim",
        node_uid="nd-irrig-sim",
        hardware_id="hw-irrig-sim",
        node_type=NodeType.IRRIG,
        sensors=[
            "level_clean_min",
            "level_clean_max",
            "level_solution_min",
            "level_solution_max",
            "flow_present",
            "pump_bus_current",
        ],
        actuators=["pump_main"],
    )
    mqtt = MqttClient(host="mqtt", port=1883, keepalive=60)

    payload = build_config_report_payload(node, mqtt, telemetry_interval_s=5.0)
    channels = {item["name"]: item for item in payload["channels"]}

    assert channels["level_clean_min"]["metric"] == "WATER_LEVEL_SWITCH"
    assert channels["level_clean_max"]["metric"] == "WATER_LEVEL_SWITCH"
    assert channels["level_solution_min"]["metric"] == "WATER_LEVEL_SWITCH"
    assert channels["level_solution_max"]["metric"] == "WATER_LEVEL_SWITCH"
    assert channels["flow_present"]["metric"] == "FLOW_RATE"
    assert channels["pump_bus_current"]["metric"] == "PUMP_CURRENT"


def test_build_config_report_payload_keeps_soil_moisture_metric_canonical():
    node = NodeModel(
        gh_uid="gh-sim",
        zone_uid="zn-sim",
        node_uid="nd-irrig-sim",
        hardware_id="hw-irrig-sim",
        node_type=NodeType.IRRIG,
        sensors=["soil_moisture"],
        actuators=["pump_main"],
    )
    mqtt = MqttClient(host="mqtt", port=1883, keepalive=60)

    payload = build_config_report_payload(node, mqtt, telemetry_interval_s=5.0)
    channels = {item["name"]: item for item in payload["channels"]}

    assert channels["soil_moisture"]["metric"] == "SOIL_MOISTURE"


def test_telemetry_publisher_maps_level_switch_channels_to_water_level_switch():
    node = NodeModel(
        gh_uid="gh-sim",
        zone_uid="zn-sim",
        node_uid="nd-irrig-sim",
        hardware_id="hw-irrig-sim",
        node_type=NodeType.IRRIG,
        sensors=["level_clean_min", "level_solution_min"],
        actuators=["pump_main"],
    )
    mqtt = MqttClient(host="mqtt", port=1883, keepalive=60)
    publisher = TelemetryPublisher(node=node, mqtt=mqtt, telemetry_interval_s=5.0)

    assert publisher._get_metric_type("level_clean_min") == "WATER_LEVEL_SWITCH"
    assert publisher._get_metric_type("level_solution_min") == "WATER_LEVEL_SWITCH"
    assert publisher._get_metric_type("flow_present") == "FLOW_RATE"
    assert publisher._get_metric_type("pump_bus_current") == "PUMP_CURRENT"


def test_telemetry_publisher_keeps_soil_moisture_metric_canonical():
    node = NodeModel(
        gh_uid="gh-sim",
        zone_uid="zn-sim",
        node_uid="nd-irrig-sim",
        hardware_id="hw-irrig-sim",
        node_type=NodeType.IRRIG,
        sensors=["soil_moisture"],
        actuators=["pump_main"],
    )
    mqtt = MqttClient(host="mqtt", port=1883, keepalive=60)
    publisher = TelemetryPublisher(node=node, mqtt=mqtt, telemetry_interval_s=5.0)

    assert publisher._get_metric_type("soil_moisture") == "SOIL_MOISTURE"

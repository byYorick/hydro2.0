"""
Публикация config_report для node-sim.
"""

from typing import Dict, List, Optional

from .logging import get_logger
from .model import NodeModel, NodeType
from .mqtt_client import MqttClient
from .topics import config_report, temp_config_report

logger = get_logger(__name__)

_CONFIG_VERSION = 3

_NODE_TYPE_MAP = {
    NodeType.PH: "ph_node",
    NodeType.EC: "ec_node",
    NodeType.CLIMATE: "climate_node",
    NodeType.PUMP: "pump_node",
    NodeType.IRRIG: "pump_node",
    NodeType.LIGHT: "lighting_node",
    NodeType.UNKNOWN: "unknown",
}

_METRIC_UNITS = {
    "PH": "pH",
    "EC": "mS/cm",
    "TEMPERATURE": "C",
    "HUMIDITY": "%",
    "CO2": "ppm",
    "LIGHT_INTENSITY": "lux",
    "PUMP_CURRENT": "mA",
}


def _normalize_sensor_channel(sensor_name: str) -> str:
    if sensor_name == "ina209_ma":
        return "ina209"
    return sensor_name


def _sensor_metric(sensor_name: str) -> str:
    name = sensor_name.lower()
    if name in ("ph_sensor", "ph"):
        return "PH"
    if name in ("ec_sensor", "ec"):
        return "EC"
    if name in ("solution_temp_c", "temp_solution", "solution_temp"):
        return "TEMPERATURE"
    if name in ("air_temp_c", "temp_air", "temperature", "temp"):
        return "TEMPERATURE"
    if name in ("air_rh", "humidity", "rh"):
        return "HUMIDITY"
    if "co2" in name:
        return "CO2"
    if "lux" in name:
        return "LIGHT_INTENSITY"
    if name in ("ina209_ma", "current_ma", "current"):
        return "PUMP_CURRENT"
    if name in ("flow_present", "flow"):
        return "FLOW_RATE"
    return name.upper()


def _actuator_type(actuator_name: str) -> str:
    name = actuator_name.lower()
    if "pump" in name:
        return "PUMP"
    if "fan" in name:
        return "FAN"
    if "heater" in name:
        return "HEATER"
    if "light" in name or "led" in name:
        return "LED"
    if "valve" in name:
        return "VALVE"
    if "drive" in name:
        return "DRIVE"
    if "pwm" in name:
        return "PWM"
    return "RELAY"


def _node_type_name(node_type: NodeType) -> str:
    return _NODE_TYPE_MAP.get(node_type, str(node_type))


def _build_channels(node: NodeModel, poll_interval_ms: Optional[int]) -> List[Dict[str, object]]:
    channels: List[Dict[str, object]] = []
    seen = set()

    for sensor in node.sensors:
        channel_name = _normalize_sensor_channel(sensor)
        if channel_name in seen:
            continue
        seen.add(channel_name)
        metric = _sensor_metric(sensor)
        entry: Dict[str, object] = {
            "name": channel_name,
            "type": "SENSOR",
            "metric": metric,
        }
        if poll_interval_ms is not None:
            entry["poll_interval_ms"] = poll_interval_ms
        unit = _METRIC_UNITS.get(metric)
        if unit:
            entry["unit"] = unit
        channels.append(entry)

    for actuator in node.actuators:
        if actuator in seen:
            continue
        seen.add(actuator)
        channels.append(
            {
                "name": actuator,
                "type": "ACTUATOR",
                "actuator_type": _actuator_type(actuator),
            }
        )

    return channels


def build_config_report_payload(
    node: NodeModel,
    mqtt: MqttClient,
    telemetry_interval_s: float,
    version: int = _CONFIG_VERSION,
) -> Dict[str, object]:
    poll_interval_ms = None
    if telemetry_interval_s and telemetry_interval_s > 0:
        poll_interval_ms = int(telemetry_interval_s * 1000)

    mqtt_payload: Dict[str, object] = {
        "host": mqtt.host,
        "port": mqtt.port,
    }
    if mqtt.username:
        mqtt_payload["username"] = mqtt.username
    if mqtt.tls:
        mqtt_payload["tls"] = mqtt.tls

    payload = {
        "node_id": node.node_uid,
        "version": version,
        "type": _node_type_name(node.node_type),
        "gh_uid": node.gh_uid,
        "zone_uid": node.zone_uid,
        "channels": _build_channels(node, poll_interval_ms),
        "wifi": {"ssid": "node-sim"},
        "mqtt": mqtt_payload,
    }
    return payload


def publish_config_report(
    node: NodeModel,
    mqtt: MqttClient,
    telemetry_interval_s: float,
    version: int = _CONFIG_VERSION,
) -> bool:
    payload = build_config_report_payload(
        node=node,
        mqtt=mqtt,
        telemetry_interval_s=telemetry_interval_s,
        version=version,
    )
    if node.mode == "preconfig":
        topic = temp_config_report(node.node_uid)
    else:
        topic = config_report(node.gh_uid, node.zone_uid, node.node_uid)

    ok = mqtt.publish_json(topic, payload, qos=1, retain=False)
    if ok:
        logger.info(f"Published config_report to {topic}")
    else:
        logger.error(f"Failed to publish config_report to {topic}")
    return ok

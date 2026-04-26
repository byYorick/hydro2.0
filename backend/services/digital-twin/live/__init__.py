"""Live-режим Digital Twin (Phase C).

DT работает как физический backend для симулированных зон:
- слушает cmd-топики симулированных зон (`MqttBridge`)
- держит фоновые ZoneWorld'ы (`WorldRegistry` + `SimWorld`)
- публикует physics-based telemetry, command_response и level events (`Publisher`)
"""
from .mqtt_bridge import MqttBridge
from .orchestrator import LiveOrchestrator, load_zone_channels
from .publisher import Publisher
from .sim_world import LevelSwitchEvent, NodeChannelSpec, SensorSample, SimWorld
from .world_registry import WorldRegistry

__all__ = [
    "MqttBridge",
    "Publisher",
    "SimWorld",
    "NodeChannelSpec",
    "SensorSample",
    "LevelSwitchEvent",
    "WorldRegistry",
    "LiveOrchestrator",
    "load_zone_channels",
]

"""
Runtime-профиль node-sim, повторяющий MQTT-логику firmware/test_node.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .logging import get_logger

logger = get_logger(__name__)

DEFAULT_MQTT_NODE_UID = "nd-test-irrig-1"
DEFAULT_GH_UID = "gh-test-1"
DEFAULT_ZONE_UID = "zn-test-1"
PRECONFIG_GH_UID = "gh-temp"
PRECONFIG_ZONE_UID = "zn-temp"

TELEMETRY_INTERVAL_MS = 5000
CONFIG_REPORT_INTERVAL_MS = 30000
COMMAND_QUEUE_LENGTH = 32
STATE_COMMAND_QUEUE_LENGTH = 12
COMMAND_WILDCARD_TOPIC = "hydro/+/+/+/+/command"
CONFIG_WILDCARD_TOPIC = "hydro/+/+/+/config"

CLEAN_FILL_MIN_DELAY_SEC = 10
CLEAN_FILL_DELAY_SEC = 30
SOLUTION_FILL_MIN_DELAY_SEC = 10
SOLUTION_FILL_DELAY_SEC = 180
CLEAN_MAX_LATCH_LEVEL = 0.92
SOLUTION_MAX_LATCH_LEVEL = 0.92
IRR_STATE_MAX_AGE_SEC = 30

PH_DRIFT_BIAS_PER_TICK = 0.0005
EC_DRIFT_BIAS_PER_TICK = -0.0025
PH_REACTION_BASE_DELTA = 0.10
EC_REACTION_BASE_DELTA = 0.055
PH_REACTION_NOMINAL_ML = 8.0
EC_REACTION_NOMINAL_ML = 12.0
CORRECTION_DURATION_TO_ML_PER_SEC = 1.0
CORRECTION_FILL_PHASE_FACTOR = 0.50
CORRECTION_RECIRC_PH_PHASE_FACTOR = 2.50
CORRECTION_RECIRC_EC_PHASE_FACTOR = 3.20
CORRECTION_SETTLE_TICKS = 4
CORRECTION_REACTION_SCALE_MIN = 0.5
CORRECTION_REACTION_SCALE_MAX = 5.0
CORRECTION_FLOW_DRIFT_HOLD_SEC = 120
CORRECTION_IDLE_DRIFT_HOLD_SEC = 24

TRANSIENT_DELAY_BASE_MIN_MS = 220
TRANSIENT_DELAY_BASE_MAX_MS = 460
TRANSIENT_DELAY_EXTRA_MIN_MS = 160
TRANSIENT_DELAY_EXTRA_MAX_MS = 360
TRANSIENT_DELAY_SCALE_PERCENT = 10
TRANSIENT_DELAY_SCALE_MIN_MS = 220
TRANSIENT_DELAY_SCALE_MAX_MS = 6500

COMMAND_DEDUP_WINDOW_SEC = 180
COMMAND_DEDUP_CACHE_SIZE = 32
MIN_VALID_UNIX_TS_SEC = 1_000_000_000

_SIG_HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class ChannelDef:
    name: str
    type: str
    metric: Optional[str] = None
    is_actuator: bool = False


@dataclass(frozen=True)
class VirtualNodeDef:
    node_uid: str
    node_type: str
    channels: tuple[ChannelDef, ...]


@dataclass
class NamespaceState:
    gh_uid: str
    zone_uid: str

    @property
    def preconfig_mode(self) -> bool:
        return self.gh_uid == PRECONFIG_GH_UID or self.zone_uid == PRECONFIG_ZONE_UID


@dataclass
class VirtualState:
    flow_rate: float = 0.0
    pump_bus_current: float = 150.0
    ph_value: float = 6.90
    ec_value: float = 0.60
    water_level: float = 0.05
    solution_level: float = 0.05
    air_temp: float = 24.0
    air_humidity: float = 60.0
    light_level: float = 18000.0
    soil_moisture: float = 43.0

    irrigation_on: bool = False
    main_pump_on: bool = False
    valve_clean_fill_on: bool = False
    valve_clean_supply_on: bool = False
    valve_solution_fill_on: bool = False
    valve_solution_supply_on: bool = False
    valve_irrigation_on: bool = False
    clean_fill_stage_active: bool = False
    clean_max_latched: bool = False
    solution_fill_stage_active: bool = False
    solution_max_latched: bool = False
    tank_fill_on: bool = False
    tank_drain_on: bool = False
    fan_on: bool = False
    heater_on: bool = False
    light_on: bool = False
    ph_sensor_mode_active: bool = False
    ec_sensor_mode_active: bool = False
    force_clean_sensor_conflict: bool = False
    force_solution_sensor_conflict: bool = False
    simulate_clean_fill_timeout: bool = False
    simulate_solution_fill_timeout: bool = False
    level_clean_min_override: int = -1
    level_clean_max_override: int = -1
    level_solution_min_override: int = -1
    level_solution_max_override: int = -1

    light_pwm: int = 0
    irrigation_boost_ticks: int = 0
    correction_boost_ticks: int = 0
    ph_drift_hold_ticks: int = 0
    ec_drift_hold_ticks: int = 0
    clean_fill_started_at: int = 0
    solution_fill_started_at: int = 0


class CommandKind(str, Enum):
    SENSOR_PROBE = "sensor_probe"
    ACTUATOR = "actuator"
    CONFIG_REPORT = "config_report"
    RESTART = "restart"
    GENERIC = "generic"
    STATE_QUERY = "state_query"


@dataclass
class PendingCommand:
    node_uid: str
    channel: str
    cmd_id: str
    cmd: str
    kind: CommandKind
    params: dict[str, Any]
    execute_delay_ms: int


IRRIGATION_CHANNELS = (
    ChannelDef("pump_main", "ACTUATOR", is_actuator=True),
    ChannelDef("valve_clean_fill", "ACTUATOR", is_actuator=True),
    ChannelDef("valve_clean_supply", "ACTUATOR", is_actuator=True),
    ChannelDef("valve_solution_fill", "ACTUATOR", is_actuator=True),
    ChannelDef("valve_solution_supply", "ACTUATOR", is_actuator=True),
    ChannelDef("valve_irrigation", "ACTUATOR", is_actuator=True),
    ChannelDef("level_clean_min", "SENSOR", "WATER_LEVEL_SWITCH"),
    ChannelDef("level_clean_max", "SENSOR", "WATER_LEVEL_SWITCH"),
    ChannelDef("level_solution_min", "SENSOR", "WATER_LEVEL_SWITCH"),
    ChannelDef("level_solution_max", "SENSOR", "WATER_LEVEL_SWITCH"),
)

PH_CORRECTION_CHANNELS = (
    ChannelDef("ph_sensor", "SENSOR", "PH"),
    ChannelDef("pump_acid", "ACTUATOR", is_actuator=True),
    ChannelDef("pump_base", "ACTUATOR", is_actuator=True),
    ChannelDef("system", "ACTUATOR", is_actuator=True),
)

EC_CORRECTION_CHANNELS = (
    ChannelDef("ec_sensor", "SENSOR", "EC"),
    ChannelDef("pump_a", "ACTUATOR", is_actuator=True),
    ChannelDef("pump_b", "ACTUATOR", is_actuator=True),
    ChannelDef("pump_c", "ACTUATOR", is_actuator=True),
    ChannelDef("pump_d", "ACTUATOR", is_actuator=True),
    ChannelDef("system", "ACTUATOR", is_actuator=True),
)

CLIMATE_CHANNELS = (
    ChannelDef("air_temp_c", "SENSOR", "TEMPERATURE"),
    ChannelDef("air_rh", "SENSOR", "HUMIDITY"),
    ChannelDef("fan_air", "ACTUATOR", is_actuator=True),
    ChannelDef("fan", "ACTUATOR", is_actuator=True),
    ChannelDef("heater", "ACTUATOR", is_actuator=True),
)

LIGHT_CHANNELS = (
    ChannelDef("light_level", "SENSOR", "LIGHT_INTENSITY"),
    ChannelDef("white_light", "ACTUATOR", is_actuator=True),
)

SOIL_CHANNELS = (
    ChannelDef("soil_moisture", "SENSOR", "SOIL_MOISTURE"),
    ChannelDef("system", "ACTUATOR", is_actuator=True),
)

VIRTUAL_NODES: tuple[VirtualNodeDef, ...] = (
    VirtualNodeDef("nd-test-irrig-1", "irrig", IRRIGATION_CHANNELS),
    VirtualNodeDef("nd-test-ph-1", "ph", PH_CORRECTION_CHANNELS),
    VirtualNodeDef("nd-test-ec-1", "ec", EC_CORRECTION_CHANNELS),
    VirtualNodeDef("nd-test-climate-1", "climate", CLIMATE_CHANNELS),
    VirtualNodeDef("nd-test-light-1", "light", LIGHT_CHANNELS),
    VirtualNodeDef("nd-test-soil-1", "water_sensor", SOIL_CHANNELS),
)
VIRTUAL_NODE_BY_UID = {node.node_uid: node for node in VIRTUAL_NODES}


def clamp_float(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


class TestNodeSimulator:
    def __init__(
        self,
        mqtt_client,
        *,
        gh_uid: str = PRECONFIG_GH_UID,
        zone_uid: str = PRECONFIG_ZONE_UID,
        telemetry_interval_ms: int = TELEMETRY_INTERVAL_MS,
        heartbeat_interval_ms: int = TELEMETRY_INTERVAL_MS,
        config_report_interval_ms: int = CONFIG_REPORT_INTERVAL_MS,
        publish_aux_telemetry: bool = True,
    ) -> None:
        self.mqtt = mqtt_client
        self.telemetry_interval_ms = telemetry_interval_ms
        self.heartbeat_interval_ms = heartbeat_interval_ms
        self.config_report_interval_ms = config_report_interval_ms
        self.publish_aux_telemetry = publish_aux_telemetry

        self.state = VirtualState()
        self.persisted_boot_namespace = (
            gh_uid or DEFAULT_GH_UID,
            zone_uid or DEFAULT_ZONE_UID,
        )
        self.namespaces: dict[str, NamespaceState] = {}
        self._init_virtual_namespaces(*self.persisted_boot_namespace)

        self._start_monotonic = time.monotonic()
        self._timestamp_offset_sec = 0
        self._timestamp_offset_valid = False
        self._telemetry_tick = 0
        self._recent_cmd_ids: OrderedDict[str, float] = OrderedDict()

        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._tasks: list[asyncio.Task] = []
        self._command_queue: asyncio.Queue[PendingCommand] = asyncio.Queue(maxsize=COMMAND_QUEUE_LENGTH)
        self._state_command_queue: asyncio.Queue[PendingCommand] = asyncio.Queue(maxsize=STATE_COMMAND_QUEUE_LENGTH)
        self._config_report_on_connect_pending = True

    def _telemetry_tick_ratio(self) -> float:
        # Keep virtual plant dynamics stable if telemetry cadence differs from the nominal profile.
        return max(0.1, float(self.telemetry_interval_ms) / float(TELEMETRY_INTERVAL_MS))

    async def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._loop = asyncio.get_running_loop()

        if hasattr(self.mqtt, "set_connection_callback"):
            self.mqtt.set_connection_callback(self._on_connection_change)
        self.mqtt.subscribe(COMMAND_WILDCARD_TOPIC, self._on_command_message, qos=1)
        self.mqtt.subscribe(CONFIG_WILDCARD_TOPIC, self._on_config_message, qos=1)

        self._tasks = [
            asyncio.create_task(self._command_worker(self._command_queue)),
            asyncio.create_task(self._command_worker(self._state_command_queue)),
            asyncio.create_task(self._telemetry_loop()),
        ]

        if getattr(self.mqtt, "is_connected", lambda: True)():
            await self._handle_connection_change(True)

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()

    def _schedule_async(self, coro: Any) -> None:
        loop = self._loop
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, loop)
        else:
            asyncio.run(coro)

    def _on_connection_change(self, connected: bool) -> None:
        self._schedule_async(self._handle_connection_change(connected))

    async def _handle_connection_change(self, connected: bool) -> None:
        if not connected:
            self._config_report_on_connect_pending = True
            return

        self._config_report_on_connect_pending = True
        for node in VIRTUAL_NODES:
            self.publish_node_hello_for_node(node)
            self.publish_status_for_node(node.node_uid, "ONLINE")

    def _on_command_message(self, topic: str, payload: bytes) -> None:
        self._schedule_async(self.process_command_payload(topic, payload))

    def _on_config_message(self, topic: str, payload: bytes) -> None:
        self._schedule_async(self.process_config_payload(topic, payload))

    def get_uptime_seconds(self) -> int:
        return int(time.monotonic() - self._start_monotonic)

    def get_timestamp_seconds(self) -> int:
        wallclock = int(time.time())
        uptime = self.get_uptime_seconds()
        if wallclock >= MIN_VALID_UNIX_TS_SEC:
            return wallclock
        if self._timestamp_offset_valid:
            return uptime + self._timestamp_offset_sec
        return uptime

    def get_timestamp_ms(self) -> int:
        return self.get_timestamp_seconds() * 1000

    def maybe_calibrate_timestamp_offset_from_command_ts(self, command_ts_raw: int) -> None:
        command_ts_sec = int(command_ts_raw)
        if command_ts_sec > 1_000_000_000_000:
            command_ts_sec //= 1000
        if command_ts_sec < MIN_VALID_UNIX_TS_SEC:
            return

        uptime = self.get_uptime_seconds()
        self._timestamp_offset_sec = command_ts_sec - uptime
        self._timestamp_offset_valid = True

    def _trim_recent_cmd_ids(self) -> None:
        now_uptime = self.get_uptime_seconds()
        for cmd_id in list(self._recent_cmd_ids.keys()):
            seen_at = self._recent_cmd_ids[cmd_id]
            if (now_uptime - seen_at) > COMMAND_DEDUP_WINDOW_SEC:
                self._recent_cmd_ids.pop(cmd_id, None)
        while len(self._recent_cmd_ids) > COMMAND_DEDUP_CACHE_SIZE:
            self._recent_cmd_ids.popitem(last=False)

    def is_duplicate_cmd_id(self, cmd_id: Optional[str]) -> bool:
        if not cmd_id:
            return False
        self._trim_recent_cmd_ids()
        if cmd_id in self._recent_cmd_ids:
            return True
        self._recent_cmd_ids[cmd_id] = float(self.get_uptime_seconds())
        return False

    def _init_virtual_namespaces(self, gh_uid: str, zone_uid: str) -> None:
        safe_gh = gh_uid or DEFAULT_GH_UID
        safe_zone = zone_uid or DEFAULT_ZONE_UID
        for node in VIRTUAL_NODES:
            self.namespaces[node.node_uid] = NamespaceState(safe_gh, safe_zone)

    def get_node_namespace(self, node_uid: str) -> NamespaceState:
        return self.namespaces[node_uid]

    def update_node_namespace(self, node_uid: str, gh_uid: str, zone_uid: str) -> bool:
        current = self.namespaces[node_uid]
        if current.gh_uid == gh_uid and current.zone_uid == zone_uid:
            return False
        self.namespaces[node_uid] = NamespaceState(gh_uid, zone_uid)
        return True

    @staticmethod
    def is_temp_namespace(gh_uid: str, zone_uid: str) -> bool:
        return gh_uid == PRECONFIG_GH_UID and zone_uid == PRECONFIG_ZONE_UID

    def namespace_matches_node(self, node_uid: str, gh_uid: str, zone_uid: str) -> bool:
        current = self.get_node_namespace(node_uid)
        return current.gh_uid == gh_uid and current.zone_uid == zone_uid

    def build_topic(self, node_uid: str, channel: Optional[str], message_type: str) -> str:
        ns = self.get_node_namespace(node_uid)
        if channel:
            return f"hydro/{ns.gh_uid}/{ns.zone_uid}/{node_uid}/{channel}/{message_type}"
        return f"hydro/{ns.gh_uid}/{ns.zone_uid}/{node_uid}/{message_type}"

    def publish_json(self, topic: str, payload: dict[str, Any], *, retain: bool = False) -> bool:
        return bool(self.mqtt.publish_json(topic, payload, qos=1, retain=retain))

    def publish_status_for_node(self, node_uid: str, status: str) -> bool:
        return self.publish_json(
            self.build_topic(node_uid, None, "status"),
            {"status": status, "ts": self.get_timestamp_seconds()},
            retain=True,
        )

    def publish_heartbeat_for_node(self, node_uid: str) -> bool:
        payload = {
            "uptime": self.get_uptime_seconds(),
            "free_heap": 200000,
            "rssi": random.randint(-70, -50),
        }
        return self.publish_json(self.build_topic(node_uid, None, "heartbeat"), payload)

    def publish_telemetry_for_node(self, node_uid: str, channel: str, metric_type: str, value: float) -> bool:
        payload: dict[str, Any] = {
            "metric_type": metric_type,
            "value": value,
            "ts": self.get_timestamp_seconds(),
            "stub": True,
        }
        if channel == "ph_sensor":
            active = self.state.ph_sensor_mode_active
            payload["flow_active"] = active
            payload["stable"] = active
            payload["corrections_allowed"] = active
        elif channel == "ec_sensor":
            active = self.state.ec_sensor_mode_active
            payload["flow_active"] = active
            payload["stable"] = active
            payload["corrections_allowed"] = active
        return self.publish_json(self.build_topic(node_uid, channel, "telemetry"), payload)

    def publish_command_response(
        self,
        node_uid: str,
        channel: str,
        cmd_id: str,
        status: str,
        details: Optional[dict[str, Any]] = None,
    ) -> bool:
        payload: dict[str, Any] = {
            "cmd_id": cmd_id,
            "status": status,
            "ts": self.get_timestamp_ms(),
        }
        if details is not None:
            payload["details"] = details
        return self.publish_json(self.build_topic(node_uid, channel, "command_response"), payload)

    def publish_irrig_node_event(self, event_code: str) -> bool:
        payload = {
            "event_code": event_code,
            "ts": self.get_timestamp_seconds(),
            "snapshot": self.build_irr_state_snapshot(),
        }
        return self.publish_json(
            self.build_topic(DEFAULT_MQTT_NODE_UID, "storage_state", "event"),
            payload,
        )

    def resolve_node_hello_name(self, node_uid: str) -> str:
        if "-irrig-" in node_uid:
            return "Test: irrigation"
        if "-ph-" in node_uid:
            return "Test: pH correction"
        if "-ec-" in node_uid:
            return "Test: EC correction"
        if "-climate-" in node_uid:
            return "Test: climate"
        if "-light-" in node_uid:
            return "Test: light"
        if "-soil-" in node_uid:
            return "Test: soil moisture"
        return "Test node"

    def publish_node_hello_for_node(self, node: VirtualNodeDef) -> bool:
        payload = {
            "message_type": "node_hello",
            "hardware_id": node.node_uid,
            "node_type": node.node_type,
            "fw_version": "node-sim-test-node-profile",
            "hardware_revision": "python-sim",
            "capabilities": [channel.name for channel in node.channels],
            "provisioning_meta": {
                "node_uid": node.node_uid,
                "node_name": self.resolve_node_hello_name(node.node_uid),
                "virtual": True,
                "sim_group": "test_node_multi_v1",
            },
        }
        return self.publish_json("hydro/node_hello", payload)

    def resolve_actuator_type(self, channel_name: str) -> str:
        if "pump" in channel_name:
            return "PUMP"
        if "light" in channel_name:
            return "LED"
        if "fan" in channel_name:
            return "FAN"
        return "RELAY"

    def actuator_type_requires_relay_type(self, actuator_type: str) -> bool:
        return actuator_type.upper() in {"RELAY", "VALVE", "FAN", "HEATER"}

    def build_config_report_payload(self, node: VirtualNodeDef) -> dict[str, Any]:
        ns = self.get_node_namespace(node.node_uid)
        channels: list[dict[str, Any]] = []
        for channel in node.channels:
            entry: dict[str, Any] = {
                "name": channel.name,
                "type": channel.type,
            }
            if channel.is_actuator:
                actuator_type = self.resolve_actuator_type(channel.name)
                entry["actuator_type"] = actuator_type
                if self.actuator_type_requires_relay_type(actuator_type):
                    entry["relay_type"] = "NO"
                entry["safe_limits"] = {
                    "max_duration_ms": 3600000,
                    "min_off_ms": 1000,
                    "fail_safe_mode": "NO",
                }
            else:
                entry["metric"] = channel.metric or "UNKNOWN"
                entry["poll_interval_ms"] = self.telemetry_interval_ms
            channels.append(entry)

        return {
            "node_id": node.node_uid,
            "version": 3,
            "type": node.node_type,
            "gh_uid": ns.gh_uid,
            "zone_uid": ns.zone_uid,
            "channels": channels,
            "wifi": {"configured": not ns.preconfig_mode},
            "mqtt": {"configured": True},
        }

    def publish_config_report_for_node(self, node: VirtualNodeDef) -> bool:
        topic = self.build_topic(node.node_uid, None, "config_report")
        return self.publish_json(topic, self.build_config_report_payload(node))

    def publish_all_config_reports(self) -> bool:
        if not getattr(self.mqtt, "is_connected", lambda: True)():
            return False
        ok = True
        for node in VIRTUAL_NODES:
            ok = self.publish_config_report_for_node(node) and ok
        return ok

    @staticmethod
    def parse_command_topic(topic: str) -> Optional[tuple[str, str, str, str]]:
        parts = topic.split("/")
        if len(parts) != 6 or parts[0] != "hydro" or parts[5] != "command":
            return None
        return parts[1], parts[2], parts[3], parts[4]

    @staticmethod
    def parse_config_topic(topic: str) -> Optional[tuple[str, str, str]]:
        parts = topic.split("/")
        if len(parts) != 5 or parts[0] != "hydro" or parts[4] != "config":
            return None
        return parts[1], parts[2], parts[3]

    @staticmethod
    def has_only_canonical_command_fields(payload: dict[str, Any]) -> bool:
        return set(payload.keys()) <= {"cmd_id", "cmd", "params", "ts", "sig"}

    def validate_command_payload_strict(self, payload: Any) -> Optional[tuple[str, str]]:
        if not isinstance(payload, dict):
            return ("invalid_command_format", "Command payload must be JSON object")
        if not self.has_only_canonical_command_fields(payload):
            return ("invalid_command_format", "Unknown fields in command payload")
        if not isinstance(payload.get("cmd_id"), str) or not payload["cmd_id"]:
            return ("invalid_command_format", "Missing or invalid cmd_id")
        if not isinstance(payload.get("cmd"), str) or not payload["cmd"]:
            return ("invalid_command_format", "Missing or invalid cmd")
        if not isinstance(payload.get("params"), dict):
            return ("invalid_command_format", "Missing or invalid params")
        ts = payload.get("ts")
        if type(ts) is not int or ts < 0:
            return ("invalid_hmac_format", "Missing or invalid ts")
        sig = payload.get("sig")
        if not isinstance(sig, str) or not _SIG_HEX64_RE.fullmatch(sig):
            return ("invalid_hmac_format", "sig must be 64-char hex string")
        return None

    async def process_command_payload(self, topic: str, payload: bytes | str) -> None:
        parsed_topic = self.parse_command_topic(topic)
        if not parsed_topic:
            return
        topic_gh_uid, topic_zone_uid, node_uid, channel = parsed_topic

        if node_uid not in VIRTUAL_NODE_BY_UID:
            return

        if not self.namespace_matches_node(node_uid, topic_gh_uid, topic_zone_uid):
            current = self.get_node_namespace(node_uid)
            topic_is_temp = self.is_temp_namespace(topic_gh_uid, topic_zone_uid)
            if current.preconfig_mode and not topic_is_temp:
                logger.info(
                    "Auto-binding virtual node %s from %s/%s to %s/%s via command topic",
                    node_uid,
                    current.gh_uid,
                    current.zone_uid,
                    topic_gh_uid,
                    topic_zone_uid,
                )
                self.update_node_namespace(node_uid, topic_gh_uid, topic_zone_uid)
            else:
                logger.warning(
                    "Ignoring command for node %s due namespace mismatch: topic=%s/%s current=%s/%s channel=%s",
                    node_uid,
                    topic_gh_uid,
                    topic_zone_uid,
                    current.gh_uid,
                    current.zone_uid,
                    channel,
                )
                return

        raw = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        try:
            command_json = json.loads(raw)
        except json.JSONDecodeError:
            self.publish_command_response(
                node_uid,
                channel,
                "unknown",
                "INVALID",
                {"error": "invalid_json", "payload_len": len(raw)},
            )
            return

        cmd_id = command_json.get("cmd_id", "unknown")
        if self.is_duplicate_cmd_id(cmd_id):
            return

        validation_error = self.validate_command_payload_strict(command_json)
        if validation_error is not None:
            error_code, error_message = validation_error
            self.publish_command_response(
                node_uid,
                channel,
                cmd_id,
                "ERROR",
                {
                    "error_code": error_code,
                    "error_message": error_message,
                },
            )
            return

        self.maybe_calibrate_timestamp_offset_from_command_ts(command_json["ts"])

        cmd_name = command_json["cmd"]
        params = dict(command_json.get("params", {}))
        kind = self.resolve_command_kind(cmd_name)
        job = PendingCommand(
            node_uid=node_uid,
            channel=channel,
            cmd_id=cmd_id,
            cmd=cmd_name,
            kind=kind,
            params=params,
            execute_delay_ms=self.resolve_command_delay_ms(kind, channel, cmd_name, params),
        )

        self.publish_command_response(node_uid, channel, cmd_id, "ACK")
        queue = self._state_command_queue if kind == CommandKind.STATE_QUERY else self._command_queue
        if queue.full():
            self.publish_command_response(
                node_uid,
                channel,
                cmd_id,
                "BUSY",
                {"error": "command_queue_full"},
            )
            return
        queue.put_nowait(job)

    async def process_config_payload(self, topic: str, payload: bytes | str) -> None:
        parsed_topic = self.parse_config_topic(topic)
        if not parsed_topic:
            return
        topic_gh_uid, topic_zone_uid, node_uid = parsed_topic
        if node_uid not in VIRTUAL_NODE_BY_UID:
            return

        current = self.get_node_namespace(node_uid)
        is_temp_topic = self.is_temp_namespace(topic_gh_uid, topic_zone_uid)
        if not current.preconfig_mode:
            if is_temp_topic:
                logger.info(
                    "Ignoring temp config for already configured node %s: current=%s/%s",
                    node_uid,
                    current.gh_uid,
                    current.zone_uid,
                )
                return
            if current.gh_uid != topic_gh_uid or current.zone_uid != topic_zone_uid:
                logger.warning(
                    "Ignoring config for node %s due namespace mismatch: topic=%s/%s current=%s/%s",
                    node_uid,
                    topic_gh_uid,
                    topic_zone_uid,
                    current.gh_uid,
                    current.zone_uid,
                )
                return

        raw = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        try:
            config_json = json.loads(raw)
        except json.JSONDecodeError:
            return

        next_gh_uid = config_json.get("gh_uid") if isinstance(config_json.get("gh_uid"), str) and config_json.get("gh_uid") else topic_gh_uid
        next_zone_uid = config_json.get("zone_uid") if isinstance(config_json.get("zone_uid"), str) and config_json.get("zone_uid") else topic_zone_uid
        if not next_gh_uid or not next_zone_uid:
            return

        self.update_node_namespace(node_uid, next_gh_uid, next_zone_uid)
        self.persist_received_config_or_namespace(node_uid, config_json, next_gh_uid, next_zone_uid)

        self.publish_status_for_node(node_uid, "ONLINE")
        self.publish_config_report_for_node(VIRTUAL_NODE_BY_UID[node_uid])

    def persist_received_config_or_namespace(
        self,
        node_uid: str,
        config_payload: dict[str, Any],
        gh_uid: str,
        zone_uid: str,
    ) -> None:
        if node_uid != DEFAULT_MQTT_NODE_UID:
            return
        self.persisted_boot_namespace = (gh_uid, zone_uid)

    def resolve_command_kind(self, cmd_name: str) -> CommandKind:
        if cmd_name in {"test_sensor", "probe_sensor"}:
            return CommandKind.SENSOR_PROBE
        if cmd_name == "state":
            return CommandKind.STATE_QUERY
        if cmd_name in {"report_config", "config_report", "get_config", "sync_config"}:
            return CommandKind.CONFIG_REPORT
        if cmd_name in {"restart", "reboot"}:
            return CommandKind.RESTART
        if cmd_name in {
            "set_relay",
            "set_pwm",
            "run_pump",
            "dose",
            "emit_event",
            "set_fault_mode",
            "reset_state",
            "reset_binding",
            "activate_sensor_mode",
            "deactivate_sensor_mode",
        }:
            return CommandKind.ACTUATOR
        return CommandKind.GENERIC

    @staticmethod
    def random_range_ms(min_value: int, max_value: int) -> int:
        return random.randint(min_value, max_value) if max_value > min_value else min_value

    def resolve_command_delay_ms(
        self,
        kind: CommandKind,
        channel: str,
        cmd: str,
        params: dict[str, Any],
    ) -> int:
        sim_delay_ms = params.get("sim_delay_ms")
        if isinstance(sim_delay_ms, (int, float)):
            return max(50, min(20000, int(sim_delay_ms)))

        if kind in {CommandKind.SENSOR_PROBE, CommandKind.STATE_QUERY}:
            return self.random_range_ms(180, 480)
        if kind == CommandKind.CONFIG_REPORT:
            return self.random_range_ms(120, 320)
        if kind == CommandKind.RESTART:
            return self.random_range_ms(1200, 2200)

        if kind == CommandKind.ACTUATOR and self.is_transient_command(cmd):
            base_ms = self.random_range_ms(TRANSIENT_DELAY_BASE_MIN_MS, TRANSIENT_DELAY_BASE_MAX_MS)
            duration_ms = params.get("duration_ms", 0)
            if (not duration_ms or duration_ms <= 0) and isinstance(params.get("ml"), (int, float)):
                duration_ms = int(float(params["ml"]) * 120.0)
            if isinstance(duration_ms, (int, float)) and duration_ms > 0:
                scaled_ms = int(float(duration_ms) * TRANSIENT_DELAY_SCALE_PERCENT / 100.0)
                scaled_ms = max(TRANSIENT_DELAY_SCALE_MIN_MS, min(TRANSIENT_DELAY_SCALE_MAX_MS, scaled_ms))
                return base_ms + scaled_ms
            return base_ms + self.random_range_ms(TRANSIENT_DELAY_EXTRA_MIN_MS, TRANSIENT_DELAY_EXTRA_MAX_MS)

        ttl_ms = params.get("ttl_ms", 900)
        if not isinstance(ttl_ms, (int, float)):
            ttl_ms = 900
        return max(150, min(8000, int(ttl_ms)))

    async def _command_worker(self, queue: asyncio.Queue[PendingCommand]) -> None:
        while self._running:
            job = await queue.get()
            try:
                await self.execute_pending_command(job)
            finally:
                queue.task_done()

    @staticmethod
    def is_main_pump_channel(channel: str) -> bool:
        return channel in {"pump_main", "main_pump"}

    @staticmethod
    def is_fill_channel(channel: str) -> bool:
        return channel in {"pump_in", "fill_valve", "water_control"}

    @staticmethod
    def is_drain_channel(channel: str) -> bool:
        return channel in {"drain_main", "drain_valve", "drain_pump", "drain"}

    @staticmethod
    def is_ph_correction_channel(channel: str) -> bool:
        return channel in {"pump_acid", "pump_base"}

    @staticmethod
    def is_ec_correction_channel(channel: str) -> bool:
        return channel in {"pump_a", "pump_b", "pump_c", "pump_d"}

    @staticmethod
    def is_storage_system_channel(channel: str) -> bool:
        return channel in {"system", "storage_state"}

    @staticmethod
    def is_transient_command(cmd: str) -> bool:
        return cmd in {"run_pump", "dose"}

    def is_supported_actuator_command(self, channel: str, cmd: str) -> bool:
        if channel == "pump_irrigation" or self.is_main_pump_channel(channel):
            return cmd in {"set_relay", "run_pump", "dose"}
        if channel in {
            "valve_clean_fill",
            "valve_clean_supply",
            "valve_solution_fill",
            "valve_solution_supply",
            "valve_irrigation",
            "fan_air",
            "fan",
            "heater",
        }:
            return cmd == "set_relay"
        if channel == "white_light":
            return cmd in {"set_relay", "set_pwm"}
        if self.is_fill_channel(channel) or self.is_drain_channel(channel) or self.is_ph_correction_channel(channel) or self.is_ec_correction_channel(channel):
            return cmd in {"set_relay", "run_pump", "dose"}
        if self.is_storage_system_channel(channel):
            return cmd in {
                "reset_state",
                "emit_event",
                "set_fault_mode",
                "reset_binding",
                "activate_sensor_mode",
                "deactivate_sensor_mode",
            }
        return False

    def is_main_pump_interlock_satisfied(self) -> bool:
        clean_fill_path = self.state.valve_clean_fill_on
        solution_fill_path = self.state.valve_clean_supply_on and self.state.valve_solution_fill_on
        recirculation_path = self.state.valve_solution_supply_on and self.state.valve_solution_fill_on
        irrigation_path = self.state.valve_solution_supply_on and self.state.valve_irrigation_on
        return clean_fill_path or solution_fill_path or recirculation_path or irrigation_path

    @staticmethod
    def append_main_pump_interlock_error(details: dict[str, Any]) -> None:
        details["error"] = "pump_interlock_blocked"
        details["error_code"] = "pump_interlock_blocked"
        details["error_message"] = (
            "pump_main requires valid flow path: clean_fill OR (clean_supply+solution_fill) "
            "OR (solution_supply+solution_fill) OR (solution_supply+irrigation)"
        )

    @staticmethod
    def switch_override_label(override_value: int) -> str:
        if override_value < 0:
            return "auto"
        return "on" if override_value > 0 else "off"

    @staticmethod
    def override_switch_value(override_value: int) -> float:
        return 1.0 if override_value > 0 else 0.0

    @staticmethod
    def level_switch_from_threshold(level_value: float, threshold: float, active_when_above: bool) -> float:
        if active_when_above:
            return 1.0 if level_value >= threshold else 0.0
        return 1.0 if level_value <= threshold else 0.0

    def resolve_clean_max_switch_value(self) -> float:
        if self.state.level_clean_max_override >= 0:
            return self.override_switch_value(self.state.level_clean_max_override)
        if self.state.clean_max_latched:
            return 1.0
        return self.level_switch_from_threshold(self.state.water_level, 0.90, True)

    def resolve_clean_min_switch_value(self) -> float:
        if self.state.level_clean_min_override >= 0:
            return self.override_switch_value(self.state.level_clean_min_override)
        clean_max_active = self.state.clean_max_latched or self.level_switch_from_threshold(self.state.water_level, 0.90, True) >= 0.5
        if self.state.force_clean_sensor_conflict and clean_max_active:
            return 0.0
        if self.state.clean_max_latched:
            return 1.0
        if self.state.clean_fill_stage_active and self.state.clean_fill_started_at > 0:
            if (self.get_timestamp_seconds() - self.state.clean_fill_started_at) >= CLEAN_FILL_MIN_DELAY_SEC:
                return 1.0
        return self.level_switch_from_threshold(self.state.water_level, 0.18, True)

    def resolve_solution_max_switch_value(self) -> float:
        if self.state.level_solution_max_override >= 0:
            return self.override_switch_value(self.state.level_solution_max_override)
        if self.state.solution_max_latched:
            return 1.0
        return self.level_switch_from_threshold(self.state.solution_level, 0.90, True)

    def resolve_solution_min_switch_value(self) -> float:
        if self.state.level_solution_min_override >= 0:
            return self.override_switch_value(self.state.level_solution_min_override)
        solution_max_active = self.state.solution_max_latched or self.level_switch_from_threshold(self.state.solution_level, 0.90, True) >= 0.5
        if self.state.force_solution_sensor_conflict and solution_max_active:
            return 0.0
        if self.state.solution_max_latched:
            return 1.0
        if self.state.solution_fill_stage_active and self.state.solution_fill_started_at > 0:
            if (self.get_timestamp_seconds() - self.state.solution_fill_started_at) >= SOLUTION_FILL_MIN_DELAY_SEC:
                return 1.0
        return self.level_switch_from_threshold(self.state.solution_level, 0.18, True)

    def is_clean_fill_active(self) -> bool:
        return self.state.tank_fill_on or (self.state.main_pump_on and self.state.valve_clean_fill_on)

    def is_solution_fill_active(self) -> bool:
        return self.state.main_pump_on and self.state.valve_clean_supply_on and self.state.valve_solution_fill_on

    def is_irrigation_active(self) -> bool:
        return self.state.irrigation_on or (
            self.state.main_pump_on and self.state.valve_solution_supply_on and self.state.valve_irrigation_on
        )

    def resolve_correction_reaction_scale(self, params: dict[str, Any], nominal_ml: float) -> float:
        commanded_ml = nominal_ml
        ml = params.get("ml")
        duration_ms = params.get("duration_ms")
        if isinstance(ml, (int, float)) and ml > 0:
            commanded_ml = float(ml)
        elif isinstance(duration_ms, (int, float)) and duration_ms > 0:
            commanded_ml = (float(duration_ms) / 1000.0) * CORRECTION_DURATION_TO_ML_PER_SEC
        scale = commanded_ml / nominal_ml
        return clamp_float(scale, CORRECTION_REACTION_SCALE_MIN, CORRECTION_REACTION_SCALE_MAX)

    def resolve_correction_phase_factor(self, ec_channel: bool) -> float:
        recirculation_path = self.state.main_pump_on and self.state.valve_solution_supply_on and self.state.valve_solution_fill_on
        solution_fill_path = (
            self.state.main_pump_on
            and self.state.valve_clean_supply_on
            and self.state.valve_solution_fill_on
            and not self.state.valve_solution_supply_on
        )
        if recirculation_path:
            return CORRECTION_RECIRC_EC_PHASE_FACTOR if ec_channel else CORRECTION_RECIRC_PH_PHASE_FACTOR
        if solution_fill_path:
            return CORRECTION_FILL_PHASE_FACTOR
        return 1.0

    def correction_drift_hold_ticks(self, phase_factor: float) -> int:
        hold_sec = CORRECTION_FLOW_DRIFT_HOLD_SEC if phase_factor > 1.0 else CORRECTION_IDLE_DRIFT_HOLD_SEC
        ticks = int((hold_sec * 1000 + self.telemetry_interval_ms - 1) / self.telemetry_interval_ms)
        return max(1, ticks)

    def arm_correction_drift_hold(self, ec_channel: bool, phase_factor: float) -> None:
        hold_ticks = self.correction_drift_hold_ticks(phase_factor)
        if ec_channel:
            self.state.ec_drift_hold_ticks = max(self.state.ec_drift_hold_ticks, hold_ticks)
        else:
            self.state.ph_drift_hold_ticks = max(self.state.ph_drift_hold_ticks, hold_ticks)

    def build_sensor_probe_details(self, channel: str) -> dict[str, Any]:
        if channel == "ph_sensor":
            metric_type, value, unit = "PH", self.state.ph_value, "pH"
        elif channel == "ec_sensor":
            metric_type, value, unit = "EC", self.state.ec_value, "mS/cm"
        elif channel == "air_temp_c":
            metric_type, value, unit = "TEMPERATURE", self.state.air_temp, "C"
        elif channel == "air_rh":
            metric_type, value, unit = "HUMIDITY", self.state.air_humidity, "%"
        elif channel == "light_level":
            metric_type, value, unit = "LIGHT_INTENSITY", self.state.light_level, "lux"
        elif channel == "soil_moisture":
            metric_type, value, unit = "SOIL_MOISTURE", self.state.soil_moisture, "%"
        elif channel == "water_level":
            metric_type, value, unit = "WATER_LEVEL", self.state.water_level, "ratio"
        elif channel == "level_clean_min":
            metric_type, value, unit = "WATER_LEVEL_SWITCH", self.resolve_clean_min_switch_value(), "bool"
        elif channel == "level_clean_max":
            metric_type, value, unit = "WATER_LEVEL_SWITCH", self.resolve_clean_max_switch_value(), "bool"
        elif channel == "level_solution_min":
            metric_type, value, unit = "WATER_LEVEL_SWITCH", self.resolve_solution_min_switch_value(), "bool"
        elif channel == "level_solution_max":
            metric_type, value, unit = "WATER_LEVEL_SWITCH", self.resolve_solution_max_switch_value(), "bool"
        elif channel == "flow_present":
            metric_type, value, unit = "FLOW_RATE", self.state.flow_rate, "l/min"
        elif channel == "pump_bus_current":
            metric_type, value, unit = "PUMP_CURRENT", self.state.pump_bus_current, "mA"
        else:
            metric_type, value, unit = "UNKNOWN", 0.0, None

        details: dict[str, Any] = {
            "metric_type": metric_type,
            "value": value,
            "virtual": True,
            "ts": self.get_timestamp_seconds(),
        }
        if unit is not None:
            details["unit"] = unit
        return details

    def build_irr_state_snapshot(self) -> dict[str, Any]:
        return {
            "clean_level_max": self.resolve_clean_max_switch_value() >= 0.5,
            "clean_level_min": self.resolve_clean_min_switch_value() >= 0.5,
            "solution_level_max": self.resolve_solution_max_switch_value() >= 0.5,
            "solution_level_min": self.resolve_solution_min_switch_value() >= 0.5,
            "valve_clean_fill": self.state.valve_clean_fill_on,
            "valve_clean_supply": self.state.valve_clean_supply_on,
            "valve_solution_fill": self.state.valve_solution_fill_on,
            "valve_solution_supply": self.state.valve_solution_supply_on,
            "valve_irrigation": self.state.valve_irrigation_on,
            "pump_main": self.state.main_pump_on,
        }

    def build_fault_modes(self) -> dict[str, Any]:
        return {
            "sensor_conflict_clean": self.state.force_clean_sensor_conflict,
            "sensor_conflict_solution": self.state.force_solution_sensor_conflict,
            "clean_fill_timeout_mode": self.state.simulate_clean_fill_timeout,
            "solution_fill_timeout_mode": self.state.simulate_solution_fill_timeout,
            "level_clean_min_override": self.switch_override_label(self.state.level_clean_min_override),
            "level_clean_max_override": self.switch_override_label(self.state.level_clean_max_override),
            "level_solution_min_override": self.switch_override_label(self.state.level_solution_min_override),
            "level_solution_max_override": self.switch_override_label(self.state.level_solution_max_override),
            "ph_value": round(self.state.ph_value, 4),
            "ec_value": round(self.state.ec_value, 4),
            "soil_moisture_pct": round(self.state.soil_moisture, 2),
        }

    async def execute_pending_command(self, job: PendingCommand) -> None:
        node = VIRTUAL_NODE_BY_UID.get(job.node_uid)
        if node is None:
            self.publish_command_response(job.node_uid, job.channel, job.cmd_id, "ERROR", {"error": "unknown_node"})
            return

        details: dict[str, Any] = {
            "virtual": True,
            "node_uid": job.node_uid,
            "channel": job.channel,
            "cmd": job.cmd,
            "exec_delay_ms": job.execute_delay_ms,
        }
        final_status = "DONE"
        trigger_reboot = False
        transient_main_pump_initial_state = False
        transient_restore_main_pump = False

        if job.kind == CommandKind.ACTUATOR and not self.is_supported_actuator_command(job.channel, job.cmd):
            details["error"] = "unsupported_channel_cmd"
            self.publish_command_response(job.node_uid, job.channel, job.cmd_id, "INVALID", details)
            return

        if job.kind == CommandKind.ACTUATOR and self.is_transient_command(job.cmd):
            if self.is_main_pump_channel(job.channel):
                transient_main_pump_initial_state = self.state.main_pump_on
                if transient_main_pump_initial_state:
                    details["main_pump_overlap"] = True
            if job.channel == "pump_irrigation" and self.state.irrigation_on:
                details["error"] = "actuator_busy"
                self.publish_command_response(job.node_uid, job.channel, job.cmd_id, "BUSY", details)
                return
            if self.is_fill_channel(job.channel) and self.state.tank_fill_on:
                details["error"] = "actuator_busy"
                self.publish_command_response(job.node_uid, job.channel, job.cmd_id, "BUSY", details)
                return
            if self.is_drain_channel(job.channel) and self.state.tank_drain_on:
                details["error"] = "actuator_busy"
                self.publish_command_response(job.node_uid, job.channel, job.cmd_id, "BUSY", details)
                return

        if job.kind == CommandKind.ACTUATOR and self.is_transient_command(job.cmd):
            if job.channel == "pump_irrigation":
                self.state.irrigation_on = True
            elif self.is_main_pump_channel(job.channel):
                if not self.is_main_pump_interlock_satisfied():
                    self.append_main_pump_interlock_error(details)
                    self.publish_command_response(job.node_uid, job.channel, job.cmd_id, "ERROR", details)
                    return
                self.state.main_pump_on = True
                transient_restore_main_pump = transient_main_pump_initial_state
            elif self.is_fill_channel(job.channel):
                self.state.tank_fill_on = True
            elif self.is_drain_channel(job.channel):
                self.state.tank_drain_on = True

        if job.execute_delay_ms > 0:
            await asyncio.sleep(job.execute_delay_ms / 1000.0)

        if job.kind == CommandKind.SENSOR_PROBE:
            details["probe"] = self.build_sensor_probe_details(job.channel)
        elif job.kind == CommandKind.STATE_QUERY:
            details["snapshot"] = self.build_irr_state_snapshot()
            details["fault_modes"] = self.build_fault_modes()
            details["sample_ts"] = self.get_timestamp_seconds()
            details["age_sec"] = 0
            details["max_age_sec"] = IRR_STATE_MAX_AGE_SEC
            details["is_fresh"] = True
        elif job.kind == CommandKind.CONFIG_REPORT:
            self.publish_config_report_for_node(node)
            details["note"] = "config_report_published"
        elif job.kind == CommandKind.RESTART:
            for virtual_node in VIRTUAL_NODES:
                self.publish_status_for_node(virtual_node.node_uid, "RESTARTING")
            details["note"] = "hardware_reboot_scheduled"
            details["scope"] = "device"
            trigger_reboot = True
        elif job.kind == CommandKind.ACTUATOR:
            final_status = self.update_virtual_state_from_command(job, details)
        else:
            details["note"] = "virtual_noop"

        if job.kind == CommandKind.ACTUATOR and self.is_transient_command(job.cmd):
            if job.channel == "pump_irrigation":
                self.state.irrigation_on = False
            elif self.is_main_pump_channel(job.channel):
                self.state.main_pump_on = transient_restore_main_pump
            elif self.is_fill_channel(job.channel):
                self.state.tank_fill_on = False
            elif self.is_drain_channel(job.channel):
                self.state.tank_drain_on = False

        self.publish_command_response(job.node_uid, job.channel, job.cmd_id, final_status, details)

        if trigger_reboot and final_status == "DONE":
            await asyncio.sleep(0.35)
            await self.simulate_reboot()

    def _param_bool(self, params: dict[str, Any], key: str) -> Optional[bool]:
        value = params.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value > 0
        return None

    def _param_number(self, params: dict[str, Any], key: str) -> Optional[float]:
        value = params.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _parse_switch_override(self, params: dict[str, Any], key: str) -> Optional[int]:
        value = params.get(key)
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, (int, float)):
            if value < 0:
                return -1
            return 1 if value > 0 else 0
        return None

    def update_virtual_state_from_command(self, job: PendingCommand, details: dict[str, Any]) -> str:
        params = job.params
        status = "DONE"
        handled = False
        was_solution_fill_active = self.is_solution_fill_active()

        sim_status = params.get("sim_status")
        if isinstance(sim_status, str):
            sim_status = sim_status.upper()
            if sim_status != "DONE":
                if sim_status == "NO_EFFECT":
                    details["note"] = "simulated_no_effect_ignored"
                elif sim_status in {"DONE", "NO_EFFECT", "BUSY", "INVALID", "ERROR"}:
                    details["error"] = "simulated_terminal_status"
                    details["error_code"] = sim_status
                    return sim_status
        if params.get("sim_no_effect") is True:
            details["note"] = "sim_no_effect_ignored"

        relay_state = self._param_bool(params, "state")
        if job.cmd == "set_relay" and relay_state is None:
            details["error"] = "missing_state"
            return "INVALID"

        pwm_value = self._param_number(params, "value")
        if job.cmd == "set_pwm" and pwm_value is None:
            details["error"] = "missing_pwm_value"
            return "INVALID"

        if job.cmd == "set_relay":
            current_state: Optional[bool] = None
            if job.channel == "pump_irrigation":
                current_state = self.state.irrigation_on
            elif self.is_main_pump_channel(job.channel):
                current_state = self.state.main_pump_on
            elif job.channel == "valve_clean_fill":
                current_state = self.state.valve_clean_fill_on
            elif job.channel == "valve_clean_supply":
                current_state = self.state.valve_clean_supply_on
            elif job.channel == "valve_solution_fill":
                current_state = self.state.valve_solution_fill_on
            elif job.channel == "valve_solution_supply":
                current_state = self.state.valve_solution_supply_on
            elif job.channel == "valve_irrigation":
                current_state = self.state.valve_irrigation_on
            elif self.is_fill_channel(job.channel):
                current_state = self.state.tank_fill_on
            elif self.is_drain_channel(job.channel):
                current_state = self.state.tank_drain_on
            elif job.channel in {"fan_air", "fan"}:
                current_state = self.state.fan_on
            elif job.channel == "heater":
                current_state = self.state.heater_on
            elif job.channel == "white_light":
                current_state = self.state.light_on

            if current_state is not None and current_state == relay_state:
                details["note"] = "already_in_requested_state_treated_as_done"

        if job.channel == "white_light" and job.cmd == "set_pwm":
            pwm_int = max(0, min(255, int(pwm_value or 0)))
            if self.state.light_pwm == pwm_int:
                details["note"] = "already_in_requested_pwm_treated_as_done"

        if self.is_ph_correction_channel(job.channel) and not self.state.ph_sensor_mode_active:
            details["error"] = "node_not_activated"
            details["error_code"] = "node_not_activated"
            details["error_message"] = "node is not activated"
            return "ERROR"
        if self.is_ec_correction_channel(job.channel) and not self.state.ec_sensor_mode_active:
            details["error"] = "node_not_activated"
            details["error_code"] = "node_not_activated"
            details["error_message"] = "node is not activated"
            return "ERROR"

        if job.channel == "pump_irrigation":
            if job.cmd == "set_relay":
                self.state.irrigation_on = bool(relay_state)
                handled = True
            elif self.is_transient_command(job.cmd):
                self.state.irrigation_boost_ticks = 3
                handled = True
        elif self.is_main_pump_channel(job.channel):
            if job.cmd == "set_relay":
                if relay_state and not self.is_main_pump_interlock_satisfied():
                    self.append_main_pump_interlock_error(details)
                    return "ERROR"
                self.state.main_pump_on = bool(relay_state)
                handled = True
            elif self.is_transient_command(job.cmd):
                if not self.is_main_pump_interlock_satisfied():
                    self.append_main_pump_interlock_error(details)
                    return "ERROR"
                handled = True
        elif job.channel == "valve_clean_fill":
            if job.cmd == "set_relay":
                was_on = self.state.valve_clean_fill_on
                self.state.valve_clean_fill_on = bool(relay_state)
                handled = True
                if not was_on and relay_state:
                    self.state.clean_fill_stage_active = True
                    self.state.clean_fill_started_at = self.get_timestamp_seconds()
                elif was_on and not relay_state:
                    self.state.clean_fill_stage_active = False
                    self.state.clean_fill_started_at = 0
        elif job.channel == "valve_clean_supply":
            if job.cmd == "set_relay":
                self.state.valve_clean_supply_on = bool(relay_state)
                handled = True
        elif job.channel == "valve_solution_fill":
            if job.cmd == "set_relay":
                self.state.valve_solution_fill_on = bool(relay_state)
                handled = True
        elif job.channel == "valve_solution_supply":
            if job.cmd == "set_relay":
                self.state.valve_solution_supply_on = bool(relay_state)
                handled = True
        elif job.channel == "valve_irrigation":
            if job.cmd == "set_relay":
                self.state.valve_irrigation_on = bool(relay_state)
                handled = True
        elif self.is_fill_channel(job.channel):
            if job.cmd == "set_relay":
                self.state.tank_fill_on = bool(relay_state)
                handled = True
            elif self.is_transient_command(job.cmd):
                self.state.water_level = clamp_float(self.state.water_level + 0.02, 0.05, 0.98)
                handled = True
        elif self.is_drain_channel(job.channel):
            if job.cmd == "set_relay":
                self.state.tank_drain_on = bool(relay_state)
                handled = True
            elif self.is_transient_command(job.cmd):
                self.state.solution_level = clamp_float(self.state.solution_level - 0.02, 0.05, 0.98)
                handled = True
        elif job.channel == "pump_acid":
            scale = self.resolve_correction_reaction_scale(params, PH_REACTION_NOMINAL_ML)
            phase_factor = self.resolve_correction_phase_factor(False)
            delta = PH_REACTION_BASE_DELTA * scale * phase_factor
            self.state.ph_value = clamp_float(self.state.ph_value - delta, 4.8, 7.2)
            self.state.correction_boost_ticks = CORRECTION_SETTLE_TICKS
            self.arm_correction_drift_hold(False, phase_factor)
            details["phase_factor"] = phase_factor
            details["delta_ph"] = -delta
            details["ph_after"] = self.state.ph_value
            handled = True
        elif job.channel == "pump_base":
            scale = self.resolve_correction_reaction_scale(params, PH_REACTION_NOMINAL_ML)
            phase_factor = self.resolve_correction_phase_factor(False)
            delta = PH_REACTION_BASE_DELTA * scale * phase_factor
            self.state.ph_value = clamp_float(self.state.ph_value + delta, 4.8, 7.2)
            self.state.correction_boost_ticks = CORRECTION_SETTLE_TICKS
            self.arm_correction_drift_hold(False, phase_factor)
            details["phase_factor"] = phase_factor
            details["delta_ph"] = delta
            details["ph_after"] = self.state.ph_value
            handled = True
        elif job.channel in {"pump_a", "pump_b", "pump_c", "pump_d"}:
            scale = self.resolve_correction_reaction_scale(params, EC_REACTION_NOMINAL_ML)
            phase_factor = self.resolve_correction_phase_factor(True)
            delta = EC_REACTION_BASE_DELTA * scale * phase_factor
            self.state.ec_value = clamp_float(self.state.ec_value + delta, 0.4, 3.2)
            self.state.correction_boost_ticks = CORRECTION_SETTLE_TICKS
            self.arm_correction_drift_hold(True, phase_factor)
            details["phase_factor"] = phase_factor
            details["delta_ec"] = delta
            details["ec_after"] = self.state.ec_value
            handled = True
        elif job.channel in {"fan_air", "fan"}:
            if job.cmd == "set_relay":
                self.state.fan_on = bool(relay_state)
                handled = True
        elif job.channel == "heater":
            if job.cmd == "set_relay":
                self.state.heater_on = bool(relay_state)
                handled = True
        elif job.channel == "white_light":
            if job.cmd == "set_relay":
                self.state.light_on = bool(relay_state)
                if not relay_state:
                    self.state.light_pwm = 0
                handled = True
            elif job.cmd == "set_pwm":
                pwm_int = max(0, min(255, int(pwm_value or 0)))
                self.state.light_pwm = pwm_int
                self.state.light_on = pwm_int > 0
                handled = True
        elif self.is_storage_system_channel(job.channel):
            if job.cmd == "reset_state":
                self.state = VirtualState()
                details["note"] = "virtual_state_reset"
                handled = True
            elif job.cmd == "emit_event":
                event_code = params.get("event_code")
                if not isinstance(event_code, str) or not event_code:
                    details["error"] = "missing_event_code"
                    details["error_code"] = "missing_event_code"
                    return "INVALID"
                self.publish_irrig_node_event(event_code)
                details["event_code"] = event_code
                handled = True
            elif job.cmd == "set_fault_mode":
                clean_sensor_conflict = self._param_bool(params, "sensor_conflict_clean")
                solution_sensor_conflict = self._param_bool(params, "sensor_conflict_solution")
                clean_fill_timeout = self._param_bool(params, "clean_fill_timeout_mode")
                solution_fill_timeout = self._param_bool(params, "solution_fill_timeout_mode")
                level_clean_min_override = self._parse_switch_override(params, "level_clean_min_override")
                level_clean_max_override = self._parse_switch_override(params, "level_clean_max_override")
                level_solution_min_override = self._parse_switch_override(params, "level_solution_min_override")
                level_solution_max_override = self._parse_switch_override(params, "level_solution_max_override")
                ph_value = self._param_number(params, "ph_value")
                ec_value = self._param_number(params, "ec_value")
                soil_moisture_pct = self._param_number(params, "soil_moisture_pct")

                if clean_sensor_conflict is not None:
                    self.state.force_clean_sensor_conflict = clean_sensor_conflict
                if solution_sensor_conflict is not None:
                    self.state.force_solution_sensor_conflict = solution_sensor_conflict
                if clean_fill_timeout is not None:
                    self.state.simulate_clean_fill_timeout = clean_fill_timeout
                if solution_fill_timeout is not None:
                    self.state.simulate_solution_fill_timeout = solution_fill_timeout
                if level_clean_min_override is not None:
                    self.state.level_clean_min_override = level_clean_min_override
                if level_clean_max_override is not None:
                    self.state.level_clean_max_override = level_clean_max_override
                if level_solution_min_override is not None:
                    self.state.level_solution_min_override = level_solution_min_override
                if level_solution_max_override is not None:
                    self.state.level_solution_max_override = level_solution_max_override
                if ph_value is not None:
                    self.state.ph_drift_hold_ticks = 0
                    self.state.ph_value = clamp_float(ph_value, 4.8, 7.2)
                if ec_value is not None:
                    self.state.ec_drift_hold_ticks = 0
                    self.state.ec_value = clamp_float(ec_value, 0.4, 3.2)
                if soil_moisture_pct is not None:
                    self.state.soil_moisture = clamp_float(soil_moisture_pct, 0.0, 100.0)

                if self.state.level_clean_max_override > 0 and self.state.clean_fill_stage_active:
                    self.state.clean_fill_stage_active = False
                    self.state.clean_fill_started_at = 0
                    self.state.clean_max_latched = True
                    if self.state.water_level < CLEAN_MAX_LATCH_LEVEL:
                        self.state.water_level = CLEAN_MAX_LATCH_LEVEL
                    self.publish_irrig_node_event("clean_fill_completed")
                    details["clean_fill_forced_complete"] = True

                if self.state.level_solution_max_override > 0 and self.state.solution_fill_stage_active:
                    self.state.solution_fill_stage_active = False
                    self.state.solution_fill_started_at = 0
                    self.state.solution_max_latched = True
                    if self.state.solution_level < SOLUTION_MAX_LATCH_LEVEL:
                        self.state.solution_level = SOLUTION_MAX_LATCH_LEVEL
                    self.publish_irrig_node_event("solution_fill_completed")
                    details["solution_fill_forced_complete"] = True

                details.update(self.build_fault_modes())
                handled = True
            elif job.cmd == "reset_binding":
                self.persisted_boot_namespace = (PRECONFIG_GH_UID, PRECONFIG_ZONE_UID)
                details["note"] = "binding_reset_pending_reboot"
                details["gh_uid"] = PRECONFIG_GH_UID
                details["zone_uid"] = PRECONFIG_ZONE_UID
                handled = True
            elif job.cmd == "activate_sensor_mode":
                if "-ph-" in job.node_uid:
                    if self.state.ph_sensor_mode_active:
                        details["note"] = "sensor_mode_already_active_treated_as_done"
                    else:
                        self.state.ph_sensor_mode_active = True
                    handled = True
                elif "-ec-" in job.node_uid:
                    if self.state.ec_sensor_mode_active:
                        details["note"] = "sensor_mode_already_active_treated_as_done"
                    else:
                        self.state.ec_sensor_mode_active = True
                    handled = True
            elif job.cmd == "deactivate_sensor_mode":
                if "-ph-" in job.node_uid:
                    if not self.state.ph_sensor_mode_active:
                        details["note"] = "sensor_mode_already_inactive_treated_as_done"
                    else:
                        self.state.ph_sensor_mode_active = False
                    handled = True
                elif "-ec-" in job.node_uid:
                    if not self.state.ec_sensor_mode_active:
                        details["note"] = "sensor_mode_already_inactive_treated_as_done"
                    else:
                        self.state.ec_sensor_mode_active = False
                    handled = True

        if not handled:
            details["error"] = "unsupported_channel_cmd"
            return "INVALID"

        amount = self._param_number(params, "ml")
        if amount is not None:
            details["amount"] = amount

        self.state.water_level = clamp_float(self.state.water_level, 0.05, 0.98)
        self.state.solution_level = clamp_float(self.state.solution_level, 0.05, 0.98)

        now_solution_fill_active = self.is_solution_fill_active()
        if not was_solution_fill_active and now_solution_fill_active:
            self.state.solution_fill_stage_active = True
            self.state.solution_fill_started_at = self.get_timestamp_seconds()
        elif was_solution_fill_active and not now_solution_fill_active:
            self.state.solution_fill_stage_active = False
            self.state.solution_fill_started_at = 0

        return status

    async def simulate_reboot(self) -> None:
        self.state = VirtualState()
        self._recent_cmd_ids.clear()
        self._timestamp_offset_valid = False
        self._timestamp_offset_sec = 0
        self._telemetry_tick = 0
        self._start_monotonic = time.monotonic()
        self._init_virtual_namespaces(*self.persisted_boot_namespace)
        await self._handle_connection_change(True)

    def apply_passive_drift(self) -> None:
        tick_ratio = self._telemetry_tick_ratio()
        drift = ((self._telemetry_tick % 11) - 5.0) * 0.002
        ph_drift = drift
        ec_drift = drift * 2.0
        soil_noise = (((self._telemetry_tick % 7) - 3.0) * 0.03) * tick_ratio
        clean_fill_active = self.is_clean_fill_active()
        solution_fill_active = self.is_solution_fill_active()
        irrigation_active = self.is_irrigation_active()
        now_sec = self.get_timestamp_seconds()

        if self.state.ph_drift_hold_ticks <= 0:
            ph_drift += PH_DRIFT_BIAS_PER_TICK
        else:
            self.state.ph_drift_hold_ticks -= 1
        if self.state.ec_drift_hold_ticks <= 0:
            ec_drift += EC_DRIFT_BIAS_PER_TICK
        else:
            self.state.ec_drift_hold_ticks -= 1

        self.state.ph_value = clamp_float(self.state.ph_value + ph_drift, 4.8, 7.2)
        self.state.ec_value = clamp_float(self.state.ec_value + ec_drift, 0.4, 3.2)

        if self.state.clean_fill_stage_active and self.state.clean_fill_started_at > 0:
            if (now_sec - self.state.clean_fill_started_at) >= CLEAN_FILL_DELAY_SEC:
                if self.state.simulate_clean_fill_timeout:
                    self.publish_irrig_node_event("clean_fill_timeout")
                else:
                    if self.state.water_level < CLEAN_MAX_LATCH_LEVEL:
                        self.state.water_level = CLEAN_MAX_LATCH_LEVEL
                    if not self.state.clean_max_latched:
                        self.publish_irrig_node_event("clean_fill_completed")
                    self.state.clean_max_latched = True
                self.state.clean_fill_stage_active = False
                self.state.clean_fill_started_at = 0

        if self.state.solution_fill_stage_active and self.state.solution_fill_started_at > 0:
            if (now_sec - self.state.solution_fill_started_at) >= SOLUTION_FILL_DELAY_SEC:
                if self.state.simulate_solution_fill_timeout:
                    self.publish_irrig_node_event("solution_fill_timeout")
                else:
                    if self.state.solution_level < SOLUTION_MAX_LATCH_LEVEL:
                        self.state.solution_level = SOLUTION_MAX_LATCH_LEVEL
                    if not self.state.solution_max_latched:
                        self.publish_irrig_node_event("solution_fill_completed")
                    self.state.solution_max_latched = True
                self.state.solution_fill_stage_active = False
                self.state.solution_fill_started_at = 0

        if clean_fill_active:
            self.state.water_level = clamp_float(self.state.water_level + (0.003 * tick_ratio), 0.05, 0.88)
        if solution_fill_active:
            transfer = 0.006 * tick_ratio
            available = self.state.water_level - 0.05
            if available > 0:
                if transfer > available:
                    transfer = available
                self.state.water_level = clamp_float(self.state.water_level - transfer, 0.05, 0.98)
                self.state.solution_level = clamp_float(self.state.solution_level + transfer, 0.05, 0.98)
        if irrigation_active:
            self.state.solution_level = clamp_float(self.state.solution_level - (0.008 * tick_ratio), 0.05, 0.98)
        if self.state.tank_drain_on:
            self.state.solution_level = clamp_float(self.state.solution_level - (0.008 * tick_ratio), 0.05, 0.98)

        if self.state.fan_on:
            self.state.air_temp = clamp_float(self.state.air_temp - 0.05, 18.0, 32.0)
            self.state.air_humidity = clamp_float(self.state.air_humidity - 0.08, 35.0, 90.0)
        else:
            self.state.air_temp = clamp_float(self.state.air_temp + 0.02, 18.0, 32.0)
            self.state.air_humidity = clamp_float(self.state.air_humidity + 0.03, 35.0, 90.0)

        if self.state.heater_on:
            self.state.air_temp = clamp_float(self.state.air_temp + 0.09, 18.0, 32.0)
            self.state.air_humidity = clamp_float(self.state.air_humidity - 0.04, 35.0, 90.0)

        if irrigation_active:
            rise = (1.2 * tick_ratio) + soil_noise
            self.state.soil_moisture = clamp_float(self.state.soil_moisture + rise, 8.0, 88.0)
        else:
            dry_back = (0.18 + max(0.0, self.state.air_temp - 22.0) * 0.015) * tick_ratio
            self.state.soil_moisture = clamp_float(self.state.soil_moisture - dry_back + soil_noise, 8.0, 88.0)

        if self.state.light_on:
            pwm_factor = self.state.light_pwm / 255.0
            if pwm_factor < 0.1:
                pwm_factor = 1.0
            self.state.light_level = clamp_float(12000.0 + (pwm_factor * 18000.0), 2000.0, 36000.0)
        else:
            self.state.light_level = clamp_float(self.state.light_level - 700.0, 100.0, 36000.0)

        self.state.flow_rate = 1.20 if irrigation_active else 0.0
        if self.state.irrigation_boost_ticks > 0:
            self.state.flow_rate += 0.40
            self.state.irrigation_boost_ticks -= 1

        self.state.pump_bus_current = 120.0
        if irrigation_active:
            self.state.pump_bus_current += 80.0
        if clean_fill_active or solution_fill_active or self.state.tank_drain_on:
            self.state.pump_bus_current += 70.0
        if self.state.correction_boost_ticks > 0:
            self.state.pump_bus_current += 50.0
            self.state.correction_boost_ticks -= 1

    def publish_virtual_telemetry_batch(self) -> None:
        self.apply_passive_drift()
        self.publish_telemetry_for_node(DEFAULT_MQTT_NODE_UID, "level_clean_min", "WATER_LEVEL_SWITCH", self.resolve_clean_min_switch_value())
        self.publish_telemetry_for_node(DEFAULT_MQTT_NODE_UID, "level_clean_max", "WATER_LEVEL_SWITCH", self.resolve_clean_max_switch_value())
        self.publish_telemetry_for_node(DEFAULT_MQTT_NODE_UID, "level_solution_min", "WATER_LEVEL_SWITCH", self.resolve_solution_min_switch_value())
        self.publish_telemetry_for_node(DEFAULT_MQTT_NODE_UID, "level_solution_max", "WATER_LEVEL_SWITCH", self.resolve_solution_max_switch_value())

        if self.state.ph_sensor_mode_active:
            self.publish_telemetry_for_node("nd-test-ph-1", "ph_sensor", "PH", self.state.ph_value)
        if self.state.ec_sensor_mode_active:
            self.publish_telemetry_for_node("nd-test-ec-1", "ec_sensor", "EC", self.state.ec_value)

        self.publish_telemetry_for_node("nd-test-soil-1", "soil_moisture", "SOIL_MOISTURE", self.state.soil_moisture)

        if self.publish_aux_telemetry:
            self.publish_telemetry_for_node("nd-test-climate-1", "air_temp_c", "TEMPERATURE", self.state.air_temp)
            self.publish_telemetry_for_node("nd-test-climate-1", "air_rh", "HUMIDITY", self.state.air_humidity)
            self.publish_telemetry_for_node("nd-test-light-1", "light_level", "LIGHT_INTENSITY", self.state.light_level)

        self._telemetry_tick += 1

    async def _telemetry_loop(self) -> None:
        config_elapsed_ms = 0
        heartbeat_elapsed_ms = 0
        while self._running:
            await asyncio.sleep(self.telemetry_interval_ms / 1000.0)
            connected = getattr(self.mqtt, "is_connected", lambda: True)()
            if connected:
                self.publish_virtual_telemetry_batch()
            else:
                self.apply_passive_drift()
                self._telemetry_tick += 1

            if connected:
                heartbeat_elapsed_ms += self.telemetry_interval_ms
                if heartbeat_elapsed_ms >= self.heartbeat_interval_ms:
                    heartbeat_elapsed_ms = 0
                    for node in VIRTUAL_NODES:
                        self.publish_heartbeat_for_node(node.node_uid)

                if self._config_report_on_connect_pending:
                    self._config_report_on_connect_pending = not self.publish_all_config_reports()
                    config_elapsed_ms = 0

                config_elapsed_ms += self.telemetry_interval_ms
                if config_elapsed_ms >= self.config_report_interval_ms:
                    if not self.publish_all_config_reports():
                        self._config_report_on_connect_pending = True
                    config_elapsed_ms = 0
            else:
                config_elapsed_ms = 0
                heartbeat_elapsed_ms = 0


async def run_test_node_profile(config, mqtt_client) -> None:
    test_node_cfg = config.test_node
    simulator = TestNodeSimulator(
        mqtt_client,
        gh_uid=test_node_cfg.gh_uid,
        zone_uid=test_node_cfg.zone_uid,
        telemetry_interval_ms=int(test_node_cfg.telemetry_interval_seconds * 1000),
        heartbeat_interval_ms=int(test_node_cfg.heartbeat_interval_seconds * 1000),
        config_report_interval_ms=int(test_node_cfg.config_report_interval_seconds * 1000),
        publish_aux_telemetry=test_node_cfg.publish_aux_telemetry,
    )
    await simulator.start()
    try:
        while True:
            await asyncio.sleep(1)
    finally:
        await simulator.stop()

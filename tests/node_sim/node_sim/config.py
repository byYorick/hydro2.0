"""
Валидатор YAML конфигурации для node-sim.
"""

import yaml
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MqttConfig:
    """Конфигурация MQTT."""
    host: str = "localhost"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    tls: bool = False
    ca_certs: Optional[str] = None
    client_id: Optional[str] = None
    keepalive: int = 60


@dataclass
class NodeConfig:
    """Конфигурация ноды."""
    gh_uid: str = "gh-1"
    zone_uid: str = "zn-1"
    node_uid: str = "nd-sim-1"
    hardware_id: str = "esp32-sim-001"
    node_type: str = "unknown"
    mode: str = "preconfig"  # preconfig | configured
    config_report_on_start: bool = True
    # начальные значения сенсоров (ключи = channel имена, значения = float)
    initial_sensors: Dict[str, float] = field(default_factory=dict)
    # дрифт сенсоров (ключи = channel, значения = единицы/мин)
    drift_per_minute: Dict[str, float] = field(default_factory=dict)
    drift_noise_per_minute: float = 0.0
    # sensors = список "channel" ключей, которые идут в MQTT topic сегмент {channel}
    # (например, ph_sensor, ec_sensor, air_temp_c, air_rh, co2_ppm, lux, solution_temp_c)
    sensors: List[str] = field(default_factory=lambda: ["ph_sensor", "ec_sensor", "solution_temp_c", "air_temp_c", "air_rh"])
    actuators: List[str] = field(default_factory=lambda: ["main_pump", "drain_pump", "fan", "heater", "light", "mister"])


@dataclass
class TelemetryConfig:
    """Конфигурация телеметрии."""
    interval_seconds: float = 5.0
    status_interval_seconds: float = 60.0
    heartbeat_interval_seconds: float = 30.0


@dataclass
class FailureModeConfig:
    """Конфигурация режимов отказов."""
    delay_response: bool = False
    delay_ms: int = 0
    drop_response: bool = False
    duplicate_response: bool = False
    random_drop_rate: float = 0.0
    random_duplicate_rate: float = 0.0
    random_delay_ms_min: int = 0
    random_delay_ms_max: int = 0
    offline_chance: float = 0.0
    offline_duration_s: float = 0.0
    offline_check_interval_s: float = 30.0


@dataclass
class SimConfig:
    """Полная конфигурация симулятора."""
    mqtt: MqttConfig = field(default_factory=MqttConfig)
    node: NodeConfig = field(default_factory=NodeConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    failure_mode: Optional[FailureModeConfig] = None
    
    @classmethod
    def from_file(cls, config_path: str) -> 'SimConfig':
        """
        Загрузить конфигурацию из YAML файла.
        
        Args:
            config_path: Путь к YAML файлу
        
        Returns:
            SimConfig
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SimConfig':
        """
        Создать конфигурацию из словаря.
        
        Args:
            data: Словарь с конфигурацией
        
        Returns:
            SimConfig
        """
        # MQTT конфигурация
        mqtt_data = data.get("mqtt", {})
        mqtt_config = MqttConfig(
            host=mqtt_data.get("host", "localhost"),
            port=mqtt_data.get("port", 1883),
            username=mqtt_data.get("username"),
            password=mqtt_data.get("password"),
            tls=mqtt_data.get("tls", False),
            ca_certs=mqtt_data.get("ca_certs"),
            client_id=mqtt_data.get("client_id"),
            keepalive=mqtt_data.get("keepalive", 60)
        )
        
        # Конфигурация ноды
        node_data = data.get("node", {})
        node_config = NodeConfig(
            gh_uid=node_data.get("gh_uid", "gh-1"),
            zone_uid=node_data.get("zone_uid", "zn-1"),
            node_uid=node_data.get("node_uid", "nd-sim-1"),
            hardware_id=node_data.get("hardware_id", "esp32-sim-001"),
            node_type=node_data.get("node_type", "unknown"),
            mode=node_data.get("mode", "preconfig"),
            config_report_on_start=node_data.get("config_report_on_start", True),
            initial_sensors=node_data.get("initial_sensors", {}) or {},
            drift_per_minute=node_data.get("drift_per_minute", {}) or {},
            drift_noise_per_minute=node_data.get("drift_noise_per_minute", 0.0),
            # Поддержка старого поля channels: считаем, что это те же MQTT channel keys
            sensors=node_data.get("sensors", node_data.get("channels", ["ph_sensor", "ec_sensor", "solution_temp_c"])),
            actuators=node_data.get("actuators", ["main_pump", "drain_pump", "fan", "heater", "light", "mister"])
        )
        
        # Конфигурация телеметрии
        telemetry_data = data.get("telemetry", {})
        telemetry_config = TelemetryConfig(
            interval_seconds=telemetry_data.get("interval_seconds", 5.0),
            status_interval_seconds=telemetry_data.get("status_interval_seconds", 60.0),
            heartbeat_interval_seconds=telemetry_data.get("heartbeat_interval_seconds", 30.0)
        )
        
        # Режим отказов
        failure_mode = None
        if "failure_mode" in data:
            fm_data = data["failure_mode"]
            failure_mode = FailureModeConfig(
                delay_response=fm_data.get("delay_response", False),
                delay_ms=fm_data.get("delay_ms", 0),
                drop_response=fm_data.get("drop_response", False),
                duplicate_response=fm_data.get("duplicate_response", False),
                random_drop_rate=fm_data.get("random_drop_rate", 0.0),
                random_duplicate_rate=fm_data.get("random_duplicate_rate", 0.0),
                random_delay_ms_min=fm_data.get("random_delay_ms_min", 0),
                random_delay_ms_max=fm_data.get("random_delay_ms_max", 0),
                offline_chance=fm_data.get("offline_chance", 0.0),
                offline_duration_s=fm_data.get("offline_duration_s", 0.0),
                offline_check_interval_s=fm_data.get("offline_check_interval_s", 30.0)
            )
        
        return cls(
            mqtt=mqtt_config,
            node=node_config,
            telemetry=telemetry_config,
            failure_mode=failure_mode
        )
    
    def validate(self):
        """Валидировать конфигурацию."""
        errors = []
        
        # Валидация MQTT
        if not self.mqtt.host:
            errors.append("mqtt.host is required")
        if not (1 <= self.mqtt.port <= 65535):
            errors.append("mqtt.port must be between 1 and 65535")
        
        # Валидация ноды
        if not self.node.gh_uid:
            errors.append("node.gh_uid is required")
        if not self.node.zone_uid:
            errors.append("node.zone_uid is required")
        if not self.node.node_uid:
            errors.append("node.node_uid is required")
        if not self.node.hardware_id:
            errors.append("node.hardware_id is required")
        if self.node.mode not in ("preconfig", "configured"):
            errors.append("node.mode must be 'preconfig' or 'configured'")
        
        # Валидация телеметрии
        if self.telemetry.interval_seconds <= 0:
            errors.append("telemetry.interval_seconds must be > 0")
        if self.telemetry.heartbeat_interval_seconds <= 0:
            errors.append("telemetry.heartbeat_interval_seconds must be > 0")

        # Валидация initial_sensors
        if self.node.initial_sensors and not isinstance(self.node.initial_sensors, dict):
            errors.append("node.initial_sensors must be a dict")
        if self.node.drift_per_minute and not isinstance(self.node.drift_per_minute, dict):
            errors.append("node.drift_per_minute must be a dict")

        # Валидация режимов отказов
        if self.failure_mode:
            if not (0.0 <= self.failure_mode.random_drop_rate <= 1.0):
                errors.append("failure_mode.random_drop_rate must be between 0 and 1")
            if not (0.0 <= self.failure_mode.random_duplicate_rate <= 1.0):
                errors.append("failure_mode.random_duplicate_rate must be between 0 and 1")
            if not (0.0 <= self.failure_mode.offline_chance <= 1.0):
                errors.append("failure_mode.offline_chance must be between 0 and 1")
            if self.failure_mode.offline_duration_s < 0:
                errors.append("failure_mode.offline_duration_s must be >= 0")
            if self.failure_mode.offline_check_interval_s <= 0:
                errors.append("failure_mode.offline_check_interval_s must be > 0")
        
        if errors:
            raise ValueError(f"Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

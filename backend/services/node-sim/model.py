"""
Модель ноды для симулятора.
Содержит идентификаторы, каналы и состояние актуаторов.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
from enum import Enum


class NodeType(str, Enum):
    """Типы нод."""
    PH = "ph"
    EC = "ec"
    CLIMATE = "climate"
    PUMP = "pump"
    IRRIG = "irrig"
    LIGHT = "light"
    UNKNOWN = "unknown"


class NodeMode(str, Enum):
    """Режимы работы ноды."""
    PRECONFIG = "preconfig"  # До получения конфигурации
    CONFIGURED = "configured"  # После получения конфигурации


@dataclass
class ChannelState:
    """Состояние канала."""
    name: str
    value: float = 0.0
    enabled: bool = False
    last_update: float = 0.0


@dataclass
class ActuatorState:
    """Состояние актуатора."""
    name: str
    state: bool = False  # Включен/выключен
    pwm_value: int = 0  # Значение PWM (0-255)
    current_ma: float = 0.0  # Ток в миллиамперах (для INA209)
    flow_present: bool = False  # Наличие потока (для насосов)


@dataclass
class NodeModel:
    """
    Модель ноды для симулятора.
    
    Содержит:
    - Идентификаторы: gh_uid, zone_uid, node_uid, hardware_id, node_type
    - Список каналов: pump_1, fan_1, heater_1, light_1, mister_1
    - Состояние актуаторов
    - Параметры "физики": current_ma, flow_present
    """
    
    # Идентификаторы
    gh_uid: str
    zone_uid: str
    node_uid: str
    hardware_id: str
    node_type: NodeType = NodeType.UNKNOWN
    
    # Режим работы
    mode: NodeMode = NodeMode.PRECONFIG
    
    # Каналы (сенсоры)
    channels: List[str] = field(default_factory=lambda: [])
    
    # Состояние каналов
    channel_states: Dict[str, ChannelState] = field(default_factory=dict)
    
    # Актуаторы
    actuators: List[str] = field(default_factory=lambda: [
        "pump_1", "fan_1", "heater_1", "light_1", "mister_1"
    ])
    
    # Состояние актуаторов
    actuator_states: Dict[str, ActuatorState] = field(default_factory=dict)
    
    # Параметры "физики"
    current_ma: float = 0.0  # Общий ток (INA209)
    flow_present: bool = False  # Наличие потока
    
    # Метаданные
    fw_version: str = "2.0.0-sim"
    uptime_seconds: int = 0
    
    def __post_init__(self):
        """Инициализация после создания."""
        # Инициализируем состояния каналов
        for ch in self.channels:
            if ch not in self.channel_states:
                self.channel_states[ch] = ChannelState(name=ch)
        
        # Инициализируем состояния актуаторов
        for act in self.actuators:
            if act not in self.actuator_states:
                self.actuator_states[act] = ActuatorState(name=act)
    
    def get_channel_value(self, channel: str) -> Optional[float]:
        """Получить значение канала."""
        if channel in self.channel_states:
            return self.channel_states[channel].value
        return None
    
    def set_channel_value(self, channel: str, value: float):
        """Установить значение канала."""
        import time
        if channel not in self.channel_states:
            self.channel_states[channel] = ChannelState(name=channel)
        self.channel_states[channel].value = value
        self.channel_states[channel].last_update = time.time()
    
    def get_actuator_state(self, actuator: str) -> Optional[ActuatorState]:
        """Получить состояние актуатора."""
        return self.actuator_states.get(actuator)
    
    def set_actuator_state(self, actuator: str, state: bool, pwm_value: int = 0):
        """Установить состояние актуатора."""
        if actuator not in self.actuator_states:
            self.actuator_states[actuator] = ActuatorState(name=actuator)
        
        self.actuator_states[actuator].state = state
        self.actuator_states[actuator].pwm_value = pwm_value
        
        # Симулируем ток для включенных актуаторов
        if state:
            # Базовый ток для разных типов актуаторов
            if "pump" in actuator:
                self.actuator_states[actuator].current_ma = 100.0 + (pwm_value / 255.0) * 50.0
                self.actuator_states[actuator].flow_present = True
            elif "fan" in actuator:
                self.actuator_states[actuator].current_ma = 50.0 + (pwm_value / 255.0) * 30.0
            elif "heater" in actuator:
                self.actuator_states[actuator].current_ma = 200.0 + (pwm_value / 255.0) * 100.0
            elif "light" in actuator:
                self.actuator_states[actuator].current_ma = 150.0 + (pwm_value / 255.0) * 100.0
            else:
                self.actuator_states[actuator].current_ma = 50.0
        else:
            self.actuator_states[actuator].current_ma = 0.0
            if "pump" in actuator:
                self.actuator_states[actuator].flow_present = False
        
        # Обновляем общий ток (INA209)
        self._update_total_current()
    
    def _update_total_current(self):
        """Обновить общий ток (INA209)."""
        total = 0.0
        for actuator in self.actuator_states.values():
            total += actuator.current_ma
        self.current_ma = total
    
    def get_ina209_current(self) -> float:
        """Получить ток INA209 (для телеметрии)."""
        return self.current_ma


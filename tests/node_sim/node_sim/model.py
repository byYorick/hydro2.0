"""
Модель ноды и "физика" для симулятора нод.
Реализует состояния каналов и эмуляцию тока/потока.
"""

import time
import random
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class NodeType(str, Enum):
    """Типы нод."""
    PH = "ph"
    EC = "ec"
    CLIMATE = "climate"
    PUMP = "pump"
    IRRIG = "irrig"
    LIGHT = "light"
    UNKNOWN = "unknown"


@dataclass
class ActuatorState:
    """Состояние актуатора."""
    name: str
    state: bool = False  # Включен/выключен
    pwm_value: int = 0  # Значение PWM (0-255)
    current_ma: float = 0.0  # Ток в миллиамперах
    flow_present: bool = False  # Наличие потока (для насосов)
    start_time: Optional[float] = None  # Время включения (для отслеживания no_flow)


@dataclass
class SensorState:
    """Состояние сенсора."""
    name: str
    value: float = 0.0
    last_update: float = 0.0


@dataclass
class NodeModel:
    """
    Модель ноды для симулятора.
    
    Содержит:
    - Идентификаторы: gh_uid, zone_uid, node_uid, hardware_id, node_type
    - Каналы актуаторов: main_pump, drain_pump, mister, fan, light, heater
    - Сенсоры: air_temp_c, air_rh, co2_ppm, lux, solution_temp_c, ph, ec, ina209_ma, flow_present
    - Правила физики для токов и потоков
    """
    
    # Идентификаторы
    gh_uid: str
    zone_uid: str
    node_uid: str
    hardware_id: str
    node_type: NodeType = NodeType.UNKNOWN
    mode: str = "configured"  # "preconfig" | "configured"
    
    # Каналы актуаторов
    actuators: List[str] = field(default_factory=lambda: [
        "main_pump", "drain_pump", "mister", "fan", "light", "heater"
    ])
    
    # Состояние актуаторов
    actuator_states: Dict[str, ActuatorState] = field(default_factory=dict)
    
    # Сенсоры
    sensors: List[str] = field(default_factory=lambda: [
        "air_temp_c", "air_rh", "co2_ppm", "lux",
        "solution_temp_c", "ph_sensor", "ec_sensor", "ina209_ma", "flow_present"
    ])
    
    # Состояние сенсоров
    sensor_states: Dict[str, SensorState] = field(default_factory=dict)
    
    # Параметры физики
    base_current: float = 50.0  # Базовый ток в мА
    noise_amplitude: float = 5.0  # Амплитуда шума для тока
    overcurrent_mode: bool = False  # Режим перегрузки
    overcurrent_current: float = 500.0  # Ток в режиме перегрузки (мА)
    no_flow_timeout_s: float = 5.0  # Таймаут отсутствия потока (секунды)

    # Дрифт сенсоров (единицы в минуту)
    drift_per_minute: Dict[str, float] = field(default_factory=dict)
    drift_noise_per_minute: float = 0.0
    
    # Токи для разных актуаторов (базовые значения в мА)
    actuator_base_currents: Dict[str, float] = field(default_factory=lambda: {
        "main_pump": 150.0,
        "drain_pump": 120.0,
        "mister": 80.0,
        "fan": 60.0,
        "light": 200.0,
        "heater": 300.0,
    })
    
    # Колбэки для ошибок
    error_callbacks: List[Callable[[str, Dict], None]] = field(default_factory=list)

    # Состояние доступности
    offline_until: Optional[float] = None
    
    def __post_init__(self):
        """Инициализация после создания."""
        # Эти сенсоры нужны для внутренней логики (INA209 и flow_present)
        for required in ("ina209_ma", "flow_present"):
            if required not in self.sensors:
                self.sensors.append(required)

        # Инициализируем состояния актуаторов
        for act in self.actuators:
            if act not in self.actuator_states:
                self.actuator_states[act] = ActuatorState(name=act)
        
        # Инициализируем состояния сенсоров
        for sensor in self.sensors:
            if sensor not in self.sensor_states:
                self.sensor_states[sensor] = SensorState(name=sensor)
        
        # Инициализируем начальные значения сенсоров
        self._initialize_sensor_values()
    
    def _initialize_sensor_values(self):
        """Инициализировать начальные значения сенсоров."""
        now = time.time()
        
        # Климатические сенсоры
        if "air_temp_c" in self.sensor_states:
            self.sensor_states["air_temp_c"].value = 22.0
        if "air_rh" in self.sensor_states:
            self.sensor_states["air_rh"].value = 60.0
        if "co2_ppm" in self.sensor_states:
            self.sensor_states["co2_ppm"].value = 400.0
        if "lux" in self.sensor_states:
            self.sensor_states["lux"].value = 1000.0
        
        # Сенсоры раствора
        if "solution_temp_c" in self.sensor_states:
            self.sensor_states["solution_temp_c"].value = 20.0
        if "ph_sensor" in self.sensor_states:
            self.sensor_states["ph_sensor"].value = 6.0
        elif "ph" in self.sensor_states:
            self.sensor_states["ph"].value = 6.0
        if "ec_sensor" in self.sensor_states:
            self.sensor_states["ec_sensor"].value = 1.5
        elif "ec" in self.sensor_states:
            self.sensor_states["ec"].value = 1.5
        
        # INA209 и flow
        if "ina209_ma" in self.sensor_states:
            self.sensor_states["ina209_ma"].value = self.base_current
        if "flow_present" in self.sensor_states:
            self.sensor_states["flow_present"].value = 0.0  # bool как float (0/1)
        
        # Обновляем время последнего обновления
        for sensor_state in self.sensor_states.values():
            sensor_state.last_update = now

    def apply_drift(self, elapsed_s: float) -> None:
        """Применить дрифт значений сенсоров."""
        if not self.drift_per_minute or elapsed_s <= 0:
            return

        minutes = elapsed_s / 60.0
        now = time.time()
        for sensor, rate in self.drift_per_minute.items():
            if sensor not in self.sensor_states:
                continue
            try:
                rate_f = float(rate)
            except (TypeError, ValueError):
                continue

            delta = rate_f * minutes
            if self.drift_noise_per_minute:
                delta += random.uniform(-self.drift_noise_per_minute, self.drift_noise_per_minute) * minutes

            self.sensor_states[sensor].value += delta
            self.sensor_states[sensor].last_update = now
    
    def set_actuator(self, actuator: str, state: bool, pwm_value: int = 255):
        """
        Установить состояние актуатора.
        
        Args:
            actuator: Имя актуатора (main_pump, drain_pump, etc.)
            state: Включен (True) или выключен (False)
            pwm_value: Значение PWM (0-255)
        """
        if actuator not in self.actuator_states:
            self.actuator_states[actuator] = ActuatorState(name=actuator)
        
        act_state = self.actuator_states[actuator]
        act_state.state = state
        act_state.pwm_value = pwm_value if state else 0
        
        now = time.time()
        
        if state:
            # Актуатор включен
            if act_state.start_time is None:
                act_state.start_time = now
            
            # Вычисляем ток для актуатора
            base = self.actuator_base_currents.get(actuator, 50.0)
            # Ток зависит от PWM
            pwm_factor = pwm_value / 255.0
            act_state.current_ma = base * pwm_factor
            
            # Для насосов устанавливаем flow_present
            if actuator in ("main_pump", "drain_pump"):
                act_state.flow_present = True
        else:
            # Актуатор выключен
            act_state.current_ma = 0.0
            act_state.start_time = None
            
            # Для насосов сбрасываем flow_present
            if actuator in ("main_pump", "drain_pump"):
                act_state.flow_present = False
        
        # Обновляем телеметрию детерминированно
        self._update_telemetry()
    
    def get_actuator_state(self, actuator: str) -> Optional[ActuatorState]:
        """Получить состояние актуатора."""
        return self.actuator_states.get(actuator)
    
    def set_sensor_value(self, sensor: str, value: float):
        """Установить значение сенсора вручную."""
        if sensor not in self.sensor_states:
            self.sensor_states[sensor] = SensorState(name=sensor)
        
        self.sensor_states[sensor].value = value
        self.sensor_states[sensor].last_update = time.time()

    def set_offline(self, duration_s: float):
        """Перевести ноду в offline на заданное время."""
        if duration_s <= 0:
            return
        self.offline_until = time.time() + duration_s

    def is_offline(self) -> bool:
        """Проверить, находится ли нода в offline."""
        if self.offline_until is None:
            return False
        if time.time() >= self.offline_until:
            self.offline_until = None
            return False
        return True
    
    def get_sensor_value(self, sensor: str) -> Optional[float]:
        """Получить значение сенсора."""
        if sensor in self.sensor_states:
            return self.sensor_states[sensor].value
        return None
    
    def _update_telemetry(self):
        """
        Обновить телеметрию детерминированно на основе состояния актуаторов.
        """
        now = time.time()
        
        # Вычисляем общий ток (INA209)
        total_current = self.base_current
        
        # Суммируем токи всех включенных актуаторов
        for act_state in self.actuator_states.values():
            if act_state.state:
                total_current += act_state.current_ma
        
        # Применяем режим перегрузки
        if self.overcurrent_mode:
            total_current = self.overcurrent_current
        else:
            # Добавляем шум к току, если включен main_pump
            main_pump = self.actuator_states.get("main_pump")
            if main_pump and main_pump.state:
                noise = random.uniform(-self.noise_amplitude, self.noise_amplitude)
                total_current += noise
        
        # Обновляем INA209
        self.sensor_states["ina209_ma"].value = max(0.0, total_current)
        self.sensor_states["ina209_ma"].last_update = now
        
        # Обновляем flow_present (логическое ИЛИ всех насосов)
        flow_present = False
        for act_name in ("main_pump", "drain_pump"):
            act_state = self.actuator_states.get(act_name)
            if act_state and act_state.state and act_state.flow_present:
                flow_present = True
                break
        
        self.sensor_states["flow_present"].value = 1.0 if flow_present else 0.0
        self.sensor_states["flow_present"].last_update = now
        
        # Проверяем условие no_flow для насосов
        self._check_no_flow_condition(now)
    
    def set_overcurrent_mode(self, enabled: bool, current: Optional[float] = None):
        """
        Установить режим перегрузки по току (overcurrent).
        
        Args:
            enabled: Включить режим перегрузки
            current: Ток в режиме перегрузки (мА), если не указан - используется overcurrent_current
        """
        self.overcurrent_mode = enabled
        if current is not None:
            self.overcurrent_current = current
        # Обновляем телеметрию сразу
        self._update_telemetry()
        logger.info(f"Overcurrent mode {'enabled' if enabled else 'disabled'}: {self.overcurrent_current}mA")
    
    def set_no_flow_mode(self, actuator: str, enabled: bool):
        """
        Установить режим отсутствия потока для актуатора (no_flow).
        
        Args:
            actuator: Имя актуатора (main_pump, drain_pump)
            enabled: Включить режим отсутствия потока
        """
        act_state = self.actuator_states.get(actuator)
        if not act_state:
            logger.warning(f"Cannot set no_flow mode: actuator {actuator} not found")
            return
        
        act_state.flow_present = not enabled
        # Обновляем телеметрию
        self._update_telemetry()
        logger.info(f"No-flow mode {'enabled' if enabled else 'disabled'} for {actuator}")
    
    def _check_no_flow_condition(self, current_time: float):
        """
        Проверить условие отсутствия потока и сгенерировать ошибку при необходимости.
        
        Args:
            current_time: Текущее время
        """
        for act_name in ("main_pump", "drain_pump"):
            act_state = self.actuator_states.get(act_name)
            if not act_state or not act_state.state:
                continue
            
            # Насос включен, проверяем flow_present
            if not act_state.flow_present:
                # Проверяем таймаут
                if act_state.start_time is not None:
                    elapsed = current_time - act_state.start_time
                    if elapsed >= self.no_flow_timeout_s:
                        # Генерируем ошибку biz_no_flow
                        self._generate_error("biz_no_flow", {
                            "actuator": act_name,
                            "elapsed_seconds": elapsed,
                            "timeout_seconds": self.no_flow_timeout_s,
                            "node_uid": self.node_uid,
                            "hardware_id": self.hardware_id,
                        })
    
    def _generate_error(self, error_code: str, details: Dict):
        """
        Сгенерировать ошибку через колбэки.
        
        Args:
            error_code: Код ошибки (например, "biz_no_flow")
            details: Детали ошибки
        """
        for callback in self.error_callbacks:
            try:
                callback(error_code, details)
            except Exception as e:
                # Логируем ошибку в колбэке, но не прерываем выполнение
                print(f"Error in error callback: {e}")
    
    def register_error_callback(self, callback: Callable[[str, Dict], None]):
        """
        Зарегистрировать колбэк для обработки ошибок.
        
        Args:
            callback: Функция, которая будет вызвана при генерации ошибки
                     Сигнатура: callback(error_code: str, details: Dict) -> None
        """
        self.error_callbacks.append(callback)
    
    def set_overcurrent_mode(self, enabled: bool, current: Optional[float] = None):
        """
        Установить режим перегрузки.
        
        Args:
            enabled: Включить режим перегрузки
            current: Ток в режиме перегрузки (если не указан, используется overcurrent_current)
        """
        was_enabled = self.overcurrent_mode
        self.overcurrent_mode = enabled
        if current is not None:
            self.overcurrent_current = current
        
        # Обновляем телеметрию
        self._update_telemetry()
        
        # Генерируем ошибку infra_overcurrent при включении режима перегрузки
        if enabled and not was_enabled:
            current_ma = self.sensor_states["ina209_ma"].value
            self._generate_error("infra_overcurrent", {
                "current_ma": current_ma,
                "threshold_ma": 500.0,  # Стандартный порог
                "overcurrent_mode": True,
                "node_uid": self.node_uid,
                "hardware_id": self.hardware_id,
            })
    
    def update(self):
        """
        Обновить модель (вызывается периодически).
        Обновляет телеметрию и проверяет условия ошибок.
        """
        self._update_telemetry()
    
    def get_telemetry_dict(self) -> Dict[str, float]:
        """
        Получить словарь со всеми значениями телеметрии.
        
        Returns:
            Словарь {sensor_name: value}
        """
        return {
            sensor_name: sensor_state.value
            for sensor_name, sensor_state in self.sensor_states.items()
        }
    
    def get_actuator_dict(self) -> Dict[str, Dict]:
        """
        Получить словарь со всеми состояниями актуаторов.
        
        Returns:
            Словарь {actuator_name: {"state": bool, "pwm": int, "current_ma": float, "flow_present": bool}}
        """
        return {
            act_name: {
                "state": act_state.state,
                "pwm": act_state.pwm_value,
                "current_ma": act_state.current_ma,
                "flow_present": act_state.flow_present,
            }
            for act_name, act_state in self.actuator_states.items()
        }

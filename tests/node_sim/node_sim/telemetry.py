"""
Публикация телеметрии для node-sim.

Публикует telemetry каждые telemetry_interval_s секунд.
Поддерживает публикацию on-demand по команде hil_request_telemetry.
"""

import asyncio
import logging
import time
import random
from typing import Optional, Callable

from .model import NodeModel
from .mqtt_client import MqttClient
from .topics import (
    telemetry, temp_telemetry,
    heartbeat, temp_heartbeat
)

logger = logging.getLogger(__name__)


class TelemetryPublisher:
    """
    Публикатор телеметрии для node-sim.
    
    Публикует:
    - Telemetry для каждого канала каждые telemetry_interval_s секунд
    - Heartbeat периодически (управляется через StatusPublisher)
    - Ток INA209 в telemetry
    - Поддерживает публикацию on-demand по команде hil_request_telemetry
    """
    
    def __init__(
        self,
        node: NodeModel,
        mqtt: MqttClient,
        telemetry_interval_s: float = 5.0
    ):
        """
        Инициализация публикатора телеметрии.
        
        Args:
            node: Модель ноды
            mqtt: MQTT клиент
            telemetry_interval_s: Интервал публикации телеметрии в секундах
        """
        self.node = node
        self.mqtt = mqtt
        self.telemetry_interval_s = telemetry_interval_s
        self._running = False
        self._telemetry_task: Optional[asyncio.Task] = None
        self._on_demand_callback: Optional[Callable[[], None]] = None
    
    async def start(self):
        """Запустить публикацию телеметрии."""
        self._running = True
        
        # Запускаем задачу публикации телеметрии
        self._telemetry_task = asyncio.create_task(self._telemetry_loop())
        
        logger.info(f"Telemetry publisher started (interval={self.telemetry_interval_s}s)")
    
    async def stop(self):
        """Остановить публикацию телеметрии."""
        self._running = False
        
        if self._telemetry_task:
            self._telemetry_task.cancel()
            try:
                await self._telemetry_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Telemetry publisher stopped")
    
    def set_on_demand_callback(self, callback: Callable[[], None]):
        """
        Установить callback для публикации телеметрии on-demand.
        
        Args:
            callback: Функция, которая будет вызвана для публикации телеметрии
        """
        self._on_demand_callback = callback
    
    async def publish_on_demand(self):
        """
        Публиковать телеметрию on-demand (по команде hil_request_telemetry).
        """
        logger.info("Publishing telemetry on-demand")
        await self._publish_all_telemetry()
    
    async def _telemetry_loop(self):
        """Цикл публикации телеметрии."""
        while self._running:
            try:
                await self._publish_all_telemetry()
                await asyncio.sleep(self.telemetry_interval_s)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in telemetry loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _publish_all_telemetry(self):
        """Опубликовать телеметрию для всех каналов."""
        # Публикуем телеметрию для каждого сенсора
        for sensor in self.node.sensors:
            # Пропускаем ina209_ma и flow_present - они публикуются отдельно
            if sensor in ("ina209_ma", "flow_present"):
                continue
            await self._publish_channel_telemetry(sensor)
        
        # Публикуем ток INA209 как отдельный канал
        await self._publish_pump_bus_current()
        
        # Публикуем flow_present как отдельный канал
        await self._publish_flow_present_telemetry()
    
    async def _publish_channel_telemetry(self, channel: str):
        """Опубликовать телеметрию для канала."""
        # Определяем тип метрики по имени канала
        metric_type = self._get_metric_type(channel)
        
        # Получаем значение сенсора
        value = self.node.get_sensor_value(channel)
        if value is None:
            # Генерируем случайное значение для симуляции
            value = self._generate_simulated_value(channel)
            self.node.set_sensor_value(channel, value)
        
        # Формируем payload в формате, который ожидает history-logger:
        # metric_type (обязательное), value (обязательное), ts (seconds) (опционально)
        payload = {
            "metric_type": metric_type,
            "value": value,
            "ts": int(time.time()),
        }
        
        # Определяем топик используя единую библиотеку topics
        if self.node.mode == "preconfig":
            topic = temp_telemetry(self.node.hardware_id, channel)
        else:
            topic = telemetry(self.node.gh_uid, self.node.zone_uid, self.node.node_uid, channel)
        
        # Публикуем
        self.mqtt.publish_json(topic, payload, qos=1, retain=False)
        logger.debug(f"Published telemetry: {channel}={value}")
    
    async def _publish_pump_bus_current(self):
        """Опубликовать телеметрию суммарного тока насосов."""
        current_ma = self.node.get_sensor_value("ina209_ma") or 0.0
        
        # Формируем payload
        payload = {
            "metric_type": "PUMP_CURRENT",
            "value": current_ma,
            "ts": int(time.time()),
        }
        
        # Определяем топик используя единую библиотеку topics
        channel = "pump_bus_current"
        if self.node.mode == "preconfig":
            topic = temp_telemetry(self.node.hardware_id, channel)
        else:
            topic = telemetry(self.node.gh_uid, self.node.zone_uid, self.node.node_uid, channel)
        
        # Публикуем
        self.mqtt.publish_json(topic, payload, qos=1, retain=False)
        logger.debug(f"Published pump_bus_current telemetry: {current_ma}mA")
    
    async def _publish_flow_present_telemetry(self):
        """Опубликовать телеметрию flow_present."""
        flow_present = self.node.get_sensor_value("flow_present") or 0.0
        
        # Формируем payload
        payload = {
            "metric_type": "FLOW_RATE",
            "value": flow_present,
            "ts": int(time.time()),
        }
        
        # Определяем топик используя единую библиотеку topics
        if self.node.mode == "preconfig":
            topic = temp_telemetry(self.node.hardware_id, "flow_present")
        else:
            topic = telemetry(self.node.gh_uid, self.node.zone_uid, self.node.node_uid, "flow_present")
        
        # Публикуем
        self.mqtt.publish_json(topic, payload, qos=1, retain=False)
        logger.debug(f"Published flow_present telemetry: {flow_present}")
    
    def _get_metric_type(self, channel: str) -> str:
        """Определить тип метрики по имени канала."""
        channel_lower = channel.lower()

        # Явные маппинги под канонический формат метрик
        if channel_lower in ("ph_sensor", "ph"):
            return "PH"
        if channel_lower in ("ec_sensor", "ec"):
            return "EC"
        if channel_lower in ("air_temp_c", "temp_air", "temperature", "temp"):
            return "TEMPERATURE"
        if channel_lower in ("air_rh", "humidity", "rh"):
            return "HUMIDITY"
        if "co2" in channel_lower:
            return "CO2"
        if "lux" in channel_lower or "light" in channel_lower:
            return "LIGHT_INTENSITY"
        if channel_lower in ("ina209_ma", "current_ma", "current", "pump_bus_current"):
            return "PUMP_CURRENT"
        if channel_lower in ("flow_present", "flow"):
            return "FLOW_RATE"
        if channel_lower in ("solution_temp_c", "temp_solution", "solution_temp"):
            return "TEMPERATURE"

        return channel_lower.upper()
    
    def _generate_simulated_value(self, channel: str) -> float:
        """Сгенерировать симулированное значение для канала."""
        channel_lower = channel.lower()
        
        if "ph" in channel_lower:
            return round(random.uniform(5.5, 7.5), 2)
        elif "ec" in channel_lower:
            return round(random.uniform(1.0, 3.0), 2)
        elif "temp" in channel_lower:
            return round(random.uniform(18.0, 28.0), 1)
        elif "humidity" in channel_lower:
            return round(random.uniform(40.0, 80.0), 1)
        elif "light" in channel_lower:
            return round(random.uniform(0, 100), 1)
        else:
            return round(random.uniform(0, 100), 2)

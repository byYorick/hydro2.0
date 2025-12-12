"""
Публикация телеметрии для node-sim.
Публикует telemetry раз в N секунд, включает ток INA209, heartbeat.
"""

import asyncio
import logging
import time
import random
from typing import Optional

from .model import NodeModel
from .mqtt_client import MqttClient
from .topics import telemetry_topic, heartbeat_topic, status_topic

logger = logging.getLogger(__name__)


class TelemetryPublisher:
    """
    Публикатор телеметрии для node-sim.
    
    Публикует:
    - Telemetry для каждого канала раз в N секунд
    - Heartbeat периодически
    - Online status при старте
    - Ток INA209 в telemetry
    """
    
    def __init__(
        self,
        node: NodeModel,
        mqtt: MqttClient,
        telemetry_interval: float = 5.0,
        heartbeat_interval: float = 30.0
    ):
        """
        Инициализация публикатора телеметрии.
        
        Args:
            node: Модель ноды
            mqtt: MQTT клиент
            telemetry_interval: Интервал публикации телеметрии в секундах
            heartbeat_interval: Интервал публикации heartbeat в секундах
        """
        self.node = node
        self.mqtt = mqtt
        self.telemetry_interval = telemetry_interval
        self.heartbeat_interval = heartbeat_interval
        self._running = False
        self._telemetry_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Запустить публикацию телеметрии."""
        self._running = True
        
        # Публикуем online status
        await self._publish_status()
        
        # Запускаем задачи
        self._telemetry_task = asyncio.create_task(self._telemetry_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        logger.info("Telemetry publisher started")
    
    async def stop(self):
        """Остановить публикацию телеметрии."""
        self._running = False
        
        if self._telemetry_task:
            self._telemetry_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        
        logger.info("Telemetry publisher stopped")
    
    async def _telemetry_loop(self):
        """Цикл публикации телеметрии."""
        while self._running:
            try:
                await self._publish_all_telemetry()
                await asyncio.sleep(self.telemetry_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in telemetry loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _heartbeat_loop(self):
        """Цикл публикации heartbeat."""
        while self._running:
            try:
                await self._publish_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _publish_all_telemetry(self):
        """Опубликовать телеметрию для всех каналов."""
        # Публикуем телеметрию для каждого канала
        for channel in self.node.channels:
            await self._publish_channel_telemetry(channel)
        
        # Публикуем ток INA209 как отдельный канал
        await self._publish_ina209_telemetry()
    
    async def _publish_channel_telemetry(self, channel: str):
        """Опубликовать телеметрию для канала."""
        # Определяем тип метрики по имени канала
        metric_type = self._get_metric_type(channel)
        
        # Получаем значение канала
        value = self.node.get_channel_value(channel)
        if value is None:
            # Генерируем случайное значение для симуляции
            value = self._generate_simulated_value(channel)
            self.node.set_channel_value(channel, value)
        
        # Формируем payload согласно MQTT_SPEC_FULL.md
        payload = {
            "node_id": self.node.node_uid,
            "channel": channel,
            "metric_type": metric_type,
            "value": value,
            "timestamp": int(time.time())
        }
        
        # Определяем топик
        if self.node.mode.value == "preconfig":
            # Temp топик
            topic = f"hydro/gh-temp/zn-temp/{self.node.hardware_id}/{channel}/telemetry"
        else:
            topic = telemetry_topic(self.node.gh_uid, self.node.zone_uid, self.node.node_uid, channel)
        
        # Публикуем
        await self.mqtt.publish_json(topic, payload, qos=1, retain=False)
        logger.debug(f"Published telemetry: {channel}={value}")
    
    async def _publish_ina209_telemetry(self):
        """Опубликовать телеметрию тока INA209."""
        current_ma = self.node.get_ina209_current()
        
        # Формируем payload
        payload = {
            "node_id": self.node.node_uid,
            "channel": "ina209",
            "metric_type": "CURRENT",
            "value": current_ma,
            "timestamp": int(time.time())
        }
        
        # Определяем топик
        if self.node.mode.value == "preconfig":
            topic = f"hydro/gh-temp/zn-temp/{self.node.hardware_id}/ina209/telemetry"
        else:
            topic = telemetry_topic(self.node.gh_uid, self.node.zone_uid, self.node.node_uid, "ina209")
        
        # Публикуем
        await self.mqtt.publish_json(topic, payload, qos=1, retain=False)
        logger.debug(f"Published INA209 telemetry: {current_ma}mA")
    
    async def _publish_heartbeat(self):
        """Опубликовать heartbeat."""
        # Обновляем uptime
        self.node.uptime_seconds += int(self.heartbeat_interval)
        
        # Формируем payload согласно MQTT_SPEC_FULL.md
        payload = {
            "uptime": self.node.uptime_seconds,
            "free_heap": 200000,  # Симулируем свободную память
            "rssi": random.randint(-70, -50)  # Симулируем RSSI
        }
        
        # Определяем топик
        if self.node.mode.value == "preconfig":
            topic = f"hydro/gh-temp/zn-temp/{self.node.hardware_id}/heartbeat"
        else:
            topic = heartbeat_topic(self.node.gh_uid, self.node.zone_uid, self.node.node_uid)
        
        # Публикуем
        await self.mqtt.publish_json(topic, payload, qos=1, retain=False)
        logger.debug(f"Published heartbeat: uptime={self.node.uptime_seconds}s")
    
    async def _publish_status(self):
        """Опубликовать online status."""
        payload = {
            "status": "ONLINE",
            "ts": int(time.time())
        }
        
        # Определяем топик
        if self.node.mode.value == "preconfig":
            topic = f"hydro/gh-temp/zn-temp/{self.node.hardware_id}/status"
        else:
            topic = status_topic(self.node.gh_uid, self.node.zone_uid, self.node.node_uid)
        
        # Публикуем с retain=True согласно спецификации
        await self.mqtt.publish_json(topic, payload, qos=1, retain=True)
        logger.info(f"Published online status")
    
    def _get_metric_type(self, channel: str) -> str:
        """Определить тип метрики по имени канала."""
        channel_lower = channel.lower()
        
        if "ph" in channel_lower:
            return "PH"
        elif "ec" in channel_lower:
            return "EC"
        elif "temp" in channel_lower:
            return "TEMPERATURE"
        elif "humidity" in channel_lower:
            return "HUMIDITY"
        elif "light" in channel_lower:
            return "LIGHT"
        else:
            return channel.upper()
    
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


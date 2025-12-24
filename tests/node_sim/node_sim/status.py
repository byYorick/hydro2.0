"""
Публикация статуса и heartbeat для node-sim.

Публикует:
- status каждые status_interval_s секунд
- heartbeat каждые heartbeat_interval_s секунд
"""

import asyncio
import logging
import time
import random
from typing import Optional

from .model import NodeModel
from .mqtt_client import MqttClient
from .topics import (
    status, temp_status,
    heartbeat, temp_heartbeat
)

logger = logging.getLogger(__name__)


class StatusPublisher:
    """
    Публикатор статуса и heartbeat для node-sim.
    
    Публикует:
    - Status (ONLINE) каждые status_interval_s секунд
    - Heartbeat периодически каждые heartbeat_interval_s секунд
    """
    
    def __init__(
        self,
        node: NodeModel,
        mqtt: MqttClient,
        status_interval_s: float = 60.0,
        heartbeat_interval_s: float = 30.0
    ):
        """
        Инициализация публикатора статуса.
        
        Args:
            node: Модель ноды
            mqtt: MQTT клиент
            status_interval_s: Интервал публикации статуса в секундах
            heartbeat_interval_s: Интервал публикации heartbeat в секундах
        """
        self.node = node
        self.mqtt = mqtt
        self.status_interval_s = status_interval_s
        self.heartbeat_interval_s = heartbeat_interval_s
        self._running = False
        self._status_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._start_time = time.time()
    
    async def start(self):
        """Запустить публикацию статуса и heartbeat."""
        self._running = True
        self._start_time = time.time()
        
        # Публикуем online status сразу при старте
        await self._publish_status()
        
        # Запускаем задачи
        self._status_task = asyncio.create_task(self._status_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        logger.info(f"Status publisher started (status_interval={self.status_interval_s}s, heartbeat_interval={self.heartbeat_interval_s}s)")
    
    async def stop(self):
        """Остановить публикацию статуса и heartbeat."""
        self._running = False
        
        if self._status_task:
            self._status_task.cancel()
            try:
                await self._status_task
            except asyncio.CancelledError:
                pass
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Status publisher stopped")
    
    async def _status_loop(self):
        """Цикл публикации статуса."""
        while self._running:
            try:
                await asyncio.sleep(self.status_interval_s)
                if self._running:
                    await self._publish_status()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in status loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _heartbeat_loop(self):
        """Цикл публикации heartbeat."""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval_s)
                if self._running:
                    await self._publish_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    async def _publish_status(self):
        """Опубликовать online status."""
        payload = {
            "status": "ONLINE",
            "ts": int(time.time())
        }
        
        # Определяем топик используя единую библиотеку topics
        if self.node.mode == "preconfig":
            topic = temp_status(self.node.hardware_id)
        else:
            topic = status(self.node.gh_uid, self.node.zone_uid, self.node.node_uid)
        
        # Публикуем с retain=True согласно спецификации
        self.mqtt.publish_json(topic, payload, qos=1, retain=True)
        logger.debug(f"Published status: ONLINE")
    
    async def _publish_heartbeat(self):
        """Опубликовать heartbeat."""
        # Вычисляем uptime с момента старта
        uptime_seconds = int(time.time() - self._start_time)
        
        # Обновляем uptime в модели ноды
        self.node.uptime_seconds = uptime_seconds
        
        # Формируем payload согласно MQTT_SPEC_FULL.md
        payload = {
            "uptime": uptime_seconds,
            "free_heap": 200000,  # Симулируем свободную память
            "rssi": random.randint(-70, -50)  # Симулируем RSSI
        }
        
        # Определяем топик используя единую библиотеку topics
        if self.node.mode == "preconfig":
            topic = temp_heartbeat(self.node.hardware_id)
        else:
            topic = heartbeat(self.node.gh_uid, self.node.zone_uid, self.node.node_uid)
        
        # Публикуем
        self.mqtt.publish_json(topic, payload, qos=1, retain=False)
        logger.debug(f"Published heartbeat: uptime={uptime_seconds}s")


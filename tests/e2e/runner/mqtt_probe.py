"""
MQTT probe для проверки сообщений в MQTT брокере.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTProbe:
    """Проверки MQTT сообщений."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        """
        Инициализация MQTT probe.
        
        Args:
            host: Хост MQTT брокера
            port: Порт MQTT брокера
            username: Имя пользователя (опционально)
            password: Пароль (опционально)
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self._message_queue: List[Dict[str, Any]] = []
        self._subscribed_topics: List[str] = []
    
    def connect(self):
        """Подключиться к MQTT брокеру."""
        if self.connected:
            return
        
        self.client = mqtt.Client()
        
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)
        
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                self.connected = True
                logger.info(f"Connected to MQTT broker at {self.host}:{self.port}")
            else:
                logger.error(f"Failed to connect to MQTT broker: {rc}")
        
        def on_message(client, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = msg.payload.decode()
            
            message = {
                "topic": msg.topic,
                "payload": payload,
                "timestamp": datetime.now().isoformat(),
                "qos": msg.qos,
                "retain": msg.retain
            }
            
            self._message_queue.append(message)
            logger.debug(f"Received MQTT message on {msg.topic}: {payload}")
        
        self.client.on_connect = on_connect
        self.client.on_message = on_message
        
        self.client.connect(self.host, self.port, 60)
        self.client.loop_start()
        
        # Ждем подключения (синхронно, так как paho-mqtt синхронный)
        import time
        timeout = 10
        start = time.time()
        while not self.connected and (time.time() - start) < timeout:
            time.sleep(0.1)
        
        if not self.connected:
            raise RuntimeError(f"Failed to connect to MQTT broker within {timeout} seconds")
    
    def disconnect(self):
        """Отключиться от MQTT брокера."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
    
    def subscribe(self, topic: str, qos: int = 1):
        """
        Подписаться на MQTT топик.
        
        Args:
            topic: MQTT топик (может содержать wildcards # или +)
            qos: Quality of Service уровень
        """
        if not self.connected or not self.client:
            raise RuntimeError("MQTT not connected")
        
        self.client.subscribe(topic, qos)
        self._subscribed_topics.append(topic)
        logger.info(f"Subscribed to MQTT topic: {topic}")

    def publish_json(self, topic: str, payload: Any, qos: int = 1, retain: bool = False):
        """
        Опубликовать JSON payload в MQTT.
        """
        if not self.connected or not self.client:
            raise RuntimeError("MQTT not connected")
        data = json.dumps(payload).encode("utf-8") if not isinstance(payload, (bytes, bytearray)) else payload
        self.client.publish(topic, data, qos=qos, retain=retain)
        logger.info(f"Published MQTT message to {topic} (qos={qos}, retain={retain})")
    
    async def wait_message(
        self,
        topic: Optional[str] = None,
        timeout: float = 10.0,
        condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Ожидать сообщение на топике.
        
        Args:
            topic: Топик для ожидания (None для любого)
            timeout: Таймаут ожидания в секундах
            condition: Дополнительное условие для фильтрации сообщений
            
        Returns:
            Сообщение или None при таймауте
        """
        import time
        start_time = time.time()
        
        while True:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning(f"Timeout waiting for MQTT message on topic: {topic}")
                return None
            
            # Проверяем очередь сообщений
            for msg in self._message_queue:
                if topic is None or msg["topic"] == topic or self._topic_matches(msg["topic"], topic):
                    if condition is None or condition(msg):
                        return msg
            
            await asyncio.sleep(0.1)
    
    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """
        Проверить, соответствует ли топик паттерну (с поддержкой wildcards).
        
        Args:
            topic: Топик сообщения
            pattern: Паттерн с wildcards (#, +)
            
        Returns:
            True если соответствует
        """
        # Простая реализация для # и +
        if "#" in pattern:
            prefix = pattern.replace("#", "")
            return topic.startswith(prefix)
        elif "+" in pattern:
            # Более сложная логика для + (заменяет один уровень)
            pattern_parts = pattern.split("/")
            topic_parts = topic.split("/")
            if len(pattern_parts) != len(topic_parts):
                return False
            for p, t in zip(pattern_parts, topic_parts):
                if p != "+" and p != t:
                    return False
            return True
        else:
            return topic == pattern
    
    def get_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Получить последние сообщения.
        
        Args:
            limit: Максимальное количество сообщений
            
        Returns:
            Список последних сообщений
        """
        return self._message_queue[-limit:]
    
    def clear_messages(self):
        """Очистить очередь сообщений."""
        self._message_queue.clear()


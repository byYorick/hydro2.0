"""
MQTT клиент для node-sim с reconnect и backoff.
Использует asyncio-mqtt для асинхронной работы.
"""

import asyncio
import logging
from typing import Callable, Optional
import time

try:
    import asyncio_mqtt
except ImportError:
    asyncio_mqtt = None

logger = logging.getLogger(__name__)


class MqttClient:
    """
    Асинхронный MQTT клиент с автоматическим переподключением и backoff.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = None,
        tls: bool = False,
        ca_certs: Optional[str] = None,
        keepalive: int = 60
    ):
        """
        Инициализация MQTT клиента.
        
        Args:
            host: MQTT брокер host
            port: MQTT брокер port
            username: Имя пользователя (опционально)
            password: Пароль (опционально)
            client_id: ID клиента (опционально, генерируется автоматически)
            tls: Использовать TLS
            ca_certs: Путь к CA сертификату
            keepalive: Keepalive интервал в секундах
        """
        if asyncio_mqtt is None:
            raise ImportError("asyncio-mqtt не установлен. Установите: pip install asyncio-mqtt")
        
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client_id = client_id or f"node-sim-{int(time.time())}"
        self.tls = tls
        self.ca_certs = ca_certs
        self.keepalive = keepalive
        
        self._client: Optional[asyncio_mqtt.Client] = None
        self._connected = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._backoff_seconds = 1.0
        self._max_backoff = 60.0
        self._lock = asyncio.Lock()
        
    async def connect(self):
        """Подключиться к MQTT брокеру."""
        async with self._lock:
            if self._connected:
                logger.debug("Already connected to MQTT broker")
                return
            
            try:
                # Создаем клиент
                client_kwargs = {
                    "hostname": self.host,
                    "port": self.port,
                    "client_id": self.client_id,
                    "keepalive": self.keepalive,
                }
                
                if self.username:
                    client_kwargs["username"] = self.username
                if self.password:
                    client_kwargs["password"] = self.password
                if self.tls:
                    if self.ca_certs:
                        import ssl
                        ssl_context = ssl.create_default_context(cafile=self.ca_certs)
                        client_kwargs["tls_context"] = ssl_context
                    else:
                        client_kwargs["tls_context"] = True
                
                self._client = asyncio_mqtt.Client(**client_kwargs)
                await self._client.connect()
                self._connected = True
                self._backoff_seconds = 1.0  # Сброс backoff при успешном подключении
                logger.info(f"Connected to MQTT broker at {self.host}:{self.port}")
                
            except Exception as e:
                logger.error(f"Failed to connect to MQTT broker: {e}")
                self._connected = False
                raise
    
    async def disconnect(self):
        """Отключиться от MQTT брокера."""
        async with self._lock:
            if not self._connected:
                return
            
            try:
                if self._client:
                    await self._client.disconnect()
                self._connected = False
                logger.info("Disconnected from MQTT broker")
            except Exception as e:
                logger.error(f"Error disconnecting from MQTT broker: {e}")
    
    async def subscribe(self, topic: str, callback: Callable[[str, bytes], None], qos: int = 1):
        """
        Подписаться на топик.
        
        Args:
            topic: MQTT топик
            callback: Функция-обработчик (topic, payload)
            qos: QoS уровень (0, 1, 2)
        """
        if not self._connected:
            await self.connect()
        
        await self._client.subscribe(topic, qos=qos)
        logger.info(f"Subscribed to topic: {topic} (QoS={qos})")
        
        # Запускаем обработчик сообщений
        asyncio.create_task(self._message_handler(topic, callback))
    
    async def _message_handler(self, topic: str, callback: Callable[[str, bytes], None]):
        """Обработчик сообщений для топика."""
        async with self._client.messages() as messages:
            async for message in messages:
                if message.topic.value == topic:
                    try:
                        await callback(message.topic.value, message.payload)
                    except Exception as e:
                        logger.error(f"Error in message handler for {topic}: {e}", exc_info=True)
    
    async def publish(self, topic: str, payload: bytes, qos: int = 1, retain: bool = False):
        """
        Опубликовать сообщение в топик.
        
        Args:
            topic: MQTT топик
            payload: Данные (bytes)
            qos: QoS уровень
            retain: Retain флаг
        """
        if not self._connected:
            await self.connect()
        
        try:
            await self._client.publish(topic, payload, qos=qos, retain=retain)
            logger.debug(f"Published to {topic} (QoS={qos}, retain={retain})")
        except Exception as e:
            logger.error(f"Failed to publish to {topic}: {e}")
            self._connected = False
            # Запускаем переподключение
            asyncio.create_task(self._reconnect_with_backoff())
            raise
    
    async def publish_json(self, topic: str, data: dict, qos: int = 1, retain: bool = False):
        """
        Опубликовать JSON сообщение в топик.
        
        Args:
            topic: MQTT топик
            data: Словарь для сериализации в JSON
            qos: QoS уровень
            retain: Retain флаг
        """
        import json
        payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
        await self.publish(topic, payload, qos=qos, retain=retain)
    
    async def _reconnect_with_backoff(self):
        """Переподключение с экспоненциальным backoff."""
        if self._reconnect_task and not self._reconnect_task.done():
            return  # Уже идет переподключение
        
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())
    
    async def _reconnect_loop(self):
        """Цикл переподключения с backoff."""
        while not self._connected:
            try:
                await asyncio.sleep(self._backoff_seconds)
                logger.info(f"Attempting to reconnect to MQTT broker (backoff={self._backoff_seconds:.1f}s)")
                await self.connect()
                break  # Успешно подключились
            except Exception as e:
                logger.warning(f"Reconnection attempt failed: {e}")
                self._backoff_seconds = min(self._backoff_seconds * 2, self._max_backoff)
    
    def is_connected(self) -> bool:
        """Проверить, подключен ли клиент."""
        return self._connected


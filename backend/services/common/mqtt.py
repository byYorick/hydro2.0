import json
import logging
import threading
import time
from typing import Callable, Optional, List, Tuple

import paho.mqtt.client as mqtt

from .env import get_settings

logger = logging.getLogger(__name__)


class MqttClient:
    def __init__(self, client_id_suffix: str = ""):
        s = get_settings()
        self._host = s.mqtt_host
        self._port = s.mqtt_port
        self._subs: List[Tuple[str, int, Callable[[str, bytes], None]]] = []
        self._client = mqtt.Client(
            client_id=f"{s.mqtt_client_id}{client_id_suffix}",
            clean_session=s.mqtt_clean_session,
        )
        if s.mqtt_user:
            self._client.username_pw_set(s.mqtt_user, s.mqtt_pass or None)
        if s.mqtt_tls:
            if s.mqtt_ca_file:
                self._client.tls_set(ca_certs=s.mqtt_ca_file)
            else:
                self._client.tls_set()
        self._connected = threading.Event()
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._event_loop = None  # Будет установлен из AsyncMqttClient

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected.set()
            logger.info(f"MQTT client connected to {self._host}:{self._port}, subscribing to {len(self._subs)} topics")
            # resubscribe - создаем новые handlers с актуальным event_loop
            for topic, qos, handler in self._subs:
                self._client.subscribe(topic, qos=qos)
                wrapped_handler = self._wrap(handler, self._event_loop)
                self._client.message_callback_add(topic, wrapped_handler)
                logger.debug(
                    f"Subscribed to topic: {topic}, qos={qos}, "
                    f"event_loop_set={self._event_loop is not None}"
                )
        else:
            self._connected.clear()
            logger.error(f"MQTT connection failed with rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self._connected.clear()
        # reconnect with backoff
        backoff = 0.5
        while not self._connected.is_set():
            try:
                self._client.reconnect()
            except Exception:
                time.sleep(backoff)
                backoff = min(backoff * 2, 10)
            else:
                break

    def _wrap(self, handler: Callable[[str, bytes], None], event_loop=None):
        import asyncio
        import inspect
        
        def on_message(client, userdata, msg):
            try:
                # Проверяем, является ли handler корутиной
                if inspect.iscoroutinefunction(handler):
                    # КРИТИЧНО: Всегда используем свежее значение self._event_loop, 
                    # а не захваченное в замыкание, так как event_loop устанавливается
                    # после создания этого замыкания
                    current_loop = getattr(self, '_event_loop', None) or event_loop
                    
                    if current_loop and current_loop.is_running():
                        # Используем run_coroutine_threadsafe для безопасного вызова из MQTT thread
                        try:
                            future = asyncio.run_coroutine_threadsafe(
                                handler(msg.topic, msg.payload), 
                                current_loop
                            )
                            # Логируем только при ошибках или для важных сообщений
                            logger.debug(
                                f"MQTT message on {msg.topic}: scheduled async handler "
                                f"(future={future})"
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to schedule async handler for topic {msg.topic}: {e}",
                                exc_info=True
                            )
                    else:
                        # Fallback: выполняем handler в новом event loop
                        # Это критично для обработки node_hello и других сообщений
                        # даже если event_loop еще не установлен
                        logger.warning(
                            f"No running event loop available for async handler on topic {msg.topic}, "
                            f"event_loop_set={current_loop is not None}, "
                            f"creating new event loop for fallback execution"
                        )
                        try:
                            # Пытаемся получить текущий running loop (если мы в async контексте)
                            loop = asyncio.get_running_loop()
                            loop.create_task(handler(msg.topic, msg.payload))
                            logger.debug(f"Created task in running loop for topic {msg.topic}")
                        except RuntimeError:
                            # Нет running loop - создаем новый для выполнения handler
                            # Это критично для обработки node_hello и других важных сообщений
                            logger.warning(
                                f"No running event loop found for topic {msg.topic}. "
                                f"Creating new event loop for fallback execution to avoid dropped messages."
                            )
                            try:
                                # Создаем новый event loop в отдельном потоке для выполнения handler
                                # Это гарантирует, что node_hello и другие сообщения будут обработаны
                                def run_in_new_loop():
                                    new_loop = asyncio.new_event_loop()
                                    asyncio.set_event_loop(new_loop)
                                    try:
                                        new_loop.run_until_complete(handler(msg.topic, msg.payload))
                                        logger.debug(f"Handler executed in fallback event loop for topic {msg.topic}")
                                    finally:
                                        new_loop.close()
                                
                                # Запускаем в отдельном потоке, чтобы не блокировать MQTT callback
                                thread = threading.Thread(target=run_in_new_loop, daemon=True)
                                thread.start()
                                logger.info(f"Started fallback execution thread for topic {msg.topic}")
                            except Exception as fallback_error:
                                logger.error(
                                    f"Failed to execute handler in fallback event loop for topic {msg.topic}: {fallback_error}",
                                    exc_info=True
                                )
                else:
                    # Обычный синхронный handler
                    handler(msg.topic, msg.payload)
            except Exception as e:
                # Логируем исключения вместо молчаливого игнорирования
                logger.error(
                    f"Error in MQTT message handler for topic {msg.topic}: {e}",
                    exc_info=True
                )
        return on_message

    def start(self):
        """Start MQTT client and wait for connection. Raises exception if connection fails."""
        self._client.connect(self._host, self._port, keepalive=30)
        self._client.loop_start()
        # wait connected with timeout
        timeout = 10.0  # 10 seconds
        elapsed = 0.0
        check_interval = 0.1
        while elapsed < timeout:
            if self._connected.is_set():
                logger.info(f"MQTT client connected to {self._host}:{self._port}")
                return
            time.sleep(check_interval)
            elapsed += check_interval
        
        # Connection failed
        self._client.loop_stop()
        raise ConnectionError(
            f"MQTT client failed to connect to {self._host}:{self._port} within {timeout} seconds"
        )

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()

    def is_connected(self) -> bool:
        """Check if MQTT client is connected."""
        return self._connected.is_set()
    
    def publish_json(self, topic: str, payload: dict, qos: int = 1, retain: bool = False):
        """Publish JSON payload to MQTT topic. Raises exception if not connected or publish fails."""
        if not self.is_connected():
            raise ConnectionError(f"MQTT client is not connected, cannot publish to {topic}")
        
        try:
            data = json.dumps(payload, separators=(",", ":"))
            result = self._client.publish(topic, data, qos=qos, retain=retain)
            # rc == 0 means success in paho-mqtt
            if result.rc != 0:
                error_msg = f"MQTT publish failed with rc={result.rc} for topic {topic}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
        except Exception as e:
            logger.error(f"Error publishing to MQTT topic {topic}: {e}", exc_info=True)
            raise

    def subscribe(self, topic: str, handler: Callable[[str, bytes], None], qos: int = 1):
        """Подписаться на MQTT топик."""
        self._subs.append((topic, qos, handler))
        
        # Создаем wrapped_handler - event_loop будет получен из self._event_loop в момент вызова
        wrapped_handler = self._wrap(handler, self._event_loop)
        
        if self.is_connected():
            # Если уже подключены, подписываемся сразу
            self._client.subscribe(topic, qos=qos)
            self._client.message_callback_add(topic, wrapped_handler)
            logger.info(
                f"Subscribed to topic: {topic}, qos={qos}, "
                f"event_loop_set={self._event_loop is not None}, "
                f"is_running={self._event_loop.is_running() if self._event_loop else False}"
            )
        else:
            # Если не подключены, подписка произойдет в _on_connect
            # wrapped_handler будет использован там
            logger.debug(f"Deferred subscription to topic: {topic} (not connected yet)")


# Async wrapper для использования в async контексте
class AsyncMqttClient:
    """Async обертка над синхронным MqttClient для использования в async коде."""
    
    def __init__(self, client_id_suffix: str = ""):
        self._client = MqttClient(client_id_suffix=client_id_suffix)
        self._started = False
        self._event_loop = None  # Сохраняем ссылку на event loop
        # Передаем event loop в базовый клиент для использования в _wrap
        self._client._event_loop = None  # Будет установлен в start()
    
    async def start(self):
        """Запустить MQTT клиент (async обертка)."""
        import asyncio
        self._event_loop = asyncio.get_event_loop()
        # Передаем event loop в базовый клиент для использования в _wrap
        self._client._event_loop = self._event_loop
        await self._event_loop.run_in_executor(None, self._client.start)
        self._started = True
    
    async def stop(self):
        """Остановить MQTT клиент (async обертка)."""
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._client.stop)
        self._started = False
    
    async def subscribe(self, topic: str, handler: Callable[[str, bytes], None], qos: int = 1):
        """Подписаться на топик (async обертка)."""
        if not self._started:
            await self.start()
        
        # Убеждаемся, что event_loop установлен
        if not self._event_loop:
            import asyncio
            self._event_loop = asyncio.get_event_loop()
            self._client._event_loop = self._event_loop
        
        # Вызываем subscribe базового клиента
        # Базовый клиент использует self._event_loop в _wrap
        self._client.subscribe(topic, handler, qos)
    
    def is_connected(self) -> bool:
        """Проверить подключение."""
        return self._client.is_connected()


# Глобальный async MQTT клиент (singleton)
_async_mqtt_client: Optional[AsyncMqttClient] = None


async def get_mqtt_client(client_id_suffix: str = "-history-logger") -> AsyncMqttClient:
    """
    Получить глобальный async MQTT клиент (singleton).
    
    Args:
        client_id_suffix: Суффикс для client_id
        
    Returns:
        AsyncMqttClient
    """
    global _async_mqtt_client
    
    if _async_mqtt_client is None:
        _async_mqtt_client = AsyncMqttClient(client_id_suffix=client_id_suffix)
        # Важно: сначала запускаем клиент (устанавливается event_loop), потом можно подписываться
        await _async_mqtt_client.start()
        logger.info(f"MQTT client started, event_loop={_async_mqtt_client._event_loop is not None}")
    
    return _async_mqtt_client



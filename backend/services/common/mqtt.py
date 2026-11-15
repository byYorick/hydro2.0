import json
import logging
import threading
from typing import Callable, List, Optional, Tuple

import paho.mqtt.client as mqtt

from .env import get_settings

logger = logging.getLogger(__name__)


def apply_mqtt_tls(client: mqtt.Client, settings) -> None:
    """Включает TLS на paho-клиенте. CA берётся из MQTT_CA_FILE, если задан."""
    if settings.mqtt_ca_file:
        client.tls_set(ca_certs=settings.mqtt_ca_file)
    else:
        client.tls_set()
    if getattr(settings, "mqtt_tls_insecure", False):
        client.tls_insecure_set(True)

_async_handler_error_callbacks: list[Callable[[str, str, BaseException], None]] = []


def register_async_handler_error_callback(
    callback: Callable[[str, str, BaseException], None],
) -> None:
    """Register callback invoked when an async MQTT handler fails after scheduling."""
    _async_handler_error_callbacks.append(callback)


def _notify_async_handler_error(handler_name: str, topic: str, exc: BaseException) -> None:
    for callback in _async_handler_error_callbacks:
        try:
            callback(handler_name, topic, exc)
        except Exception:
            logger.error(
                "MQTT async handler error callback failed for handler=%s topic=%s",
                handler_name,
                topic,
                exc_info=True,
            )


def _make_async_done_callback(handler: Callable, topic: str):
    handler_name = getattr(handler, "__name__", "unknown")

    def _on_done(future) -> None:
        if future.cancelled():
            return
        try:
            exc = future.exception()
            if exc is not None:
                logger.error(
                    "Async MQTT handler %s failed for topic %s: %s",
                    handler_name,
                    topic,
                    exc,
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
                _notify_async_handler_error(handler_name, topic, exc)
        except Exception as callback_error:
            logger.error(
                "Error in MQTT async handler done_callback for topic %s: %s",
                topic,
                callback_error,
                exc_info=True,
            )

    return _on_done


class MqttClient:
    """
    Синхронный MQTT клиент на основе paho-mqtt.
    
    ВАЖНО: Этот клиент работает в отдельном потоке (paho-mqtt внутренний поток).
    Методы _on_connect() и _on_disconnect() вызываются из MQTT callback thread,
    поэтому не блокируют event loop основного приложения.
    
    Метод start() может вызываться через run_in_executor() из async контекста,
    блокируя executor thread, но не event loop.
    
    Все блокирующие операции используют threading.Event.wait() для неблокирующего
    ожидания, что позволяет прервать ожидание при установке соединения.
    """
    def __init__(self, client_id_suffix: str = "", *, manual_ack: bool = False):
        import os
        import sys
        s = get_settings()
        self._host = s.mqtt_host
        self._port = s.mqtt_port
        self._subs: List[Tuple[str, int, Callable[[str, bytes], None], bool]] = []
        self._manual_ack = manual_ack
        self._connection_generation = 0
        # Логируем переменную окружения и настройки TLS для диагностики
        mqtt_tls_env = os.getenv("MQTT_TLS", "NOT_SET")
        # Используем print для гарантированного вывода, так как логирование может быть не настроено
        print(f"[MQTT] MQTT_TLS env var: {mqtt_tls_env}, Settings mqtt_tls: {s.mqtt_tls}", file=sys.stderr, flush=True)
        print(f"[MQTT] MQTT client config: host={self._host}, port={self._port}, tls={s.mqtt_tls}, user={s.mqtt_user}", file=sys.stderr, flush=True)
        logger.info(f"MQTT_TLS env var: {mqtt_tls_env}, Settings mqtt_tls: {s.mqtt_tls}")
        logger.info(f"MQTT client config: host={self._host}, port={self._port}, tls={s.mqtt_tls}, user={s.mqtt_user}")
        callback_options = ({"callback_api_version": mqtt.CallbackAPIVersion.VERSION2}
                            if hasattr(mqtt, "CallbackAPIVersion") else {})
        self._client = mqtt.Client(
            client_id=f"{s.mqtt_client_id}{client_id_suffix}",
            clean_session=s.mqtt_clean_session,
            **callback_options,
        )
        if manual_ack:
            if s.mqtt_clean_session:
                raise ValueError("Durable MQTT ingress requires a persistent session")
            if not hasattr(self._client, "manual_ack_set"):
                raise RuntimeError("Durable MQTT ingress requires paho-mqtt >= 2")
            self._client.manual_ack_set(True)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        if s.mqtt_user:
            self._client.username_pw_set(s.mqtt_user, s.mqtt_pass or None)
        if s.mqtt_tls:
            logger.info("Enabling TLS for MQTT connection")
            apply_mqtt_tls(self._client, s)
        else:
            logger.info("TLS disabled for MQTT connection")
        self._connected = threading.Event()
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._event_loop = None  # Будет установлен из AsyncMqttClient

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._connection_generation = getattr(self, "_connection_generation", 0) + 1
            self._connected.set()
            logger.info(f"MQTT client connected to {self._host}:{self._port}, subscribing to {len(self._subs)} topics")
            print(f"[MQTT] Connected to {self._host}:{self._port}, will subscribe to {len(self._subs)} topics", flush=True)
            # resubscribe - создаем новые handlers с актуальным event_loop
            for topic, qos, handler, ack_after_handler in self._subs:
                self._client.subscribe(topic, qos=qos)
                wrapped_handler = self._wrap(handler, self._event_loop, ack_after_handler=ack_after_handler)
                self._client.message_callback_add(topic, wrapped_handler)
                logger.debug(
                    f"Subscribed to topic: {topic}, qos={qos}, "
                    f"event_loop_set={self._event_loop is not None}"
                )
        else:
            self._connected.clear()
            logger.error(f"MQTT connection failed with rc={rc}")

    def _on_disconnect(self, client, userdata, flags_or_rc, reason_code=None, properties=None):
        """Return immediately so Paho can reconnect and process CONNACK.

        This callback runs on Paho's network thread. Calling reconnect() and
        waiting here prevents that same thread from handling on_connect().
        loop_start() owns retry/backoff, including transient DNS failures.
        """
        rc = flags_or_rc if reason_code is None else reason_code
        self._connected.clear()
        if rc != 0:
            logger.warning(
                "MQTT client disconnected unexpectedly (rc=%s); network loop will reconnect",
                rc,
            )
        else:
            logger.info("MQTT client disconnected normally (rc=0)")

    def _ack_message(self, msg, generation: int) -> None:
        if not getattr(self, "_manual_ack", False) or msg.qos == 0:
            return
        if generation != self._connection_generation:
            return  # Never ACK a reused MID on a later connection/session.
        result = self._client.ack(msg.mid, msg.qos)
        if result != mqtt.MQTT_ERR_SUCCESS:
            logger.warning("MQTT ACK could not be sent for mid=%s; broker retains delivery", msg.mid)

    def _wrap(self, handler: Callable[[str, bytes], None], event_loop=None, *, ack_after_handler=False):
        import asyncio
        import inspect
        
        def on_message(client, userdata, msg):
            generation = getattr(self, "_connection_generation", 0)
            if ack_after_handler and msg.qos == 0:
                logger.warning("Durable telemetry requires QoS 1; rejecting QoS 0 on %s", msg.topic)
                _notify_async_handler_error(
                    getattr(handler, "__name__", "telemetry"), msg.topic,
                    ValueError("QoS 0 is outside the durable telemetry contract"),
                )
                return

            async def dispatch():
                await handler(msg.topic, msg.payload)
                if ack_after_handler:
                    self._ack_message(msg, generation)

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
                                dispatch(),
                                current_loop,
                            )
                            future.add_done_callback(
                                _make_async_done_callback(handler, msg.topic)
                            )
                            # Детальное логирование всех MQTT сообщений для диагностики
                            logger.info(
                                f"[MQTT] Message received on {msg.topic}: scheduled async handler "
                                f"(future={future}, payload_len={len(msg.payload)}, handler={handler.__name__ if hasattr(handler, '__name__') else 'unknown'})"
                            )
                            print(f"[MQTT] Message on {msg.topic}: payload_len={len(msg.payload)}, handler={handler.__name__ if hasattr(handler, '__name__') else 'unknown'}", flush=True)
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
                            loop.create_task(dispatch())
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
                                        new_loop.run_until_complete(dispatch())
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
                    if ack_after_handler:
                        self._ack_message(msg, generation)
                if not ack_after_handler:
                    self._ack_message(msg, generation)
            except Exception as e:
                # Логируем исключения вместо молчаливого игнорирования
                logger.error(
                    f"Error in MQTT message handler for topic {msg.topic}: {e}",
                    exc_info=True
                )
        return on_message

    def start(self):
        """
        Start MQTT client and wait for connection. Raises exception if connection fails.

        ВАЖНО: Этот метод может вызываться через run_in_executor() из async контекста,
        поэтому блокирует executor thread, но не event loop. Используем неблокирующее
        ожидание через threading.Event для возможности прервать ожидание.

        Transient DNS/connect ошибки (типичны при docker compose restart mqtt) —
        ретраим с backoff, чтобы lifespan HL/других сервисов не падал с первого раза.
        """
        # Если уже подключены, ничего не делаем - используем существующее соединение
        if self._connected.is_set():
            logger.debug("MQTT client already connected, skipping start()")
            return

        s = get_settings()
        client_id = self._client._client_id.decode() if isinstance(self._client._client_id, bytes) else self._client._client_id
        logger.info(
            f"Starting MQTT client: host={self._host}, port={self._port}, "
            f"tls={s.mqtt_tls}, user={s.mqtt_user}, client_id={client_id}"
        )

        connect_timeout = 5.0
        max_attempts = 6
        backoff = 0.5
        max_backoff = 5.0
        last_error: Optional[BaseException] = None

        for attempt in range(1, max_attempts + 1):
            try:
                # Проверяем, не запущен ли уже loop (чтобы не создавать дублирующие подключения)
                if hasattr(self._client, '_thread') and self._client._thread and self._client._thread.is_alive():
                    logger.debug("MQTT loop already running, attempting reconnect instead of new connection")
                    try:
                        self._client.reconnect()
                    except Exception as reconnect_error:
                        logger.warning(f"Reconnect failed, doing full reconnection: {reconnect_error}")
                        self._client.loop_stop()
                        self._client.connect(self._host, self._port, keepalive=60)
                        self._client.loop_start()
                else:
                    # Новое подключение
                    self._client.connect(self._host, self._port, keepalive=60)
                    self._client.loop_start()

                if self._connected.wait(timeout=connect_timeout):
                    logger.info(f"MQTT client connected to {self._host}:{self._port}")
                    return

                # Handshake timeout — останавливаем loop перед следующей попыткой
                self._client.loop_stop()
                last_error = ConnectionError(
                    f"MQTT client failed to connect to {self._host}:{self._port} "
                    f"within {connect_timeout} seconds"
                )
                logger.warning(
                    f"MQTT connect attempt {attempt}/{max_attempts} timed out "
                    f"({self._host}:{self._port})"
                )
            except Exception as e:
                last_error = e
                try:
                    self._client.loop_stop()
                except Exception:
                    pass
                logger.warning(
                    f"MQTT connect attempt {attempt}/{max_attempts} failed "
                    f"({self._host}:{self._port}, TLS={s.mqtt_tls}): {e}"
                )

            if attempt >= max_attempts:
                break
            # Даём шанс параллельно установившемуся on_connect
            if self._connected.wait(timeout=backoff):
                logger.info(
                    f"MQTT client connected to {self._host}:{self._port} during backoff"
                )
                return
            backoff = min(backoff * 2, max_backoff)

        logger.error(
            f"Failed to connect to MQTT broker {self._host}:{self._port} "
            f"(TLS={s.mqtt_tls}) after {max_attempts} attempts: {last_error}"
        )
        if isinstance(last_error, BaseException):
            raise last_error
        raise ConnectionError(
            f"MQTT client failed to connect to {self._host}:{self._port} "
            f"after {max_attempts} attempts"
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

    def subscribe(self, topic: str, handler: Callable[[str, bytes], None], qos: int = 1, *, ack_after_handler=False):
        """Подписаться на MQTT топик."""
        if ack_after_handler and (not self._manual_ack or qos < 1):
            raise ValueError("Deferred MQTT acknowledgement requires manual ACK mode and QoS >= 1")
        self._subs.append((topic, qos, handler, ack_after_handler))
        
        # Создаем wrapped_handler - event_loop будет получен из self._event_loop в момент вызова
        wrapped_handler = self._wrap(handler, self._event_loop, ack_after_handler=ack_after_handler)
        
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
    
    def __init__(self, client_id_suffix: str = "", *, manual_ack: bool = False):
        self._manual_ack = manual_ack
        self._client = MqttClient(client_id_suffix=client_id_suffix, manual_ack=manual_ack)
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
    
    async def subscribe(self, topic: str, handler: Callable[[str, bytes], None], qos: int = 1, *, ack_after_handler=False, start=True):
        """Подписаться на топик (async обертка)."""
        if not self._started and start:
            await self.start()
        
        # Убеждаемся, что event_loop установлен
        if not self._event_loop:
            import asyncio
            self._event_loop = asyncio.get_event_loop()
            self._client._event_loop = self._event_loop
        
        # Вызываем subscribe базового клиента
        # Базовый клиент использует self._event_loop в _wrap
        self._client.subscribe(topic, handler, qos, ack_after_handler=ack_after_handler)
    
    def is_connected(self) -> bool:
        """Проверить подключение."""
        return self._client.is_connected()


# Глобальный async MQTT клиент (singleton)
_async_mqtt_client: Optional[AsyncMqttClient] = None


async def get_mqtt_client(client_id_suffix: str = "-history-logger", *, manual_ack: bool = False, start: bool = True) -> AsyncMqttClient:
    """
    Получить глобальный async MQTT клиент (singleton).
    
    Args:
        client_id_suffix: Суффикс для client_id
        
    Returns:
        AsyncMqttClient
    """
    global _async_mqtt_client
    
    if _async_mqtt_client is None:
        _async_mqtt_client = AsyncMqttClient(client_id_suffix=client_id_suffix, manual_ack=manual_ack)
    if manual_ack and not _async_mqtt_client._manual_ack:
        raise RuntimeError("MQTT client was initialized without durable ingress acknowledgements")
    if start and not _async_mqtt_client._started:
        await _async_mqtt_client.start()
        logger.info(f"MQTT client started, event_loop={_async_mqtt_client._event_loop is not None}")
    
    return _async_mqtt_client



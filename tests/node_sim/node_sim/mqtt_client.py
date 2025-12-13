"""
MQTT клиент для node_sim с автоматическим переподключением, backoff и jitter.
Поддерживает подписки на команды в normal и preconfig режимах.
"""

import json
import random
import threading
import time
from typing import Callable, List, Optional, Tuple

import paho.mqtt.client as mqtt

from .logging import get_logger

logger = get_logger(__name__)


class MqttClient:
    """
    Устойчивый MQTT клиент с автоматическим переподключением.
    
    Особенности:
    - Экспоненциальный backoff с jitter для переподключения
    - QoS=1 для telemetry, command_response, error, status
    - Подписки на normal и temp топики команд
    - Логирование всех операций
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = None,
        keepalive: int = 60,
        tls: bool = False,
        ca_certs: Optional[str] = None,
    ):
        """
        Инициализация MQTT клиента.
        
        Args:
            host: MQTT брокер host
            port: MQTT брокер port
            username: Имя пользователя (опционально)
            password: Пароль (опционально)
            client_id: ID клиента (опционально, генерируется автоматически)
            keepalive: Keepalive интервал в секундах
            tls: Использовать TLS
            ca_certs: Путь к CA сертификату
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client_id = client_id or f"node-sim-{int(time.time() * 1000)}"
        self.keepalive = keepalive
        self.tls = tls
        self.ca_certs = ca_certs
        
        # Состояние подключения
        self._client: Optional[mqtt.Client] = None
        self._connected = threading.Event()
        self._connecting = False
        self._lock = threading.Lock()
        
        # Backoff параметры
        self._base_backoff = 1.0  # Начальная задержка в секундах
        self._max_backoff = 60.0  # Максимальная задержка в секундах
        self._current_backoff = self._base_backoff
        self._jitter_range = 0.3  # ±30% jitter
        
        # Подписки: список (topic, qos, callback)
        self._subscriptions: List[Tuple[str, int, Callable[[str, bytes], None]]] = []
        
        # Callback для обработки команд
        self._command_callback: Optional[Callable[[str, dict], None]] = None
        
        # Флаги режима работы
        self._preconfig_mode = False
        self._gh_uid: Optional[str] = None
        self._zone_uid: Optional[str] = None
        self._node_uid: Optional[str] = None
        self._node_hw_id: Optional[str] = None
        
    def set_node_info(
        self,
        gh_uid: str,
        zone_uid: str,
        node_uid: str,
        node_hw_id: Optional[str] = None,
        preconfig_mode: bool = False
    ):
        """
        Установить информацию об узле для формирования топиков.
        
        Args:
            gh_uid: UID теплицы
            zone_uid: UID зоны
            node_uid: UID узла
            node_hw_id: Hardware ID узла (для preconfig режима)
            preconfig_mode: Режим предварительной конфигурации
        """
        self._gh_uid = gh_uid
        self._zone_uid = zone_uid
        self._node_uid = node_uid
        self._node_hw_id = node_hw_id
        self._preconfig_mode = preconfig_mode
        
    def set_command_callback(self, callback: Callable[[str, dict], None]):
        """
        Установить callback для обработки команд.
        
        Args:
            callback: Функция (topic, command_dict) -> None
        """
        self._command_callback = callback
        
    def _create_client(self) -> mqtt.Client:
        """Создать новый MQTT клиент."""
        client = mqtt.Client(
            client_id=self.client_id,
            clean_session=True,
            protocol=mqtt.MQTTv311
        )
        
        # Настройка аутентификации
        if self.username:
            client.username_pw_set(self.username, self.password)
        
        # Настройка TLS
        if self.tls:
            if self.ca_certs:
                client.tls_set(ca_certs=self.ca_certs)
            else:
                client.tls_set()
        
        # Callbacks
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.on_subscribe = self._on_subscribe
        client.on_publish = self._on_publish
        
        return client
    
    def _on_connect(self, client: mqtt.Client, userdata, flags, rc: int):
        """Обработчик подключения."""
        if rc == 0:
            self._connected.set()
            self._current_backoff = self._base_backoff  # Сброс backoff
            logger.info(f"Connected to MQTT broker at {self.host}:{self.port}")
            
            # Переподписка на все топики
            self._resubscribe_all()
        else:
            self._connected.clear()
            logger.error(f"Failed to connect to MQTT broker: rc={rc}")
    
    def _on_disconnect(self, client: mqtt.Client, userdata, rc: int):
        """Обработчик отключения."""
        self._connected.clear()
        
        if rc == 0:
            logger.info("Disconnected from MQTT broker normally")
        else:
            logger.warning(f"Unexpected disconnect from MQTT broker: rc={rc}")
            # Запускаем переподключение в отдельном потоке
            threading.Thread(
                target=self._reconnect_with_backoff,
                daemon=True,
                name="mqtt-reconnect"
            ).start()
    
    def _on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        """Обработчик входящих сообщений."""
        try:
            topic = msg.topic
            payload = msg.payload
            
            # Парсим JSON если возможно
            try:
                data = json.loads(payload.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = None
            
            # Логируем получение команды
            if '/command' in topic:
                logger.info(f"✓ RECEIVED COMMAND on topic: {topic}, payload_len={len(payload)}")
                if data:
                    cmd_id = data.get('cmd_id', 'unknown')
                    cmd = data.get('cmd', 'unknown')
                    logger.info(f"  → cmd_id={cmd_id}, cmd={cmd}, params={data.get('params', {})}")
                else:
                    logger.warning(f"  → Failed to parse command JSON: {payload[:100]}")
                
                # Вызываем callback если установлен
                if self._command_callback and data:
                    try:
                        self._command_callback(topic, data)
                    except Exception as e:
                        logger.error(f"Error in command callback: {e}", exc_info=True)
            
            # Вызываем специфичные обработчики для подписок
            for sub_topic, _, callback in self._subscriptions:
                if self._topic_matches(topic, sub_topic):
                    try:
                        callback(topic, payload)
                    except Exception as e:
                        logger.error(f"Error in subscription callback for {sub_topic}: {e}", exc_info=True)
                        
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}", exc_info=True)
    
    def _on_subscribe(self, client: mqtt.Client, userdata, mid, granted_qos):
        """Обработчик успешной подписки."""
        logger.info(f"Subscribed topics: mid={mid}, granted_qos={granted_qos}")
    
    def _on_publish(self, client: mqtt.Client, userdata, mid):
        """Обработчик успешной публикации."""
        logger.debug(f"Published response: mid={mid}")
    
    def _topic_matches(self, topic: str, pattern: str) -> bool:
        """
        Проверить, соответствует ли топик паттерну.
        Поддерживает wildcard + в паттерне.
        """
        # Простая проверка для паттернов с +
        pattern_parts = pattern.split('/')
        topic_parts = topic.split('/')
        
        if len(pattern_parts) != len(topic_parts):
            return False
        
        for p, t in zip(pattern_parts, topic_parts):
            if p == '+':
                continue
            if p != t:
                return False
        
        return True
    
    def _resubscribe_all(self):
        """Переподписаться на все топики после переподключения."""
        if not self._client:
            return
        
        # Подписки на команды
        if self._gh_uid and self._zone_uid and self._node_uid:
            if self._preconfig_mode:
                # Preconfig режим: hydro/gh-temp/zn-temp/{node_uid_or_hw}/+/command
                node_id = self._node_hw_id or self._node_uid
                temp_topic = f"hydro/gh-temp/zn-temp/{node_id}/+/command"
                self._client.subscribe(temp_topic, qos=1)
                logger.info(f"Subscribed to temp command topic: {temp_topic}")
            else:
                # Normal режим: hydro/{gh}/{zone}/{node}/+/command
                normal_topic = f"hydro/{self._gh_uid}/{self._zone_uid}/{self._node_uid}/+/command"
                self._client.subscribe(normal_topic, qos=1)
                logger.info(f"Subscribed to normal command topic: {normal_topic}")
        
        # Переподписка на дополнительные подписки
        for topic, qos, _ in self._subscriptions:
            self._client.subscribe(topic, qos=qos)
            logger.info(f"Resubscribed to topic: {topic} (QoS={qos})")
    
    def connect(self, timeout: float = 10.0) -> bool:
        """
        Подключиться к MQTT брокеру.
        
        Args:
            timeout: Таймаут подключения в секундах
            
        Returns:
            True если подключение успешно, False иначе
        """
        with self._lock:
            if self._connected.is_set():
                logger.debug("Already connected to MQTT broker")
                return True
            
            if self._connecting:
                logger.debug("Connection already in progress")
                return False
            
            self._connecting = True
        
        try:
            self._client = self._create_client()
            self._client.connect_async(self.host, self.port, self.keepalive)
            self._client.loop_start()
            
            # Ждем подключения
            if self._connected.wait(timeout=timeout):
                logger.info("Successfully connected to MQTT broker")
                return True
            else:
                logger.error(f"Connection timeout after {timeout}s")
                self._client.loop_stop()
                self._client = None
                return False
                
        except Exception as e:
            logger.error(f"Error connecting to MQTT broker: {e}", exc_info=True)
            if self._client:
                try:
                    self._client.loop_stop()
                except:
                    pass
                self._client = None
            return False
        finally:
            with self._lock:
                self._connecting = False
    
    def _reconnect_with_backoff(self):
        """Переподключение с экспоненциальным backoff и jitter."""
        logger.info("Starting reconnection with exponential backoff")
        
        while not self._connected.is_set():
            # Вычисляем задержку с jitter
            jitter = random.uniform(
                -self._jitter_range * self._current_backoff,
                self._jitter_range * self._current_backoff
            )
            delay = max(0.1, self._current_backoff + jitter)
            
            logger.info(f"Reconnecting in {delay:.2f}s (backoff={self._current_backoff:.2f}s ± {self._jitter_range*100:.0f}%)")
            time.sleep(delay)
            
            # Попытка переподключения
            if self.connect(timeout=5.0):
                logger.info("Successfully reconnected to MQTT broker")
                break
            else:
                # Увеличиваем backoff экспоненциально
                self._current_backoff = min(
                    self._current_backoff * 2,
                    self._max_backoff
                )
                logger.warning(f"Reconnection failed, next attempt in {self._current_backoff:.2f}s")
    
    def disconnect(self):
        """Отключиться от MQTT брокера."""
        with self._lock:
            if not self._client:
                return
            
            try:
                self._client.loop_stop()
                self._client.disconnect()
                self._connected.clear()
                logger.info("Disconnected from MQTT broker")
            except Exception as e:
                logger.error(f"Error disconnecting from MQTT broker: {e}", exc_info=True)
            finally:
                self._client = None
    
    def subscribe(
        self,
        topic: str,
        callback: Callable[[str, bytes], None],
        qos: int = 1
    ):
        """
        Подписаться на топик.
        
        Args:
            topic: MQTT топик
            callback: Функция-обработчик (topic, payload)
            qos: QoS уровень (по умолчанию 1)
        """
        if not self._connected.is_set():
            logger.warning("Not connected, subscription will be made after connection")
        
        self._subscriptions.append((topic, qos, callback))
        
        if self._client and self._connected.is_set():
            self._client.subscribe(topic, qos=qos)
            logger.info(f"Subscribed to topic: {topic} (QoS={qos})")
    
    def subscribe_commands(self):
        """
        Подписаться на топики команд в зависимости от режима.
        Вызывается после установки node_info через set_node_info().
        """
        if not self._gh_uid or not self._zone_uid or not self._node_uid:
            logger.warning("Node info not set, cannot subscribe to commands")
            return
        
        if not self._connected.is_set():
            logger.warning("Not connected, command subscription will be made after connection")
            return
        
        if self._preconfig_mode:
            # Preconfig режим: hydro/gh-temp/zn-temp/{node_uid_or_hw}/+/command
            node_id = self._node_hw_id or self._node_uid
            temp_topic = f"hydro/gh-temp/zn-temp/{node_id}/+/command"
            self._client.subscribe(temp_topic, qos=1)
            logger.info(f"Subscribed to temp command topic: {temp_topic}")
        else:
            # Normal режим: hydro/{gh}/{zone}/{node}/+/command
            normal_topic = f"hydro/{self._gh_uid}/{self._zone_uid}/{self._node_uid}/+/command"
            self._client.subscribe(normal_topic, qos=1)
            logger.info(f"Subscribed to normal command topic: {normal_topic}")
    
    def publish(
        self,
        topic: str,
        payload: bytes,
        qos: int = 1,
        retain: bool = False
    ) -> bool:
        """
        Опубликовать сообщение в топик.
        
        Args:
            topic: MQTT топик
            payload: Данные (bytes)
            qos: QoS уровень (по умолчанию 1)
            retain: Retain флаг
            
        Returns:
            True если публикация успешна, False иначе
        """
        if not self._connected.is_set():
            logger.warning("Not connected, cannot publish")
            return False
        
        try:
            result = self._client.publish(topic, payload, qos=qos, retain=retain)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"Published response to {topic} (QoS={qos}, retain={retain}, payload_len={len(payload)})")
                return True
            else:
                logger.error(f"Failed to publish to {topic}: rc={result.rc}")
                return False
        except Exception as e:
            logger.error(f"Error publishing to {topic}: {e}", exc_info=True)
            return False
    
    def publish_json(
        self,
        topic: str,
        data: dict,
        qos: int = 1,
        retain: bool = False
    ) -> bool:
        """
        Опубликовать JSON сообщение в топик.
        
        Args:
            topic: MQTT топик
            data: Словарь для сериализации в JSON
            qos: QoS уровень (по умолчанию 1)
            retain: Retain флаг
            
        Returns:
            True если публикация успешна, False иначе
        """
        try:
            payload = json.dumps(data, separators=(',', ':')).encode('utf-8')
            return self.publish(topic, payload, qos=qos, retain=retain)
        except Exception as e:
            logger.error(f"Error serializing JSON for {topic}: {e}", exc_info=True)
            return False
    
    def publish_telemetry(
        self,
        channel: str,
        data: dict,
        qos: int = 1
    ) -> bool:
        """
        Опубликовать telemetry сообщение.
        
        Args:
            channel: Имя канала
            data: Данные телеметрии
            qos: QoS уровень (по умолчанию 1, как требуется)
            
        Returns:
            True если публикация успешна, False иначе
        """
        if not self._gh_uid or not self._zone_uid or not self._node_uid:
            logger.warning("Node info not set, cannot publish telemetry")
            return False
        
        topic = f"hydro/{self._gh_uid}/{self._zone_uid}/{self._node_uid}/{channel}/telemetry"
        return self.publish_json(topic, data, qos=qos, retain=False)
    
    def publish_command_response(
        self,
        channel: str,
        data: dict,
        qos: int = 1
    ) -> bool:
        """
        Опубликовать command_response сообщение.
        
        Args:
            channel: Имя канала
            data: Данные ответа
            qos: QoS уровень (по умолчанию 1, как требуется)
            
        Returns:
            True если публикация успешна, False иначе
        """
        if not self._gh_uid or not self._zone_uid or not self._node_uid:
            logger.warning("Node info not set, cannot publish command_response")
            return False
        
        topic = f"hydro/{self._gh_uid}/{self._zone_uid}/{self._node_uid}/{channel}/command_response"
        return self.publish_json(topic, data, qos=qos, retain=False)
    
    def publish_status(
        self,
        data: dict,
        qos: int = 1,
        retain: bool = True
    ) -> bool:
        """
        Опубликовать status сообщение.
        
        Args:
            data: Данные статуса
            qos: QoS уровень (по умолчанию 1, как требуется)
            retain: Retain флаг (по умолчанию True для status)
            
        Returns:
            True если публикация успешна, False иначе
        """
        if not self._gh_uid or not self._zone_uid or not self._node_uid:
            logger.warning("Node info not set, cannot publish status")
            return False
        
        topic = f"hydro/{self._gh_uid}/{self._zone_uid}/{self._node_uid}/status"
        return self.publish_json(topic, data, qos=qos, retain=retain)
    
    def publish_error(
        self,
        channel: str,
        data: dict,
        qos: int = 1
    ) -> bool:
        """
        Опубликовать error сообщение.
        
        Args:
            channel: Имя канала
            data: Данные ошибки
            qos: QoS уровень (по умолчанию 1, как требуется)
            
        Returns:
            True если публикация успешна, False иначе
        """
        if not self._gh_uid or not self._zone_uid or not self._node_uid:
            logger.warning("Node info not set, cannot publish error")
            return False
        
        topic = f"hydro/{self._gh_uid}/{self._zone_uid}/{self._node_uid}/{channel}/error"
        return self.publish_json(topic, data, qos=qos, retain=False)
    
    def is_connected(self) -> bool:
        """Проверить, подключен ли клиент."""
        return self._connected.is_set()

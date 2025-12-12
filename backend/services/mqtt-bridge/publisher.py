from typing import Dict, Any, Optional
import logging
import threading

from common.mqtt import MqttClient
from common.env import get_settings

logger = logging.getLogger(__name__)


class Publisher:
    def __init__(self):
        """Инициализация Publisher без подключения к MQTT."""
        self._mqtt = MqttClient(client_id_suffix="-bridge")
        self._ready = threading.Event()  # Флаг готовности MQTT
        self._retry_task = None  # Фоновая задача ретраев
        self._shutdown = threading.Event()  # Флаг для остановки ретраев
    
    def is_ready(self) -> bool:
        """Проверить, готов ли Publisher к работе (MQTT подключен)."""
        return self._ready.is_set() and self._mqtt.is_connected()
    
    def start(self):
        """Запустить подключение к MQTT и фоновые ретраи."""
        try:
            self._mqtt.start()
            if self._mqtt.is_connected():
                self._ready.set()
                logger.info("Publisher MQTT connected successfully")
            else:
                logger.warning("Publisher MQTT start() completed but not connected yet")
        except Exception as e:
            logger.error(f"Failed to start Publisher MQTT: {e}", exc_info=True)
            # Не устанавливаем _ready, но продолжаем попытки в фоне
        
        # Запускаем фоновую задачу ретраев
        self._start_retry_loop()
    
    def _start_retry_loop(self):
        """Запустить фоновый поток для ретраев подключения к MQTT."""
        def retry_loop():
            """Фоновая задача для периодических попыток подключения."""
            retry_interval = 5.0  # Интервал между попытками (секунды)
            max_retry_interval = 60.0  # Максимальный интервал
            current_interval = retry_interval
            
            while not self._shutdown.is_set():
                try:
                    if not self._mqtt.is_connected():
                        logger.info("Publisher MQTT not connected, attempting to reconnect...")
                        try:
                            # Пытаемся переподключиться
                            if not self._mqtt.is_connected():
                                self._mqtt.start()
                            
                            # Проверяем результат
                            if self._mqtt.is_connected():
                                self._ready.set()
                                current_interval = retry_interval  # Сбрасываем интервал при успехе
                                logger.info("Publisher MQTT reconnected successfully")
                            else:
                                logger.warning(f"Publisher MQTT reconnection attempt failed, will retry in {current_interval}s")
                        except Exception as reconnect_error:
                            logger.warning(f"Publisher MQTT reconnection error: {reconnect_error}, will retry in {current_interval}s")
                            # Увеличиваем интервал при ошибке (exponential backoff)
                            current_interval = min(current_interval * 1.5, max_retry_interval)
                    else:
                        # Если подключены, сбрасываем интервал и проверяем готовность
                        if not self._ready.is_set():
                            self._ready.set()
                            logger.info("Publisher MQTT connection confirmed, ready")
                        current_interval = retry_interval
                    
                    # Ждем перед следующей проверкой
                    self._shutdown.wait(timeout=current_interval)
                except Exception as e:
                    logger.error(f"Error in Publisher retry loop: {e}", exc_info=True)
                    self._shutdown.wait(timeout=current_interval)
        
        # Запускаем в отдельном потоке
        retry_thread = threading.Thread(target=retry_loop, daemon=True, name="PublisherRetryLoop")
        retry_thread.start()
        logger.info("Publisher retry loop started")
    
    def stop(self):
        """Остановить Publisher и закрыть MQTT соединение."""
        logger.info("Stopping Publisher...")
        self._shutdown.set()
        try:
            self._mqtt.stop()
        except Exception as e:
            logger.error(f"Error stopping Publisher MQTT: {e}", exc_info=True)
        self._ready.clear()
        logger.info("Publisher stopped")

    def publish_command(self, gh_uid: str, zone_id: int, node_uid: str, channel: str, payload: Dict[str, Any], hardware_id: Optional[str] = None, zone_uid: Optional[str] = None, node_preconfig: bool = False):
        """
        Публиковать команду в MQTT.
        
        Правило публикации (одна команда = один publish path):
        - Если node_preconfig=True (PRECONFIG) → публикуем ТОЛЬКО в temp-topic
        - Если node_preconfig=False → публикуем ТОЛЬКО в main-topic
        
        Temp-topic: hydro/gh-temp/zn-temp/{hardware_id}/{channel}/command
        Main-topic: hydro/{gh_uid}/{zone_segment}/{node_uid}/{channel}/command
        
        QoS: 1, Retain: false
        
        Args:
            gh_uid: Greenhouse UID
            zone_id: Zone ID
            node_uid: Node UID
            channel: Channel name
            payload: Command payload (dict with cmd, cmd_id, params)
            hardware_id: Hardware ID для временного топика (обязателен если node_preconfig=True)
            zone_uid: Zone UID для использования в топике, если mqtt_zone_format="uid" (опционально)
            node_preconfig: Флаг PRECONFIG состояния (lifecycle_state = REGISTERED_BACKEND)
        
        Returns:
            bool: True если публикация успешна, False в противном случае
        
        Raises:
            ConnectionError: Если MQTT не подключен
            ValueError: Если параметры невалидны
            RuntimeError: Если публикация не удалась
        """
        # Проверяем готовность MQTT
        if not self.is_ready():
            raise ConnectionError("MQTT client is not connected and ready")
        
        # Валидация входных параметров
        if not gh_uid or not node_uid or not channel:
            raise ValueError(f"Invalid parameters: gh_uid={gh_uid}, node_uid={node_uid}, channel={channel}")
        
        # Валидация: если PRECONFIG, то hardware_id обязателен
        if node_preconfig and not hardware_id:
            raise ValueError(f"hardware_id is required when node_preconfig=True for node {node_uid}")
        
        try:
            s = get_settings()
            
            # ОДНА КОМАНДА = ОДИН PUBLISH PATH
            if node_preconfig:
                # PRECONFIG: публикуем ТОЛЬКО в temp-topic
                temp_topic = f"hydro/gh-temp/zn-temp/{hardware_id}/{channel}/command"
                logger.info(f"Publishing command to temp topic (PRECONFIG): {temp_topic}, node_uid: {node_uid}, hardware_id: {hardware_id}, channel: {channel}")
                self._mqtt.publish_json(temp_topic, payload, qos=1, retain=False)
                logger.info(f"Command published successfully to temp topic: {temp_topic}")
            else:
                # НЕ PRECONFIG: публикуем ТОЛЬКО в main-topic
                zone_segment = f"zn-{zone_id}"  # id by default
                if s.mqtt_zone_format == "uid" and zone_uid:
                    zone_segment = zone_uid
                elif s.mqtt_zone_format == "uid":
                    logger.warning(f"mqtt_zone_format=uid but zone_uid not provided, using zn-{zone_id} (may cause mismatch with node subscription)")
                
                main_topic = f"hydro/{gh_uid}/{zone_segment}/{node_uid}/{channel}/command"
                logger.info(f"Publishing command to main topic: {main_topic}, node_uid: {node_uid}, channel: {channel}, zone_id: {zone_id}, zone_segment: {zone_segment}")
                self._mqtt.publish_json(main_topic, payload, qos=1, retain=False)
                logger.info(f"Command published successfully to main topic: {main_topic}")
            
            return True
        except Exception as e:
            logger.error(f"Error publishing command for node {node_uid}: {e}", exc_info=True)
            raise

    def publish_config(self, gh_uid: str, zone_id: int, node_uid: str, config: Dict[str, Any], hardware_id: Optional[str] = None, node_preconfig: bool = False):
        """
        Публиковать NodeConfig в MQTT.
        
        Правило публикации (один конфиг = один publish path):
        - Если node_preconfig=True (PRECONFIG) → публикуем ТОЛЬКО в temp-topic
        - Если node_preconfig=False → публикуем ТОЛЬКО в main-topic
        
        Temp-topic: hydro/gh-temp/zn-temp/{hardware_id}/config
        Main-topic: hydro/{gh_uid}/{zone_segment}/{node_uid}/config
        
        QoS: 1, Retain: true (чтобы узел получил конфигурацию при подписке)
        
        Args:
            gh_uid: Greenhouse UID
            zone_id: Zone ID
            node_uid: Node UID
            config: NodeConfig dict
            hardware_id: Hardware ID для временного топика (обязателен если node_preconfig=True)
            node_preconfig: Флаг PRECONFIG состояния (lifecycle_state = REGISTERED_BACKEND)
        
        Returns:
            bool: True если публикация успешна, False в противном случае
        
        Raises:
            ConnectionError: Если MQTT не подключен
            ValueError: Если параметры невалидны
            RuntimeError: Если публикация не удалась
        """
        # Проверяем готовность MQTT
        if not self.is_ready():
            raise ConnectionError("MQTT client is not connected and ready")
        
        # Валидация: если PRECONFIG, то hardware_id обязателен
        if node_preconfig and not hardware_id:
            raise ValueError(f"hardware_id is required when node_preconfig=True for node {node_uid}")
        
        try:
            s = get_settings()
            
            # ОДИН КОНФИГ = ОДИН PUBLISH PATH
            if node_preconfig:
                # PRECONFIG: публикуем ТОЛЬКО в temp-topic
                temp_topic = f"hydro/gh-temp/zn-temp/{hardware_id}/config"
                logger.info(f"Publishing config to temp topic (PRECONFIG): {temp_topic}, node_uid: {node_uid}, hardware_id: {hardware_id}")
                self._mqtt.publish_json(temp_topic, config, qos=1, retain=True)
                logger.info(f"Config published successfully to temp topic: {temp_topic}")
            else:
                # НЕ PRECONFIG: публикуем ТОЛЬКО в main-topic
                zone_segment = f"zn-{zone_id}"  # id by default
                if s.mqtt_zone_format == "uid" and config.get("zone_uid"):
                    zone_segment = config["zone_uid"]
                
                main_topic = f"hydro/{gh_uid}/{zone_segment}/{node_uid}/config"
                logger.info(f"Publishing config to main topic: {main_topic}, node_uid: {node_uid}, zone_id: {zone_id}")
                self._mqtt.publish_json(main_topic, config, qos=1, retain=True)
                logger.info(f"Config published successfully to main topic: {main_topic}")
            
            return True
        except Exception as e:
            logger.error(f"Error publishing config for node {node_uid}: {e}", exc_info=True)
            raise



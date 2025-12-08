from typing import Dict, Any, Optional
import logging

from common.mqtt import MqttClient
from common.env import get_settings

logger = logging.getLogger(__name__)


class Publisher:
    def __init__(self):
        self._mqtt = MqttClient(client_id_suffix="-bridge")
        self._mqtt.start()

    def publish_command(self, gh_uid: str, zone_id: int, node_uid: str, channel: str, payload: Dict[str, Any], hardware_id: Optional[str] = None, zone_uid: Optional[str] = None):
        """
        Публиковать команду в MQTT.
        
        Топик: hydro/{gh_uid}/{zone_segment}/{node_uid}/{channel}/command
        QoS: 1
        Retain: false
        
        Также публикуем на временный топик (gh-temp/zn-temp/{hardware_id}/{channel}/command),
        если узел еще не получил конфигурацию и подписан на временные идентификаторы.
        Используем hardware_id для временного топика, чтобы избежать конфликтов при одинаковом node_uid.
        
        Args:
            gh_uid: Greenhouse UID
            zone_id: Zone ID
            node_uid: Node UID
            channel: Channel name
            payload: Command payload (dict with cmd, cmd_id, params)
            hardware_id: Hardware ID для временного топика (опционально)
            zone_uid: Zone UID для использования в топике, если mqtt_zone_format="uid" (опционально)
        """
        try:
            # Проверяем подключение - используем reconnect вместо start для сохранения соединения
            if not self._mqtt.is_connected():
                logger.warning("MQTT client not connected, attempting to reconnect...")
                try:
                    # Используем start() который теперь умный и проверяет существующее подключение
                    # Это предотвратит создание новых подключений
                    self._mqtt.start()
                    # Дополнительная проверка после попытки переподключения
                    if not self._mqtt.is_connected():
                        raise ConnectionError("MQTT client failed to reconnect")
                    logger.info("MQTT client reconnected successfully")
                except Exception as reconnect_error:
                    logger.error(f"Failed to reconnect MQTT client: {reconnect_error}", exc_info=True)
                    raise ConnectionError(f"MQTT client is not connected and reconnection failed: {reconnect_error}")
            
            # Валидация входных параметров
            if not gh_uid or not node_uid or not channel:
                raise ValueError(f"Invalid parameters: gh_uid={gh_uid}, node_uid={node_uid}, channel={channel}")
            
            s = get_settings()
            zone_segment = f"zn-{zone_id}"  # id by default
            # Исправлено: используем zone_uid из параметра, а не из payload (zone_uid нет в payload команд)
            if s.mqtt_zone_format == "uid" and zone_uid:
                zone_segment = zone_uid
            elif s.mqtt_zone_format == "uid":
                logger.warning(f"mqtt_zone_format=uid but zone_uid not provided, using zn-{zone_id} (may cause mismatch with node subscription)")
            
            # Публикуем на правильный топик
            topic = f"hydro/{gh_uid}/{zone_segment}/{node_uid}/{channel}/command"
            logger.info(f"Publishing command to topic: {topic}, node_uid: {node_uid}, channel: {channel}, zone_id: {zone_id}, zone_segment: {zone_segment}")
            self._mqtt.publish_json(topic, payload, qos=1, retain=False)
            logger.info(f"Command published successfully to {topic}")
            
            # Также публикуем на временный топик для узлов, которые еще не получили конфигурацию
            # Узел может быть подписан на временные идентификаторы до получения первой конфигурации
            # Используем hardware_id для временного топика, чтобы избежать конфликтов при одинаковом node_uid
            if hardware_id:
                temp_topic = f"hydro/gh-temp/zn-temp/{hardware_id}/{channel}/command"
                logger.info(f"Publishing command to temp topic: {temp_topic} (using hardware_id)")
                self._mqtt.publish_json(temp_topic, payload, qos=1, retain=False)
                logger.info(f"Command published successfully to {temp_topic}")
            else:
                # Fallback: используем node_uid, если hardware_id не указан (для обратной совместимости)
                temp_topic = f"hydro/gh-temp/zn-temp/{node_uid}/{channel}/command"
                logger.warning(f"hardware_id not provided, using node_uid for temp topic: {temp_topic} (may cause conflicts)")
                self._mqtt.publish_json(temp_topic, payload, qos=1, retain=False)
                logger.info(f"Command published successfully to {temp_topic}")
        except Exception as e:
            logger.error(f"Error publishing command for node {node_uid}: {e}", exc_info=True)
            raise

    def publish_config(self, gh_uid: str, zone_id: int, node_uid: str, config: Dict[str, Any], hardware_id: Optional[str] = None):
        """
        Публиковать NodeConfig в MQTT.
        
        Топик: hydro/{gh_uid}/{zone_segment}/{node_uid}/config
        QoS: 1
        Retain: true (чтобы узел получил конфигурацию при подписке)
        
        Также публикуем на временный топик (gh-temp/zn-temp/{hardware_id}/config), 
        если узел еще не получил конфигурацию и подписан на временные идентификаторы.
        Используем hardware_id для временного топика, чтобы избежать конфликтов при одинаковом node_uid.
        """
        try:
            # Проверяем подключение - используем reconnect вместо start для сохранения соединения
            if not self._mqtt.is_connected():
                logger.warning("MQTT client not connected, attempting to reconnect...")
                try:
                    # Используем start() который теперь умный и проверяет существующее подключение
                    # Это предотвратит создание новых подключений
                    self._mqtt.start()
                    # Дополнительная проверка после попытки переподключения
                    if not self._mqtt.is_connected():
                        raise ConnectionError("MQTT client failed to reconnect")
                    logger.info("MQTT client reconnected successfully")
                except Exception as reconnect_error:
                    logger.error(f"Failed to reconnect MQTT client: {reconnect_error}", exc_info=True)
                    raise ConnectionError(f"MQTT client is not connected and reconnection failed: {reconnect_error}")
            
            s = get_settings()
            zone_segment = f"zn-{zone_id}"  # id by default
            if s.mqtt_zone_format == "uid" and config.get("zone_uid"):
                zone_segment = config["zone_uid"]
            
            # Публикуем на правильный топик с retain=true
            topic = f"hydro/{gh_uid}/{zone_segment}/{node_uid}/config"
            logger.info(f"Publishing config to topic: {topic}, node_uid: {node_uid}, zone_id: {zone_id}")
            self._mqtt.publish_json(topic, config, qos=1, retain=True)
            logger.info(f"Config published successfully to {topic}")
            
            # Также публикуем на временный топик для узлов, которые еще не получили конфигурацию
            # Узел может быть подписан на временные идентификаторы до получения первой конфигурации
            # Используем hardware_id для временного топика, чтобы избежать конфликтов при одинаковом node_uid
            if hardware_id:
                temp_topic = f"hydro/gh-temp/zn-temp/{hardware_id}/config"
                logger.info(f"Publishing config to temp topic: {temp_topic} (using hardware_id)")
                self._mqtt.publish_json(temp_topic, config, qos=1, retain=True)
                logger.info(f"Config published successfully to {temp_topic}")
            else:
                # Fallback: используем node_uid, если hardware_id не указан (для обратной совместимости)
                temp_topic = f"hydro/gh-temp/zn-temp/{node_uid}/config"
                logger.warning(f"hardware_id not provided, using node_uid for temp topic: {temp_topic} (may cause conflicts)")
                self._mqtt.publish_json(temp_topic, config, qos=1, retain=True)
                logger.info(f"Config published successfully to {temp_topic}")
        except Exception as e:
            logger.error(f"Error publishing config for node {node_uid}: {e}", exc_info=True)
            raise



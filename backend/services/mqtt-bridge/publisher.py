from typing import Dict, Any
import logging

from common.mqtt import MqttClient
from common.env import get_settings

logger = logging.getLogger(__name__)


class Publisher:
    def __init__(self):
        self._mqtt = MqttClient(client_id_suffix="-bridge")
        self._mqtt.start()

    def publish_command(self, gh_uid: str, zone_id: int, node_uid: str, channel: str, payload: Dict[str, Any]):
        s = get_settings()
        zone_segment = f"zn-{zone_id}"  # id by default
        if s.mqtt_zone_format == "uid" and payload.get("zone_uid"):
            zone_segment = payload["zone_uid"]
        topic = f"hydro/{gh_uid}/{zone_segment}/{node_uid}/{channel}/command"
        self._mqtt.publish_json(topic, payload, qos=1, retain=False)

    def publish_config(self, gh_uid: str, zone_id: int, node_uid: str, config: Dict[str, Any]):
        """
        Публиковать NodeConfig в MQTT.
        
        Топик: hydro/{gh_uid}/{zone_segment}/{node_uid}/config
        QoS: 1
        Retain: true (чтобы узел получил конфигурацию при подписке)
        
        Также публикуем на временный топик (gh-temp/zn-temp/node-temp), 
        если узел еще не получил конфигурацию и подписан на временные идентификаторы.
        """
        try:
            # Проверяем подключение и переподключаемся при необходимости
            if not self._mqtt.is_connected():
                logger.warning("MQTT client not connected, attempting to reconnect...")
                try:
                    self._mqtt.start()
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
            temp_topic = f"hydro/gh-temp/zn-temp/{node_uid}/config"
            logger.info(f"Publishing config to temp topic: {temp_topic}")
            self._mqtt.publish_json(temp_topic, config, qos=1, retain=True)
            logger.info(f"Config published successfully to {temp_topic}")
        except Exception as e:
            logger.error(f"Error publishing config for node {node_uid}: {e}", exc_info=True)
            raise



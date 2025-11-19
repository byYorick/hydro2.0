from typing import Dict, Any

from common.mqtt import MqttClient
from common.env import get_settings


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
        s = get_settings()
        zone_segment = f"zn-{zone_id}"  # id by default
        if s.mqtt_zone_format == "uid" and config.get("zone_uid"):
            zone_segment = config["zone_uid"]
        
        # Публикуем на правильный топик с retain=true
        topic = f"hydro/{gh_uid}/{zone_segment}/{node_uid}/config"
        self._mqtt.publish_json(topic, config, qos=1, retain=True)
        
        # Также публикуем на временный топик для узлов, которые еще не получили конфигурацию
        # Узел может быть подписан на временные идентификаторы до получения первой конфигурации
        temp_topic = f"hydro/gh-temp/zn-temp/{node_uid}/config"
        self._mqtt.publish_json(temp_topic, config, qos=1, retain=True)



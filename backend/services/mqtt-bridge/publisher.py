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



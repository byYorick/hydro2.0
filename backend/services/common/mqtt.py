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

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected.set()
            # resubscribe
            for topic, qos, handler in self._subs:
                self._client.subscribe(topic, qos=qos)
                self._client.message_callback_add(topic, self._wrap(handler))
        else:
            self._connected.clear()

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

    def _wrap(self, handler: Callable[[str, bytes], None]):
        def on_message(client, userdata, msg):
            try:
                handler(msg.topic, msg.payload)
            except Exception as e:
                # Логируем исключения вместо молчаливого игнорирования
                logger.error(
                    f"Error in MQTT message handler for topic {msg.topic}: {e}",
                    exc_info=True
                )
        return on_message

    def start(self):
        self._client.connect(self._host, self._port, keepalive=30)
        self._client.loop_start()
        # wait connected
        for _ in range(100):
            if self._connected.is_set():
                return
            time.sleep(0.1)

    def stop(self):
        self._client.loop_stop()
        self._client.disconnect()

    def publish_json(self, topic: str, payload: dict, qos: int = 1, retain: bool = False):
        data = json.dumps(payload, separators=(",", ":"))
        self._client.publish(topic, data, qos=qos, retain=retain)

    def subscribe(self, topic: str, handler: Callable[[str, bytes], None], qos: int = 1):
        self._subs.append((topic, qos, handler))
        self._client.subscribe(topic, qos=qos)
        self._client.message_callback_add(topic, self._wrap(handler))



"""MqttBridge — асинхронный мост над paho-mqtt для DT live-режима.

Реализует:
- асинхронный subscribe/unsubscribe;
- асинхронный publish (тред paho → asyncio через loop.call_soon_threadsafe);
- callback с extracted topic-segments для подписчиков (на cmd-сообщения зон).

Формат cmd-топика (см. `tests/node_sim/node_sim/topics.py`):
    hydro/{gh}/{zone}/{node}/{channel}/command

Phase C MVP: bridge поднимается при первой live-симуляции и держится
на уровне приложения (один на digital-twin instance).
"""
import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


# Сигнатура async cmd-handler: (gh_uid, zone_uid, node_uid, channel, payload) -> None
CmdHandler = Callable[[str, str, str, str, Dict], Awaitable[None]]


@dataclass
class _ParsedCommand:
    gh_uid: str
    zone_uid: str
    node_uid: str
    channel: str
    payload: Dict


def _parse_command_topic(topic: str) -> Optional[Tuple[str, str, str, str]]:
    """Распарсить `hydro/{gh}/{zone}/{node}/{channel}/command` → tuple."""
    parts = topic.split("/")
    if len(parts) != 6:
        return None
    if parts[0] != "hydro" or parts[5] != "command":
        return None
    return parts[1], parts[2], parts[3], parts[4]


class MqttBridge:
    """Асинхронная обёртка paho-mqtt для DT live-режима."""

    def __init__(
        self,
        host: str = "mqtt",
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        keepalive: int = 60,
        client_id: str = "digital-twin-live",
    ) -> None:
        self._host = host
        self._port = port
        self._keepalive = keepalive
        self._client = mqtt.Client(client_id=client_id, clean_session=True)
        if username:
            self._client.username_pw_set(username, password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._cmd_handler: Optional[CmdHandler] = None
        self._subscribed_topics: List[str] = []
        self._connected = asyncio.Event()
        self._started = False

    # ---- public API --------------------------------------------------------

    async def start(self, cmd_handler: CmdHandler) -> None:
        if self._started:
            return
        self._loop = asyncio.get_running_loop()
        self._cmd_handler = cmd_handler
        await asyncio.to_thread(
            self._client.connect, self._host, self._port, self._keepalive
        )
        self._client.loop_start()
        self._started = True
        # Ждём первого on_connect; не критично, дальше всё равно будет работать.
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning(
                "MqttBridge: on_connect not received within 5s — continuing"
            )

    async def stop(self) -> None:
        if not self._started:
            return
        try:
            self._client.loop_stop()
            self._client.disconnect()
        finally:
            self._started = False
            self._loop = None

    async def subscribe_zone_commands(self, gh_uid: str, zone_uid: str) -> None:
        """Подписаться на все cmd-топики симулированной зоны (всеми node/channel)."""
        topic = f"hydro/{gh_uid}/{zone_uid}/+/+/command"
        await asyncio.to_thread(self._client.subscribe, topic, 1)
        if topic not in self._subscribed_topics:
            self._subscribed_topics.append(topic)
        logger.info("Subscribed to zone commands", extra={"topic": topic})

    async def unsubscribe_zone_commands(self, gh_uid: str, zone_uid: str) -> None:
        topic = f"hydro/{gh_uid}/{zone_uid}/+/+/command"
        await asyncio.to_thread(self._client.unsubscribe, topic)
        try:
            self._subscribed_topics.remove(topic)
        except ValueError:
            pass

    async def publish(
        self,
        topic: str,
        payload: bytes,
        qos: int = 1,
        retain: bool = False,
    ) -> None:
        await asyncio.to_thread(self._client.publish, topic, payload, qos, retain)

    # ---- internals ---------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):  # paho callback (thread)
        if rc == 0:
            logger.info("MqttBridge connected")
            if self._loop:
                self._loop.call_soon_threadsafe(self._connected.set)
            for topic in self._subscribed_topics:
                client.subscribe(topic, 1)
        else:
            logger.warning("MqttBridge connect rc=%s", rc)

    def _on_message(self, client, userdata, msg):  # paho callback (thread)
        parsed = _parse_command_topic(msg.topic)
        if not parsed:
            return
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            logger.debug("Bad cmd payload on %s — ignoring", msg.topic)
            return
        if not isinstance(payload, dict):
            return
        gh_uid, zone_uid, node_uid, channel = parsed
        if not (self._loop and self._cmd_handler):
            return
        asyncio.run_coroutine_threadsafe(
            self._cmd_handler(gh_uid, zone_uid, node_uid, channel, payload),
            self._loop,
        )

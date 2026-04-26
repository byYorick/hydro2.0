"""Publisher — публикация physics-based MQTT-сообщений от имени узлов.

Покрывает три типа сообщений (формат — `MQTT_SPEC_FULL.md`):
- telemetry (`hydro/{gh}/{zone}/{node}/{ch}/telemetry`)
- command_response (`hydro/{gh}/{zone}/{node}/{ch}/command_response`)
- event (`hydro/{gh}/{zone}/{node}/event`) — для `level_switch_changed`

Status/heartbeat/lwt не публикуем (это инфраструктурные сообщения, остаются на
node-sim или реальных нодах).
"""
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .sim_world import LevelSwitchEvent, SensorSample

logger = logging.getLogger(__name__)


# Сигнатура async publish-функции: (topic: str, payload: bytes, qos: int, retain: bool) -> None.
PublishFn = Callable[[str, bytes, int, bool], Awaitable[None]]


class Publisher:
    """Тонкий wrapper, формирующий MQTT-сообщения по контракту проекта."""

    def __init__(self, publish_fn: PublishFn) -> None:
        self._publish = publish_fn

    # ---- public API --------------------------------------------------------

    async def publish_samples(
        self,
        gh_uid: str,
        zone_uid: str,
        samples: List[SensorSample],
    ) -> None:
        for sample in samples:
            topic = (
                f"hydro/{gh_uid}/{zone_uid}/{sample.node_uid}/"
                f"{sample.channel}/telemetry"
            )
            payload = {
                "metric_type": sample.metric_type,
                "value": sample.value,
                "ts": int(sample.ts_seconds),
                "stable": True,
                "stub": False,
                "is_simulation": True,
            }
            await self._safe_publish(topic, payload, qos=1, retain=False)

    async def publish_level_events(
        self,
        gh_uid: str,
        zone_uid: str,
        events: List[LevelSwitchEvent],
    ) -> None:
        for event in events:
            topic = f"hydro/{gh_uid}/{zone_uid}/{event.node_uid}/event"
            payload = {
                "event_code": "level_switch_changed",
                "channel": event.channel,
                "state": event.state,
                "initial": event.initial,
                "ts": int(event.ts_seconds),
                "is_simulation": True,
            }
            await self._safe_publish(topic, payload, qos=1, retain=False)

    async def publish_command_response(
        self,
        *,
        gh_uid: str,
        zone_uid: str,
        node_uid: str,
        channel: str,
        cmd_id: Optional[str],
        status: str,
        ts_seconds: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        topic = (
            f"hydro/{gh_uid}/{zone_uid}/{node_uid}/{channel}/command_response"
        )
        payload: Dict[str, Any] = {
            "cmd_id": cmd_id,
            "status": status,
            # Контракт проекта: ts в command_response — миллисекунды.
            "ts": int(ts_seconds * 1000),
            "is_simulation": True,
        }
        if details:
            payload["details"] = details
        await self._safe_publish(topic, payload, qos=1, retain=False)

    # ---- internal ----------------------------------------------------------

    async def _safe_publish(
        self,
        topic: str,
        payload: Dict[str, Any],
        qos: int,
        retain: bool,
    ) -> None:
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            await self._publish(topic, data, qos, retain)
        except Exception as exc:
            logger.warning(
                "Publish failed for topic=%s: %s", topic, exc, exc_info=True
            )

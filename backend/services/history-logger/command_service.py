import asyncio
import hashlib
import hmac
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import HTTPException

from common.db import fetch
from common.env import get_settings
from common.hmac_utils import canonical_json_payload
from common.mqtt import AsyncMqttClient, MqttClient

logger = logging.getLogger(__name__)


def _create_command_payload(
    cmd_id: Optional[str] = None,
    params: Optional[dict] = None,
    cmd: Optional[str] = None,
    ts: Optional[int] = None,
    sig: Optional[str] = None,
) -> dict:
    """Создать payload для команды MQTT."""
    cmd_id = cmd_id or str(uuid.uuid4())
    if not cmd:
        raise ValueError("'cmd' is required")
    if sig and ts is None:
        raise ValueError("sig requires ts")

    payload = {"cmd": cmd, "cmd_id": cmd_id, "params": params or {}}

    secret = get_settings().node_default_secret
    if ts is None and sig is None:
        if secret:
            ts = int(time.time())
    elif ts is not None and sig is None and not secret:
        raise ValueError("sig requires node_default_secret")

    if ts is not None:
        payload["ts"] = ts
    if sig is None and secret:
        payload_str = canonical_json_payload(payload)
        sig = hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
    if sig:
        payload["sig"] = sig
    return payload


@asynccontextmanager
async def _mqtt_client_context(suffix: str):
    """Context manager для создания и закрытия MQTT клиента."""
    mqtt = MqttClient(client_id_suffix=suffix)
    mqtt.start()
    try:
        yield mqtt
    finally:
        mqtt.stop()


def _validate_target_level(value: float, min_val: float, max_val: float, operation: str) -> None:
    """Валидация target_level для fill/drain операций."""
    if not (min_val <= value <= max_val):
        raise HTTPException(
            status_code=400,
            detail=f"target_level must be between {min_val} and {max_val} for {operation}",
        )


async def _get_zone_uid_from_id(zone_id: int) -> Optional[str]:
    """Получить zone_uid из zone_id для MQTT публикации."""
    rows = await fetch(
        """
        SELECT uid
        FROM zones
        WHERE id = $1
        """,
        zone_id,
    )
    if rows:
        zone_uid = rows[0].get("uid")
        if not zone_uid:
            logger.warning(
                f"Zone {zone_id} has no uid, using zn-{zone_id} as fallback"
            )
        return zone_uid
    logger.warning(f"Zone {zone_id} not found, using zn-{zone_id} as fallback")
    return None


async def _get_gh_uid_from_zone_id(zone_id: int) -> str:
    """Получить greenhouse_uid из zone_id."""
    rows = await fetch(
        """
        SELECT g.uid
        FROM zones z
        JOIN greenhouses g ON g.id = z.greenhouse_id
        WHERE z.id = $1
        """,
        zone_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Zone not found or has no greenhouse")
    return rows[0]["uid"]


async def publish_command_mqtt(
    mqtt_client: AsyncMqttClient,
    gh_uid: str,
    zone_id: int,
    node_uid: str,
    channel: str,
    payload: Dict[str, Any],
    zone_uid: Optional[str] = None,
) -> None:
    """
    Публиковать команду в MQTT.
    """
    try:
        if not mqtt_client.is_connected():
            logger.warning("MQTT client not connected, attempting to reconnect...")
            await mqtt_client.start()
            if not mqtt_client.is_connected():
                raise ConnectionError("MQTT client is not connected and reconnection failed")

        s = get_settings()
        zone_segment = f"zn-{zone_id}"
        if hasattr(s, "mqtt_zone_format") and s.mqtt_zone_format == "uid" and zone_uid:
            zone_segment = zone_uid
        elif hasattr(s, "mqtt_zone_format") and s.mqtt_zone_format == "uid":
            logger.warning(
                "mqtt_zone_format=uid but zone_uid not provided, using zn-%s (may cause mismatch with node subscription)",
                zone_id,
            )

        topic = f"hydro/{gh_uid}/{zone_segment}/{node_uid}/{channel}/command"
        logger.info(
            "[MQTT_PUBLISH] Publishing command to topic: %s, node_uid: %s, channel: %s, zone_id: %s, zone_segment: %s, cmd_id=%s",
            topic,
            node_uid,
            channel,
            zone_id,
            zone_segment,
            payload.get("cmd_id", "unknown"),
        )

        base_client = mqtt_client._client
        import json as json_lib

        command_json = json_lib.dumps(payload, separators=(",", ":"))
        result = base_client._client.publish(topic, command_json, qos=1, retain=False)
        if result.rc != 0:
            logger.error(
                "[MQTT_PUBLISH] FAILED: MQTT publish failed with rc=%s for topic %s, cmd_id=%s",
                result.rc,
                topic,
                payload.get("cmd_id", "unknown"),
            )
            raise RuntimeError(
                f"MQTT publish failed with rc={result.rc} for topic {topic}"
            )
        logger.info(
            "[MQTT_PUBLISH] SUCCESS: Command published successfully to %s, cmd_id=%s, payload_size=%s",
            topic,
            payload.get("cmd_id", "unknown"),
            len(command_json),
        )

    except Exception as e:
        logger.error("Error publishing command for node %s: %s", node_uid, e, exc_info=True)
        raise

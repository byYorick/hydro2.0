import asyncio
import hashlib
import hmac
import logging
import os
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


class NodeSecretResolutionError(RuntimeError):
    """Raised when a command cannot be signed with an authorized node secret."""


def _wait_mqtt_message_puback(result: Any, timeout: float) -> bool:
    """Block for PUBACK and return whether the message was published."""
    result.wait_for_publish(timeout=timeout)
    return bool(result.is_published())


# ── Command validation bounds (audit F2 + F7) ─────────────────────────

#: Maximum acceptable offset between a caller-supplied ``ts`` and server
#: time before the command is rejected as stale/replayed. MQTT spec
#: mandates a 10-second window for timestamp validation on the node side;
#: history-logger enforces the same contract at command creation time so
#: stale clocks fail fast with an actionable error instead of silently
#: reaching a node that will reject the signed payload as too old.
_MAX_COMMAND_TS_OFFSET_SEC: int = 10

#: Early-warning threshold: когда фактический offset приближается к лимиту,
#: логируем warning чтобы обнаруживать clock drift ДО того как он вызовет
#: отказы. Прод-инфра должна мониторить эти warnings и триггерить NTP sync.
_CLOCK_SKEW_WARNING_SEC: int = 5

#: Safety ceiling for ``params.ml`` — the per-command dose volume in
#: millilitres. This is a **transport-layer sanity guard**, not a domain
#: bound: CorrectionPlanner in AE3 already enforces ``max_ec_dose_ml``
#: (default 50 ml) and ``max_ph_dose_ml`` (default 20 ml) per zone config.
#: The ceiling here catches integration bugs (e.g., a caller passing litres
#: instead of ml) without interfering with large-volume EC nutrition pulses
#: that are legitimate for 100+ litre tanks.
_MAX_DOSE_ML_SANITY: float = 500.0

#: Absolute bounds for pump run duration in milliseconds. The 300000 ms
#: (5 minutes) ceiling is a transport-layer sanity guard. Firmware-side
#: pump_driver has its own per-NodeConfig safe_limits. This catches
#: integration bugs without blocking large-tank multi-component dosing
#: sequences where the pump legitimately runs for > 60s per step.
_MAX_DURATION_MS_SANITY: int = 300_000


def _validate_command_params(*, cmd: str, params: dict) -> None:
    """Reject commands with clearly out-of-range dose/duration fields.

    Transport-layer sanity guard only — the real domain bounds live in
    CorrectionPlanner (``max_ec_dose_ml``, ``max_ph_dose_ml``) and
    pump_calibration config. History-logger rejects only values that are
    obviously bugs (negative, zero dose, or absurdly large) so a
    misconfigured caller cannot accidentally send a signed command that
    orders hundreds of ml or minutes of pumping.
    """
    dose_ml = params.get("ml") if isinstance(params.get("ml"), (int, float)) else None
    if dose_ml is not None:
        if float(dose_ml) <= 0:
            raise ValueError(
                f"command {cmd} params.ml={dose_ml} must be positive"
            )
        if float(dose_ml) > _MAX_DOSE_ML_SANITY:
            raise ValueError(
                f"command {cmd} params.ml={dose_ml} exceeds sanity ceiling "
                f"{_MAX_DOSE_ML_SANITY}"
            )
    duration_ms = (
        params.get("duration_ms") if isinstance(params.get("duration_ms"), (int, float)) else None
    )
    if duration_ms is not None:
        if int(duration_ms) <= 0:
            raise ValueError(
                f"command {cmd} params.duration_ms={duration_ms} must be positive"
            )
        if int(duration_ms) > _MAX_DURATION_MS_SANITY:
            raise ValueError(
                f"command {cmd} params.duration_ms={duration_ms} exceeds sanity "
                f"ceiling {_MAX_DURATION_MS_SANITY}"
            )
    if cmd == "set_position":
        pct = params.get("position_pct")
        if pct is None or not isinstance(pct, (int, float)):
            raise ValueError(f"command {cmd} requires numeric params.position_pct")
        if float(pct) < 0 or float(pct) > 100:
            raise ValueError(f"command {cmd} params.position_pct={pct} must be within 0..100")
        mstep = params.get("max_step_pct")
        if mstep is not None and isinstance(mstep, (int, float)):
            if float(mstep) < 0 or float(mstep) > 100:
                raise ValueError(f"command {cmd} params.max_step_pct={mstep} must be within 0..100")


async def _resolve_node_secret(
    *,
    node_uid: str,
    node_id: Optional[int] = None,
    zone_id: Optional[int] = None,
) -> str:
    """Resolve the per-node HMAC secret, failing closed in production-like environments.

    When ``zone_id`` is provided, secret lookup and zone assignment are checked in
    one SQL (closes TOCTOU rebind window between assign-check and secret read).
    Secret value is returned raw (no ``.strip()``) to match Laravel ``NodeSecretService``.
    """
    if not node_uid:
        raise NodeSecretResolutionError("node_uid is required to resolve command signing secret")

    try:
        if zone_id is not None and node_id is not None:
            rows = await fetch(
                """
                SELECT config->>'node_secret' AS node_secret
                FROM nodes
                WHERE id = $1 AND uid = $2 AND zone_id = $3
                """,
                node_id,
                node_uid,
                zone_id,
            )
        elif zone_id is not None:
            rows = await fetch(
                """
                SELECT config->>'node_secret' AS node_secret
                FROM nodes
                WHERE uid = $1 AND zone_id = $2
                """,
                node_uid,
                zone_id,
            )
        elif node_id is None:
            rows = await fetch(
                """
                SELECT config->>'node_secret' AS node_secret
                FROM nodes
                WHERE uid = $1
                """,
                node_uid,
            )
        else:
            rows = await fetch(
                """
                SELECT config->>'node_secret' AS node_secret
                FROM nodes
                WHERE id = $1 AND uid = $2
                """,
                node_id,
                node_uid,
            )
    except Exception as exc:
        logger.error(
            "Failed to resolve per-node command signing secret: "
            "node_uid=%s node_id=%s zone_id=%s",
            node_uid,
            node_id,
            zone_id,
            exc_info=True,
        )
        raise NodeSecretResolutionError(
            f"Unable to resolve command signing secret for node '{node_uid}'"
        ) from exc

    if not rows:
        if zone_id is not None:
            raise NodeSecretResolutionError(
                f"Node '{node_uid}' is not assigned to zone {zone_id} "
                "(or secret lookup missed during rebind)"
            )
        raise NodeSecretResolutionError(
            f"Unable to resolve command signing secret for node '{node_uid}'"
        )

    # Match Laravel NodeSecretService: non-empty string check without mutating secret.
    secret = rows[0].get("node_secret")
    if isinstance(secret, str) and secret != "":
        return secret

    app_env = os.getenv("APP_ENV", "").strip().lower()
    if app_env in ("production", "prod"):
        logger.error(
            "Per-node command signing secret is missing; refusing publish: "
            "node_uid=%s node_id=%s zone_id=%s",
            node_uid,
            node_id,
            zone_id,
        )
        raise NodeSecretResolutionError(
            f"Per-node command signing secret is not configured for node '{node_uid}'"
        )

    fallback = get_settings().node_default_secret
    if not isinstance(fallback, str) or not fallback:
        raise NodeSecretResolutionError(
            f"Command signing secret is not configured for node '{node_uid}'"
        )

    logger.warning(
        "Using NODE_DEFAULT_SECRET fallback for command signing outside production: "
        "node_uid=%s node_id=%s zone_id=%s app_env=%s",
        node_uid,
        node_id,
        zone_id,
        app_env or "unset",
    )
    return fallback


def _create_command_payload(
    *,
    node_uid: str,
    secret: str,
    cmd_id: Optional[str] = None,
    params: Optional[dict] = None,
    cmd: Optional[str] = None,
    ts: Optional[int] = None,
    sig: Optional[str] = None,
) -> dict:
    """Создать payload для команды MQTT.

    Audit F2: a caller-supplied ``ts`` is validated against server time —
    offsets larger than ``_MAX_COMMAND_TS_OFFSET_SEC`` are rejected so a
    client with a skewed clock (or a replay attempt) fails before HMAC
    is produced. When ``ts`` is absent we stamp with current UTC seconds.

    Audit F7: dose/duration params are bound-checked via
    ``_validate_command_params`` before HMAC is computed, so out-of-range
    commands never reach a node signed.
    """
    cmd_id = cmd_id or str(uuid.uuid4())
    if not node_uid:
        raise ValueError("'node_uid' is required")
    if not cmd:
        raise ValueError("'cmd' is required")
    if not secret:
        raise ValueError(f"command signing secret is not configured for node '{node_uid}'")

    effective_params = params or {}
    _validate_command_params(cmd=cmd, params=effective_params)

    payload = {"cmd": cmd, "cmd_id": cmd_id, "params": effective_params}

    now_ts = int(time.time())
    if ts is None:
        ts = now_ts
    else:
        offset = abs(now_ts - int(ts))
        if offset > _MAX_COMMAND_TS_OFFSET_SEC:
            raise ValueError(
                f"command {cmd} ts={ts} stale: offset {offset}s exceeds "
                f"maximum {_MAX_COMMAND_TS_OFFSET_SEC}s"
            )
        if offset >= _CLOCK_SKEW_WARNING_SEC:
            logger.warning(
                "Clock skew approaching command ts tolerance: offset=%ds (max=%ds). "
                "Check NTP sync on caller. cmd=%s cmd_id=%s",
                offset, _MAX_COMMAND_TS_OFFSET_SEC, cmd, cmd_id,
            )

    payload["ts"] = ts
    payload_str = canonical_json_payload(payload)
    computed_sig = hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
    if sig:
        logger.warning(
            "Ignoring caller-provided command signature and re-signing server-side: "
            "node_uid=%s cmd_id=%s",
            node_uid,
            cmd_id,
        )
    payload["sig"] = computed_sig
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

        zone_segment = zone_uid or f"zn-{zone_id}"

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

        from metrics import COMMANDS_PUBLISH_UNCONFIRMED

        settings = get_settings()
        # paho wait_for_publish() returns None on success; use is_published().
        puback_ok = await asyncio.to_thread(
            _wait_mqtt_message_puback,
            result,
            settings.mqtt_publish_ack_timeout_sec,
        )
        if not puback_ok:
            COMMANDS_PUBLISH_UNCONFIRMED.inc()
            raise RuntimeError(
                f"MQTT PUBACK timeout after {settings.mqtt_publish_ack_timeout_sec}s for topic {topic}"
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


async def publish_config_mqtt(
    mqtt_client: AsyncMqttClient,
    gh_uid: str,
    zone_id: int,
    node_uid: str,
    config_payload: Dict[str, Any],
    zone_uid: Optional[str] = None,
) -> None:
    """
    Публиковать NodeConfig в MQTT.
    """
    try:
        if not mqtt_client.is_connected():
            logger.warning("MQTT client not connected, attempting to reconnect...")
            await mqtt_client.start()
            if not mqtt_client.is_connected():
                raise ConnectionError("MQTT client is not connected and reconnection failed")

        zone_segment = zone_uid or f"zn-{zone_id}"

        topic = f"hydro/{gh_uid}/{zone_segment}/{node_uid}/config"
        import json as json_lib
        try:
            has_secret = isinstance(config_payload.get("node_secret"), str) and bool(config_payload.get("node_secret"))
            payload_size = len(json_lib.dumps(config_payload, separators=(",", ":")))
            logger.info(
                "[CONFIG_PUBLISH] node_uid=%s topic=%s temp=%s node_secret_present=%s payload_size=%s",
                node_uid,
                topic,
                False,
                has_secret,
                payload_size,
            )
        except Exception as log_err:
            logger.warning(
                "[CONFIG_PUBLISH] Failed to compute payload diagnostics for node_uid=%s: %s",
                node_uid,
                log_err,
            )
        logger.info(
            "[MQTT_PUBLISH] Publishing config to topic: %s, node_uid: %s, zone_id: %s, zone_segment: %s",
            topic,
            node_uid,
            zone_id,
            zone_segment,
        )

        base_client = mqtt_client._client
        import json as json_lib

        payload_json = json_lib.dumps(config_payload, separators=(",", ":"))
        result = base_client._client.publish(topic, payload_json, qos=1, retain=False)
        if result.rc != 0:
            logger.error(
                "[MQTT_PUBLISH] FAILED: MQTT publish failed with rc=%s for topic %s",
                result.rc,
                topic,
            )
            raise RuntimeError(
                f"MQTT publish failed with rc={result.rc} for topic {topic}"
            )
        logger.info(
            "[MQTT_PUBLISH] SUCCESS: Config published to %s, payload_size=%s",
            topic,
            len(payload_json),
        )
    except Exception as e:
        logger.error("Error publishing config for node %s: %s", node_uid, e, exc_info=True)
        raise


async def publish_config_temp_mqtt(
    mqtt_client: AsyncMqttClient,
    hardware_id: str,
    config_payload: Dict[str, Any],
) -> None:
    """
    Публиковать NodeConfig в temp-топик (gh-temp/zn-temp) по hardware_id.
    """
    try:
        if not mqtt_client.is_connected():
            logger.warning("MQTT client not connected, attempting to reconnect...")
            await mqtt_client.start()
            if not mqtt_client.is_connected():
                raise ConnectionError("MQTT client is not connected and reconnection failed")

        topic = f"hydro/gh-temp/zn-temp/{hardware_id}/config"
        import json as json_lib
        try:
            has_secret = isinstance(config_payload.get("node_secret"), str) and bool(config_payload.get("node_secret"))
            payload_size = len(json_lib.dumps(config_payload, separators=(",", ":")))
            logger.info(
                "[CONFIG_PUBLISH] node_uid=%s topic=%s temp=%s node_secret_present=%s payload_size=%s",
                hardware_id,
                topic,
                True,
                has_secret,
                payload_size,
            )
        except Exception as log_err:
            logger.warning(
                "[CONFIG_PUBLISH] Failed to compute payload diagnostics for hardware_id=%s: %s",
                hardware_id,
                log_err,
            )
        logger.info(
            "[MQTT_PUBLISH] Publishing temp config to topic: %s, hardware_id: %s",
            topic,
            hardware_id,
        )

        base_client = mqtt_client._client
        payload_json = json_lib.dumps(config_payload, separators=(",", ":"))
        result = base_client._client.publish(topic, payload_json, qos=1, retain=False)
        if result.rc != 0:
            logger.error(
                "[MQTT_PUBLISH] FAILED: MQTT publish failed with rc=%s for topic %s",
                result.rc,
                topic,
            )
            raise RuntimeError(
                f"MQTT publish failed with rc={result.rc} for topic {topic}"
            )
        logger.info(
            "[MQTT_PUBLISH] SUCCESS: Temp config published to %s, payload_size=%s",
            topic,
            len(payload_json),
        )
    except Exception as e:
        logger.error(
            "Error publishing temp config for hardware_id %s: %s",
            hardware_id,
            e,
            exc_info=True,
        )
        raise

"""DRY publish loop для command ingress routes.

Устраняет дублирование между ``POST /zones/{id}/commands``, ``POST /nodes/{uid}/commands``
и ``POST /commands``: все три ранее содержали идентичный retry + mark_sent +
send_status_to_laravel + fallback-alert блок (~150 строк каждый).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import HTTPException

import chain_webhook
from command_service import publish_command_mqtt
from common.command_status_queue import send_status_to_laravel
from common.commands import mark_command_send_failed, mark_command_sent
from common.mqtt import get_mqtt_client
from common.utils.time import utcnow
from metrics import COMMANDS_SENT, MQTT_PUBLISH_ERRORS

from .alerts import emit_command_send_failed_alert
from .constants import MAX_PUBLISH_RETRIES, MQTT_PUBLISH_RETRY_DELAYS_SEC
from .lifecycle import ensure_post_publish_status_persisted

logger = logging.getLogger(__name__)


async def publish_command_with_retry(
    *,
    payload: dict,
    cmd_id: str,
    cmd_name: str,
    zone_id: int,
    node_uid: str,
    channel: str,
    effective_gh_uid: str,
    zone_uid: str | None,
    log_context: dict[str, Any] | None = None,
    max_retries: int = MAX_PUBLISH_RETRIES,
) -> dict:
    """Publish command в MQTT с retry/backoff, mark SENT + Laravel ACK + метриками.

    На успехе возвращает response body для route.
    На окончательной ошибке — mark SEND_FAILED + alert + бросает HTTP 500.
    """
    mqtt = await get_mqtt_client()
    retry_delays = MQTT_PUBLISH_RETRY_DELAYS_SEC

    publish_success = False
    last_error: Any = None

    for attempt in range(max_retries):
        try:
            await publish_command_mqtt(
                mqtt,
                effective_gh_uid,
                zone_id,
                node_uid,
                channel,
                payload,
                zone_uid=zone_uid,
            )
            publish_success = True
            logger.info(
                "Command published successfully (attempt %s/%s): zone_id=%s, node_uid=%s, channel=%s, cmd_id=%s",
                attempt + 1,
                max_retries,
                zone_id,
                node_uid,
                channel,
                cmd_id,
            )
            break
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = retry_delays[attempt]
                logger.warning(
                    "Failed to publish command (attempt %s/%s): %s. Retrying in %ss...",
                    attempt + 1,
                    max_retries,
                    e,
                    delay,
                    extra=log_context,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Failed to publish command after %s attempts: %s",
                    max_retries,
                    e,
                    exc_info=True,
                    extra=log_context,
                )

    if publish_success:
        return await _on_publish_success(
            cmd_id=cmd_id,
            cmd_name=cmd_name,
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            log_context=log_context,
        )

    return await _on_publish_failed(
        cmd_id=cmd_id,
        cmd_name=cmd_name,
        zone_id=zone_id,
        node_uid=node_uid,
        channel=channel,
        last_error=last_error,
        max_retries=max_retries,
    )


async def _on_publish_success(
    *,
    cmd_id: str,
    cmd_name: str,
    zone_id: int,
    node_uid: str,
    channel: str,
    log_context: dict[str, Any] | None,
) -> dict:
    try:
        await mark_command_sent(cmd_id, allow_resend=True)
        await ensure_post_publish_status_persisted(cmd_id)
        logger.info(f"Command {cmd_id} status updated to SENT")
    except Exception as e:
        logger.error(
            f"Failed to update command status to SENT: {e}",
            exc_info=True,
            extra=log_context or {"cmd_id": cmd_id},
        )
        raise HTTPException(
            status_code=500,
            detail="published_but_status_not_persisted",
        ) from e

    try:
        await send_status_to_laravel(
            cmd_id=cmd_id,
            status="SENT",
            details={
                "zone_id": zone_id,
                "node_uid": node_uid,
                "channel": channel,
                "command": cmd_name,
                "published_at": utcnow().isoformat(),
            },
        )
        logger.debug(f"Correlation ACK sent for command {cmd_id} (status: SENT)")
    except Exception as e:
        # ``send_status_to_laravel`` нормально queue-ит на HTTP failure
        # (``enqueue_on_failure=True``) — этот блок триггерится только на
        # catastrophic случаях (cancellation, pool exhaustion, queue-enqueue
        # fail). Command уже SENT в БД и опубликована — не бросаем. exc_info
        # обязателен для post-mortem (тип exception + стек).
        logger.warning(
            "Failed to send correlation ACK for command %s: %s",
            cmd_id,
            e,
            exc_info=True,
            extra={"cmd_id": cmd_id},
        )

    COMMANDS_SENT.labels(zone_id=str(zone_id), metric=cmd_name).inc()

    # Causal chain webhook (Scheduler Cockpit UI) — шаг DISPATCH. Laravel
    # резолвит execution_id из cmd_id. Fire-and-forget: всё что может упасть
    # глушится внутри chain_webhook.
    try:
        await chain_webhook.emit_execution_step(
            zone_id=zone_id,
            cmd_id=cmd_id,
            step="DISPATCH",
            ref=f"cmd-{cmd_id}",
            status="ok",
            detail=f"history-logger → mqtt {node_uid}/{channel} · {cmd_name}",
            at_iso=utcnow().isoformat(),
        )
    except Exception as webhook_exc:  # pragma: no cover — defensive
        logger.debug("chain_webhook DISPATCH emit failed: %s", webhook_exc)

    return {
        "status": "ok",
        "data": {
            "command_id": cmd_id,
            "zone_id": zone_id,
            "node_uid": node_uid,
            "channel": channel,
        },
    }


async def _on_publish_failed(
    *,
    cmd_id: str,
    cmd_name: str,
    zone_id: int,
    node_uid: str,
    channel: str,
    last_error: Any,
    max_retries: int,
) -> dict:
    try:
        await mark_command_send_failed(cmd_id, str(last_error))
        logger.error(f"Command {cmd_id} status updated to SEND_FAILED")
    except Exception as e:
        logger.error(
            f"Failed to update command status to SEND_FAILED: {e}",
            exc_info=True,
        )

    await emit_command_send_failed_alert(
        zone_id=zone_id,
        node_uid=node_uid,
        channel=channel,
        cmd=cmd_name,
        cmd_id=cmd_id,
        error=last_error,
        max_retries=max_retries,
    )

    MQTT_PUBLISH_ERRORS.labels(error_type=type(last_error).__name__).inc()
    raise HTTPException(
        status_code=500,
        detail=f"Failed to publish command after {max_retries} attempts: {str(last_error)}",
    )

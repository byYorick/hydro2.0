import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Request

from auth import _auth_ingest
from command_service import (
    _create_command_payload,
    _get_gh_uid_from_zone_id,
    _get_zone_uid_from_id,
    _mqtt_client_context,
    _validate_target_level,
    publish_config_mqtt,
    publish_config_temp_mqtt,
    publish_command_mqtt,
)
from common.command_status_queue import send_status_to_laravel
from common.commands import mark_command_send_failed, mark_command_sent
from common.db import execute, fetch
from common.env import get_settings
from common.infra_alerts import send_infra_alert, send_infra_exception_alert
from common.mqtt import get_mqtt_client
from common.trace_context import get_trace_id, set_trace_id
from common.utils.time import utcnow
from common.water_flow import calibrate_flow, calibrate_pump, execute_drain_mode, execute_fill_mode
from metrics import COMMANDS_SENT, MQTT_PUBLISH_ERRORS
from models import (
    CalibrateFlowRequest,
    CalibratePumpRequest,
    CommandRequest,
    FillDrainRequest,
    NodeConfigPublishRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _apply_trace_id(trace_id: Optional[str]) -> None:
    if trace_id and not get_trace_id():
        set_trace_id(trace_id, allow_generate=False)


def _ensure_node_secret(config: dict) -> dict:
    node_secret = config.get("node_secret")
    if isinstance(node_secret, str) and node_secret:
        return config
    secret = get_settings().node_default_secret
    if not secret:
        raise HTTPException(status_code=500, detail="node_default_secret is not configured")
    config["node_secret"] = secret
    logger.warning("NodeConfig missing node_secret, injecting default secret for publish")
    return config


def _log_config_publish_context(
    *,
    node_uid: str,
    topic: str,
    config_payload: dict,
    is_temp: bool,
) -> None:
    import json as json_lib

    has_secret = isinstance(config_payload.get("node_secret"), str) and bool(config_payload.get("node_secret"))
    payload_size = len(json_lib.dumps(config_payload, separators=(",", ":")))
    logger.info(
        "[CONFIG_PUBLISH] node_uid=%s topic=%s temp=%s node_secret_present=%s payload_size=%s",
        node_uid,
        topic,
        is_temp,
        has_secret,
        payload_size,
    )


async def _emit_command_send_failed_alert(
    *,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    cmd_id: str,
    error: Any,
    max_retries: int,
) -> None:
    await send_infra_alert(
        code="infra_command_send_failed",
        alert_type="Command Send Failed",
        message=f"Не удалось отправить команду {cmd} после {max_retries} попыток: {error}",
        severity="critical",
        zone_id=zone_id,
        service="history-logger",
        component="command_publish",
        node_uid=node_uid,
        channel=channel,
        cmd=cmd,
        error_type=type(error).__name__ if error else "UnknownError",
        details={
            "cmd_id": cmd_id,
            "max_retries": max_retries,
            "error_message": str(error),
        },
    )


async def _resolve_effective_gh_uid(zone_id: int, requested_gh_uid: Optional[str]) -> str:
    """
    Резолвить канонический gh_uid по zone_id.
    Если БД временно недоступна, допускается fallback на запрошенный gh_uid.
    """
    try:
        resolved_gh_uid = await _get_gh_uid_from_zone_id(zone_id)
    except Exception as exc:
        if requested_gh_uid:
            logger.warning(
                "[MQTT_PUBLISH] Failed to resolve gh_uid from zone_id=%s, fallback to requested greenhouse_uid=%s, error=%s",
                zone_id,
                requested_gh_uid,
                exc,
            )
            return requested_gh_uid
        raise

    if requested_gh_uid and requested_gh_uid != resolved_gh_uid:
        logger.warning(
            "[MQTT_PUBLISH] greenhouse_uid mismatch for zone_id=%s: requested=%s, resolved=%s. Using resolved value.",
            zone_id,
            requested_gh_uid,
            resolved_gh_uid,
        )

    return resolved_gh_uid


async def _require_node_assigned_to_zone(node_uid: str, zone_id: int) -> int:
    """
    Fail-closed проверка: node_uid должен быть закреплен за zone_id.
    Возвращает numeric node_id для записи в commands.
    """
    try:
        rows = await fetch(
            """
            SELECT id, zone_id, pending_zone_id
            FROM nodes
            WHERE uid = $1
            """,
            node_uid,
        )
    except Exception as exc:
        logger.error(
            "[COMMAND_PUBLISH] Failed to validate node-zone assignment: node_uid=%s zone_id=%s error=%s",
            node_uid,
            zone_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to validate node assignment, try again later",
        ) from exc

    if not rows:
        raise HTTPException(status_code=404, detail=f"Node '{node_uid}' not found")

    node = rows[0]
    node_zone_id = node.get("zone_id")
    pending_zone_id = node.get("pending_zone_id")

    if node_zone_id != zone_id:
        if node_zone_id is None and pending_zone_id == zone_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Node '{node_uid}' is not assigned to zone {zone_id} yet "
                    "(pending assignment confirmation)"
                ),
            )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Node '{node_uid}' is assigned to zone {node_zone_id}, "
                f"not zone {zone_id}"
            ),
        )

    return int(node["id"])


@router.post("/nodes/{node_uid}/config")
async def publish_node_config(
    request: Request,
    node_uid: str,
    req: NodeConfigPublishRequest = Body(...),
):
    """
    Публикация NodeConfig в MQTT.
    Разрешена только с параметрами теплица/зона (greenhouse_uid + zone_id/zone_uid).
    """
    _auth_ingest(request)

    if not req.zone_id and not req.zone_uid:
        raise HTTPException(
            status_code=400,
            detail="zone_id or zone_uid is required",
        )

    zone_uid = req.zone_uid
    if not zone_uid and req.zone_id:
        zone_uid = await _get_zone_uid_from_id(req.zone_id)

    if not zone_uid:
        raise HTTPException(
            status_code=400,
            detail="zone_uid could not be resolved",
        )

    if not req.zone_id:
        raise HTTPException(
            status_code=400,
            detail="zone_id is required to resolve greenhouse_uid",
        )

    node_rows = await fetch(
        """
        SELECT id, zone_id, pending_zone_id, hardware_id
        FROM nodes
        WHERE uid = $1
        """,
        node_uid,
    )
    if not node_rows:
        raise HTTPException(
            status_code=404,
            detail="node_uid not found",
        )
    node = node_rows[0]
    node_zone_id = node.get("zone_id")
    pending_zone_id = node.get("pending_zone_id")
    hardware_id = node.get("hardware_id")

    logger.info(
        "[CONFIG_PUBLISH] Decision inputs: node_uid=%s, node_zone_id=%s, pending_zone_id=%s, req_zone_id=%s",
        node_uid,
        node_zone_id,
        pending_zone_id,
        req.zone_id,
    )

    if node_zone_id and node_zone_id != req.zone_id:
        raise HTTPException(
            status_code=409,
            detail="node is already bound to another zone",
        )

    if pending_zone_id and pending_zone_id != req.zone_id and not node_zone_id:
        raise HTTPException(
            status_code=409,
            detail="pending_zone_id does not match requested zone_id",
        )

    gh_uid = await _resolve_effective_gh_uid(req.zone_id, req.greenhouse_uid)

    mqtt = await get_mqtt_client()
    config_payload = _ensure_node_secret(dict(req.config))
    use_temp_topic = pending_zone_id == req.zone_id and not node_zone_id
    if pending_zone_id == req.zone_id and node_zone_id:
        logger.warning(
            "[CONFIG_PUBLISH] Inconsistent node state: pending_zone_id set while zone_id already set. Forcing temp publish. node_uid=%s, node_zone_id=%s, pending_zone_id=%s",
            node_uid,
            node_zone_id,
            pending_zone_id,
        )
        use_temp_topic = True

    if use_temp_topic:
        if not hardware_id:
            raise HTTPException(
                status_code=409,
                detail="hardware_id is required for temp config publish",
            )
        logger.info(
            "[CONFIG_PUBLISH] Using temp topic publish: node_uid=%s, hardware_id=%s, zone_id=%s, zone_uid=%s",
            node_uid,
            hardware_id,
            req.zone_id,
            zone_uid,
        )
        temp_topic = f"hydro/gh-temp/zn-temp/{hardware_id}/config"
        _log_config_publish_context(
            node_uid=node_uid,
            topic=temp_topic,
            config_payload=config_payload,
            is_temp=True,
        )
        await publish_config_temp_mqtt(
            mqtt_client=mqtt,
            hardware_id=hardware_id,
            config_payload=config_payload,
        )
    else:
        zone_segment = zone_uid or f"zn-{req.zone_id}"
        topic = f"hydro/{gh_uid}/{zone_segment}/{node_uid}/config"
        _log_config_publish_context(
            node_uid=node_uid,
            topic=topic,
            config_payload=config_payload,
            is_temp=False,
        )
        logger.info(
            "[CONFIG_PUBLISH] Using normal topic publish: node_uid=%s, zone_id=%s, zone_uid=%s, gh_uid=%s",
            node_uid,
            req.zone_id,
            zone_uid,
            gh_uid,
        )
        await publish_config_mqtt(
            mqtt_client=mqtt,
            gh_uid=gh_uid,
            zone_id=req.zone_id,
            node_uid=node_uid,
            config_payload=config_payload,
            zone_uid=zone_uid,
        )

    return {
        "status": "ok",
        "data": {
            "node_uid": node_uid,
            "greenhouse_uid": gh_uid,
            "zone_id": req.zone_id,
            "zone_uid": zone_uid,
        },
    }


@router.post("/zones/{zone_id}/commands")
async def publish_zone_command(
    request: Request, zone_id: int, req: CommandRequest = Body(...)
):
    """
    Публиковать команду для зоны через history-logger.
    Все общение бэка с нодами должно происходить через history-logger.
    """
    _auth_ingest(request)
    _apply_trace_id(req.trace_id)

    if not (req.greenhouse_uid and req.node_uid and req.channel):
        raise HTTPException(
            status_code=400, detail="greenhouse_uid, node_uid and channel are required"
        )

    if not req.get_command_name():
        raise HTTPException(status_code=400, detail="'cmd' is required")

    node_id = await _require_node_assigned_to_zone(req.node_uid, zone_id)

    zone_uid = None
    s = get_settings()
    if hasattr(s, "mqtt_zone_format") and s.mqtt_zone_format == "uid":
        zone_uid = await _get_zone_uid_from_id(zone_id)
    command_source = req.source or "api"
    effective_gh_uid = await _resolve_effective_gh_uid(zone_id, req.greenhouse_uid)

    try:
        payload = _create_command_payload(
            cmd=req.cmd,
            cmd_id=req.cmd_id,
            params=req.params,
            ts=req.ts,
            sig=req.sig,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cmd_id = payload["cmd_id"]
    set_trace_id(cmd_id, allow_generate=False)

    mqtt = await get_mqtt_client()

    try:
        existing_cmd = await fetch(
            "SELECT status, source FROM commands WHERE cmd_id = $1", cmd_id
        )
        if existing_cmd:
            cmd_status = existing_cmd[0].get("status", "").lower()
            if not existing_cmd[0].get("source") and command_source:
                try:
                    await execute(
                        "UPDATE commands SET source = $1 WHERE cmd_id = $2",
                        command_source,
                        cmd_id,
                    )
                except Exception:
                    logger.warning(
                        f"[COMMAND_PUBLISH] Failed to backfill source for command {cmd_id}"
                    )
            if cmd_status in ("ack", "done", "no_effect", "error", "invalid", "busy", "timeout"):
                logger.info(
                    "[IDEMPOTENCY] Command %s already in terminal status '%s', skipping republish",
                    cmd_id,
                    cmd_status,
                )
                return {
                    "status": "ok",
                    "data": {
                        "command_id": cmd_id,
                        "message": f"Command already in terminal status: {cmd_status}",
                        "skipped": True,
                    },
                }

        if not existing_cmd:
            await execute(
                """
                INSERT INTO commands (zone_id, node_id, channel, cmd, params, status, source, cmd_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, 'QUEUED', $6, $7, NOW(), NOW())
                """,
                zone_id,
                node_id,
                req.channel,
                req.get_command_name(),
                req.params,
                command_source,
                cmd_id,
            )
            logger.info(f"Command {cmd_id} created in DB with status QUEUED")
        else:
            current_status = existing_cmd[0]["status"]
            if current_status not in ("QUEUED", "SEND_FAILED"):
                logger.warning(
                    "Command %s already exists with status %s, cannot republish. Skipping.",
                    cmd_id,
                    current_status,
                )
                return {
                    "status": "ok",
                    "data": {
                        "command_id": cmd_id,
                        "zone_id": zone_id,
                        "node_uid": req.node_uid,
                        "channel": req.channel,
                        "note": f"Command already exists with status {current_status}",
                    },
                }
    except Exception as e:
        logger.error(
            f"Failed to ensure command in DB: {e}",
            exc_info=True,
            extra={
                "zone_id": zone_id,
                "node_uid": req.node_uid,
                "channel": req.channel,
                "cmd_id": cmd_id,
            },
        )

    max_retries = 3
    retry_delays = [0.5, 1.0, 2.0]

    publish_success = False
    last_error: Any = None

    for attempt in range(max_retries):
        try:
            await publish_command_mqtt(
                mqtt,
                effective_gh_uid,
                zone_id,
                req.node_uid,
                req.channel,
                payload,
                zone_uid=zone_uid,
            )
            publish_success = True
            logger.info(
                "Command published successfully (attempt %s/%s): zone_id=%s, node_uid=%s, channel=%s, cmd_id=%s",
                attempt + 1,
                max_retries,
                zone_id,
                req.node_uid,
                req.channel,
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
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Failed to publish command after %s attempts: %s",
                    max_retries,
                    e,
                    exc_info=True,
                )

    if publish_success:
        try:
            await mark_command_sent(cmd_id, allow_resend=True)
            logger.info(f"Command {cmd_id} status updated to SENT")

            try:
                await send_status_to_laravel(
                    cmd_id=cmd_id,
                    status="SENT",
                    details={
                        "zone_id": zone_id,
                        "node_uid": req.node_uid,
                        "channel": req.channel,
                        "command": req.get_command_name(),
                        "published_at": utcnow().isoformat(),
                    },
                )
                logger.debug(
                    f"Correlation ACK sent for command {cmd_id} (status: SENT)"
                )
            except Exception as e:
                logger.warning(f"Failed to send correlation ACK for command {cmd_id}: {e}")
        except Exception as e:
            logger.error(
                f"Failed to update command status to SENT: {e}",
                exc_info=True,
                extra={"cmd_id": cmd_id},
            )

        COMMANDS_SENT.labels(zone_id=str(zone_id), metric=req.get_command_name()).inc()

        return {
            "status": "ok",
            "data": {
                "command_id": cmd_id,
                "zone_id": zone_id,
                "node_uid": req.node_uid,
                "channel": req.channel,
            },
        }

    try:
        await mark_command_send_failed(cmd_id, str(last_error))
        logger.error(f"Command {cmd_id} status updated to SEND_FAILED")
    except Exception as e:
        logger.error(
            f"Failed to update command status to SEND_FAILED: {e}",
            exc_info=True,
        )
    await _emit_command_send_failed_alert(
        zone_id=zone_id,
        node_uid=req.node_uid,
        channel=req.channel,
        cmd=req.get_command_name(),
        cmd_id=cmd_id,
        error=last_error,
        max_retries=max_retries,
    )

    MQTT_PUBLISH_ERRORS.labels(error_type=type(last_error).__name__).inc()
    raise HTTPException(
        status_code=500,
        detail=f"Failed to publish command after {max_retries} attempts: {str(last_error)}",
    )


@router.post("/nodes/{node_uid}/commands")
async def publish_node_command(
    request: Request, node_uid: str, req: CommandRequest = Body(...)
):
    """
    Публиковать команду для ноды через history-logger.
    Все общение бэка с нодами должно происходить через history-logger.
    """
    _auth_ingest(request)
    _apply_trace_id(req.trace_id)

    if not (req.greenhouse_uid and req.zone_id and req.channel):
        raise HTTPException(
            status_code=400, detail="greenhouse_uid, zone_id and channel are required"
        )

    if not req.cmd:
        raise HTTPException(status_code=400, detail="'cmd' is required")

    node_id = await _require_node_assigned_to_zone(node_uid, req.zone_id)

    zone_uid = None
    s = get_settings()
    if hasattr(s, "mqtt_zone_format") and s.mqtt_zone_format == "uid":
        zone_uid = await _get_zone_uid_from_id(req.zone_id)
    command_source = req.source or "api"
    effective_gh_uid = await _resolve_effective_gh_uid(req.zone_id, req.greenhouse_uid)

    try:
        payload = _create_command_payload(
            cmd=req.cmd,
            cmd_id=req.cmd_id,
            params=req.params,
            ts=req.ts,
            sig=req.sig,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cmd_id = payload["cmd_id"]
    set_trace_id(cmd_id, allow_generate=False)

    mqtt = await get_mqtt_client()

    try:
        existing_cmd = await fetch(
            "SELECT status, source FROM commands WHERE cmd_id = $1", cmd_id
        )
        if existing_cmd:
            cmd_status = existing_cmd[0].get("status", "").lower()
            if not existing_cmd[0].get("source") and command_source:
                try:
                    await execute(
                        "UPDATE commands SET source = $1 WHERE cmd_id = $2",
                        command_source,
                        cmd_id,
                    )
                except Exception:
                    logger.warning(
                        f"[COMMAND_PUBLISH] Failed to backfill source for command {cmd_id}"
                    )
            if cmd_status in ("ack", "done", "no_effect", "error", "invalid", "busy", "timeout"):
                logger.info(
                    "[IDEMPOTENCY] Command %s already in terminal status '%s', skipping republish",
                    cmd_id,
                    cmd_status,
                )
                return {
                    "status": "ok",
                    "data": {
                        "command_id": cmd_id,
                        "message": f"Command already in terminal status: {cmd_status}",
                        "skipped": True,
                    },
                }

        if not existing_cmd:
            await execute(
                """
                INSERT INTO commands (zone_id, node_id, channel, cmd, params, status, source, cmd_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, 'QUEUED', $6, $7, NOW(), NOW())
                """,
                req.zone_id,
                node_id,
                req.channel,
                req.get_command_name(),
                req.params,
                command_source,
                cmd_id,
            )
            logger.info(f"Command {cmd_id} created in DB with status QUEUED")
        else:
            current_status = existing_cmd[0]["status"]
            if current_status not in ("QUEUED", "SEND_FAILED"):
                logger.warning(
                    "Command %s already exists with status %s, cannot republish. Skipping.",
                    cmd_id,
                    current_status,
                )
                return {
                    "status": "ok",
                    "data": {
                        "command_id": cmd_id,
                        "zone_id": req.zone_id,
                        "node_uid": node_uid,
                        "channel": req.channel,
                        "note": f"Command already exists with status {current_status}",
                    },
                }
    except Exception as e:
        logger.error(
            f"Failed to ensure command in DB: {e}",
            exc_info=True,
            extra={
                "zone_id": req.zone_id,
                "node_uid": node_uid,
                "channel": req.channel,
                "cmd_id": cmd_id,
            },
        )

    max_retries = 3
    retry_delays = [0.5, 1.0, 2.0]

    publish_success = False
    last_error: Any = None

    for attempt in range(max_retries):
        try:
            await publish_command_mqtt(
                mqtt,
                effective_gh_uid,
                req.zone_id,
                node_uid,
                req.channel,
                payload,
                zone_uid=zone_uid,
            )
            publish_success = True
            logger.info(
                "Command published successfully (attempt %s/%s): zone_id=%s, node_uid=%s, channel=%s, cmd_id=%s",
                attempt + 1,
                max_retries,
                req.zone_id,
                node_uid,
                req.channel,
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
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Failed to publish command after %s attempts: %s",
                    max_retries,
                    e,
                    exc_info=True,
                )

    if publish_success:
        try:
            await mark_command_sent(cmd_id, allow_resend=True)
            logger.info(f"Command {cmd_id} status updated to SENT")

            try:
                await send_status_to_laravel(
                    cmd_id=cmd_id,
                    status="SENT",
                    details={
                        "zone_id": req.zone_id,
                        "node_uid": node_uid,
                        "channel": req.channel,
                        "command": req.get_command_name(),
                        "published_at": utcnow().isoformat(),
                    },
                )
                logger.debug(
                    f"Correlation ACK sent for command {cmd_id} (status: SENT)"
                )
            except Exception as e:
                logger.warning(f"Failed to send correlation ACK for command {cmd_id}: {e}")
        except Exception as e:
            logger.error(
                f"Failed to update command status to SENT: {e}",
                exc_info=True,
                extra={"cmd_id": cmd_id},
            )

        COMMANDS_SENT.labels(zone_id=str(req.zone_id), metric=req.get_command_name()).inc()

        return {
            "status": "ok",
            "data": {
                "command_id": cmd_id,
                "zone_id": req.zone_id,
                "node_uid": node_uid,
                "channel": req.channel,
            },
        }

    try:
        await mark_command_send_failed(cmd_id, str(last_error))
        logger.error(f"Command {cmd_id} status updated to SEND_FAILED")
    except Exception as e:
        logger.error(
            f"Failed to update command status to SEND_FAILED: {e}",
            exc_info=True,
        )
    await _emit_command_send_failed_alert(
        zone_id=req.zone_id,
        node_uid=node_uid,
        channel=req.channel,
        cmd=req.get_command_name(),
        cmd_id=cmd_id,
        error=last_error,
        max_retries=max_retries,
    )

    MQTT_PUBLISH_ERRORS.labels(error_type=type(last_error).__name__).inc()
    raise HTTPException(
        status_code=500,
        detail=f"Failed to publish command after {max_retries} attempts: {str(last_error)}",
    )


@router.post("/commands")
async def publish_command(request: Request, req: CommandRequest = Body(...)):
    """
    Универсальный endpoint для публикации команд через history-logger.
    """
    _auth_ingest(request)
    _apply_trace_id(req.trace_id)

    if not req.cmd:
        raise HTTPException(status_code=400, detail="'cmd' is required")

    if not (req.greenhouse_uid and req.zone_id and req.node_uid and req.channel):
        raise HTTPException(
            status_code=400,
            detail="greenhouse_uid, zone_id, node_uid and channel are required",
        )

    node_id = await _require_node_assigned_to_zone(req.node_uid, req.zone_id)

    zone_uid = None
    s = get_settings()
    if hasattr(s, "mqtt_zone_format") and s.mqtt_zone_format == "uid":
        zone_uid = await _get_zone_uid_from_id(req.zone_id)
    command_source = req.source or "api"
    effective_gh_uid = await _resolve_effective_gh_uid(req.zone_id, req.greenhouse_uid)

    cmd_id = req.cmd_id
    params_without_cmd_id = req.params or {}

    try:
        payload = _create_command_payload(
            cmd=req.cmd,
            cmd_id=cmd_id,
            params=params_without_cmd_id,
            ts=req.ts,
            sig=req.sig,
        )
        cmd_id = payload["cmd_id"]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    set_trace_id(cmd_id, allow_generate=False)

    log_context = {
        "zone_id": req.zone_id,
        "node_uid": req.node_uid,
        "channel": req.channel,
        "cmd_id": cmd_id,
        "command": req.get_command_name(),
        "source": command_source,
    }
    if req.trace_id:
        log_context["trace_id"] = req.trace_id

    logger.info(
        f"Publishing command via /commands endpoint: {log_context}",
        extra=log_context,
    )

    try:
        existing_cmd = await fetch(
            """
            SELECT status, source FROM commands WHERE cmd_id = $1
            """,
            cmd_id,
        )

        if existing_cmd:
            cmd_status = existing_cmd[0].get("status", "").lower()
            if not existing_cmd[0].get("source") and command_source:
                try:
                    await execute(
                        "UPDATE commands SET source = $1 WHERE cmd_id = $2",
                        command_source,
                        cmd_id,
                    )
                except Exception:
                    logger.warning(
                        f"[COMMAND_PUBLISH] Failed to backfill source for command {cmd_id}"
                    )
            if cmd_status in ("ack", "done", "no_effect", "error", "invalid", "busy", "timeout"):
                logger.info(
                    "[IDEMPOTENCY] Command %s already in terminal status '%s', skipping republish",
                    cmd_id,
                    cmd_status,
                )
                return {
                    "status": "ok",
                    "data": {
                        "command_id": cmd_id,
                        "message": f"Command already in terminal status: {cmd_status}",
                        "skipped": True,
                    },
                }

        if not existing_cmd:
            await execute(
                """
                INSERT INTO commands (zone_id, node_id, channel, cmd, params, status, source, cmd_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, 'QUEUED', $6, $7, NOW(), NOW())
                """,
                req.zone_id,
                node_id,
                req.channel,
                req.get_command_name(),
                params_without_cmd_id,
                command_source,
                cmd_id,
            )
            logger.info(f"Command {cmd_id} created in DB with status QUEUED")
        else:
            current_status = existing_cmd[0]["status"]
            if current_status not in ("QUEUED", "SEND_FAILED"):
                logger.warning(
                    "Command %s already exists with status %s, cannot republish. Skipping.",
                    cmd_id,
                    current_status,
                )
                return {
                    "status": "ok",
                    "data": {
                        "command_id": cmd_id,
                        "zone_id": req.zone_id,
                        "node_uid": req.node_uid,
                        "channel": req.channel,
                        "note": f"Command already exists with status {current_status}",
                    },
                }
    except Exception as e:
        logger.error(
            f"Failed to ensure command in DB: {e}",
            exc_info=True,
            extra=log_context,
        )

    mqtt = await get_mqtt_client()
    max_retries = 3
    retry_delays = [0.5, 1.0, 2.0]

    publish_success = False
    last_error: Any = None

    for attempt in range(max_retries):
        try:
            await publish_command_mqtt(
                mqtt,
                effective_gh_uid,
                req.zone_id,
                req.node_uid,
                req.channel,
                payload,
                zone_uid=zone_uid,
            )
            publish_success = True
            logger.info(
                "Command published successfully (attempt %s/%s): %s",
                attempt + 1,
                max_retries,
                log_context,
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
        try:
            await mark_command_sent(cmd_id, allow_resend=True)
            logger.info(f"Command {cmd_id} status updated to SENT")

            try:
                await send_status_to_laravel(
                    cmd_id=cmd_id,
                    status="SENT",
                    details={
                        "zone_id": req.zone_id,
                        "node_uid": req.node_uid,
                        "channel": req.channel,
                        "command": req.get_command_name(),
                        "published_at": utcnow().isoformat(),
                    },
                )
                logger.debug(
                    f"Correlation ACK sent for command {cmd_id} (status: SENT)"
                )
            except Exception as e:
                logger.warning(f"Failed to send correlation ACK for command {cmd_id}: {e}")
        except Exception as e:
            logger.error(
                f"Failed to update command status to SENT: {e}",
                exc_info=True,
                extra=log_context,
            )

        COMMANDS_SENT.labels(zone_id=str(req.zone_id), metric=req.get_command_name()).inc()

        return {
            "status": "ok",
            "data": {
                "command_id": cmd_id,
                "zone_id": req.zone_id,
                "node_uid": req.node_uid,
                "channel": req.channel,
            },
        }

    try:
        await mark_command_send_failed(cmd_id, str(last_error))
        logger.error(f"Command {cmd_id} status updated to SEND_FAILED")
    except Exception as e:
        logger.error(
            f"Failed to update command status to SEND_FAILED: {e}",
            exc_info=True,
        )
    await _emit_command_send_failed_alert(
        zone_id=req.zone_id,
        node_uid=req.node_uid,
        channel=req.channel,
        cmd=req.get_command_name(),
        cmd_id=cmd_id,
        error=last_error,
        max_retries=max_retries,
    )

    MQTT_PUBLISH_ERRORS.labels(error_type=type(last_error).__name__).inc()
    raise HTTPException(
        status_code=500,
        detail=f"Failed to publish command after {max_retries} attempts: {str(last_error)}",
    )


@router.post("/zones/{zone_id}/fill")
async def zone_fill(
    request: Request, zone_id: int, req: FillDrainRequest = Body(...)
):
    """Выполнить режим наполнения (Fill Mode) через history-logger."""
    _auth_ingest(request)

    _validate_target_level(req.target_level, 0.1, 1.0, "fill")

    gh_uid = await _get_gh_uid_from_zone_id(zone_id)

    async with _mqtt_client_context("-fill") as mqtt:
        try:
            result = await execute_fill_mode(
                zone_id, req.target_level, mqtt, gh_uid, req.max_duration_sec
            )
            return {"status": "ok", "data": result}
        except Exception as e:
            logger.error(
                f"Failed to execute fill mode for zone {zone_id}: {e}", exc_info=True
            )
            await send_infra_exception_alert(
                error=e,
                code="infra_fill_mode_failed",
                alert_type="Fill Mode Failed",
                severity="error",
                zone_id=zone_id,
                service="history-logger",
                component="water_flow",
                details={
                    "target_level": req.target_level,
                    "max_duration_sec": req.max_duration_sec,
                },
            )
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/zones/{zone_id}/drain")
async def zone_drain(
    request: Request, zone_id: int, req: FillDrainRequest = Body(...)
):
    """Выполнить режим слива (Drain Mode) через history-logger."""
    _auth_ingest(request)

    _validate_target_level(req.target_level, 0.0, 0.9, "drain")

    gh_uid = await _get_gh_uid_from_zone_id(zone_id)

    async with _mqtt_client_context("-drain") as mqtt:
        try:
            result = await execute_drain_mode(
                zone_id, req.target_level, mqtt, gh_uid, req.max_duration_sec
            )
            return {"status": "ok", "data": result}
        except Exception as e:
            logger.error(
                f"Failed to execute drain mode for zone {zone_id}: {e}", exc_info=True
            )
            await send_infra_exception_alert(
                error=e,
                code="infra_drain_mode_failed",
                alert_type="Drain Mode Failed",
                severity="error",
                zone_id=zone_id,
                service="history-logger",
                component="water_flow",
                details={
                    "target_level": req.target_level,
                    "max_duration_sec": req.max_duration_sec,
                },
            )
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/zones/{zone_id}/calibrate-flow")
async def zone_calibrate_flow(
    request: Request, zone_id: int, req: CalibrateFlowRequest = Body(...)
):
    """Выполнить калибровку расхода воды (Flow Calibration) через history-logger."""
    _auth_ingest(request)

    gh_uid = await _get_gh_uid_from_zone_id(zone_id)

    async with _mqtt_client_context("-calibrate") as mqtt:
        try:
            result = await calibrate_flow(
                zone_id,
                req.node_id,
                req.channel,
                mqtt,
                gh_uid,
                req.pump_duration_sec,
            )
            return {"status": "ok", "data": result}
        except Exception as e:
            logger.error(
                f"Failed to calibrate flow for zone {zone_id}: {e}", exc_info=True
            )
            await send_infra_exception_alert(
                error=e,
                code="infra_flow_calibration_failed",
                alert_type="Flow Calibration Failed",
                severity="error",
                zone_id=zone_id,
                service="history-logger",
                component="flow_calibration",
                details={
                    "node_id": req.node_id,
                    "channel": req.channel,
                    "pump_duration_sec": req.pump_duration_sec,
                },
            )
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/zones/{zone_id}/calibrate-pump")
async def zone_calibrate_pump(
    request: Request, zone_id: int, req: CalibratePumpRequest = Body(...)
):
    """Выполнить калибровку дозирующей помпы (ml/sec) через history-logger."""
    _auth_ingest(request)

    gh_uid = await _get_gh_uid_from_zone_id(zone_id)

    async with _mqtt_client_context("-calibrate-pump") as mqtt:
        try:
            result = await calibrate_pump(
                zone_id=zone_id,
                node_channel_id=req.node_channel_id,
                duration_sec=req.duration_sec,
                actual_ml=req.actual_ml,
                skip_run=req.skip_run,
                component=req.component,
                test_volume_l=req.test_volume_l,
                ec_before_ms=req.ec_before_ms,
                ec_after_ms=req.ec_after_ms,
                temperature_c=req.temperature_c,
                mqtt_client=mqtt,
                gh_uid=gh_uid,
            )
            return {"status": "ok", "data": result}
        except Exception as e:
            logger.error(
                f"Failed to calibrate pump for zone {zone_id}: {e}", exc_info=True
            )
            await send_infra_exception_alert(
                error=e,
                code="infra_pump_calibration_failed",
                alert_type="Pump Calibration Failed",
                severity="error",
                zone_id=zone_id,
                service="history-logger",
                component="pump_calibration",
                details={
                    "node_channel_id": req.node_channel_id,
                    "duration_sec": req.duration_sec,
                    "actual_ml": req.actual_ml,
                    "skip_run": req.skip_run,
                    "component": req.component,
                    "test_volume_l": req.test_volume_l,
                    "ec_before_ms": req.ec_before_ms,
                    "ec_after_ms": req.ec_after_ms,
                    "temperature_c": req.temperature_c,
                },
            )
            raise HTTPException(status_code=500, detail=str(e))

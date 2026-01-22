import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from auth import _auth_ingest
from command_service import (
    _create_command_payload,
    _get_gh_uid_from_zone_id,
    _get_zone_uid_from_id,
    _mqtt_client_context,
    _validate_target_level,
    publish_command_mqtt,
)
from common.command_status_queue import send_status_to_laravel
from common.commands import mark_command_send_failed, mark_command_sent
from common.db import execute, fetch
from common.env import get_settings
from common.mqtt import get_mqtt_client
from common.utils.time import utcnow
from common.water_flow import calibrate_flow, execute_drain_mode, execute_fill_mode
from metrics import COMMANDS_SENT, MQTT_PUBLISH_ERRORS
from models import (
    CalibrateFlowRequest,
    CommandRequest,
    FillDrainRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/nodes/{node_uid}/config")
async def publish_node_config(request: Request, node_uid: str):
    """
    Публикация NodeConfig отключена: ноды отправляют config_report при подключении.
    """
    logger.warning(
        "[PUBLISH_CONFIG] Config publish endpoint is disabled. node_uid=%s",
        node_uid,
    )
    raise HTTPException(
        status_code=410,
        detail="Config publishing from server is disabled. Nodes send config_report on connect.",
    )


@router.post("/zones/{zone_id}/commands")
async def publish_zone_command(
    request: Request, zone_id: int, req: CommandRequest = Body(...)
):
    """
    Публиковать команду для зоны через history-logger.
    Все общение бэка с нодами должно происходить через history-logger.
    """
    _auth_ingest(request)

    if not (req.greenhouse_uid and req.node_uid and req.channel):
        raise HTTPException(
            status_code=400, detail="greenhouse_uid, node_uid and channel are required"
        )

    if not req.get_command_name():
        raise HTTPException(status_code=400, detail="'cmd' is required")

    zone_uid = None
    s = get_settings()
    if hasattr(s, "mqtt_zone_format") and s.mqtt_zone_format == "uid":
        zone_uid = await _get_zone_uid_from_id(zone_id)
    command_source = req.source or "api"

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
            node_rows = await fetch(
                """
                SELECT id FROM nodes WHERE uid = $1 AND zone_id = $2
                """,
                req.node_uid,
                zone_id,
            )
            node_id = node_rows[0]["id"] if node_rows else None

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
                req.greenhouse_uid,
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

    if not (req.greenhouse_uid and req.zone_id and req.channel):
        raise HTTPException(
            status_code=400, detail="greenhouse_uid, zone_id and channel are required"
        )

    if not req.cmd:
        raise HTTPException(status_code=400, detail="'cmd' is required")

    zone_uid = None
    s = get_settings()
    if hasattr(s, "mqtt_zone_format") and s.mqtt_zone_format == "uid":
        zone_uid = await _get_zone_uid_from_id(req.zone_id)
    command_source = req.source or "api"

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
            node_rows = await fetch(
                """
                SELECT id FROM nodes WHERE uid = $1 AND zone_id = $2
                """,
                node_uid,
                req.zone_id,
            )
            node_id = node_rows[0]["id"] if node_rows else None

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
                req.greenhouse_uid,
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

    if not req.cmd:
        raise HTTPException(status_code=400, detail="'cmd' is required")

    if not (req.greenhouse_uid and req.zone_id and req.node_uid and req.channel):
        raise HTTPException(
            status_code=400,
            detail="greenhouse_uid, zone_id, node_uid and channel are required",
        )

    zone_uid = None
    s = get_settings()
    if hasattr(s, "mqtt_zone_format") and s.mqtt_zone_format == "uid":
        zone_uid = await _get_zone_uid_from_id(req.zone_id)
    command_source = req.source or "api"

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
            node_rows = await fetch(
                """
                SELECT id FROM nodes WHERE uid = $1 AND zone_id = $2
                """,
                req.node_uid,
                req.zone_id,
            )
            node_id = node_rows[0]["id"] if node_rows else None

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
                req.greenhouse_uid,
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
            raise HTTPException(status_code=500, detail=str(e))

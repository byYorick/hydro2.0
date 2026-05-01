"""FastAPI routes для command publish. Вся логика — в ``commands/`` subpackage."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Request

from auth import _auth_ingest
from command_service import (
    _create_command_payload,
    _get_gh_uid_from_zone_id,
    _get_zone_uid_from_id,
    publish_command_mqtt,
    publish_config_mqtt,
    publish_config_temp_mqtt,
)
from common.commands import mark_command_send_failed, mark_command_sent
from common.db import execute, fetch
from common.db import create_zone_event
from common.env import get_settings
from common.infra_alerts import send_infra_alert
from common.mqtt import get_mqtt_client
from common.trace_context import set_trace_id
from commands import alerts as alerts_module
from commands import lifecycle as lifecycle_module
from commands import publisher as publisher_module
from commands import resolution as resolution_module
from commands.lifecycle import ensure_command_for_publish
from commands.publisher import publish_command_with_retry
from commands.resolution import (
    require_node_assigned_to_zone,
    resolve_effective_gh_uid,
    resolve_zone_uid_for_command_publish,
)
from commands.validation import (
    apply_trace_id,
    ensure_node_secret,
    validate_command_request_contract,
)
from models import CommandRequest, NodeConfigPublishRequest
logger = logging.getLogger(__name__)

router = APIRouter()

# Backward-compat exports for legacy tests/imports that patch symbols from
# this module directly.
async def _ensure_command_for_publish(**kwargs):
    _sync_legacy_dependency_overrides()
    original_fetch = lifecycle_module.fetch
    original_execute = lifecycle_module.execute
    lifecycle_module.fetch = fetch
    lifecycle_module.execute = execute
    try:
        return await ensure_command_for_publish(**kwargs)
    finally:
        lifecycle_module.fetch = original_fetch
        lifecycle_module.execute = original_execute


def _sync_legacy_dependency_overrides() -> None:
    """Keep refactored command modules patchable via ``command_routes.*`` symbols."""
    lifecycle_module.fetch = fetch
    lifecycle_module.execute = execute
    resolution_module.fetch = fetch
    resolution_module.get_settings = get_settings
    resolution_module._get_gh_uid_from_zone_id = _get_gh_uid_from_zone_id
    resolution_module._get_zone_uid_from_id = _get_zone_uid_from_id
    alerts_module.send_infra_alert = send_infra_alert
    alerts_module.create_zone_event = create_zone_event
    publisher_module.get_mqtt_client = get_mqtt_client
    publisher_module.publish_command_mqtt = publish_command_mqtt
    publisher_module.mark_command_sent = mark_command_sent
    publisher_module.mark_command_send_failed = mark_command_send_failed


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


@router.post("/nodes/{node_uid}/config")
async def publish_node_config(
    request: Request,
    node_uid: str,
    req: NodeConfigPublishRequest = Body(...),
):
    """Publish NodeConfig в MQTT. Требует greenhouse_uid + zone_id/zone_uid."""
    _sync_legacy_dependency_overrides()
    _auth_ingest(request)

    if not req.zone_id and not req.zone_uid:
        raise HTTPException(status_code=400, detail="zone_id or zone_uid is required")

    zone_uid = req.zone_uid
    if not zone_uid and req.zone_id:
        zone_uid = await _get_zone_uid_from_id(req.zone_id)

    if not zone_uid:
        raise HTTPException(status_code=400, detail="zone_uid could not be resolved")

    if not req.zone_id:
        raise HTTPException(status_code=400, detail="zone_id is required to resolve greenhouse_uid")

    node_rows = await fetch(
        """
        SELECT id, zone_id, pending_zone_id, hardware_id
        FROM nodes
        WHERE uid = $1
        """,
        node_uid,
    )
    if not node_rows:
        raise HTTPException(status_code=404, detail="node_uid not found")

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
        raise HTTPException(status_code=409, detail="node is already bound to another zone")

    if pending_zone_id and pending_zone_id != req.zone_id and not node_zone_id:
        raise HTTPException(status_code=409, detail="pending_zone_id does not match requested zone_id")

    gh_uid = await resolve_effective_gh_uid(req.zone_id, req.greenhouse_uid)

    mqtt = await get_mqtt_client()
    config_payload = ensure_node_secret(dict(req.config))
    use_temp_topic = pending_zone_id == req.zone_id and not node_zone_id
    if pending_zone_id == req.zone_id and node_zone_id:
        raise HTTPException(
            status_code=409,
            detail="inconsistent node binding state: zone_id and pending_zone_id are both set",
        )

    if use_temp_topic:
        if not hardware_id:
            raise HTTPException(status_code=409, detail="hardware_id is required for temp config publish")
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


async def _publish_command_core(
    *,
    req: CommandRequest,
    zone_id: int,
    node_uid: str,
    channel: str,
    log_context: Optional[dict] = None,
) -> dict:
    """Общая часть всех трёх command-routes: validate → resolve → ensure DB → publish retry.

    Route-handler'ы отличаются только тем, ОТКУДА берутся ``zone_id/node_uid/channel``
    (path vs body), и что они валидируют на входе. Этот helper централизует всё остальное.
    """
    _sync_legacy_dependency_overrides()
    validate_command_request_contract(req)

    node_id = await require_node_assigned_to_zone(node_uid, zone_id)
    zone_uid = await resolve_zone_uid_for_command_publish(zone_id)
    command_source = req.source or "api"
    effective_gh_uid = await resolve_effective_gh_uid(zone_id, req.greenhouse_uid)

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

    skip_response = await ensure_command_for_publish(
        cmd_id=cmd_id,
        zone_id=zone_id,
        node_id=node_id,
        node_uid=node_uid,
        channel=channel,
        cmd_name=req.get_command_name(),
        params=req.params,
        command_source=command_source,
    )
    if skip_response:
        return skip_response

    return await publish_command_with_retry(
        payload=payload,
        cmd_id=cmd_id,
        cmd_name=req.get_command_name(),
        zone_id=zone_id,
        node_uid=node_uid,
        channel=channel,
        effective_gh_uid=effective_gh_uid,
        zone_uid=zone_uid,
        log_context=log_context,
    )


@router.post("/zones/{zone_id}/commands")
async def publish_zone_command(
    request: Request, zone_id: int, req: CommandRequest = Body(...)
):
    """Publish команду для зоны через history-logger (единственный путь команд → MQTT)."""
    _auth_ingest(request)
    apply_trace_id(req.trace_id)

    if not (req.greenhouse_uid and req.node_uid and req.channel):
        raise HTTPException(
            status_code=400, detail="greenhouse_uid, node_uid and channel are required"
        )

    return await _publish_command_core(
        req=req,
        zone_id=zone_id,
        node_uid=req.node_uid,
        channel=req.channel,
    )


@router.post("/nodes/{node_uid}/commands")
async def publish_node_command(
    request: Request, node_uid: str, req: CommandRequest = Body(...)
):
    """Publish команду для ноды через history-logger."""
    _auth_ingest(request)
    apply_trace_id(req.trace_id)

    if not (req.greenhouse_uid and req.zone_id and req.channel):
        raise HTTPException(
            status_code=400, detail="greenhouse_uid, zone_id and channel are required"
        )

    return await _publish_command_core(
        req=req,
        zone_id=req.zone_id,
        node_uid=node_uid,
        channel=req.channel,
    )


@router.post("/commands")
async def publish_command(request: Request, req: CommandRequest = Body(...)):
    """Универсальный endpoint: все параметры берутся из body."""
    _auth_ingest(request)
    apply_trace_id(req.trace_id)

    validate_command_request_contract(req)

    if not (req.greenhouse_uid and req.zone_id and req.node_uid and req.channel):
        raise HTTPException(
            status_code=400,
            detail="greenhouse_uid, zone_id, node_uid and channel are required",
        )

    log_context = {
        "zone_id": req.zone_id,
        "node_uid": req.node_uid,
        "channel": req.channel,
        "cmd_id": req.cmd_id,
        "command": req.get_command_name(),
        "source": req.source or "api",
    }
    if req.trace_id:
        log_context["trace_id"] = req.trace_id
    logger.info(
        f"Publishing command via /commands endpoint: {log_context}",
        extra=log_context,
    )

    return await _publish_command_core(
        req=req,
        zone_id=req.zone_id,
        node_uid=req.node_uid,
        channel=req.channel,
        log_context=log_context,
    )

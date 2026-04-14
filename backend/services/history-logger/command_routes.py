import asyncio
import json
import logging
from typing import Any, Optional

import asyncpg
from fastapi import APIRouter, Body, HTTPException, Request

from auth import _auth_ingest
from command_service import (
    _create_command_payload,
    _get_gh_uid_from_zone_id,
    _get_zone_uid_from_id,
    publish_config_mqtt,
    publish_config_temp_mqtt,
    publish_command_mqtt,
)
from common.command_status_queue import send_status_to_laravel
from common.commands import mark_command_send_failed, mark_command_sent
from common.db import create_zone_event, execute, fetch
from common.env import get_settings
from common.infra_alerts import send_infra_alert
from common.mqtt import get_mqtt_client
from common.trace_context import get_trace_id, set_trace_id
from common.utils.time import utcnow
from metrics import COMMANDS_SENT, MQTT_PUBLISH_ERRORS
from models import (
    CommandRequest,
    NodeConfigPublishRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_FINAL_COMMAND_STATUSES = {"DONE", "NO_EFFECT", "ERROR", "INVALID", "BUSY", "TIMEOUT"}
_NON_REPUBLISHABLE_COMMAND_STATUSES = _FINAL_COMMAND_STATUSES | {"ACK"}
_REPUBLISH_ALLOWED_STATUSES = {"QUEUED", "SEND_FAILED"}
_POST_PUBLISH_ALLOWED_STATUSES = _NON_REPUBLISHABLE_COMMAND_STATUSES | _REPUBLISH_ALLOWED_STATUSES | {"SENT"}

# Audit F8 + F10: centralised constants for previously inline magic values.
# Tuple (not list) so accidental mutation raises; underscore prefix marks
# them private to this module.

#: Exponential backoff schedule for MQTT publish retry attempts.
#: The first retry fires 500ms after the first failure, then 1s, then 2s.
#: Total worst-case delay is ~3.5s before bubbling a 500 to the caller,
#: which keeps Laravel's dispatch loop responsive while still absorbing
#: transient MQTT broker hiccups.
_MQTT_PUBLISH_RETRY_DELAYS_SEC: tuple[float, ...] = (0.5, 1.0, 2.0)

#: Statuses that must never be produced by history-logger or persisted
#: into ``commands.status``. ACCEPTED/FAILED are legacy values from the
#: pre-ae3 dispatch pipeline and are explicitly blocked at both inbound
#: validation (normalize_status) and would be surfaced here if any new
#: code path ever tried to materialise them.
_FORBIDDEN_COMMAND_STATUSES = frozenset({"ACCEPTED", "FAILED"})


def _validate_command_request_contract(req: CommandRequest) -> None:
    if "legacy_type" in req.model_fields_set:
        raise HTTPException(
            status_code=400,
            detail="Legacy field 'type' is not supported, use 'cmd'",
        )
    if not req.get_command_name():
        raise HTTPException(status_code=400, detail="'cmd' is required")


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


async def _emit_command_node_zone_mismatch_observability(
    *,
    zone_id: int,
    node_uid: str,
    node_zone_id: Any,
    pending_zone_id: Any,
) -> None:
    """Emit zone_event + infra alert for fail-closed node/zone guard rejections."""
    details = {
        "reason": "zone_mismatch",
        "node_uid": node_uid,
        "requested_zone_id": zone_id,
        "actual_zone_id": node_zone_id,
        "pending_zone_id": pending_zone_id,
    }

    try:
        await create_zone_event(zone_id, "COMMAND_ZONE_NODE_MISMATCH", details)
    except Exception as exc:
        logger.warning(
            "[COMMAND_PUBLISH] Failed to create COMMAND_ZONE_NODE_MISMATCH event: zone_id=%s node_uid=%s error=%s",
            zone_id,
            node_uid,
            exc,
        )

    try:
        await send_infra_alert(
            code="infra_command_node_zone_mismatch",
            alert_type="Command Node/Zone Mismatch",
            message=(
                f"Command publish blocked: node '{node_uid}' is assigned to zone "
                f"{node_zone_id}, requested zone is {zone_id}"
            ),
            severity="warning",
            zone_id=zone_id,
            service="history-logger",
            component="command_publish_guard",
            node_uid=node_uid,
            details=details,
        )
    except Exception as exc:
        logger.warning(
            "[COMMAND_PUBLISH] Failed to send infra_command_node_zone_mismatch alert: zone_id=%s node_uid=%s error=%s",
            zone_id,
            node_uid,
            exc,
        )


async def _resolve_effective_gh_uid(zone_id: int, requested_gh_uid: Optional[str]) -> str:
    """
    Резолвить канонический gh_uid по zone_id.
    Publish работает fail-closed: greenhouse_uid из запроса не является authority.
    """
    resolved_gh_uid = await _get_gh_uid_from_zone_id(zone_id)

    if requested_gh_uid and requested_gh_uid != resolved_gh_uid:
        logger.warning(
            "[MQTT_PUBLISH] greenhouse_uid mismatch for zone_id=%s: requested=%s, resolved=%s. Using resolved value.",
            zone_id,
            requested_gh_uid,
            resolved_gh_uid,
        )

    return resolved_gh_uid


async def _resolve_zone_uid_for_command_publish(zone_id: int) -> Optional[str]:
    """
    Единая точка резолва zone segment для publish команд.
    При MQTT_ZONE_FORMAT=uid работаем fail-closed: без zone_uid публиковать нельзя.
    """
    s = get_settings()
    zone_format = getattr(s, "mqtt_zone_format", "id")
    if zone_format != "uid":
        return None

    zone_uid = await _get_zone_uid_from_id(zone_id)
    if zone_uid:
        return zone_uid

    raise HTTPException(
        status_code=409,
        detail=(
            f"zone_uid could not be resolved for zone_id={zone_id} while "
            "MQTT_ZONE_FORMAT=uid"
        ),
    )


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
        await _emit_command_node_zone_mismatch_observability(
            zone_id=zone_id,
            node_uid=node_uid,
            node_zone_id=node_zone_id,
            pending_zone_id=pending_zone_id,
        )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Node '{node_uid}' is assigned to zone {node_zone_id}, "
                f"not zone {zone_id}"
            ),
        )

    return int(node["id"])


def _normalize_command_status(status: Any) -> str:
    return str(status or "").strip().upper()


async def _ensure_post_publish_status_persisted(cmd_id: str) -> None:
    """Verify the commands row is in a post-publish-valid state.

    Raises a ``RuntimeError`` with the full ``(reason, cmd_id, observed_status)``
    context so the caller's ``logger.error(..., exc_info=True)`` captures
    something actionable in the trace rather than a bare error name.

    Audit F11: the previous version raised
    ``RuntimeError("post_publish_status_not_transitioned")`` without the
    actual cmd_id, forcing a manual lookup to correlate the failure with
    a specific command.
    """
    rows = await fetch("SELECT status FROM commands WHERE cmd_id = $1", cmd_id)
    if not rows:
        raise RuntimeError(f"command_not_found_after_publish:cmd_id={cmd_id}")
    status = _normalize_command_status(rows[0].get("status"))
    if status not in _POST_PUBLISH_ALLOWED_STATUSES:
        raise RuntimeError(
            f"invalid_post_publish_status:cmd_id={cmd_id} status={status!r} "
            f"allowed={sorted(_POST_PUBLISH_ALLOWED_STATUSES)}"
        )
    if status == "QUEUED":
        raise RuntimeError(
            f"post_publish_status_not_transitioned:cmd_id={cmd_id} "
            f"status still QUEUED after publish — MQTT publish succeeded but "
            f"mark_command_sent failed to flip to SENT before this check"
        )


def _normalize_params_for_idempotency(params: Any) -> str:
    """Канонизация params для проверки коллизий cmd_id.

    Audit F14: this is NOT a duplicate of ``canonical_json_payload`` from
    ``common.hmac_utils``. The two serialisers have different contracts:

    * ``canonical_json_payload`` — HMAC signing format. Uses custom float
      canonicalisation (cJSON-compatible) and strips the ``sig`` key. Its
      output is fed into ``hmac.new(secret, payload.encode(), sha256)`` and
      any change produces a different signature. Cannot change numeric
      format without breaking every node's verification.

    * ``_normalize_params_for_idempotency`` — idempotency key for DB
      collision detection on ``(cmd_id, params_hash)``. Uses ``sort_keys``
      to handle Laravel historically persisting params in different key
      orders between runs. Numeric format must match whatever Laravel
      emits, not the cJSON canonical form.

    Merging them would break either HMAC verification on nodes or
    idempotency collision detection for legacy Laravel rows.
    """
    candidate = {} if params is None else params
    if isinstance(candidate, str):
        try:
            candidate = json.loads(candidate)
        except Exception:
            candidate = candidate.strip()
    # Laravel historically persisted empty params both as [] and {},
    # treat them as equivalent for cmd_id idempotency checks.
    if isinstance(candidate, list) and len(candidate) == 0:
        candidate = {}
    try:
        return json.dumps(candidate, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except Exception:
        return str(candidate)


async def _ensure_command_for_publish(
    *,
    cmd_id: str,
    zone_id: int,
    node_id: int,
    node_uid: str,
    channel: str,
    cmd_name: str,
    params: Optional[dict],
    command_source: str,
    _retry_on_conflict: bool = True,
) -> Optional[dict]:
    """Гарантирует fail-closed подготовку команды в БД перед MQTT publish."""
    try:
        existing_rows = await fetch(
            "SELECT status, source, zone_id, node_id, channel, cmd, params FROM commands WHERE cmd_id = $1",
            cmd_id,
        )
    except Exception as exc:
        logger.error(
            "[COMMAND_PUBLISH] Failed to fetch command before publish: cmd_id=%s zone_id=%s node_uid=%s channel=%s error=%s",
            cmd_id,
            zone_id,
            node_uid,
            channel,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to persist command, try again later",
        ) from exc

    if existing_rows:
        existing = existing_rows[0]
        if not existing.get("source") and command_source:
            try:
                await execute(
                    "UPDATE commands SET source = $1 WHERE cmd_id = $2",
                    command_source,
                    cmd_id,
                )
            except Exception:
                logger.warning(
                    "[COMMAND_PUBLISH] Failed to backfill source for command %s",
                    cmd_id,
                )

        collisions: list[str] = []
        existing_zone_id = existing.get("zone_id")
        if existing_zone_id is not None:
            try:
                if int(existing_zone_id) != int(zone_id):
                    collisions.append(f"zone_id={existing_zone_id}")
            except (TypeError, ValueError):
                collisions.append(f"zone_id={existing_zone_id}")

        existing_node_id = existing.get("node_id")
        if existing_node_id is not None:
            try:
                if int(existing_node_id) != int(node_id):
                    collisions.append(f"node_id={existing_node_id}")
            except (TypeError, ValueError):
                collisions.append(f"node_id={existing_node_id}")

        existing_channel = existing.get("channel")
        if existing_channel and str(existing_channel) != str(channel):
            collisions.append(f"channel={existing_channel}")

        existing_cmd = existing.get("cmd")
        if (
            existing_cmd
            and str(existing_cmd).strip().lower() != "unknown"
            and str(existing_cmd) != str(cmd_name)
        ):
            collisions.append(f"cmd={existing_cmd}")

        existing_params = _normalize_params_for_idempotency(existing.get("params"))
        requested_params = _normalize_params_for_idempotency(params)
        if existing_params != requested_params:
            collisions.append("params")

        if collisions:
            collision_text = ", ".join(collisions)
            logger.warning(
                "[IDEMPOTENCY] cmd_id collision detected: cmd_id=%s requested=(zone_id=%s,node_uid=%s,channel=%s,cmd=%s) existing=(%s)",
                cmd_id,
                zone_id,
                node_uid,
                channel,
                cmd_name,
                collision_text,
            )
            raise HTTPException(
                status_code=409,
                detail=f"Command ID '{cmd_id}' already belongs to another command ({collision_text})",
            )

        cmd_status = _normalize_command_status(existing.get("status"))
        if cmd_status in _NON_REPUBLISHABLE_COMMAND_STATUSES:
            status_kind = "final" if cmd_status in _FINAL_COMMAND_STATUSES else "in_progress"
            logger.info(
                "[IDEMPOTENCY] Command %s already in non-republishable status '%s' (%s), skipping republish",
                cmd_id,
                cmd_status.lower(),
                status_kind,
            )
            return {
                "status": "ok",
                "data": {
                    "command_id": cmd_id,
                    "message": f"Command already in non-republishable status: {cmd_status.lower()} ({status_kind})",
                    "skipped": True,
                },
            }

        if cmd_status not in _REPUBLISH_ALLOWED_STATUSES:
            logger.warning(
                "Command %s already exists with status %s, cannot republish. Skipping.",
                cmd_id,
                cmd_status,
            )
            return {
                "status": "ok",
                "data": {
                    "command_id": cmd_id,
                    "zone_id": zone_id,
                    "node_uid": node_uid,
                    "channel": channel,
                    "note": f"Command already exists with status {cmd_status}",
                },
            }

        return None

    if cmd_id and cmd_id.startswith("hl-"):
        # Audit (cmd_id forensics): legitimate AE3 / Laravel callers никогда не
        # генерируют префикс `hl-` для cmd_id (это есть только в тестовых моках).
        # Если такое всплыло в проде — нужен полный stack trace для root cause.
        logger.warning(
            "[CMD_ID_FORENSICS] About to INSERT command with hl- prefix cmd_id=%s "
            "zone_id=%s node_uid=%s channel=%s cmd=%s source=%s",
            cmd_id, zone_id, node_uid, channel, cmd_name, command_source,
            stack_info=True,
        )
    try:
        await execute(
            """
            INSERT INTO commands (zone_id, node_id, channel, cmd, params, status, source, cmd_id, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, 'QUEUED', $6, $7, NOW(), NOW())
            """,
            zone_id,
            node_id,
            channel,
            cmd_name,
            params or {},
            command_source,
            cmd_id,
        )
        logger.info("Command %s created in DB with status QUEUED", cmd_id)
    except asyncpg.UniqueViolationError as exc:
        if _retry_on_conflict:
            logger.info(
                "[IDEMPOTENCY] Concurrent command insert detected for cmd_id=%s, re-checking existing row",
                cmd_id,
            )
            return await _ensure_command_for_publish(
                cmd_id=cmd_id,
                zone_id=zone_id,
                node_id=node_id,
                node_uid=node_uid,
                channel=channel,
                cmd_name=cmd_name,
                params=params,
                command_source=command_source,
                _retry_on_conflict=False,
            )
        logger.error(
            "[COMMAND_PUBLISH] Unique cmd_id conflict persisted after retry: cmd_id=%s zone_id=%s node_uid=%s channel=%s error=%s",
            cmd_id,
            zone_id,
            node_uid,
            channel,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=409,
            detail=f"Command ID '{cmd_id}' already exists",
        ) from exc
    except Exception as exc:
        logger.error(
            "[COMMAND_PUBLISH] Failed to ensure command in DB: cmd_id=%s zone_id=%s node_uid=%s channel=%s error=%s",
            cmd_id,
            zone_id,
            node_uid,
            channel,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to persist command, try again later",
        ) from exc

    return None


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
        raise HTTPException(
            status_code=409,
            detail="inconsistent node binding state: zone_id and pending_zone_id are both set",
        )

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

    _validate_command_request_contract(req)

    node_id = await _require_node_assigned_to_zone(req.node_uid, zone_id)

    zone_uid = await _resolve_zone_uid_for_command_publish(zone_id)
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

    skip_response = await _ensure_command_for_publish(
        cmd_id=cmd_id,
        zone_id=zone_id,
        node_id=node_id,
        node_uid=req.node_uid,
        channel=req.channel,
        cmd_name=req.get_command_name(),
        params=req.params,
        command_source=command_source,
    )
    if skip_response:
        return skip_response

    max_retries = 3
    retry_delays = _MQTT_PUBLISH_RETRY_DELAYS_SEC

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
            await _ensure_post_publish_status_persisted(cmd_id)
            logger.info(f"Command {cmd_id} status updated to SENT")
        except Exception as e:
            logger.error(
                f"Failed to update command status to SENT: {e}",
                exc_info=True,
                extra={"cmd_id": cmd_id},
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
            # Audit F1+F5: send_status_to_laravel normally queues on HTTP
            # failure (enqueue_on_failure=True inside deliver_status_to_laravel)
            # so this except block only trips on catastrophic errors —
            # cancellation, pool exhaustion, queue enqueue failure. Command
            # IS already marked SENT in our DB and published to MQTT, so we
            # don't raise. Full exc_info is required for post-mortem: without
            # it we only see the exception type, no traceback, no way to
            # distinguish a Redis outage from a pool exhaustion.
            logger.warning(
                "Failed to send correlation ACK for command %s: %s",
                cmd_id,
                e,
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

    _validate_command_request_contract(req)

    node_id = await _require_node_assigned_to_zone(node_uid, req.zone_id)

    zone_uid = await _resolve_zone_uid_for_command_publish(req.zone_id)
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

    skip_response = await _ensure_command_for_publish(
        cmd_id=cmd_id,
        zone_id=req.zone_id,
        node_id=node_id,
        node_uid=node_uid,
        channel=req.channel,
        cmd_name=req.get_command_name(),
        params=req.params,
        command_source=command_source,
    )
    if skip_response:
        return skip_response

    max_retries = 3
    retry_delays = _MQTT_PUBLISH_RETRY_DELAYS_SEC

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
            await _ensure_post_publish_status_persisted(cmd_id)
            logger.info(f"Command {cmd_id} status updated to SENT")
        except Exception as e:
            logger.error(
                f"Failed to update command status to SENT: {e}",
                exc_info=True,
                extra={"cmd_id": cmd_id},
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
            # Audit F1+F5: send_status_to_laravel normally queues on HTTP
            # failure (enqueue_on_failure=True inside deliver_status_to_laravel)
            # so this except block only trips on catastrophic errors —
            # cancellation, pool exhaustion, queue enqueue failure. Command
            # IS already marked SENT in our DB and published to MQTT, so we
            # don't raise. Full exc_info is required for post-mortem: without
            # it we only see the exception type, no traceback, no way to
            # distinguish a Redis outage from a pool exhaustion.
            logger.warning(
                "Failed to send correlation ACK for command %s: %s",
                cmd_id,
                e,
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

    _validate_command_request_contract(req)

    if not (req.greenhouse_uid and req.zone_id and req.node_uid and req.channel):
        raise HTTPException(
            status_code=400,
            detail="greenhouse_uid, zone_id, node_uid and channel are required",
        )

    node_id = await _require_node_assigned_to_zone(req.node_uid, req.zone_id)

    zone_uid = await _resolve_zone_uid_for_command_publish(req.zone_id)
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

    skip_response = await _ensure_command_for_publish(
        cmd_id=cmd_id,
        zone_id=req.zone_id,
        node_id=node_id,
        node_uid=req.node_uid,
        channel=req.channel,
        cmd_name=req.get_command_name(),
        params=params_without_cmd_id,
        command_source=command_source,
    )
    if skip_response:
        return skip_response

    mqtt = await get_mqtt_client()
    max_retries = 3
    retry_delays = _MQTT_PUBLISH_RETRY_DELAYS_SEC

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
            await _ensure_post_publish_status_persisted(cmd_id)
            logger.info(f"Command {cmd_id} status updated to SENT")
        except Exception as e:
            logger.error(
                f"Failed to update command status to SENT: {e}",
                exc_info=True,
                extra=log_context,
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
            # Audit F1+F5: send_status_to_laravel normally queues on HTTP
            # failure (enqueue_on_failure=True inside deliver_status_to_laravel)
            # so this except block only trips on catastrophic errors —
            # cancellation, pool exhaustion, queue enqueue failure. Command
            # IS already marked SENT in our DB and published to MQTT, so we
            # don't raise. Full exc_info is required for post-mortem: without
            # it we only see the exception type, no traceback, no way to
            # distinguish a Redis outage from a pool exhaustion.
            logger.warning(
                "Failed to send correlation ACK for command %s: %s",
                cmd_id,
                e,
                exc_info=True,
                extra={"cmd_id": cmd_id},
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

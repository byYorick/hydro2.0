"""CommandBus guard and validation helpers."""

import logging
from typing import Any, Dict, Optional, Tuple

from common.db import create_zone_event, fetch
from common.infra_alerts import send_infra_alert, send_infra_exception_alert
from common.simulation_events import record_simulation_event
from services.resilience_contract import (
    INFRA_COMMAND_CHANNEL_TYPE_VALIDATION_FAILED,
    INFRA_COMMAND_INVALID_CHANNEL_TYPE,
    INFRA_COMMAND_NODE_ZONE_MISMATCH,
    INFRA_COMMAND_NODE_ZONE_VALIDATION_FAILED,
)

from .command_bus_shared import _ACTUATOR_COMMANDS, _SYSTEM_MODE_COMMANDS, COMMAND_VALIDATION_FAILED

logger = logging.getLogger(__name__)


async def safe_create_zone_event(
    command_bus: Any,
    zone_id: int,
    event_type: str,
    payload: Dict[str, Any],
) -> None:
    try:
        await create_zone_event(zone_id, event_type, payload)
    except Exception:
        logger.warning(
            "Zone %s: failed to create %s event",
            zone_id,
            event_type,
            exc_info=True,
        )


async def verify_node_zone_assignment(
    command_bus: Any,
    *,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
) -> bool:
    if not command_bus.enforce_node_zone_assignment:
        return True

    try:
        rows = await fetch(
            """
            SELECT zone_id, status
            FROM nodes
            WHERE uid = $1
            LIMIT 1
            """,
            node_uid,
        )
    except Exception as exc:
        logger.error(
            "Zone %s: failed to verify node-zone assignment for node_uid=%s: %s",
            zone_id,
            node_uid,
            exc,
            exc_info=True,
        )
        await send_infra_exception_alert(
            error=exc,
            code=INFRA_COMMAND_NODE_ZONE_VALIDATION_FAILED,
            alert_type="Command Node-Zone Validation Failed",
            severity="critical",
            zone_id=zone_id,
            service="automation-engine",
            component="command_bus",
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
        )
        return False

    if not rows:
        await _emit_node_zone_mismatch(
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            reason="node_not_found",
            actual_zone_id=None,
        )
        return False

    actual_zone_id = rows[0].get("zone_id")
    if actual_zone_id is None or int(actual_zone_id) != int(zone_id):
        await _emit_node_zone_mismatch(
            zone_id=zone_id,
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
            reason="zone_mismatch",
            actual_zone_id=actual_zone_id,
        )
        return False

    return True


async def _emit_node_zone_mismatch(
    *,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    reason: str,
    actual_zone_id: Optional[int],
) -> None:
    try:
        await create_zone_event(
            zone_id,
            "COMMAND_ZONE_NODE_MISMATCH",
            {
                "reason": reason,
                "expected_zone_id": zone_id,
                "actual_zone_id": actual_zone_id,
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
            },
        )
    except Exception:
        logger.warning("Zone %s: failed to create COMMAND_ZONE_NODE_MISMATCH event", zone_id, exc_info=True)

    if reason == "node_not_found":
        message = f"Команда {cmd} отклонена: node_uid={node_uid} не найден"
        error_type = "NodeNotFound"
    else:
        message = (
            f"Команда {cmd} отклонена: node_uid={node_uid} закреплен за zone_id={actual_zone_id}, "
            f"ожидался zone_id={zone_id}"
        )
        error_type = "NodeZoneMismatch"

    await send_infra_alert(
        code=INFRA_COMMAND_NODE_ZONE_MISMATCH,
        alert_type="Command Node-Zone Mismatch",
        message=message,
        severity="critical",
        zone_id=zone_id,
        service="automation-engine",
        component="command_bus",
        node_uid=node_uid,
        channel=channel,
        cmd=cmd,
        error_type=error_type,
        details={
            "reason": reason,
            "expected_zone_id": zone_id,
            "actual_zone_id": actual_zone_id,
        },
    )


async def resolve_greenhouse_uid_for_zone(command_bus: Any, zone_id: int) -> str:
    """Resolve canonical greenhouse_uid for zone and cache it on command_bus."""
    cached = command_bus._zone_gh_uid_cache.get(zone_id)
    if cached:
        return cached

    fallback_gh_uid = command_bus.gh_uid
    try:
        rows = await fetch(
            """
            SELECT g.uid AS gh_uid
            FROM zones z
            JOIN greenhouses g ON g.id = z.greenhouse_id
            WHERE z.id = $1
            LIMIT 1
            """,
            zone_id,
        )
        if rows:
            resolved = str(rows[0].get("gh_uid") or "").strip()
            if resolved:
                command_bus._zone_gh_uid_cache[zone_id] = resolved
                if fallback_gh_uid and fallback_gh_uid != resolved:
                    logger.warning(
                        "Zone %s: overridden greenhouse_uid from %s to %s for command publish",
                        zone_id,
                        fallback_gh_uid,
                        resolved,
                    )
                return resolved
    except Exception as exc:
        logger.warning(
            "Zone %s: failed to resolve greenhouse_uid from DB, fallback to configured value: %s",
            zone_id,
            exc,
        )

    if fallback_gh_uid:
        return fallback_gh_uid
    raise RuntimeError(f"Unable to resolve greenhouse_uid for zone_id={zone_id}")


async def verify_command_channel_compatibility(
    command_bus: Any,
    *,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
) -> Tuple[bool, Optional[str]]:
    if not command_bus.enforce_command_channel_compatibility:
        return True, None

    normalized_cmd = str(cmd or "").strip().lower()
    normalized_channel = str(channel or "").strip().lower()

    if normalized_cmd in _SYSTEM_MODE_COMMANDS:
        if normalized_channel != "system":
            return False, "sensor_mode_requires_system_channel"
        return True, None

    if normalized_cmd not in _ACTUATOR_COMMANDS:
        return True, None

    if normalized_channel == "system":
        return False, "actuator_command_on_system_channel"

    try:
        rows = await fetch(
            """
            SELECT UPPER(TRIM(COALESCE(nc.type, ''))) AS channel_type
            FROM nodes n
            LEFT JOIN node_channels nc
              ON nc.node_id = n.id
             AND LOWER(TRIM(COALESCE(nc.channel, ''))) = $2
            WHERE n.uid = $1
            LIMIT 1
            """,
            node_uid,
            normalized_channel,
        )
    except Exception as exc:
        logger.error(
            "Zone %s: failed to verify command/channel compatibility node_uid=%s channel=%s cmd=%s: %s",
            zone_id,
            node_uid,
            channel,
            cmd,
            exc,
            exc_info=True,
        )
        await send_infra_exception_alert(
            error=exc,
            code=INFRA_COMMAND_CHANNEL_TYPE_VALIDATION_FAILED,
            alert_type="Command Channel Type Validation Failed",
            severity="critical",
            zone_id=zone_id,
            service="automation-engine",
            component="command_bus",
            node_uid=node_uid,
            channel=channel,
            cmd=cmd,
        )
        return False, "channel_type_validation_failed"

    if not rows:
        return False, "channel_not_found"

    channel_type = str(rows[0].get("channel_type") or "").strip().upper()
    if not channel_type:
        return False, "channel_not_found"
    if channel_type != "ACTUATOR":
        return False, f"channel_type_{channel_type.lower()}"
    return True, None


async def handle_command_channel_compatibility_failure(
    command_bus: Any,
    *,
    zone_id: int,
    node_uid: str,
    channel: str,
    cmd: str,
    error_code: str,
) -> None:
    COMMAND_VALIDATION_FAILED.labels(zone_id=str(zone_id), reason=error_code).inc()
    logger.error(
        "Zone %s: command validation failed - incompatible channel/cmd node_uid=%s channel=%s cmd=%s reason=%s",
        zone_id,
        node_uid,
        channel,
        cmd,
        error_code,
    )
    try:
        await create_zone_event(
            zone_id,
            "COMMAND_VALIDATION_FAILED",
            {
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
                "error": error_code,
                "reason": "channel_command_mismatch",
            },
        )
    except Exception:
        logger.warning("Zone %s: failed to create COMMAND_VALIDATION_FAILED event", zone_id, exc_info=True)

    await record_simulation_event(
        zone_id,
        service="automation-engine",
        stage="command_validate",
        status="validation_failed",
        level="error",
        message="Команда отклонена: несовместимы cmd и тип канала",
        payload={
            "node_uid": node_uid,
            "channel": channel,
            "cmd": cmd,
            "error_code": error_code,
        },
    )
    await send_infra_alert(
        code=INFRA_COMMAND_INVALID_CHANNEL_TYPE,
        alert_type="Command Channel Type Mismatch",
        message=f"Команда {cmd} отклонена: несовместимый тип канала {channel}",
        severity="warning",
        zone_id=zone_id,
        service="automation-engine",
        component="command_bus",
        node_uid=node_uid,
        channel=channel,
        cmd=cmd,
        error_type=error_code,
        details={
            "reason": "channel_command_mismatch",
            "error_code": error_code,
        },
    )


"""Infra alerts: send-failed и node/zone mismatch (fail-closed guard diagnostics)."""

from __future__ import annotations

import logging
from typing import Any

from common.db import create_zone_event
from common.infra_alerts import send_infra_alert

logger = logging.getLogger(__name__)


async def emit_command_send_failed_alert(
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


async def emit_command_node_zone_mismatch_observability(
    *,
    zone_id: int,
    node_uid: str,
    node_zone_id: Any,
    pending_zone_id: Any,
) -> None:
    """Emit zone_event + infra alert для fail-closed node/zone guard rejections."""
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

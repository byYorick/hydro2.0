"""gh_uid / zone_uid / node-zone resolution (fail-closed guards)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from command_service import _get_gh_uid_from_zone_id, _get_zone_uid_from_id
from common.db import fetch
from common.env import get_settings

from .alerts import emit_command_node_zone_mismatch_observability

logger = logging.getLogger(__name__)


async def resolve_effective_gh_uid(zone_id: int, requested_gh_uid: str | None) -> str:
    """Canonical gh_uid по zone_id. Publish работает fail-closed:
    greenhouse_uid из запроса не является authority.
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


async def resolve_zone_uid_for_command_publish(zone_id: int) -> str | None:
    """Единая точка резолва zone segment. При MQTT_ZONE_FORMAT=uid — fail-closed:
    без zone_uid публиковать нельзя.
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


async def require_node_assigned_to_zone(node_uid: str, zone_id: int) -> int:
    """Fail-closed: node_uid должен быть закреплён за zone_id.
    Возвращает numeric ``node_id`` для записи в ``commands``.
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

    node: Any = rows[0]
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
        await emit_command_node_zone_mismatch_observability(
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

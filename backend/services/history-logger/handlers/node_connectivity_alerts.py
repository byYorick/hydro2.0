"""Алерты при потере/восстановлении связи с узлом (LWT, stale timeout)."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from common.alert_publisher import AlertPublisher
from common.alerts import AlertCode, AlertSource
from common.db import fetch

logger = logging.getLogger(__name__)

_publisher = AlertPublisher()

_LWT_REASON = "mqtt_lwt"
_STALE_REASON = "heartbeat_timeout"


def _offline_message(*, node_uid: str, reason: str) -> str:
    if reason == _LWT_REASON:
        return f"Узел {node_uid} потерял связь с MQTT-брокером (LWT offline)."
    return f"Узел {node_uid} не отвечает дольше допустимого таймаута heartbeat."


async def _load_node_row(node_uid: str) -> Mapping[str, Any] | None:
    rows = await fetch(
        """
        SELECT uid, zone_id, hardware_id, type
        FROM nodes
        WHERE uid = $1
        LIMIT 1
        """,
        node_uid,
    )
    if not rows:
        return None
    row = rows[0]
    return row if isinstance(row, Mapping) else None


async def raise_node_offline_alert(*, node_uid: str, reason: str) -> None:
    """Поднимает ``biz_node_offline`` при потере связи с узлом."""
    uid = str(node_uid or "").strip()
    if not uid:
        return

    row = await _load_node_row(uid)
    if row is None:
        logger.debug("[NODE_OFFLINE_ALERT] skip unknown node_uid=%s reason=%s", uid, reason)
        return

    zone_id = row.get("zone_id")
    hardware_id = row.get("hardware_id")
    node_type = row.get("type")
    message = _offline_message(node_uid=uid, reason=reason)
    dedupe_key = _publisher.build_dedupe_key(
        code=AlertCode.BIZ_NODE_OFFLINE.value,
        zone_id=int(zone_id) if zone_id is not None else None,
        parts=(AlertSource.BIZ.value, f"node_uid:{uid}"),
    )

    try:
        await _publisher.raise_active(
            zone_id=int(zone_id) if zone_id is not None else None,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NODE_OFFLINE.value,
            alert_type="Node Offline",
            details={
                "node_uid": uid,
                "hardware_id": hardware_id,
                "node_type": node_type,
                "reason": reason,
                "message": message,
                "dedupe_key": dedupe_key,
            },
            dedupe_key=dedupe_key,
            scoped=True,
            node_uid=uid,
            hardware_id=str(hardware_id) if hardware_id is not None else None,
            severity="error",
        )
        logger.warning(
            "[NODE_OFFLINE_ALERT] raised biz_node_offline node_uid=%s zone_id=%s reason=%s",
            uid,
            zone_id,
            reason,
        )
    except Exception:
        logger.error(
            "[NODE_OFFLINE_ALERT] failed node_uid=%s zone_id=%s reason=%s",
            uid,
            zone_id,
            reason,
            exc_info=True,
        )


async def resolve_node_online_alert(*, node_uid: str, reason: str = "node_online") -> None:
    """Закрывает ``biz_node_offline`` после восстановления связи."""
    uid = str(node_uid or "").strip()
    if not uid:
        return

    row = await _load_node_row(uid)
    if row is None:
        return

    zone_id = row.get("zone_id")
    hardware_id = row.get("hardware_id")
    dedupe_key = _publisher.build_dedupe_key(
        code=AlertCode.BIZ_NODE_OFFLINE.value,
        zone_id=int(zone_id) if zone_id is not None else None,
        parts=(AlertSource.BIZ.value, f"node_uid:{uid}"),
    )

    try:
        await _publisher.resolve(
            zone_id=int(zone_id) if zone_id is not None else None,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NODE_OFFLINE.value,
            alert_type="Node Offline",
            details={
                "node_uid": uid,
                "hardware_id": hardware_id,
                "resolved_reason": reason,
                "dedupe_key": dedupe_key,
            },
            dedupe_key=dedupe_key,
            scoped=True,
            node_uid=uid,
            hardware_id=str(hardware_id) if hardware_id is not None else None,
            severity="error",
        )
        logger.info(
            "[NODE_OFFLINE_ALERT] resolved biz_node_offline node_uid=%s zone_id=%s reason=%s",
            uid,
            zone_id,
            reason,
        )
    except Exception:
        logger.warning(
            "[NODE_OFFLINE_ALERT] resolve failed node_uid=%s zone_id=%s",
            uid,
            zone_id,
            exc_info=True,
        )

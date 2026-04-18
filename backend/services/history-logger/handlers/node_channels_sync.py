"""Идемпотентная синхронизация ``node_channels`` из config_report payload узла.

Вынесено из ``config_report.py`` — 160+ строк SQL-логики + защита protected-ключей
(``pump_calibration`` / ``flow_calibration`` / ``pid*``) от перезаписи узлом.
"""

from __future__ import annotations

import logging
from typing import Any

from common.db import execute

from ._shared import PROTECTED_NODE_CHANNEL_CONFIG_KEYS

logger = logging.getLogger(__name__)


async def sync_node_channels_from_payload(
    node_id: int, node_uid: str, channels_payload: Any, *, allow_prune: bool = False
) -> None:
    """Идемпотентный sync. Protected-ключи от ноды игнорируются (backend-owned).

    ``allow_prune=true`` делает soft-deactivate каналов, не присутствующих в snapshot
    (только при полном channels snapshot).
    """
    if not node_id:
        logger.warning("[CONFIG_REPORT] Cannot sync channels: node_id missing")
        return

    if not isinstance(channels_payload, list):
        logger.warning(
            "[CONFIG_REPORT] channels payload is not a list for node %s: %s",
            node_uid,
            type(channels_payload),
        )
        return

    if len(channels_payload) == 0:
        logger.info(f"[CONFIG_REPORT] channels payload empty for node {node_uid}, skipping sync")
        return

    updated = 0
    skipped = 0
    stripped_protected_keys = 0
    channel_names: list[str] = []
    for channel in channels_payload:
        channel_name, type_value, metric_value, unit_value, config, parse_skipped, stripped = (
            _parse_channel_entry(channel, node_uid)
        )
        if parse_skipped:
            skipped += 1
            continue
        stripped_protected_keys += stripped

        await execute(
            """
            INSERT INTO node_channels (node_id, channel, type, metric, unit, config, last_seen_at, is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW(), TRUE, NOW(), NOW())
            ON CONFLICT (node_id, channel)
            DO UPDATE SET
                type = COALESCE(EXCLUDED.type, node_channels.type),
                metric = COALESCE(EXCLUDED.metric, node_channels.metric),
                unit = COALESCE(EXCLUDED.unit, node_channels.unit),
                -- Preserve local/runtime keys (e.g. pump_calibration) while applying fresh node config.
                config = CASE
                    WHEN EXCLUDED.config IS NULL THEN node_channels.config
                    WHEN node_channels.config IS NULL THEN EXCLUDED.config
                    ELSE node_channels.config || EXCLUDED.config
                END,
                last_seen_at = NOW(),
                is_active = TRUE,
                updated_at = NOW()
            """,
            node_id,
            channel_name,
            type_value,
            metric_value,
            unit_value,
            config,
        )
        channel_names.append(channel_name)
        updated += 1

    await _maybe_prune_stale_channels(
        node_id=node_id,
        node_uid=node_uid,
        channel_names=channel_names,
        allow_prune=allow_prune,
    )

    logger.info(
        "[CONFIG_REPORT] Synced %s channel(s) for node %s, skipped %s, stripped_protected_keys=%s, allow_prune=%s",
        updated,
        node_uid,
        skipped,
        stripped_protected_keys,
        allow_prune,
    )


def _parse_channel_entry(channel: Any, node_uid: str):
    """Parse entry. Возвращает: (name, type, metric, unit, config, skip, stripped_count).

    При ``skip=True`` остальные значения невалидны.
    """
    if not isinstance(channel, dict):
        return None, None, None, None, None, True, 0

    channel_name = channel.get("name") or channel.get("channel")
    if channel_name is None:
        return None, None, None, None, None, True, 0

    channel_name = str(channel_name).strip()
    if not channel_name:
        return None, None, None, None, None, True, 0
    channel_name = channel_name[:255]

    type_value = channel.get("type") or channel.get("channel_type")
    if type_value is not None:
        type_value = str(type_value).strip().upper()
        if not type_value:
            type_value = None

    metric_value = channel.get("metric") or channel.get("metrics")
    if metric_value is not None:
        metric_value = str(metric_value).strip().upper()
        if not metric_value:
            metric_value = None

    unit_value = channel.get("unit")
    if unit_value is not None:
        unit_value = str(unit_value).strip()
        if not unit_value:
            unit_value = None

    raw_config = {
        key: value
        for key, value in channel.items()
        if key not in {"name", "channel", "type", "channel_type", "metric", "metrics", "unit"}
    }
    protected_keys_in_payload = [
        key for key in raw_config.keys() if key in PROTECTED_NODE_CHANNEL_CONFIG_KEYS
    ]
    stripped = len(protected_keys_in_payload)
    if protected_keys_in_payload:
        logger.warning(
            "[CONFIG_REPORT] Ignoring protected channel config keys from node payload: node_uid=%s channel=%s keys=%s",
            node_uid,
            channel_name,
            protected_keys_in_payload,
        )
    config = {
        key: value
        for key, value in raw_config.items()
        if key not in PROTECTED_NODE_CHANNEL_CONFIG_KEYS
    }
    if not config:
        config = None

    return channel_name, type_value, metric_value, unit_value, config, False, stripped


async def _maybe_prune_stale_channels(
    *,
    node_id: int,
    node_uid: str,
    channel_names: list[str],
    allow_prune: bool,
) -> None:
    if allow_prune and channel_names:
        await execute(
            """
            UPDATE node_channels
            SET is_active = FALSE,
                updated_at = NOW()
            WHERE node_id = $1
              AND NOT (channel = ANY($2))
              AND COALESCE(is_active, TRUE) = TRUE
            """,
            node_id,
            list(set(channel_names)),
        )
        logger.info(
            "[CONFIG_REPORT] Soft-deactivated missing channels from config_report full-snapshot: node_uid=%s kept=%s",
            node_uid,
            sorted(list(set(channel_names))),
        )
    elif allow_prune and not channel_names:
        logger.warning(
            "[CONFIG_REPORT] Refused destructive prune: allow_prune=true but no valid channels were parsed for node_uid=%s",
            node_uid,
        )
    else:
        logger.info(
            "[CONFIG_REPORT] Channel prune disabled for node_uid=%s (transport-safe mode)",
            node_uid,
        )

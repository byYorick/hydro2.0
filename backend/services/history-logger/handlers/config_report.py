"""``handle_config_report`` + синхронизация ``node_channels`` + binding completion."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from common.db import execute, fetch
from common.env import get_settings
from common.trace_context import clear_trace_id, inject_trace_id_header
from common.utils.time import utcnow
from metrics import CONFIG_REPORT_ERROR, CONFIG_REPORT_PROCESSED, CONFIG_REPORT_RECEIVED
from utils import _extract_gh_uid, _extract_node_uid, _extract_zone_uid, _parse_json

from ._shared import (
    CONFIG_REPORT_DEFAULT_ALLOW_PRUNE,
    apply_trace_context,
    get_binding_completion_lock,
    log_transient_warning,
    store_pending_config_report,
    to_optional_bool,
)
from .node_channels_sync import sync_node_channels_from_payload

logger = logging.getLogger(__name__)


async def handle_config_report(topic: str, payload: bytes) -> None:
    """Сохраняет NodeConfig в БД + синхронизирует ``node_channels`` + завершает binding."""
    try:
        logger.info("[CONFIG_REPORT] ===== START processing config_report =====")
        logger.info(f"[CONFIG_REPORT] Topic: {topic}, payload length: {len(payload)}")

        data = _parse_json(payload)
        if not data or not isinstance(data, dict):
            logger.warning(f"[CONFIG_REPORT] Invalid JSON in config_report from topic {topic}")
            CONFIG_REPORT_ERROR.labels(node_uid="unknown").inc()
            return

        apply_trace_context(data)

        node_uid = _extract_node_uid(topic)
        if not node_uid:
            logger.warning(f"[CONFIG_REPORT] Could not extract node_uid from topic {topic}")
            CONFIG_REPORT_ERROR.labels(node_uid="unknown").inc()
            return

        gh_uid = _extract_gh_uid(topic)
        zone_uid = _extract_zone_uid(topic)
        is_temp_topic = gh_uid == "gh-temp" and zone_uid == "zn-temp"

        node, node_uid, node_id = await _load_node_row_or_buffer(
            topic=topic,
            payload=payload,
            node_uid=node_uid,
            data=data,
            is_temp_topic=is_temp_topic,
        )
        if node is None:
            return

        CONFIG_REPORT_RECEIVED.inc()
        data = _normalize_config_report_channels_for_storage(data)

        await execute(
            """
            UPDATE nodes
            SET config = $1,
                updated_at = NOW()
            WHERE id = $2
            """,
            data,
            node_id,
        )

        try:
            await _complete_sensor_calibrations_after_config_report(int(node_id), data)
        except Exception as sync_sensor_err:
            logger.warning(
                "[CONFIG_REPORT] Failed to finalize sensor calibrations for node %s: %s",
                node_uid,
                sync_sensor_err,
                exc_info=True,
            )

        channels_payload = data.get("channels")
        if channels_payload is not None:
            try:
                allow_prune = CONFIG_REPORT_DEFAULT_ALLOW_PRUNE
                for key in ("channels_replace", "channels_full_snapshot", "full_snapshot"):
                    parsed = to_optional_bool(data.get(key))
                    if parsed is not None:
                        allow_prune = parsed
                        break
                await sync_node_channels_from_payload(
                    node_id, node_uid, channels_payload, allow_prune=allow_prune
                )
            except Exception as sync_err:
                logger.warning(
                    "[CONFIG_REPORT] Failed to sync channels for node %s: %s",
                    node_uid,
                    sync_err,
                    exc_info=True,
                )

        await _complete_binding_after_config_report(
            node,
            node_uid,
            is_temp_topic=is_temp_topic,
            topic_gh_uid=gh_uid,
            topic_zone_uid=zone_uid,
        )

        CONFIG_REPORT_PROCESSED.inc()
        logger.info(f"[CONFIG_REPORT] Config stored for node {node_uid}")
    except Exception as e:
        logger.error(
            f"[CONFIG_REPORT] Unexpected error processing config_report: {e}",
            exc_info=True,
        )
        CONFIG_REPORT_ERROR.labels(node_uid="unknown").inc()
    finally:
        clear_trace_id()


async def _load_node_row_or_buffer(
    *,
    topic: str,
    payload: bytes,
    node_uid: str,
    data: Dict[str, Any],
    is_temp_topic: bool,
) -> tuple[Optional[Dict[str, Any]], Optional[str], Optional[int]]:
    """Возвращает (node, resolved_node_uid, node_id). ``None`` если config буферизован."""
    if is_temp_topic:
        hardware_id = node_uid
        node_rows = await fetch(
            """
            SELECT id,
                   uid,
                   lifecycle_state,
                   zone_id,
                   pending_zone_id
            FROM nodes
            WHERE hardware_id = $1
            """,
            hardware_id,
        )
        if not node_rows:
            logger.debug(
                "[CONFIG_REPORT] Temp config_report buffered by registration flow: hardware_id=%s",
                hardware_id,
            )
            CONFIG_REPORT_ERROR.labels(node_uid="unknown").inc()
            await store_pending_config_report(hardware_id, topic, payload)
            logger.debug(
                "[CONFIG_REPORT] Buffered config_report until node registration: hardware_id=%s",
                hardware_id,
            )
            return None, None, None
        node = node_rows[0]
        resolved_uid = node.get("uid")
        node_id = node.get("id")
        if resolved_uid and isinstance(data, dict):
            data["node_id"] = resolved_uid
        logger.info(
            "[CONFIG_REPORT] Mapped temp config_report: hardware_id=%s -> node_uid=%s",
            hardware_id,
            resolved_uid,
        )
        return node, resolved_uid, node_id

    node_rows = await fetch(
        """
        SELECT id,
               uid,
               lifecycle_state,
               zone_id,
               pending_zone_id
        FROM nodes
        WHERE uid = $1
        """,
        node_uid,
    )
    if not node_rows:
        log_transient_warning(
            "config_report_node_missing",
            node_uid,
            f"[CONFIG_REPORT] Node {node_uid} not found in database, skipping config_report",
        )
        CONFIG_REPORT_ERROR.labels(node_uid=node_uid).inc()
        return None, None, None
    node = node_rows[0]
    return node, node_uid, node.get("id")


def _extract_persisted_sensor_calibration_types(config: Dict[str, Any]) -> set[str]:
    calibration = config.get("calibration")
    if not isinstance(calibration, dict):
        return set()

    persisted: set[str] = set()
    for sensor_type in ("ph", "ec"):
        if isinstance(calibration.get(sensor_type), dict) and calibration.get(sensor_type):
            persisted.add(sensor_type)
    return persisted


async def _complete_sensor_calibrations_after_config_report(
    node_id: int, config: Dict[str, Any]
) -> None:
    persisted_sensor_types = _extract_persisted_sensor_calibration_types(config)
    if not persisted_sensor_types:
        return

    rows = await fetch(
        """
        SELECT sc.id, sc.sensor_type, sc.meta
        FROM sensor_calibrations sc
        JOIN node_channels nc ON nc.id = sc.node_channel_id
        WHERE nc.node_id = $1
          AND sc.status = 'point_2_pending'
          AND sc.point_2_result = 'DONE'
        """,
        node_id,
    )
    if not rows:
        return

    completed_ids: list[int] = []
    persisted_at = utcnow().isoformat()
    for row in rows:
        sensor_type = str(row.get("sensor_type") or "").strip().lower()
        if sensor_type not in persisted_sensor_types:
            continue

        meta = row.get("meta") or {}
        if not isinstance(meta, dict):
            meta = {}
        meta["awaiting_config_report"] = False
        meta["persisted_via_config_report"] = True
        meta["persisted_at"] = persisted_at

        await execute(
            """
            UPDATE sensor_calibrations
            SET status = 'completed',
                completed_at = NOW(),
                meta = $2,
                updated_at = NOW()
            WHERE id = $1
              AND status = 'point_2_pending'
              AND point_2_result = 'DONE'
            """,
            row["id"],
            meta,
        )
        completed_ids.append(int(row["id"]))

    if completed_ids:
        logger.info(
            "[CONFIG_REPORT] Finalized sensor calibration(s) after persisted config report: node_id=%s ids=%s sensors=%s",
            node_id,
            completed_ids,
            sorted(list(persisted_sensor_types)),
        )


def _normalize_config_report_channels_for_storage(config: Dict[str, Any]) -> Dict[str, Any]:
    channels = config.get("channels")
    if not isinstance(channels, list):
        return config

    normalized_channels: list[Any] = []
    mutated = False
    relay_required_types = {"RELAY", "VALVE", "FAN", "HEATER"}

    for channel in channels:
        if not isinstance(channel, dict):
            normalized_channels.append(channel)
            continue

        normalized_channel = dict(channel)
        channel_type = str(normalized_channel.get("type") or "").strip().upper()
        actuator_type = str(normalized_channel.get("actuator_type") or "").strip().upper()

        if channel_type == "ACTUATOR" and actuator_type in relay_required_types:
            relay_type = str(normalized_channel.get("relay_type") or "").strip().upper()
            if relay_type not in {"NC", "NO"}:
                normalized_channel["relay_type"] = "NO"
                mutated = True

        normalized_channels.append(normalized_channel)

    if not mutated:
        return config

    normalized_config = dict(config)
    normalized_config["channels"] = normalized_channels
    return normalized_config


async def _complete_binding_after_config_report(
    node: Dict[str, Any],
    node_uid: str,
    *,
    is_temp_topic: bool = False,
    topic_gh_uid: Optional[str] = None,
    topic_zone_uid: Optional[str] = None,
) -> None:
    node_id = node.get("id")
    if not node_id:
        return

    lock = await get_binding_completion_lock(int(node_id))
    async with lock:
        if is_temp_topic:
            return

        s = get_settings()
        laravel_url = s.laravel_api_url if hasattr(s, "laravel_api_url") else None
        ingest_token = (
            s.history_logger_api_token
            if hasattr(s, "history_logger_api_token") and s.history_logger_api_token
            else (
                s.ingest_token
                if hasattr(s, "ingest_token") and s.ingest_token
                else None
            )
        )

        if not laravel_url:
            logger.error(
                "[CONFIG_REPORT] Laravel API URL not configured, cannot update node lifecycle"
            )
            return

        headers = inject_trace_id_header(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        if ingest_token:
            headers["Authorization"] = f"Bearer {ingest_token}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                observe_response = await client.post(
                    f"{laravel_url}/api/python/nodes/config-report-observed",
                    headers=headers,
                    json={
                        "node_id": int(node_id),
                        "node_uid": node_uid,
                        "gh_uid": topic_gh_uid,
                        "zone_uid": topic_zone_uid,
                        "is_temp_topic": bool(is_temp_topic),
                    },
                )

                if observe_response.status_code != 200:
                    logger.warning(
                        "[CONFIG_REPORT] Failed to notify Laravel about observed config_report for node %s (id=%s): %s %s",
                        node_uid,
                        node_id,
                        observe_response.status_code,
                        observe_response.text,
                    )
        except Exception as e:
            logger.error(
                "[CONFIG_REPORT] Error while notifying Laravel about config_report for node %s: %s",
                node_uid,
                e,
                exc_info=True,
            )


__all__ = ["handle_config_report", "sync_node_channels_from_payload"]

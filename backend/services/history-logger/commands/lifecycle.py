"""DB state machine для ``commands``: ensure QUEUED row перед publish + post-publish status check."""

from __future__ import annotations

import logging
from typing import Optional

import asyncpg
from fastapi import HTTPException

from common.db import execute, fetch

from .constants import (
    FINAL_COMMAND_STATUSES,
    NON_REPUBLISHABLE_COMMAND_STATUSES,
    POST_PUBLISH_ALLOWED_STATUSES,
    REPUBLISH_ALLOWED_STATUSES,
)
from .validation import normalize_command_status, normalize_params_for_idempotency

logger = logging.getLogger(__name__)


async def ensure_post_publish_status_persisted(cmd_id: str) -> None:
    """Проверяет, что строка ``commands`` в post-publish валидном состоянии.

    Raises ``RuntimeError`` с ``(reason, cmd_id, observed_status)`` контекстом,
    чтобы caller-side ``logger.error(..., exc_info=True)`` захватил actionable
    данные (раньше бросали bare ``post_publish_status_not_transitioned`` без cmd_id).
    """
    rows = await fetch("SELECT status FROM commands WHERE cmd_id = $1", cmd_id)
    if not rows:
        raise RuntimeError(f"command_not_found_after_publish:cmd_id={cmd_id}")
    status = normalize_command_status(rows[0].get("status"))
    if status not in POST_PUBLISH_ALLOWED_STATUSES:
        raise RuntimeError(
            f"invalid_post_publish_status:cmd_id={cmd_id} status={status!r} "
            f"allowed={sorted(POST_PUBLISH_ALLOWED_STATUSES)}"
        )
    if status == "QUEUED":
        raise RuntimeError(
            f"post_publish_status_not_transitioned:cmd_id={cmd_id} "
            f"status still QUEUED after publish — MQTT publish succeeded but "
            f"mark_command_sent failed to flip to SENT before this check"
        )


async def ensure_command_for_publish(
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
    """Гарантирует fail-closed подготовку команды в БД перед MQTT publish.

    Возвращает:
    * ``None`` — строка QUEUED создана (или существующая в QUEUED/SEND_FAILED) — caller publish-ит.
    * ``dict`` (skip_response) — уже terminal/ACK, publish пропускается.

    Бросает HTTPException:
    * 409 — cmd_id коллидирует с другой командой (params/zone/node/channel/cmd)
    * 503 — fetch/insert DB error
    """
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

        collisions = _detect_collisions(existing, zone_id, node_id, channel, cmd_name, params)
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

        cmd_status = normalize_command_status(existing.get("status"))
        if cmd_status in NON_REPUBLISHABLE_COMMAND_STATUSES:
            status_kind = "final" if cmd_status in FINAL_COMMAND_STATUSES else "in_progress"
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

        if cmd_status not in REPUBLISH_ALLOWED_STATUSES:
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
        # генерируют префикс ``hl-`` для cmd_id — только тестовые моки. Prod случай
        # требует полный stack trace для root cause.
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
            return await ensure_command_for_publish(
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


def _detect_collisions(
    existing: dict,
    zone_id: int,
    node_id: int,
    channel: str,
    cmd_name: str,
    params: Optional[dict],
) -> list[str]:
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

    existing_params = normalize_params_for_idempotency(existing.get("params"))
    requested_params = normalize_params_for_idempotency(params)
    if existing_params != requested_params:
        collisions.append("params")

    return collisions

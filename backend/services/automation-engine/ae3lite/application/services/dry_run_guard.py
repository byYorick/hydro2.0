"""Проверка сухого хода перед поливом и дозированием.

Вызывает ``common.pump_safety.check_dry_run``. Отказ или исключение
не дают опубликовать команду включения.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from ae3lite.domain.errors import CommandPublishError

logger = logging.getLogger(__name__)


def command_needs_dry_run(
    *,
    cmd: str,
    channel: str,
    params: Mapping[str, Any] | None,
    stage: str,
) -> bool:
    command = str(cmd or "").strip().lower()
    if command == "dose":
        return True
    stage_text = str(stage or "").lower()
    if "irrig" not in stage_text:
        return False
    if command == "run_pump":
        return True
    if command != "set_relay" or "pump" not in str(channel or "").lower():
        return False
    payload = params if isinstance(params, Mapping) else {}
    state = payload.get("state")
    if state is True or state == 1:
        return True
    return str(state or "").strip().lower() in {"true", "1", "on"}


async def guard_pump_start(
    *,
    zone_id: int,
    cmd: str,
    channel: str,
    params: Mapping[str, Any] | None,
    stage: str,
) -> None:
    if not command_needs_dry_run(cmd=cmd, channel=channel, params=params, stage=stage):
        return
    from common.alerts import AlertCode, AlertSource, create_alert
    from common.pump_safety import check_dry_run

    try:
        safe, error = await check_dry_run(int(zone_id))
    except Exception as exc:
        logger.warning(
            "AE3 dry-run check failed zone_id=%s cmd=%s channel=%s",
            zone_id,
            cmd,
            channel,
            exc_info=True,
        )
        try:
            await create_alert(
                zone_id=int(zone_id),
                source=AlertSource.BIZ.value,
                code=AlertCode.BIZ_DRY_RUN.value,
                type="Dry run check failed",
                details={"cmd": cmd, "channel": channel, "error": str(exc)},
            )
        except Exception:
            logger.warning("AE3 не смог записать alert сухого хода zone_id=%s", zone_id, exc_info=True)
        raise CommandPublishError("dry_run_check_failed") from exc
    if not safe:
        raise CommandPublishError(str(error or "dry_run"))

"""Shared records and immutable policy values for CycleStartPlanner."""

from __future__ import annotations

import logging

_logger = logging.getLogger('ae3lite.domain.services.cycle_start_planner')


def _schedule_dli_sensor_alert(zone_id: int, local_date: str) -> None:
    """Один biz-алерт на зону за местные сутки. GET суток сюда не заходит."""
    try:
        import asyncio

        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _send() -> None:
        from common.biz_alerts import send_biz_alert

        await send_biz_alert(
            code="dli_sensor_unavailable",
            message="Нет ряда PPFD для потолка DLI. Свет не гасится.",
            zone_id=int(zone_id),
            alert_type="DLI sensor unavailable",
            severity="warning",
            dedupe_key=f"dli_sensor_unavailable:zone:{int(zone_id)}:day:{local_date}",
            details={"local_date": local_date},
        )

    loop.create_task(_send())

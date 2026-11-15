"""climate tick command wait: explicit dependencies and invocation data."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable

from ae3lite.greenhouse_climate.climate_tick_records import _GreenhouseLeaseStop


@dataclass(frozen=True)
class ClimateTickCommandWaitPorts:
    lease_lost_status: Callable[..., Any]
    terminal_statuses: Callable[..., Any]
    fetch: Callable[..., Any]
    logger: Callable[..., Any]


class ClimateTickCommandWait:
    def __init__(self, ports: ClimateTickCommandWaitPorts) -> None:
        self._ports = ports

    async def wait_command_terminal(
        self,
        cmd_id: str,
        *,
        timeout_sec: float,
        poll_sec: float,
        lease_renew: Any | None,
        renew_interval_sec: float | None,
    ) -> str:
        """Ждёт terminal текущей команды.

        ``lease_renew``:
        - ``False`` — подтверждённая потеря владельца, немедленный ``LEASE_LOST``;
        - исключение внутри бюджета — текущую команду не отменяет;
        - ``_GreenhouseLeaseStop`` или ошибка сверх бюджета — ``LEASE_LOST``.
        Голый ``CancelledError`` не поглощается.
        """
        deadline = time.monotonic() + max(0.1, float(timeout_sec))
        next_renew = time.monotonic()
        interval = (
            max(0.0, float(renew_interval_sec)) if renew_interval_sec is not None else max(10.0, float(poll_sec) * 5)
        )
        while True:
            if lease_renew is not None and time.monotonic() >= next_renew:
                try:
                    renewed = await lease_renew()
                except asyncio.CancelledError:
                    raise
                except _GreenhouseLeaseStop:
                    return self._ports.lease_lost_status()
                except Exception:
                    self._ports.logger().warning(
                        "greenhouse_climate_tick lease renew unclassified failure cmd_id=%s",
                        cmd_id,
                        exc_info=True,
                    )
                    return self._ports.lease_lost_status()
                if renewed is False:
                    return self._ports.lease_lost_status()
                next_renew = time.monotonic() + interval
            rows = await self._ports.fetch(
                "SELECT status FROM commands WHERE cmd_id = $1 LIMIT 1",
                cmd_id,
            )
            if rows:
                status = str(rows[0].get("status") or "").strip().upper()
                if status in self._ports.terminal_statuses():
                    return status
            if time.monotonic() >= deadline:
                return "TIMEOUT"
            await asyncio.sleep(max(0.1, float(poll_sec)))

"""GetZoneAutomationStateUseCase time values: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ZoneStateTimeValuesPorts:
    pass


class ZoneStateTimeValues:
    def __init__(self, ports: ZoneStateTimeValuesPorts) -> None:
        self._ports = ports

    def iso_or_none(self, value: Any) -> str | None:
        if isinstance(value, datetime):
            return value.isoformat()
        return None

    def now(self) -> Any:
        from common.utils.time import utcnow_naive

        return utcnow_naive()

    def normalize_utc_naive(self, value: Any) -> Any:
        if not isinstance(value, datetime):
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value

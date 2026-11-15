"""compat ingress values: explicit dependencies and invocation data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompatIngressValuesPorts:
    pass


class CompatIngressValues:
    def __init__(self, ports: CompatIngressValuesPorts) -> None:
        self._ports = ports

    def optional_int(self, value: Any) -> int | None:
        return int(value) if value is not None else None

    def normalized_status(self, value: Any) -> str | None:
        normalized = str(value or "").strip().lower()
        return normalized or None

    def error_extra(self, details: Any, **overrides: Any) -> dict[str, Any]:
        """Merge exception details with path/body overrides into one kwargs dict.

        Overrides win over ``details`` so callers can safely do
        ``api_error_detail(code, status_code=..., **_error_extra(details, zone_id=zone_id))``.
        Passing ``zone_id=zone_id, **details`` separately raises ``KeyError('zone_id')``
        under Python 3.11+ (DICT_MERGE on duplicate keyword keys).
        """
        payload = dict(details if isinstance(details, dict) else {})
        payload.update(overrides)
        return payload

    def log_route_info(self, logger: Any, message: str, **extra: object) -> None:
        info = getattr(logger, "info", None)
        if callable(info):
            info(message, extra=extra)

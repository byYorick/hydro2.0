"""Config loader exceptions.

Kept in a separate module to avoid circular imports between loader, schemas,
and handler code that may want to catch these.
"""

from __future__ import annotations

from typing import Any


class ConfigLoaderError(Exception):
    """Base class for config loader failures."""


class ConfigValidationError(ConfigLoaderError):
    """Pydantic validation of a config payload failed.

    Carries the structured list of errors (Pydantic's `e.errors()`) so that
    callers can render them to logs / events / operator UI without having to
    re-parse the original `ValidationError` message.
    """

    def __init__(
        self,
        zone_id: int | None,
        namespace: str,
        errors: list[dict[str, Any]],
    ) -> None:
        self.zone_id = zone_id
        self.namespace = namespace
        self.errors = errors
        message = (
            f"config validation failed"
            f" (zone_id={zone_id}, namespace={namespace}, "
            f"violations={len(errors)})"
        )
        super().__init__(message)

    def __repr__(self) -> str:
        return (
            f"ConfigValidationError(zone_id={self.zone_id}, "
            f"namespace={self.namespace!r}, violations={len(self.errors)})"
        )

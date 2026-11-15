"""Typed records shared by the component boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OfflineFailure:
    code: str
    message: str
    details: dict[str, Any]

"""Канонический контракт versioned runtime events AE3."""

from __future__ import annotations

from typing import Any, Mapping


AE3_RUNTIME_EVENT_SCHEMA_VERSION = 2


def with_runtime_event_contract(payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    result = dict(payload or {})
    result.setdefault("event_schema_version", AE3_RUNTIME_EVENT_SCHEMA_VERSION)
    return result

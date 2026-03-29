"""
Canonical publisher for alert lifecycle producers.

Все Python-сервисы публикуют только intent:
- raise_active
- resolve

Фактическим owner lifecycle остаётся Laravel AlertService.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional, Sequence

from .alert_queue import send_alert_to_laravel

logger = logging.getLogger(__name__)


class AlertPublisher:
    """Thin producer-side adapter over Laravel ingest contract."""

    def __init__(self, *, default_source: Optional[str] = None) -> None:
        self._default_source = self._normalize_string(default_source)

    async def raise_active(
        self,
        *,
        zone_id: Optional[int],
        source: Optional[str],
        code: str,
        alert_type: str,
        details: Optional[Mapping[str, Any]] = None,
        dedupe_key: Optional[str] = None,
        scoped: bool = False,
        node_uid: Optional[str] = None,
        hardware_id: Optional[str] = None,
        severity: Optional[str] = None,
        ts_device: Optional[str] = None,
    ) -> bool:
        payload_details = self._prepare_details(
            details=details,
            code=code,
            zone_id=zone_id,
            dedupe_key=dedupe_key,
            scoped=scoped,
        )

        return await send_alert_to_laravel(
            zone_id=zone_id,
            source=self._resolve_source(source),
            code=code,
            type=alert_type,
            status="ACTIVE",
            details=payload_details,
            node_uid=node_uid,
            hardware_id=hardware_id,
            severity=severity,
            ts_device=ts_device,
        )

    async def resolve(
        self,
        *,
        zone_id: Optional[int],
        source: Optional[str],
        code: str,
        alert_type: str,
        details: Optional[Mapping[str, Any]] = None,
        dedupe_key: Optional[str] = None,
        scoped: bool = False,
        node_uid: Optional[str] = None,
        hardware_id: Optional[str] = None,
        severity: Optional[str] = None,
        ts_device: Optional[str] = None,
    ) -> bool:
        payload_details = self._prepare_details(
            details=details,
            code=code,
            zone_id=zone_id,
            dedupe_key=dedupe_key,
            scoped=scoped,
        )

        return await send_alert_to_laravel(
            zone_id=zone_id,
            source=self._resolve_source(source),
            code=code,
            type=alert_type,
            status="RESOLVED",
            details=payload_details,
            node_uid=node_uid,
            hardware_id=hardware_id,
            severity=severity,
            ts_device=ts_device,
        )

    def build_dedupe_key(
        self,
        *,
        code: str,
        zone_id: Optional[int],
        parts: Sequence[Any],
    ) -> str:
        normalized_parts = [self._normalize_part(item) for item in parts if self._normalize_part(item) is not None]
        base_parts = [self._resolve_source(None) or "unknown", str(code or "").strip() or "unknown_alert", f"zone:{zone_id if zone_id is not None else 'global'}"]
        return "|".join([*base_parts, *normalized_parts])

    def _prepare_details(
        self,
        *,
        details: Optional[Mapping[str, Any]],
        code: str,
        zone_id: Optional[int],
        dedupe_key: Optional[str],
        scoped: bool,
    ) -> dict[str, Any]:
        payload_details = dict(details) if isinstance(details, Mapping) else {}
        resolved_dedupe_key = self._normalize_string(dedupe_key) or self._normalize_string(payload_details.get("dedupe_key"))
        if scoped and not resolved_dedupe_key:
            raise ValueError(f"Scoped alert '{code}' must define dedupe_key")
        if resolved_dedupe_key:
            payload_details["dedupe_key"] = resolved_dedupe_key
        elif zone_id is not None:
            payload_details.setdefault("dedupe_key", self.build_dedupe_key(code=code, zone_id=zone_id, parts=()))
        return payload_details

    def _resolve_source(self, source: Optional[str]) -> str:
        resolved = self._normalize_string(source) or self._default_source or "biz"
        return resolved

    def _normalize_part(self, value: Any) -> Optional[str]:
        normalized = self._normalize_string(value)
        if normalized is None:
            return None
        return normalized.replace("|", "_")

    def _normalize_string(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

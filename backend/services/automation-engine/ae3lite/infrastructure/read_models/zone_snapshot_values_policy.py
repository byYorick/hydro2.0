"""PgZoneSnapshotReadModel values policy: explicit collaborators and invocation context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional

from .effective_targets_sql_utils import (
    merge_recursive,
)


@dataclass(frozen=True)
class ZoneSnapshotValuesPolicyPorts:
    is_recipe_phase_chemical_target_parameter: Callable[..., Any]


class ZoneSnapshotValuesPolicy:
    def __init__(self, ports: ZoneSnapshotValuesPolicyPorts) -> None:
        self._ports = ports

    @staticmethod
    def normalize_timestamp(value: Any) -> Any:
        if not isinstance(value, datetime):
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value

    @staticmethod
    def as_mapping(value: Any) -> Optional[Dict[str, Any]]:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                value = json.loads(text)
            except (TypeError, ValueError):
                return None
        if isinstance(value, Mapping):
            return dict(value)
        return None

    def normalize_override_rows(self, rows: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            parameter = str(row.get("parameter") or "").strip()
            if not parameter:
                continue
            if self._ports.is_recipe_phase_chemical_target_parameter(parameter):
                continue
            normalized.append(
                {
                    "parameter": parameter,
                    "value_type": str(row.get("value_type") or "").strip().lower(),
                    "value": self.extract_override_value(row),
                }
            )
        return normalized

    def extract_override_value(self, row: Mapping[str, Any]) -> Any:
        value_type = str(row.get("value_type") or "").strip().lower()
        value = row.get("value")
        if value_type in {"integer", "int"}:
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return value
        if value_type in {"decimal", "float", "numeric"}:
            return self.to_float(value)
        if value_type == "boolean":
            normalized = str(value or "").strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        if value_type == "json" and isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    def to_int(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def to_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def set_nested_value(self, *, payload: Dict[str, Any], dotted_key: str, value: Any) -> None:
        segments = [str(item).strip() for item in dotted_key.split(".") if str(item).strip()]
        if not segments:
            return

        current = payload
        for segment in segments[:-1]:
            existing = current.get(segment)
            if not isinstance(existing, dict):
                existing = {}
                current[segment] = existing
            current = existing
        current[segments[-1]] = value

    def apply_overrides(
        self,
        *,
        payload: Dict[str, Any],
        override_rows: List[Mapping[str, Any]],
        prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        merged = merge_recursive({}, payload)
        for row in override_rows:
            parameter = str(row.get("parameter") or "").strip()
            if prefix:
                if not parameter.lower().startswith(prefix.lower()):
                    continue
                parameter = parameter[len(prefix) :]
            if not parameter:
                continue
            if self._ports.is_recipe_phase_chemical_target_parameter(parameter):
                continue
            self.set_nested_value(payload=merged, dotted_key=parameter, value=row.get("value"))
        return merged

    @staticmethod
    def component_gains_from_source(source, *, as_mapping_fn=None):
        if as_mapping_fn is None:
            as_mapping_fn = ZoneSnapshotValuesPolicy.as_mapping
        if "ec_component_gains" in source:
            copied = as_mapping_fn(source.get("ec_component_gains"))
            if copied is not None:
                return copied
        meta = as_mapping_fn(source.get("meta"))
        if meta is not None and "ec_component_gains" in meta:
            return as_mapping_fn(meta.get("ec_component_gains"))
        return None

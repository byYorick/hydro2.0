"""StageRuntimeConfig validation: explicit collaborators and invocation context."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ae3lite.application.services.stage_config_shared import _MISSING_CONFIG
from ae3lite.domain.errors import ErrorCodes, TaskExecutionError


@dataclass(frozen=True)
class StageConfigValidationPorts:
    pass


class StageConfigValidation:
    def __init__(self, ports: StageConfigValidationPorts) -> None:
        self._ports = ports

    @staticmethod
    def mapping_value(mapping: Any, key: str) -> Any:
        if isinstance(mapping, Mapping):
            if key not in mapping:
                return _MISSING_CONFIG
            return mapping[key]
        if mapping is None or not hasattr(mapping, key):
            return _MISSING_CONFIG
        return getattr(mapping, key)

    @staticmethod
    def mapping_view(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping):
            return value
        if value is not None and hasattr(value, "model_dump"):
            dumped = value.model_dump(mode="python")
            if isinstance(dumped, Mapping):
                return dumped
        return {}

    def required_config_int(
        self,
        *,
        field_name: str,
        candidates: Sequence[tuple[str, Any]],
        minimum: int,
        error_code: str = ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
    ) -> int:
        for source_name, raw in candidates:
            if raw is _MISSING_CONFIG:
                continue
            if raw is None or isinstance(raw, bool):
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}",
                )
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}",
                ) from None
            if value < minimum:
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}: требуется >= {minimum}",
                )
            return value

        raise TaskExecutionError(
            error_code,
            f"Отсутствует обязательный параметр {field_name}",
        )

    def required_config_float(
        self,
        *,
        field_name: str,
        candidates: Sequence[tuple[str, Any]],
        minimum: float,
        error_code: str = ErrorCodes.ZONE_CORRECTION_CONFIG_MISSING_CRITICAL,
    ) -> float:
        for source_name, raw in candidates:
            if raw is _MISSING_CONFIG:
                continue
            if raw is None or isinstance(raw, bool):
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}",
                )
            try:
                value = float(raw)
            except (TypeError, ValueError):
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}",
                ) from None
            if not math.isfinite(value) or value < minimum:
                raise TaskExecutionError(
                    error_code,
                    f"Некорректное значение {field_name} в {source_name}: требуется >= {minimum}",
                )
            return value

        raise TaskExecutionError(
            error_code,
            f"Отсутствует обязательный параметр {field_name}",
        )

    def required_correction_int(
        self,
        *,
        correction_cfg: Mapping[str, Any],
        key: str,
        minimum: int = 1,
    ) -> int:
        return self.required_config_int(
            field_name=f"correction.{key}",
            candidates=((f"correction.{key}", self.mapping_value(correction_cfg, key)),),
            minimum=minimum,
        )

    def coerce_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

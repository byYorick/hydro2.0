"""PgZoneSnapshotReadModel execution: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping

from ae3lite.domain.errors import ErrorCodes, SnapshotBuildError

from .effective_targets_sql_utils import (
    clean_null_values,
    merge_recursive,
)


@dataclass(frozen=True)
class ZoneSnapshotExecutionPorts:
    apply_overrides: Callable[..., Any]


class ZoneSnapshotExecution:
    def __init__(self, ports: ZoneSnapshotExecutionPorts) -> None:
        self._ports = ports

    def resolve_diagnostics_execution(
        self,
        *,
        zone_row: Mapping[str, Any],
        override_rows: List[Mapping[str, Any]],
        profile_row: Mapping[str, Any],
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        phase_extensions = zone_row.get("phase_extensions")
        if isinstance(phase_extensions, Mapping):
            phase_targets = phase_extensions.get("targets")
            diagnostics = phase_targets.get("diagnostics") if isinstance(phase_targets, Mapping) else None
            execution = diagnostics.get("execution") if isinstance(diagnostics, Mapping) else None
            if isinstance(execution, Mapping):
                result = merge_recursive(result, dict(execution))

        result = self._ports.apply_overrides(
            payload=result,
            override_rows=override_rows,
            prefix="diagnostics.execution.",
        )

        profile_execution = self.resolve_profile_execution(profile_row)
        if profile_execution:
            result = merge_recursive(result, profile_execution)
        return clean_null_values(result)

    def resolve_profile_execution(self, profile_row: Mapping[str, Any]) -> Dict[str, Any]:
        command_plans = profile_row.get("command_plans")
        plans = command_plans.get("plans") if isinstance(command_plans, Mapping) else None
        diagnostics_plan = plans.get("diagnostics") if isinstance(plans, Mapping) else None
        subsystems = profile_row.get("subsystems")
        diagnostics = subsystems.get("diagnostics") if isinstance(subsystems, Mapping) else None
        subsystem_execution = diagnostics.get("execution") if isinstance(diagnostics, Mapping) else None
        plan_execution = diagnostics_plan.get("execution") if isinstance(diagnostics_plan, Mapping) else None
        return self.merge_execution_sources(
            subsystem_execution if isinstance(subsystem_execution, Mapping) else {},
            plan_execution if isinstance(plan_execution, Mapping) else {},
            path="diagnostics.execution",
        )

    def normalize_two_tank_execution_contract(self, execution: Dict[str, Any]) -> None:
        """Удаляет legacy top-level поля из two_tank execution contract прямо в исходном объекте."""
        execution.pop("startup", None)
        execution.pop("required_node_types", None)

    def merge_execution_sources(
        self,
        left: Mapping[str, Any],
        right: Mapping[str, Any],
        *,
        path: str,
    ) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(left)
        for key, right_value in right.items():
            current_path = f"{path}.{key}"
            if key not in merged:
                merged[key] = right_value
                continue
            left_value = merged[key]
            if isinstance(left_value, Mapping) and isinstance(right_value, Mapping):
                merged[key] = self.merge_execution_sources(left_value, right_value, path=current_path)
                continue
            if left_value != right_value:
                raise SnapshotBuildError(
                    f"Конфликтующее значение для {current_path}",
                    code=ErrorCodes.AE3_SNAPSHOT_CONFLICTING_CONFIG_VALUES,
                )
        return merged

"""PgZoneSnapshotReadModel targets: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping

from .effective_targets_sql_utils import (
    build_base_targets,
    clean_null_values,
    merge_recursive,
    merge_runtime_profile,
)


@dataclass(frozen=True)
class ZoneSnapshotTargetsPorts:
    apply_overrides: Callable[..., Any]


class ZoneSnapshotTargets:
    def __init__(self, ports: ZoneSnapshotTargetsPorts) -> None:
        self._ports = ports

    def build_targets(
        self,
        *,
        zone_row: Mapping[str, Any],
        override_rows: List[Mapping[str, Any]],
        profile_row: Mapping[str, Any],
    ) -> Dict[str, Any]:
        targets = self.build_phase_targets(zone_row=zone_row)
        targets = self._ports.apply_overrides(payload=targets, override_rows=override_rows)
        targets = merge_runtime_profile(
            targets,
            {
                "mode": profile_row.get("mode"),
                "updated_at": profile_row.get("updated_at"),
                "subsystems": profile_row.get("subsystems"),
            },
        )
        targets = self.merge_diagnostics_runtime_targets(targets=targets, profile_row=profile_row)
        return clean_null_values(targets)

    def build_phase_targets(
        self,
        *,
        zone_row: Mapping[str, Any],
    ) -> Dict[str, Any]:
        targets = build_base_targets(dict(zone_row))

        phase_extensions = zone_row.get("phase_extensions")
        if isinstance(phase_extensions, Mapping):
            existing_extensions = targets.get("extensions")
            existing_extensions = existing_extensions if isinstance(existing_extensions, Mapping) else {}
            targets["extensions"] = merge_recursive(dict(existing_extensions), dict(phase_extensions))
            phase_extension_targets = phase_extensions.get("targets")
            if isinstance(phase_extension_targets, Mapping):
                overlay = self.without_chemical_target_overlay(phase_extension_targets)
                if overlay:
                    targets = merge_recursive(targets, overlay)

        return clean_null_values(targets)

    def merge_diagnostics_runtime_targets(
        self,
        *,
        targets: Dict[str, Any],
        profile_row: Mapping[str, Any],
    ) -> Dict[str, Any]:
        subsystems = profile_row.get("subsystems")
        diagnostics = subsystems.get("diagnostics") if isinstance(subsystems, Mapping) else None
        execution = diagnostics.get("execution") if isinstance(diagnostics, Mapping) else None
        if not isinstance(execution, Mapping):
            return targets

        merged = merge_recursive({}, targets)
        diagnostics_targets = merged.get("diagnostics")
        diagnostics_targets = diagnostics_targets if isinstance(diagnostics_targets, dict) else {}
        diagnostics_targets = merge_recursive(diagnostics_targets, dict(execution))
        execution_targets = diagnostics_targets.get("execution")
        execution_targets = execution_targets if isinstance(execution_targets, dict) else {}
        diagnostics_targets["execution"] = merge_recursive(execution_targets, dict(execution))
        merged["diagnostics"] = diagnostics_targets
        return merged

    @staticmethod
    def without_chemical_target_overlay(payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Non-chemical keys from ``extensions.targets`` may overlay (diagnostics).

        ``ph`` / ``ec`` / ``solution_temp`` stay in ``targets.extensions`` and never
        replace SQL columns of the current recipe phase.
        """
        chemical_sections = {"ph", "ec", "solution_temp"}
        return {key: value for key, value in payload.items() if str(key).strip().lower() not in chemical_sections}

    @staticmethod
    def is_recipe_phase_chemical_target_parameter(parameter: str) -> bool:
        """Parity with PHP ``EffectiveTargetsService::isRecipePhaseChemicalTargetParameter``."""
        return parameter in {
            "ph.target",
            "ph.min",
            "ph.max",
            "ec.target",
            "ec.min",
            "ec.max",
            "solution_temp.target",
            "solution_temp.min",
            "solution_temp.max",
        }

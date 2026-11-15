"""PostgreSQL read-model snapshot'а зоны для AE3-Lite v1."""

from __future__ import annotations
from functools import cached_property

from datetime import datetime, timezone
import json
import os
from typing import Any, Dict, List, Mapping, Optional

from ae3lite.application.dto import ZoneActuatorRef, ZoneSnapshot
from ae3lite.domain.errors import ErrorCodes, SnapshotBuildError
from ae3lite.domain.services.phase_utils import normalize_phase_key
from common.db import get_pool
from .active_grow_cycle_order_sql import SQL_ACTIVE_GROW_CYCLE_ORDER_BY
from .effective_targets_sql_utils import (
    build_base_targets,
    clean_null_values,
    merge_recursive,
    merge_runtime_profile,
)


from ae3lite.infrastructure.read_models.zone_snapshot_shared import (
    _node_freshness_fallback_sec,
    _node_persistent_dead_sec,
)

from ae3lite.infrastructure.read_models.zone_snapshot_loader import ZoneSnapshotLoader, ZoneSnapshotLoaderPorts
from ae3lite.infrastructure.read_models.zone_snapshot_values_policy import (
    ZoneSnapshotValuesPolicy,
    ZoneSnapshotValuesPolicyPorts,
)
from ae3lite.infrastructure.read_models.zone_snapshot_bundle_rows import (
    ZoneSnapshotBundleRows,
    ZoneSnapshotBundleRowsPorts,
)
from ae3lite.infrastructure.read_models.zone_snapshot_targets import ZoneSnapshotTargets, ZoneSnapshotTargetsPorts
from ae3lite.infrastructure.read_models.zone_snapshot_execution import ZoneSnapshotExecution, ZoneSnapshotExecutionPorts
from ae3lite.infrastructure.read_models.zone_snapshot_correction import (
    ZoneSnapshotCorrection,
    ZoneSnapshotCorrectionPorts,
)
from ae3lite.infrastructure.read_models.zone_snapshot_telemetry import ZoneSnapshotTelemetry, ZoneSnapshotTelemetryPorts
from ae3lite.infrastructure.read_models.zone_snapshot_pump_calibration import (
    ZoneSnapshotPumpCalibration,
    ZoneSnapshotPumpCalibrationPorts,
)


class PgZoneSnapshotReadModel:
    """Загружает согласованный неизменяемый `ZoneSnapshot` из PostgreSQL."""

    @cached_property
    def _zone_snapshot_loader(self):
        return ZoneSnapshotLoader(
            ZoneSnapshotLoaderPorts(
                after_zone_row_loaded=lambda *args, **kwargs: self._after_zone_row_loaded(*args, **kwargs),
                build_correction_config=lambda *args, **kwargs: self._build_correction_config(*args, **kwargs),
                build_no_actuators_diagnostics=lambda *args, **kwargs: self._build_no_actuators_diagnostics(
                    *args, **kwargs
                ),
                build_phase_targets=lambda *args, **kwargs: self._build_phase_targets(*args, **kwargs),
                build_pid_configs=lambda *args, **kwargs: self._build_pid_configs(*args, **kwargs),
                build_pid_state=lambda *args, **kwargs: self._build_pid_state(*args, **kwargs),
                build_process_calibrations=lambda *args, **kwargs: self._build_process_calibrations(*args, **kwargs),
                build_targets=lambda *args, **kwargs: self._build_targets(*args, **kwargs),
                build_telemetry_last=lambda *args, **kwargs: self._build_telemetry_last(*args, **kwargs),
                bundle_correction_config_row=lambda *args, **kwargs: self._bundle_correction_config_row(
                    *args, **kwargs
                ),
                bundle_override_rows=lambda *args, **kwargs: self._bundle_override_rows(*args, **kwargs),
                bundle_pid_config_rows=lambda *args, **kwargs: self._bundle_pid_config_rows(*args, **kwargs),
                bundle_process_calibration_rows=lambda *args, **kwargs: self._bundle_process_calibration_rows(
                    *args, **kwargs
                ),
                extract_pump_calibration=lambda *args, **kwargs: self._extract_pump_calibration(*args, **kwargs),
                merge_pump_calibration_policy=lambda *args, **kwargs: self._merge_pump_calibration_policy(
                    *args, **kwargs
                ),
                normalize_override_rows=lambda *args, **kwargs: self._normalize_override_rows(*args, **kwargs),
                resolve_diagnostics_execution=lambda *args, **kwargs: self._resolve_diagnostics_execution(
                    *args, **kwargs
                ),
                global_get_pool=lambda *args, **kwargs: get_pool(*args, **kwargs),
            )
        )

    @cached_property
    def _zone_snapshot_values_policy(self):
        return ZoneSnapshotValuesPolicy(
            ZoneSnapshotValuesPolicyPorts(
                is_recipe_phase_chemical_target_parameter=lambda *args, **kwargs: (
                    self._is_recipe_phase_chemical_target_parameter(*args, **kwargs)
                ),
            )
        )

    @cached_property
    def _zone_snapshot_bundle_rows(self):
        return ZoneSnapshotBundleRows(ZoneSnapshotBundleRowsPorts())

    @cached_property
    def _zone_snapshot_targets(self):
        return ZoneSnapshotTargets(
            ZoneSnapshotTargetsPorts(
                apply_overrides=lambda *args, **kwargs: self._apply_overrides(*args, **kwargs),
            )
        )

    @cached_property
    def _zone_snapshot_execution(self):
        return ZoneSnapshotExecution(
            ZoneSnapshotExecutionPorts(
                apply_overrides=lambda *args, **kwargs: self._apply_overrides(*args, **kwargs),
            )
        )

    @cached_property
    def _zone_snapshot_correction(self):
        return ZoneSnapshotCorrection(
            ZoneSnapshotCorrectionPorts(
                as_mapping=lambda *args, **kwargs: self._as_mapping(*args, **kwargs),
                to_float=lambda *args, **kwargs: self._to_float(*args, **kwargs),
            )
        )

    @cached_property
    def _zone_snapshot_telemetry(self):
        return ZoneSnapshotTelemetry(
            ZoneSnapshotTelemetryPorts(
                normalize_timestamp=lambda *args, **kwargs: self._normalize_timestamp(*args, **kwargs),
                to_float=lambda *args, **kwargs: self._to_float(*args, **kwargs),
            )
        )

    @cached_property
    def _zone_snapshot_pump_calibration(self):
        return ZoneSnapshotPumpCalibration(
            ZoneSnapshotPumpCalibrationPorts(
                to_float=lambda *args, **kwargs: self._to_float(*args, **kwargs),
                to_int=lambda *args, **kwargs: self._to_int(*args, **kwargs),
            )
        )

    _normalize_timestamp = staticmethod(ZoneSnapshotValuesPolicy.normalize_timestamp)

    async def _after_zone_row_loaded(self, *, conn: Any, zone_id: int, grow_cycle_id: int) -> None:
        """Test hook for proving transaction isolation between snapshot SELECT statements."""
        return None

    async def load(self, *, zone_id: int) -> ZoneSnapshot:
        return await self._zone_snapshot_loader.load(zone_id=zone_id)

    _build_no_actuators_diagnostics = staticmethod(ZoneSnapshotTelemetry.build_no_actuators_diagnostics)

    _bundle_override_rows = staticmethod(ZoneSnapshotBundleRows.bundle_override_rows)

    _bundle_pid_config_rows = staticmethod(ZoneSnapshotBundleRows.bundle_pid_config_rows)

    _bundle_correction_config_row = staticmethod(ZoneSnapshotBundleRows.bundle_correction_config_row)

    _bundle_process_calibration_rows = staticmethod(ZoneSnapshotBundleRows.bundle_process_calibration_rows)

    def _build_targets(
        self,
        *,
        zone_row: Mapping[str, Any],
        override_rows: List[Mapping[str, Any]],
        profile_row: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return self._zone_snapshot_targets.build_targets(
            zone_row=zone_row, override_rows=override_rows, profile_row=profile_row
        )

    def _build_phase_targets(
        self,
        *,
        zone_row: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return self._zone_snapshot_targets.build_phase_targets(zone_row=zone_row)

    def _merge_diagnostics_runtime_targets(
        self,
        *,
        targets: Dict[str, Any],
        profile_row: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return self._zone_snapshot_targets.merge_diagnostics_runtime_targets(targets=targets, profile_row=profile_row)

    def _resolve_diagnostics_execution(
        self,
        *,
        zone_row: Mapping[str, Any],
        override_rows: List[Mapping[str, Any]],
        profile_row: Mapping[str, Any],
    ) -> Dict[str, Any]:
        return self._zone_snapshot_execution.resolve_diagnostics_execution(
            zone_row=zone_row, override_rows=override_rows, profile_row=profile_row
        )

    def _resolve_profile_execution(self, profile_row: Mapping[str, Any]) -> Dict[str, Any]:
        return self._zone_snapshot_execution.resolve_profile_execution(profile_row=profile_row)

    def _normalize_two_tank_execution_contract(self, execution: Dict[str, Any]) -> None:
        return self._zone_snapshot_execution.normalize_two_tank_execution_contract(execution=execution)

    def _resolve_ec_component_policy(self, execution: Mapping[str, Any]) -> Dict[str, Any]:
        return self._zone_snapshot_correction.resolve_ec_component_policy(execution=execution)

    def _build_correction_config(self, row: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
        return self._zone_snapshot_correction.build_correction_config(row=row)

    def _build_process_calibrations(self, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        return self._zone_snapshot_correction.build_process_calibrations(rows=rows)

    _as_mapping = staticmethod(ZoneSnapshotValuesPolicy.as_mapping)

    @classmethod
    def _ec_component_gains_from_source(cls, source: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        return ZoneSnapshotValuesPolicy.component_gains_from_source(source, as_mapping_fn=cls._as_mapping)

    def _merge_execution_sources(
        self,
        left: Mapping[str, Any],
        right: Mapping[str, Any],
        *,
        path: str,
    ) -> Dict[str, Any]:
        return self._zone_snapshot_execution.merge_execution_sources(left=left, right=right, path=path)

    def _normalize_override_rows(self, rows: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        return self._zone_snapshot_values_policy.normalize_override_rows(rows=rows)

    _without_chemical_target_overlay = staticmethod(ZoneSnapshotTargets.without_chemical_target_overlay)

    _is_recipe_phase_chemical_target_parameter = staticmethod(
        ZoneSnapshotTargets.is_recipe_phase_chemical_target_parameter
    )

    def _build_telemetry_last(self, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        return self._zone_snapshot_telemetry.build_telemetry_last(rows=rows)

    def _build_pid_state(self, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        return self._zone_snapshot_telemetry.build_pid_state(rows=rows)

    def _build_pid_configs(self, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        return self._zone_snapshot_correction.build_pid_configs(rows=rows)

    def _extract_override_value(self, row: Mapping[str, Any]) -> Any:
        return self._zone_snapshot_values_policy.extract_override_value(row=row)

    def _extract_pump_calibration(
        self,
        row: Mapping[str, Any],
        *,
        pump_calibration_policy: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        return self._zone_snapshot_pump_calibration.extract_pump_calibration(
            row=row, pump_calibration_policy=pump_calibration_policy
        )

    def _merge_pump_calibration_policy(
        self,
        correction_config: Mapping[str, Any],
        pump_calibration_policy: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        return self._zone_snapshot_pump_calibration.merge_pump_calibration_policy(
            correction_config=correction_config, pump_calibration_policy=pump_calibration_policy
        )

    def _to_int(self, value: Any) -> Optional[int]:
        return self._zone_snapshot_values_policy.to_int(value=value)

    def _apply_overrides(
        self,
        *,
        payload: Dict[str, Any],
        override_rows: List[Mapping[str, Any]],
        prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._zone_snapshot_values_policy.apply_overrides(
            payload=payload, override_rows=override_rows, prefix=prefix
        )

    def _set_nested_value(self, *, payload: Dict[str, Any], dotted_key: str, value: Any) -> None:
        return self._zone_snapshot_values_policy.set_nested_value(payload=payload, dotted_key=dotted_key, value=value)

    def _to_float(self, value: Any) -> Optional[float]:
        return self._zone_snapshot_values_policy.to_float(value=value)

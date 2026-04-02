"""PostgreSQL zone snapshot read-model for AE3-Lite v1."""

from __future__ import annotations

from datetime import datetime, timezone
import json
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


class PgZoneSnapshotReadModel:
    """Loads a consistent immutable ZoneSnapshot from PostgreSQL."""

    @staticmethod
    def _normalize_timestamp(value: Any) -> Any:
        if not isinstance(value, datetime):
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value

    async def load(self, *, zone_id: int) -> ZoneSnapshot:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                zone_row = await conn.fetchrow(
                    f"""
                    SELECT
                        z.id AS zone_id,
                        z.greenhouse_id,
                        z.automation_runtime,
                        gc.id AS grow_cycle_id,
                        gc.current_phase_id,
                        gc.settings AS cycle_settings,
                        gcp.name AS phase_name,
                        COALESCE(zws.workflow_phase, 'idle') AS workflow_phase,
                        COALESCE(zws.version, 0) AS workflow_version,
                        gcp.ph_target,
                        gcp.ph_min,
                        gcp.ph_max,
                        gcp.ec_target,
                        gcp.ec_min,
                        gcp.ec_max,
                        gcp.irrigation_mode,
                        gcp.irrigation_interval_sec,
                        gcp.irrigation_duration_sec,
                        gcp.lighting_photoperiod_hours,
                        gcp.lighting_start_time,
                        gcp.temp_air_target,
                        gcp.humidity_target,
                        gcp.co2_target,
                        gcp.mist_interval_sec,
                        gcp.mist_duration_sec,
                        gcp.mist_mode,
                        gcp.extensions AS phase_extensions
                    FROM zones z
                    LEFT JOIN grow_cycles gc
                        ON gc.zone_id = z.id
                       AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
                    LEFT JOIN grow_cycle_phases gcp
                        ON gcp.id = gc.current_phase_id
                    LEFT JOIN zone_workflow_state zws
                        ON zws.zone_id = z.id
                    WHERE z.id = $1
                    {SQL_ACTIVE_GROW_CYCLE_ORDER_BY.strip()}
                    LIMIT 1
                    """,
                    zone_id,
                )
                if zone_row is None:
                    raise SnapshotBuildError(
                        f"Zone {zone_id} not found",
                        code=ErrorCodes.AE3_SNAPSHOT_ZONE_NOT_FOUND,
                    )

                grow_cycle_id = zone_row.get("grow_cycle_id")
                if grow_cycle_id is None:
                    raise SnapshotBuildError(
                        f"Zone {zone_id} has no active grow_cycle",
                        code=ErrorCodes.AE3_SNAPSHOT_NO_ACTIVE_GROW_CYCLE,
                    )
                if zone_row.get("current_phase_id") is None:
                    raise SnapshotBuildError(
                        f"Zone {zone_id} has no current_phase_id for active grow_cycle",
                        code=ErrorCodes.AE3_SNAPSHOT_MISSING_CURRENT_PHASE,
                    )

                bundle_row = await conn.fetchrow(
                    """
                    SELECT scope_type, scope_id, bundle_revision, config
                    FROM automation_effective_bundles
                    WHERE scope_type = 'grow_cycle'
                      AND scope_id = $1
                    LIMIT 1
                    """,
                    grow_cycle_id,
                )
                if bundle_row is None:
                    raise SnapshotBuildError(
                        f"Grow cycle {grow_cycle_id} has no automation_effective_bundle",
                        code=ErrorCodes.AE3_SNAPSHOT_BUNDLE_MISSING,
                    )

                cycle_settings = zone_row.get("cycle_settings")
                cycle_settings = cycle_settings if isinstance(cycle_settings, Mapping) else {}
                expected_bundle_revision = str(cycle_settings.get("bundle_revision") or "").strip()
                actual_bundle_revision = str(bundle_row.get("bundle_revision") or "").strip()
                if expected_bundle_revision and expected_bundle_revision != actual_bundle_revision:
                    raise SnapshotBuildError(
                        (
                            f"Grow cycle {grow_cycle_id} bundle revision mismatch: "
                            f"expected={expected_bundle_revision} actual={actual_bundle_revision or 'empty'}"
                        ),
                        code=ErrorCodes.AE3_SNAPSHOT_BUNDLE_INVALID,
                    )

                bundle_config = bundle_row.get("config")
                if not isinstance(bundle_config, Mapping):
                    raise SnapshotBuildError(
                        f"Grow cycle {grow_cycle_id} has invalid automation bundle config",
                        code=ErrorCodes.AE3_SNAPSHOT_BUNDLE_INVALID,
                    )

                system_bundle = bundle_config.get("system")
                pump_calibration_policy = (
                    system_bundle.get("pump_calibration_policy")
                    if isinstance(system_bundle, Mapping)
                    else None
                )

                zone_bundle = bundle_config.get("zone")
                if not isinstance(zone_bundle, Mapping):
                    raise SnapshotBuildError(
                        f"Grow cycle {grow_cycle_id} has no zone bundle",
                        code=ErrorCodes.AE3_SNAPSHOT_ZONE_BUNDLE_MISSING,
                    )

                logic_profile = zone_bundle.get("logic_profile")
                if not isinstance(logic_profile, Mapping):
                    raise SnapshotBuildError(
                        f"Zone {zone_id} has no active logic profile bundle",
                        code=ErrorCodes.AE3_SNAPSHOT_LOGIC_PROFILE_BUNDLE_MISSING,
                    )

                active_profile = logic_profile.get("active_profile")
                if not isinstance(active_profile, Mapping):
                    raise SnapshotBuildError(
                        f"Zone {zone_id} has no active automation logic profile",
                        code=ErrorCodes.AE3_SNAPSHOT_ACTIVE_LOGIC_PROFILE_MISSING,
                    )

                profile_row = {
                    "mode": logic_profile.get("active_mode"),
                    "updated_at": active_profile.get("updated_at"),
                    "command_plans": active_profile.get("command_plans"),
                    "subsystems": active_profile.get("subsystems"),
                }

                cycle_bundle = bundle_config.get("cycle")
                override_rows = self._bundle_override_rows(cycle_bundle)

                telemetry_rows = await conn.fetch(
                    """
                    SELECT
                        LOWER(COALESCE(s.type, '')) AS sensor_type,
                        s.id AS sensor_id,
                        s.label AS sensor_label,
                        tl.last_value,
                        COALESCE(tl.last_ts, tl.updated_at) AS sample_ts,
                        tl.last_quality
                    FROM sensors s
                    LEFT JOIN telemetry_last tl
                        ON tl.sensor_id = s.id
                    WHERE s.zone_id = $1
                      AND s.is_active = TRUE
                    ORDER BY
                        COALESCE(tl.last_ts, tl.updated_at) DESC NULLS LAST,
                        s.id DESC
                    """,
                    zone_id,
                )

                pid_state_rows = await conn.fetch(
                    """
                    SELECT
                        pid_type,
                        integral,
                        prev_error,
                        prev_derivative,
                        last_output_ms,
                        last_dose_at,
                        hold_until,
                        last_measurement_at,
                        last_measured_value,
                        feedforward_bias,
                        no_effect_count,
                        last_correction_kind,
                        stats,
                        current_zone,
                        updated_at
                    FROM pid_state
                    WHERE zone_id = $1
                    ORDER BY pid_type ASC
                    """,
                    zone_id,
                )

                pid_config_rows = self._bundle_pid_config_rows(zone_bundle)
                correction_config_row = self._bundle_correction_config_row(zone_bundle)
                process_calibration_rows = self._bundle_process_calibration_rows(zone_bundle)

                actuator_rows = await conn.fetch(
                    """
                    SELECT
                        nc.id AS node_channel_id,
                        n.uid AS node_uid,
                        LOWER(COALESCE(n.type, '')) AS node_type,
                        LOWER(COALESCE(nc.channel, 'default')) AS channel,
                        UPPER(COALESCE(nc.type, 'ACTUATOR')) AS channel_type,
                        LOWER(COALESCE(cb.role, '')) AS role,
                        nc.config AS channel_config,
                        pc.ml_per_sec AS calibration_ml_per_sec,
                        pc.k_ms_per_ml_l AS calibration_k_ms_per_ml_l,
                        pc.component AS calibration_component,
                        pc.source AS calibration_source,
                        pc.quality_score AS calibration_quality_score,
                        pc.sample_count AS calibration_sample_count,
                        pc.valid_from AS calibration_valid_from
                    FROM nodes n
                    JOIN node_channels nc
                        ON nc.node_id = n.id
                    LEFT JOIN channel_bindings cb
                        ON cb.node_channel_id = nc.id
                    LEFT JOIN LATERAL (
                        SELECT
                            p.ml_per_sec,
                            p.k_ms_per_ml_l,
                            p.component,
                            p.source,
                            p.quality_score,
                            p.sample_count,
                            p.valid_from
                        FROM pump_calibrations p
                        WHERE p.node_channel_id = nc.id
                          AND p.is_active = TRUE
                          AND p.valid_from <= NOW()
                          AND (p.valid_to IS NULL OR p.valid_to > NOW())
                        ORDER BY p.valid_from DESC, p.id DESC
                        LIMIT 1
                    ) pc ON TRUE
                    WHERE n.zone_id = $1
                      AND LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
                      AND UPPER(TRIM(COALESCE(nc.type, ''))) IN ('ACTUATOR', 'SERVICE')
                      AND COALESCE(nc.is_active, TRUE) = TRUE
                    ORDER BY n.id ASC, nc.id ASC
                    """,
                    zone_id,
                )

        command_plans = profile_row.get("command_plans")
        if not isinstance(command_plans, Mapping) or not command_plans:
            raise SnapshotBuildError(
                f"Zone {zone_id} has empty command_plans",
                code=ErrorCodes.AE3_SNAPSHOT_EMPTY_COMMAND_PLANS,
            )

        normalized_overrides = self._normalize_override_rows(override_rows)
        phase_targets = self._build_phase_targets(zone_row=zone_row)
        targets = self._build_targets(
            zone_row=zone_row,
            override_rows=normalized_overrides,
            profile_row=profile_row,
        )
        diagnostics_execution = self._resolve_diagnostics_execution(
            zone_row=zone_row,
            override_rows=normalized_overrides,
            profile_row=profile_row,
        )
        telemetry_last = self._build_telemetry_last(telemetry_rows)
        pid_state = self._build_pid_state(pid_state_rows)
        pid_configs = self._build_pid_configs(pid_config_rows)
        correction_config = self._build_correction_config(correction_config_row)
        process_calibrations = self._build_process_calibrations(process_calibration_rows)
        actuators = tuple(
            ZoneActuatorRef(
                node_uid=str(row.get("node_uid") or "").strip(),
                node_type=str(row.get("node_type") or "").strip().lower(),
                channel=str(row.get("channel") or "default").strip().lower() or "default",
                node_channel_id=int(row["node_channel_id"]),
                channel_type=str(row.get("channel_type") or "ACTUATOR").strip().upper() or "ACTUATOR",
                role=str(row.get("role") or "").strip().lower() or None,
                pump_calibration=self._extract_pump_calibration(
                    row,
                    pump_calibration_policy=pump_calibration_policy,
                ),
            )
            for row in actuator_rows
            if str(row.get("node_uid") or "").strip()
        )
        if not actuators:
            raise SnapshotBuildError(
                f"Zone {zone_id} has no online actuator channels",
                code=ErrorCodes.AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS,
            )

        return ZoneSnapshot(
            zone_id=int(zone_row["zone_id"]),
            greenhouse_id=int(zone_row["greenhouse_id"]) if zone_row.get("greenhouse_id") is not None else None,
            automation_runtime=str(zone_row.get("automation_runtime") or "").strip().lower(),
            grow_cycle_id=int(grow_cycle_id),
            current_phase_id=int(zone_row["current_phase_id"]),
            phase_name=str(zone_row["phase_name"]) if zone_row.get("phase_name") is not None else None,
            workflow_phase=str(zone_row.get("workflow_phase") or "idle").strip().lower() or "idle",
            workflow_version=int(zone_row.get("workflow_version") or 0),
            targets=targets,
            phase_targets=phase_targets,
            diagnostics_execution=diagnostics_execution,
            command_plans=command_plans,
            telemetry_last=telemetry_last,
            pid_state=pid_state,
            pid_configs=pid_configs,
            actuators=actuators,
            process_calibrations=process_calibrations,
            correction_config=correction_config,
        )

    @staticmethod
    def _bundle_override_rows(cycle_bundle: Any) -> List[Mapping[str, Any]]:
        if not isinstance(cycle_bundle, Mapping):
            return []

        rows: List[Mapping[str, Any]] = []
        phase_overrides = cycle_bundle.get("phase_overrides")
        if isinstance(phase_overrides, Mapping):
            phase_map = {
                "irrigation_mode": ("irrigation.mode", "string"),
                "irrigation_interval_sec": ("irrigation.interval_sec", "integer"),
                "irrigation_duration_sec": ("irrigation.duration_sec", "integer"),
            }
            for legacy_key, value in phase_overrides.items():
                mapping = phase_map.get(str(legacy_key).strip())
                if mapping is None or value is None:
                    continue
                parameter, value_type = mapping
                rows.append({"parameter": parameter, "value_type": value_type, "value": value})

        manual_overrides = cycle_bundle.get("manual_overrides")
        if isinstance(manual_overrides, list):
            rows.extend(item for item in manual_overrides if isinstance(item, Mapping))

        return rows

    @staticmethod
    def _bundle_pid_config_rows(zone_bundle: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        pid_bundle = zone_bundle.get("pid")
        if not isinstance(pid_bundle, Mapping):
            return []

        rows: List[Mapping[str, Any]] = []
        for pid_type in ("ec", "ph"):
            entry = pid_bundle.get(pid_type)
            if not isinstance(entry, Mapping):
                continue
            rows.append(
                {
                    "type": pid_type,
                    "config": entry.get("config"),
                    "updated_at": None,
                }
            )
        return rows

    @staticmethod
    def _bundle_correction_config_row(zone_bundle: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
        correction_bundle = zone_bundle.get("correction")
        if not isinstance(correction_bundle, Mapping):
            return None

        resolved = correction_bundle.get("resolved_config")
        version = 1
        if isinstance(resolved, Mapping):
            meta = resolved.get("meta")
            if isinstance(meta, Mapping):
                try:
                    version = int(meta.get("version") or version)
                except (TypeError, ValueError):
                    version = 1

        return {
            "version": version,
            "resolved_config": resolved if isinstance(resolved, Mapping) else {},
            "phase_overrides": correction_bundle.get("phase_overrides"),
        }

    @staticmethod
    def _bundle_process_calibration_rows(zone_bundle: Mapping[str, Any]) -> List[Mapping[str, Any]]:
        calibrations = zone_bundle.get("process_calibration")
        if not isinstance(calibrations, Mapping):
            return []

        rows: List[Mapping[str, Any]] = []
        for mode, payload in calibrations.items():
            if not isinstance(payload, Mapping):
                continue
            rows.append(
                {
                    "mode": mode,
                    "ec_gain_per_ml": payload.get("ec_gain_per_ml"),
                    "ph_up_gain_per_ml": payload.get("ph_up_gain_per_ml"),
                    "ph_down_gain_per_ml": payload.get("ph_down_gain_per_ml"),
                    "ph_per_ec_ml": payload.get("ph_per_ec_ml"),
                    "ec_per_ph_ml": payload.get("ec_per_ph_ml"),
                    "transport_delay_sec": payload.get("transport_delay_sec"),
                    "settle_sec": payload.get("settle_sec"),
                    "confidence": payload.get("confidence"),
                    "source": payload.get("source"),
                    "valid_from": payload.get("valid_from"),
                    "valid_to": payload.get("valid_to"),
                    "is_active": payload.get("is_active", True),
                    "meta": payload.get("meta"),
                    "updated_at": payload.get("updated_at"),
                }
            )
        return rows

    def _build_targets(
        self,
        *,
        zone_row: Mapping[str, Any],
        override_rows: List[Mapping[str, Any]],
        profile_row: Mapping[str, Any],
    ) -> Dict[str, Any]:
        targets = self._build_phase_targets(zone_row=zone_row)
        targets = self._apply_overrides(payload=targets, override_rows=override_rows)
        targets = merge_runtime_profile(
            targets,
            {
                "mode": profile_row.get("mode"),
                "updated_at": profile_row.get("updated_at"),
                "subsystems": profile_row.get("subsystems"),
            },
        )
        targets = self._merge_diagnostics_runtime_targets(targets=targets, profile_row=profile_row)
        return clean_null_values(targets)

    def _build_phase_targets(
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
                targets = merge_recursive(targets, dict(phase_extension_targets))

        return clean_null_values(targets)

    def _merge_diagnostics_runtime_targets(
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

    def _resolve_diagnostics_execution(
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

        result = self._apply_overrides(
            payload=result,
            override_rows=override_rows,
            prefix="diagnostics.execution.",
        )

        profile_execution = self._resolve_profile_execution(profile_row)
        if profile_execution:
            result = merge_recursive(result, profile_execution)
        return clean_null_values(result)

    def _resolve_profile_execution(self, profile_row: Mapping[str, Any]) -> Dict[str, Any]:
        command_plans = profile_row.get("command_plans")
        plans = command_plans.get("plans") if isinstance(command_plans, Mapping) else None
        diagnostics_plan = plans.get("diagnostics") if isinstance(plans, Mapping) else None
        subsystems = profile_row.get("subsystems")
        diagnostics = subsystems.get("diagnostics") if isinstance(subsystems, Mapping) else None
        subsystem_execution = diagnostics.get("execution") if isinstance(diagnostics, Mapping) else None
        plan_execution = diagnostics_plan.get("execution") if isinstance(diagnostics_plan, Mapping) else None
        return self._merge_execution_sources(
            subsystem_execution if isinstance(subsystem_execution, Mapping) else {},
            plan_execution if isinstance(plan_execution, Mapping) else {},
            path="diagnostics.execution",
        )

    def _normalize_two_tank_execution_contract(self, execution: Dict[str, Any]) -> None:
        """Remove legacy top-level fields from two_tank execution contract (in-place)."""
        execution.pop("startup", None)
        execution.pop("required_node_types", None)

    def _resolve_ec_component_policy(self, execution: Mapping[str, Any]) -> Dict[str, Any]:
        correction = execution.get("correction")
        if not isinstance(correction, Mapping):
            return {}
        policy = correction.get("ec_component_policy")
        if not isinstance(policy, Mapping):
            return {}
        result: Dict[str, Any] = {}
        for phase, phase_policy in policy.items():
            if isinstance(phase_policy, Mapping):
                result[str(phase).strip()] = dict(phase_policy)
        return result

    def _build_correction_config(self, row: Optional[Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        version = row.get("version")
        try:
            version_int = int(version)
        except (TypeError, ValueError):
            return None
        resolved = row.get("resolved_config")
        result: Dict[str, Any] = dict(resolved) if isinstance(resolved, Mapping) else {}
        meta = result.get("meta")
        result["meta"] = dict(meta) if isinstance(meta, dict) else {}
        result["meta"]["version"] = version_int
        phase_overrides = row.get("phase_overrides")
        if isinstance(phase_overrides, Mapping):
            result["meta"]["phase_overrides"] = dict(phase_overrides)
        return result

    def _build_process_calibrations(self, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for row in rows:
            if not row.get("is_active", True):
                continue
            mode = normalize_phase_key(row.get("mode"))
            if not mode or mode in result:
                continue
            result[mode] = {
                "ec_gain_per_ml": self._to_float(row.get("ec_gain_per_ml")),
                "ph_up_gain_per_ml": self._to_float(row.get("ph_up_gain_per_ml")),
                "ph_down_gain_per_ml": self._to_float(row.get("ph_down_gain_per_ml")),
                "ph_per_ec_ml": self._to_float(row.get("ph_per_ec_ml")),
                "ec_per_ph_ml": self._to_float(row.get("ec_per_ph_ml")),
                "transport_delay_sec": int(row.get("transport_delay_sec") or 0),
                "settle_sec": int(row.get("settle_sec") or 0),
                "confidence": self._to_float(row.get("confidence")),
                "source": row.get("source"),
                "valid_from": row.get("valid_from"),
                "valid_to": row.get("valid_to"),
                "meta": dict(row.get("meta")) if isinstance(row.get("meta"), Mapping) else {},
                "updated_at": row.get("updated_at"),
            }
        return result

    def _merge_execution_sources(
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
                merged[key] = self._merge_execution_sources(left_value, right_value, path=current_path)
                continue
            if left_value != right_value:
                raise SnapshotBuildError(
                    f"Conflicting value for {current_path}",
                    code=ErrorCodes.AE3_SNAPSHOT_CONFLICTING_CONFIG_VALUES,
                )
        return merged

    def _normalize_override_rows(self, rows: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            parameter = str(row.get("parameter") or "").strip()
            if not parameter:
                continue
            if self._is_recipe_phase_chemical_target_parameter(parameter):
                continue
            normalized.append(
                {
                    "parameter": parameter,
                    "value_type": str(row.get("value_type") or "").strip().lower(),
                    "value": self._extract_override_value(row),
                }
            )
        return normalized

    @staticmethod
    def _is_recipe_phase_chemical_target_parameter(parameter: str) -> bool:
        return parameter in {
            "ph.target",
            "ph.min",
            "ph.max",
            "ec.target",
            "ec.min",
            "ec.max",
        }

    def _build_telemetry_last(self, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        seen_sensor_types: dict[str, int] = {}
        for row in rows:
            sensor_type = str(row.get("sensor_type") or "").strip().lower()
            if not sensor_type:
                continue
            seen_sensor_types[sensor_type] = seen_sensor_types.get(sensor_type, 0) + 1
            if sensor_type in {"ph", "ec"} and seen_sensor_types[sensor_type] > 1:
                raise SnapshotBuildError(
                    f"Zone snapshot has multiple active telemetry sensors for critical type={sensor_type}",
                    code=ErrorCodes.AE3_SNAPSHOT_CONFLICTING_CONFIG_VALUES,
                )
            if sensor_type in result:
                continue
            result[sensor_type] = {
                "sensor_id": row.get("sensor_id"),
                "sensor_label": row.get("sensor_label"),
                "value": float(row["last_value"]) if row.get("last_value") is not None else None,
                "sample_ts": row.get("sample_ts"),
                "quality": row.get("last_quality"),
            }
        return result

    def _build_pid_state(self, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for row in rows:
            pid_type = str(row.get("pid_type") or "").strip().lower()
            if not pid_type:
                continue
            result[pid_type] = {
                "integral": self._to_float(row.get("integral")),
                "prev_error": self._to_float(row.get("prev_error")),
                "prev_derivative": self._to_float(row.get("prev_derivative")),
                "last_output_ms": int(row.get("last_output_ms") or 0),
                "last_dose_at": self._normalize_timestamp(row.get("last_dose_at")),
                "hold_until": self._normalize_timestamp(row.get("hold_until")),
                "last_measurement_at": self._normalize_timestamp(row.get("last_measurement_at")),
                "last_measured_value": self._to_float(row.get("last_measured_value")),
                "feedforward_bias": self._to_float(row.get("feedforward_bias")),
                "no_effect_count": int(row.get("no_effect_count") or 0),
                "last_correction_kind": row.get("last_correction_kind"),
                "stats": row.get("stats"),
                "current_zone": row.get("current_zone"),
                "updated_at": self._normalize_timestamp(row.get("updated_at")),
            }
        return result

    def _build_pid_configs(self, rows: List[Mapping[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for row in rows:
            pid_type = str(row.get("type") or "").strip().lower()
            if not pid_type:
                continue
            result[pid_type] = {
                "config": row.get("config"),
                "updated_at": row.get("updated_at"),
            }
        return result

    def _extract_override_value(self, row: Mapping[str, Any]) -> Any:
        value_type = str(row.get("value_type") or "").strip().lower()
        value = row.get("value")
        if value_type in {"integer", "int"}:
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return value
        if value_type in {"decimal", "float", "numeric"}:
            return self._to_float(value)
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

    def _extract_pump_calibration(
        self,
        row: Mapping[str, Any],
        *,
        pump_calibration_policy: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        result: Dict[str, Any] = {}
        if isinstance(pump_calibration_policy, Mapping):
            result.update(
                {
                    "min_dose_ms": pump_calibration_policy.get("min_dose_ms"),
                    "ml_per_sec_min": self._to_float(pump_calibration_policy.get("ml_per_sec_min")),
                    "ml_per_sec_max": self._to_float(pump_calibration_policy.get("ml_per_sec_max")),
                }
            )

        if row.get("calibration_ml_per_sec") is not None:
            result.update(
                {
                    "ml_per_sec": self._to_float(row.get("calibration_ml_per_sec")),
                    "k_ms_per_ml_l": self._to_float(row.get("calibration_k_ms_per_ml_l")),
                    "component": row.get("calibration_component"),
                    "source": row.get("calibration_source"),
                    "quality_score": self._to_float(row.get("calibration_quality_score")),
                    "sample_count": int(row.get("calibration_sample_count") or 0),
                    "valid_from": row.get("calibration_valid_from"),
                }
            )

        return result or None

    def _apply_overrides(
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
                parameter = parameter[len(prefix):]
            if not parameter:
                continue
            self._set_nested_value(payload=merged, dotted_key=parameter, value=row.get("value"))
        return merged

    def _set_nested_value(self, *, payload: Dict[str, Any], dotted_key: str, value: Any) -> None:
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

    def _to_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

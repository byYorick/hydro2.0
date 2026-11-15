"""PgZoneSnapshotReadModel loader: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, List, Mapping

from ae3lite.application.dto import ZoneActuatorRef, ZoneSnapshot
from ae3lite.domain.errors import ErrorCodes, SnapshotBuildError
from ae3lite.infrastructure.read_models.zone_snapshot_shared import _node_freshness_fallback_sec

from .active_grow_cycle_order_sql import SQL_ACTIVE_GROW_CYCLE_ORDER_BY


@dataclass(frozen=True)
class ZoneSnapshotLoaderPorts:
    after_zone_row_loaded: Callable[..., Awaitable[Any]]
    build_correction_config: Callable[..., Any]
    build_no_actuators_diagnostics: Callable[..., Any]
    build_phase_targets: Callable[..., Any]
    build_pid_configs: Callable[..., Any]
    build_pid_state: Callable[..., Any]
    build_process_calibrations: Callable[..., Any]
    build_targets: Callable[..., Any]
    build_telemetry_last: Callable[..., Any]
    bundle_correction_config_row: Callable[..., Any]
    bundle_override_rows: Callable[..., Any]
    bundle_pid_config_rows: Callable[..., Any]
    bundle_process_calibration_rows: Callable[..., Any]
    extract_pump_calibration: Callable[..., Any]
    merge_pump_calibration_policy: Callable[..., Any]
    normalize_override_rows: Callable[..., Any]
    resolve_diagnostics_execution: Callable[..., Any]
    global_get_pool: Callable[..., Any]


class ZoneSnapshotLoader:
    def __init__(self, ports: ZoneSnapshotLoaderPorts) -> None:
        self._ports = ports

    async def load(self, *, zone_id: int) -> ZoneSnapshot:
        pool = await self._ports.global_get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                zone_row = await conn.fetchrow(
                    f"""
                    SELECT
                        z.id AS zone_id,
                        z.greenhouse_id,
                        g.timezone AS greenhouse_timezone,
                        z.automation_runtime,
                        z.config_revision AS zone_config_revision,
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
                        gcp.irrigation_system_type,
                        gcp.substrate_type,
                        gcp.day_night_enabled,
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
                        gcp.solution_temp_target,
                        gcp.solution_temp_min,
                        gcp.solution_temp_max,
                        gcp.dli_target,
                        gcp.extensions AS phase_extensions
                    FROM zones z
                    LEFT JOIN greenhouses g
                        ON g.id = z.greenhouse_id
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
                        f"Зона {zone_id} не найдена",
                        code=ErrorCodes.AE3_SNAPSHOT_ZONE_NOT_FOUND,
                    )

                grow_cycle_id = zone_row.get("grow_cycle_id")
                if grow_cycle_id is None:
                    raise SnapshotBuildError(
                        f"У зоны {zone_id} отсутствует активный grow_cycle",
                        code=ErrorCodes.AE3_SNAPSHOT_NO_ACTIVE_GROW_CYCLE,
                    )
                if zone_row.get("current_phase_id") is None:
                    raise SnapshotBuildError(
                        f"У зоны {zone_id} отсутствует current_phase_id для активного grow_cycle",
                        code=ErrorCodes.AE3_SNAPSHOT_MISSING_CURRENT_PHASE,
                    )

                await self._ports.after_zone_row_loaded(
                    conn=conn,
                    zone_id=zone_id,
                    grow_cycle_id=int(grow_cycle_id),
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
                        f"У grow cycle {grow_cycle_id} отсутствует automation_effective_bundle",
                        code=ErrorCodes.AE3_SNAPSHOT_BUNDLE_MISSING,
                    )

                cycle_settings = zone_row.get("cycle_settings")
                cycle_settings = cycle_settings if isinstance(cycle_settings, Mapping) else {}
                expected_bundle_revision = str(cycle_settings.get("bundle_revision") or "").strip()
                actual_bundle_revision = str(bundle_row.get("bundle_revision") or "").strip()
                if expected_bundle_revision and expected_bundle_revision != actual_bundle_revision:
                    raise SnapshotBuildError(
                        (
                            f"У grow cycle {grow_cycle_id} не совпадает bundle revision: "
                            f"expected={expected_bundle_revision} actual={actual_bundle_revision or 'empty'}"
                        ),
                        code=ErrorCodes.AE3_SNAPSHOT_BUNDLE_INVALID,
                    )

                bundle_config = bundle_row.get("config")
                if not isinstance(bundle_config, Mapping):
                    raise SnapshotBuildError(
                        f"У grow cycle {grow_cycle_id} некорректный automation bundle config",
                        code=ErrorCodes.AE3_SNAPSHOT_BUNDLE_INVALID,
                    )

                system_bundle = bundle_config.get("system")
                pump_calibration_policy = (
                    system_bundle.get("pump_calibration_policy") if isinstance(system_bundle, Mapping) else None
                )

                zone_bundle = bundle_config.get("zone")
                if not isinstance(zone_bundle, Mapping):
                    raise SnapshotBuildError(
                        f"У grow cycle {grow_cycle_id} отсутствует zone bundle",
                        code=ErrorCodes.AE3_SNAPSHOT_ZONE_BUNDLE_MISSING,
                    )

                logic_profile = zone_bundle.get("logic_profile")
                if not isinstance(logic_profile, Mapping):
                    raise SnapshotBuildError(
                        f"У зоны {zone_id} отсутствует active logic profile bundle",
                        code=ErrorCodes.AE3_SNAPSHOT_LOGIC_PROFILE_BUNDLE_MISSING,
                    )

                active_profile = logic_profile.get("active_profile")
                if not isinstance(active_profile, Mapping):
                    raise SnapshotBuildError(
                        f"У зоны {zone_id} отсутствует active automation logic profile",
                        code=ErrorCodes.AE3_SNAPSHOT_ACTIVE_LOGIC_PROFILE_MISSING,
                    )

                profile_row = {
                    "mode": logic_profile.get("active_mode"),
                    "updated_at": active_profile.get("updated_at"),
                    "command_plans": active_profile.get("command_plans"),
                    "subsystems": active_profile.get("subsystems"),
                }

                cycle_bundle = bundle_config.get("cycle")
                override_rows = self._ports.bundle_override_rows(cycle_bundle)

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

                pid_config_rows = self._ports.bundle_pid_config_rows(zone_bundle)
                correction_config_row = self._ports.bundle_correction_config_row(zone_bundle)
                process_calibration_rows = self._ports.bundle_process_calibration_rows(zone_bundle)

                freshness_sec = _node_freshness_fallback_sec()
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
                      AND (
                          LOWER(TRIM(COALESCE(n.status, ''))) = 'online'
                          OR COALESCE(n.last_seen_at, n.last_heartbeat_at, n.updated_at)
                                 >= NOW() - ($2 * INTERVAL '1 second')
                      )
                      AND UPPER(TRIM(COALESCE(nc.type, ''))) IN ('ACTUATOR', 'SERVICE')
                      AND COALESCE(nc.is_active, TRUE) = TRUE
                    ORDER BY n.id ASC, nc.id ASC
                    """,
                    zone_id,
                    freshness_sec,
                )

                zone_nodes_diag_rows: List[Mapping[str, Any]] = []
                if not actuator_rows:
                    zone_nodes_diag_rows = await conn.fetch(
                        """
                        SELECT
                            n.uid AS node_uid,
                            LOWER(COALESCE(n.type, '')) AS node_type,
                            LOWER(TRIM(COALESCE(n.status, ''))) AS status,
                            EXTRACT(
                                EPOCH FROM (
                                    NOW() - COALESCE(
                                        n.last_seen_at,
                                        n.last_heartbeat_at,
                                        n.updated_at
                                    )
                                )
                            )::BIGINT AS last_seen_age_sec,
                            COUNT(nc.id) FILTER (
                                WHERE UPPER(TRIM(COALESCE(nc.type, ''))) IN ('ACTUATOR', 'SERVICE')
                                  AND COALESCE(nc.is_active, TRUE) = TRUE
                            ) AS active_actuator_count
                        FROM nodes n
                        LEFT JOIN node_channels nc
                            ON nc.node_id = n.id
                        WHERE n.zone_id = $1
                        GROUP BY n.id
                        ORDER BY n.id ASC
                        """,
                        zone_id,
                    )

                command_plans = profile_row.get("command_plans")
                if not isinstance(command_plans, Mapping) or not command_plans:
                    raise SnapshotBuildError(
                        f"У зоны {zone_id} пустой command_plans",
                        code=ErrorCodes.AE3_SNAPSHOT_EMPTY_COMMAND_PLANS,
                    )

                normalized_overrides = self._ports.normalize_override_rows(override_rows)
                phase_targets = self._ports.build_phase_targets(zone_row=zone_row)
                targets = self._ports.build_targets(
                    zone_row=zone_row,
                    override_rows=normalized_overrides,
                    profile_row=profile_row,
                )
                diagnostics_execution = self._ports.resolve_diagnostics_execution(
                    zone_row=zone_row,
                    override_rows=normalized_overrides,
                    profile_row=profile_row,
                )
                telemetry_last = self._ports.build_telemetry_last(telemetry_rows)
                pid_state = self._ports.build_pid_state(pid_state_rows)
                pid_configs = self._ports.build_pid_configs(pid_config_rows)
                correction_config = self._ports.build_correction_config(correction_config_row)
                if isinstance(correction_config, Mapping):
                    correction_config = self._ports.merge_pump_calibration_policy(
                        correction_config,
                        pump_calibration_policy,
                    )
                process_calibrations = self._ports.build_process_calibrations(process_calibration_rows)
                actuators = tuple(
                    ZoneActuatorRef(
                        node_uid=str(row.get("node_uid") or "").strip(),
                        node_type=str(row.get("node_type") or "").strip().lower(),
                        channel=str(row.get("channel") or "default").strip().lower() or "default",
                        node_channel_id=int(row["node_channel_id"]),
                        channel_type=str(row.get("channel_type") or "ACTUATOR").strip().upper() or "ACTUATOR",
                        role=str(row.get("role") or "").strip().lower() or None,
                        pump_calibration=self._ports.extract_pump_calibration(
                            row,
                            pump_calibration_policy=pump_calibration_policy,
                        ),
                    )
                    for row in actuator_rows
                    if str(row.get("node_uid") or "").strip()
                )
                if not actuators:
                    raise SnapshotBuildError(
                        f"У зоны {zone_id} отсутствуют online actuator channels",
                        code=ErrorCodes.AE3_SNAPSHOT_NO_ONLINE_ACTUATOR_CHANNELS,
                        details=self._ports.build_no_actuators_diagnostics(
                            zone_id=zone_id,
                            diag_rows=zone_nodes_diag_rows,
                        ),
                    )

                from .dli_light_series import load_dli_light_series

                dli_light_series = await load_dli_light_series(
                    conn,
                    zone_id=zone_id,
                    targets=targets,
                    greenhouse_timezone=(
                        str(zone_row.get("greenhouse_timezone")).strip()
                        if isinstance(zone_row.get("greenhouse_timezone"), str)
                        else None
                    ),
                )

        return ZoneSnapshot(
            zone_id=int(zone_row["zone_id"]),
            greenhouse_id=int(zone_row["greenhouse_id"]) if zone_row.get("greenhouse_id") is not None else None,
            automation_runtime=str(zone_row.get("automation_runtime") or "").strip().lower(),
            bundle_revision=actual_bundle_revision or None,
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
            config_revision=(
                int(zone_row["zone_config_revision"]) if zone_row.get("zone_config_revision") is not None else None
            ),
            dli_light_series=dli_light_series,
        )

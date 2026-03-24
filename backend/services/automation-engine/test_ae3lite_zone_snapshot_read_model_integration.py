from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4

import pytest

from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import SnapshotBuildError
from ae3lite.domain.services import CycleStartPlanner
from ae3lite.infrastructure.read_models import PgZoneSnapshotReadModel
from common.db import execute, fetch


def _merge_dict(base: dict, patch: dict) -> dict:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
            continue
        merged[key] = value
    return merged


async def _resolve_active_grow_cycle_id(zone_id: int) -> int:
    rows = await fetch(
        """
        SELECT id
        FROM grow_cycles
        WHERE zone_id = $1
          AND status IN ('PLANNED', 'RUNNING', 'PAUSED')
        ORDER BY id DESC
        LIMIT 1
        """,
        zone_id,
    )
    return int(rows[0]["id"])


async def _upsert_cycle_bundle(grow_cycle_id: int, patch: dict) -> None:
    rows = await fetch(
        """
        SELECT config
        FROM automation_effective_bundles
        WHERE scope_type = 'grow_cycle'
          AND scope_id = $1
        LIMIT 1
        """,
        grow_cycle_id,
    )
    current = rows[0]["config"] if rows else {}
    if isinstance(current, str):
        current = json.loads(current)
    if not isinstance(current, dict):
        current = {}

    config = _merge_dict(
        {
            "schema_version": 1,
            "system": {},
            "zone": {},
            "cycle": {
                "start_snapshot": {},
                "phase_overrides": {},
                "manual_overrides": [],
            },
        },
        current,
    )
    config = _merge_dict(config, patch)
    bundle_revision = f"test-{uuid4().hex}"

    await execute(
        """
        INSERT INTO automation_effective_bundles (
            scope_type,
            scope_id,
            bundle_revision,
            schema_revision,
            config,
            violations,
            status,
            compiled_at,
            inputs_checksum,
            created_at,
            updated_at
        )
        VALUES (
            'grow_cycle',
            $1,
            $2,
            'test-schema-v1',
            $3::jsonb,
            '[]'::jsonb,
            'valid',
            NOW(),
            $2,
            NOW(),
            NOW()
        )
        ON CONFLICT (scope_type, scope_id) DO UPDATE
        SET bundle_revision = EXCLUDED.bundle_revision,
            schema_revision = EXCLUDED.schema_revision,
            config = EXCLUDED.config,
            violations = EXCLUDED.violations,
            status = EXCLUDED.status,
            compiled_at = EXCLUDED.compiled_at,
            inputs_checksum = EXCLUDED.inputs_checksum,
            updated_at = EXCLUDED.updated_at
        """,
        grow_cycle_id,
        bundle_revision,
        config,
    )


async def _upsert_zone_bundle(zone_id: int, zone_patch: dict) -> None:
    grow_cycle_id = await _resolve_active_grow_cycle_id(zone_id)
    await _upsert_cycle_bundle(grow_cycle_id, {"zone": zone_patch})


async def _insert_greenhouse(prefix: str) -> int:
    short_uid = f"gh-{uuid4().hex[:20]}"
    short_token = f"pt-{uuid4().hex[:20]}"
    rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        short_uid,
        f"{prefix}-gh",
        short_token,
    )
    return int(rows[0]["id"])


async def _insert_zone(prefix: str, *, greenhouse_id: int) -> int:
    short_uid = f"zn-{uuid4().hex[:20]}"
    rows = await fetch(
        """
        INSERT INTO zones (greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at)
        VALUES ($1, $2, $3, 'online', 'ae3', NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        prefix,
        short_uid,
    )
    return int(rows[0]["id"])


async def _insert_recipe_revision(prefix: str) -> tuple[int, int]:
    rows = await fetch(
        """
        INSERT INTO recipes (name, metadata, created_at, updated_at)
        VALUES ($1, '{}'::jsonb, NOW(), NOW())
        RETURNING id
        """,
        f"{prefix}-recipe",
    )
    recipe_id = int(rows[0]["id"])
    rows = await fetch(
        """
        INSERT INTO recipe_revisions (
            recipe_id,
            revision_number,
            status,
            created_at,
            updated_at
        )
        VALUES ($1, 1, 'PUBLISHED', NOW(), NOW())
        RETURNING id
        """,
        recipe_id,
    )
    return recipe_id, int(rows[0]["id"])


async def _insert_grow_cycle(zone_id: int, *, greenhouse_id: int, recipe_revision_id: int) -> int:
    rows = await fetch(
        """
        INSERT INTO grow_cycles (
            greenhouse_id,
            zone_id,
            recipe_revision_id,
            status,
            created_at,
            updated_at
        )
        VALUES ($1, $2, $3, 'RUNNING', NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        zone_id,
        recipe_revision_id,
    )
    return int(rows[0]["id"])


async def _insert_phase(grow_cycle_id: int, *, ph_target: float) -> int:
    rows = await fetch(
        """
        INSERT INTO grow_cycle_phases (
            grow_cycle_id,
            phase_index,
            name,
            ph_target,
            ph_min,
            ph_max,
            ec_target,
            ec_min,
            ec_max,
            irrigation_mode,
            irrigation_interval_sec,
            irrigation_duration_sec,
            extensions,
            created_at,
            updated_at
        )
        VALUES (
            $1,
            0,
            'VEG',
            $2,
            5.50,
            6.10,
            1.40,
            1.20,
            1.60,
            'SUBSTRATE',
            600,
            45,
            $3::jsonb,
            NOW(),
            NOW()
        )
        RETURNING id
        """,
        grow_cycle_id,
        ph_target,
        {
            "targets": {
                "diagnostics": {
                    "execution": {
                        "workflow": "cycle_start",
                        "startup": {
                            "clean_fill_timeout_sec": 30,
                        },
                    }
                }
            }
        },
    )
    return int(rows[0]["id"])


async def _insert_profile(zone_id: int) -> None:
    execution = {
        "workflow": "cycle_start",
        "topology": "two_tank_drip_substrate_trays",
        "required_node_types": ["irrig"],
        "startup": {
            "level_poll_interval_sec": 11,
            "clean_fill_timeout_sec": 30,
            "solution_fill_timeout_sec": 45,
            "prepare_recirculation_timeout_sec": 600,
        },
        "target_ph": 5.8,
        "target_ec": 1.4,
        "prepare_tolerance": {"ph_pct": 15, "ec_pct": 25},
        "two_tank_commands": {
            "clean_fill_start": [{"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": True}}],
            "clean_fill_stop": [{"channel": "valve_clean_fill", "cmd": "set_relay", "params": {"state": False}}],
            "solution_fill_start": [
                {"channel": "valve_clean_supply", "cmd": "set_relay", "params": {"state": True}},
                {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": True}},
                {"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}},
            ],
            "solution_fill_stop": [
                {"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}},
                {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": False}},
                {"channel": "valve_clean_supply", "cmd": "set_relay", "params": {"state": False}},
            ],
            "prepare_recirculation_start": [
                {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": True}},
                {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": True}},
                {"channel": "pump_main", "cmd": "set_relay", "params": {"state": True}},
            ],
            "prepare_recirculation_stop": [
                {"channel": "pump_main", "cmd": "set_relay", "params": {"state": False}},
                {"channel": "valve_solution_fill", "cmd": "set_relay", "params": {"state": False}},
                {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": False}},
            ],
        },
    }
    await _upsert_zone_bundle(
        zone_id,
        {
            "logic_profile": {
                "active_mode": "working",
                "active_profile": {
                    "mode": "working",
                    "updated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                    "subsystems": {"diagnostics": {"execution": execution}},
                    "command_plans": {
                        "schema_version": 1,
                        "plan_version": 1,
                        "plans": {
                            "diagnostics": {
                                "execution": execution,
                                "steps": [
                                    {
                                        "name": "pump_start",
                                        "channel": "irrigation_pump",
                                        "cmd": "set_relay",
                                        "params": {"state": True},
                                        "timeout_sec": 20,
                                    }
                                ],
                            }
                        },
                    },
                },
            }
        },
    )


async def _insert_correction_config(zone_id: int) -> None:
    """Insert a complete authority correction bundle fixture for fail-closed runtime validation."""
    minimal_cfg = {
        "base": {
            "runtime": {
                "required_node_type": "irrig",
                "clean_fill_timeout_sec": 1200,
                "solution_fill_timeout_sec": 1800,
                "clean_fill_retry_cycles": 1,
                "level_switch_on_threshold": 0.5,
                "clean_max_sensor_label": "level_clean_max",
                "clean_min_sensor_label": "level_clean_min",
                "solution_max_sensor_label": "level_solution_max",
                "solution_min_sensor_label": "level_solution_min",
            },
            "timing": {
                "sensor_mode_stabilization_time_sec": 60,
                "stabilization_sec": 60,
                "telemetry_max_age_sec": 60,
                "irr_state_max_age_sec": 30,
                "level_poll_interval_sec": 10,
            },
            "retry": {
                "max_ec_correction_attempts": 5,
                "max_ph_correction_attempts": 5,
                "prepare_recirculation_timeout_sec": 1200,
                "prepare_recirculation_max_attempts": 3,
                "prepare_recirculation_max_correction_attempts": 20,
            },
            "dosing": {
                "solution_volume_l": 100.0,
                "dose_ec_channel": "ec_npk_pump",
                "dose_ph_up_channel": "ph_base_pump",
                "dose_ph_down_channel": "ph_acid_pump",
                "max_ec_dose_ml": 50.0,
                "max_ph_dose_ml": 20.0,
            },
            "tolerance": {
                "prepare_tolerance": {"ph_pct": 15.0, "ec_pct": 25.0},
            },
            "controllers": {
                "ph": {
                    "mode": "cross_coupled_pi_d",
                    "kp": 5.0,
                    "ki": 0.05,
                    "kd": 0.0,
                    "derivative_filter_alpha": 0.35,
                    "deadband": 0.05,
                    "max_dose_ml": 20.0,
                    "min_interval_sec": 90,
                    "max_integral": 20.0,
                    "anti_windup": {"enabled": True},
                    "overshoot_guard": {"enabled": True, "hard_min": 4.0, "hard_max": 9.0},
                    "no_effect": {"enabled": True, "max_count": 3},
                    "observe": {
                        "telemetry_period_sec": 2,
                        "window_min_samples": 3,
                        "decision_window_sec": 6,
                        "observe_poll_sec": 2,
                        "min_effect_fraction": 0.25,
                        "stability_max_slope": 0.02,
                        "no_effect_consecutive_limit": 3,
                    },
                },
                "ec": {
                    "mode": "supervisory_allocator",
                    "kp": 30.0,
                    "ki": 0.3,
                    "kd": 0.0,
                    "derivative_filter_alpha": 0.35,
                    "deadband": 0.1,
                    "max_dose_ml": 50.0,
                    "min_interval_sec": 120,
                    "max_integral": 100.0,
                    "anti_windup": {"enabled": True},
                    "overshoot_guard": {"enabled": True, "hard_min": 0.0, "hard_max": 10.0},
                    "no_effect": {"enabled": True, "max_count": 3},
                    "observe": {
                        "telemetry_period_sec": 2,
                        "window_min_samples": 3,
                        "decision_window_sec": 6,
                        "observe_poll_sec": 2,
                        "min_effect_fraction": 0.25,
                        "stability_max_slope": 0.05,
                        "no_effect_consecutive_limit": 3,
                    },
                },
            },
            "safety": {
                "safe_mode_on_no_effect": True,
                "block_on_active_no_effect_alert": True,
            },
        },
        "phases": {
            "solution_fill": {},
            "tank_recirc": {},
            "irrigation": {},
        },
        "meta": {},
    }
    await _upsert_zone_bundle(
        zone_id,
        {
            "correction": {
                "phase_overrides": {},
                "resolved_config": minimal_cfg,
            }
        },
    )


async def _insert_process_calibrations(zone_id: int) -> None:
    calibration = {
        "ec_gain_per_ml": 0.10,
        "ph_up_gain_per_ml": 0.05,
        "ph_down_gain_per_ml": -0.05,
        "transport_delay_sec": 6,
        "settle_sec": 4,
        "confidence": 0.90,
        "source": "test-fixture",
        "is_active": True,
        "meta": {},
    }
    await _upsert_zone_bundle(
        zone_id,
        {
            "process_calibration": {
                "solution_fill": dict(calibration),
                "tank_recirc": dict(calibration),
                "irrigation": dict(calibration),
            }
        },
    )


async def _insert_irrig_node(zone_id: int, *, prefix: str) -> tuple[int, str]:
    short_uid = f"nd-{uuid4().hex[:20]}"
    rows = await fetch(
        """
        INSERT INTO nodes (zone_id, uid, type, status, created_at, updated_at)
        VALUES ($1, $2, 'irrig', 'online', NOW(), NOW())
        RETURNING id
        """,
        zone_id,
        short_uid,
    )
    return int(rows[0]["id"]), short_uid


async def _insert_sensor(*, greenhouse_id: int, zone_id: int, node_id: int, sensor_type: str, label: str) -> int:
    rows = await fetch(
        """
        INSERT INTO sensors (
            greenhouse_id,
            zone_id,
            node_id,
            scope,
            type,
            label,
            unit,
            is_active,
            created_at,
            updated_at
        )
        VALUES ($1, $2, $3, 'inside', $4, $5, '%', TRUE, NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        zone_id,
        node_id,
        sensor_type,
        label,
    )
    return int(rows[0]["id"])


async def _cleanup(prefix: str) -> None:
    await execute(
        """
        DELETE FROM ae_stage_transitions
        WHERE task_id IN (
            SELECT t.id
            FROM ae_tasks t
            JOIN zones z ON z.id = t.zone_id
            JOIN greenhouses g ON g.id = z.greenhouse_id
            WHERE g.name LIKE $1
        )
        """,
        f"{prefix}%",
    )
    await execute(
        """
        DELETE FROM ae_commands
        WHERE task_id IN (
            SELECT t.id
            FROM ae_tasks t
            JOIN zones z ON z.id = t.zone_id
            JOIN greenhouses g ON g.id = z.greenhouse_id
            WHERE g.name LIKE $1
        )
        """,
        f"{prefix}%",
    )
    await execute(
        """
        DELETE FROM ae_zone_leases
        WHERE zone_id IN (
            SELECT z.id
            FROM zones z
            JOIN greenhouses g ON g.id = z.greenhouse_id
            WHERE g.name LIKE $1
        )
        """,
        f"{prefix}%",
    )
    await execute(
        """
        DELETE FROM commands
        WHERE zone_id IN (
            SELECT z.id
            FROM zones z
            JOIN greenhouses g ON g.id = z.greenhouse_id
            WHERE g.name LIKE $1
        )
        """,
        f"{prefix}%",
    )
    await execute("DELETE FROM greenhouses WHERE name LIKE $1", f"{prefix}%")


@pytest.mark.asyncio
async def test_zone_snapshot_read_model_and_planner_build_cycle_start_plan() -> None:
    prefix = f"ae3-snapshot-{uuid4().hex}"
    read_model = PgZoneSnapshotReadModel()
    planner = CycleStartPlanner()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(f"{prefix}-zone", greenhouse_id=greenhouse_id)
        _, recipe_revision_id = await _insert_recipe_revision(prefix)
        grow_cycle_id = await _insert_grow_cycle(
            zone_id,
            greenhouse_id=greenhouse_id,
            recipe_revision_id=recipe_revision_id,
        )
        phase_id = await _insert_phase(grow_cycle_id, ph_target=5.8)
        await execute(
            """
            UPDATE grow_cycles
            SET current_phase_id = $2,
                started_at = $3,
                recipe_started_at = $3,
                updated_at = $3
            WHERE id = $1
            """,
            grow_cycle_id,
            phase_id,
            now,
        )
        await _upsert_cycle_bundle(
            grow_cycle_id,
            {
                "cycle": {
                    "manual_overrides": [
                        {"parameter": "ph.target", "value_type": "decimal", "value": "5.90", "is_active": True},
                        {
                            "parameter": "diagnostics.execution.startup.clean_fill_timeout_sec",
                            "value_type": "integer",
                            "value": "47",
                            "is_active": True,
                        },
                    ]
                }
            },
        )
        await _insert_profile(zone_id)
        await _insert_correction_config(zone_id)
        await _insert_process_calibrations(zone_id)
        await execute(
            """
            INSERT INTO zone_workflow_state (zone_id, workflow_phase, version, updated_at, payload)
            VALUES ($1, 'waiting_command', 7, NOW(), '{}'::jsonb)
            """,
            zone_id,
        )

        node_id, node_uid = await _insert_irrig_node(zone_id, prefix=prefix)
        sensor_id = await _insert_sensor(
            greenhouse_id=greenhouse_id,
            zone_id=zone_id,
            node_id=node_id,
            sensor_type="WATER_LEVEL",
            label="level_clean_min",
        )
        await execute(
            """
            INSERT INTO telemetry_last (sensor_id, last_value, last_ts, last_quality, updated_at)
            VALUES ($1, 81.50, NOW(), 'GOOD', NOW())
            """,
            sensor_id,
        )
        await execute(
            """
            INSERT INTO pid_state (
                zone_id,
                pid_type,
                integral,
                prev_error,
                prev_derivative,
                last_output_ms,
                last_dose_at,
                stats,
                current_zone,
                updated_at
            )
            VALUES ($1, 'ph', 1.25, 0.15, 0.05, 1200, NOW(), $2::jsonb, 'mixing', NOW())
            """,
            zone_id,
            {"window": 3},
        )
        await _upsert_zone_bundle(
            zone_id,
            {
                "pid": {
                    "ph": {"config": {"kp": 1.2, "ki": 0.4, "kd": 0.1}},
                    "ec": {"config": {"kp": 1.5, "ki": 0.3, "kd": 0.0}},
                }
            },
        )

        node_channel_ids: dict[str, int] = {}
        for channel in (
            "valve_clean_fill",
            "valve_clean_supply",
            "valve_solution_fill",
            "valve_solution_supply",
            "pump_main",
        ):
            rows = await fetch(
                """
                INSERT INTO node_channels (node_id, channel, type, config, created_at, updated_at)
                VALUES ($1, $2, 'ACTUATOR', $3::jsonb, NOW(), NOW())
                RETURNING id
                """,
                node_id,
                channel,
                {"pump_calibration": {"ml_per_sec": 7.5, "source": "legacy_config"}} if channel == "pump_main" else {},
            )
            node_channel_ids[channel] = int(rows[0]["id"])
        node_channel_id = node_channel_ids["pump_main"]
        await execute(
            """
            INSERT INTO pump_calibrations (
                node_channel_id,
                ml_per_sec,
                k_ms_per_ml_l,
                source,
                quality_score,
                sample_count,
                valid_from,
                is_active,
                created_at,
                updated_at
            )
            VALUES ($1, 12.50, 1.80, 'manual_calibration', 0.95, 4, NOW() - INTERVAL '1 minute', TRUE, NOW(), NOW())
            """,
            node_channel_id,
        )
        rows = await fetch(
            """
            INSERT INTO infrastructure_instances (
                owner_type,
                owner_id,
                asset_type,
                label,
                required,
                created_at,
                updated_at
            )
            VALUES ('zone', $1, 'PUMP', 'Main Pump', TRUE, NOW(), NOW())
            RETURNING id
            """,
            zone_id,
        )
        asset_id = int(rows[0]["id"])
        await execute(
            """
            INSERT INTO channel_bindings (
                infrastructure_instance_id,
                node_channel_id,
                direction,
                role,
                created_at,
                updated_at
            )
            VALUES ($1, $2, 'actuator', 'irrigation_pump', NOW(), NOW())
            """,
            asset_id,
            node_channel_id,
        )

        snapshot = await read_model.load(zone_id=zone_id)
        pump_channel = next(item for item in snapshot.actuators if item.channel == "pump_main")

        assert snapshot.zone_id == zone_id
        assert snapshot.greenhouse_id == greenhouse_id
        assert snapshot.grow_cycle_id == grow_cycle_id
        assert snapshot.workflow_phase == "waiting_command"
        assert snapshot.workflow_version == 7
        assert snapshot.targets["ph"]["target"] == 5.9
        assert snapshot.targets["diagnostics"]["execution"]["startup"]["level_poll_interval_sec"] == 11
        assert snapshot.diagnostics_execution["workflow"] == "cycle_start"
        assert snapshot.diagnostics_execution["startup"]["level_poll_interval_sec"] == 11
        assert snapshot.telemetry_last["water_level"]["value"] == 81.5
        assert snapshot.pid_state["ph"]["integral"] == 1.25
        assert snapshot.pid_configs["ph"]["config"]["kp"] == 1.2
        assert pump_channel.role == "irrigation_pump"
        assert pump_channel.node_channel_id == node_channel_id
        assert pump_channel.pump_calibration["ml_per_sec"] == 12.5
        assert pump_channel.pump_calibration["source"] == "manual_calibration"

        task = AutomationTask.from_row({
            "id": 900, "zone_id": zone_id, "task_type": "cycle_start", "status": "claimed",
            "idempotency_key": f"{prefix}-task", "scheduled_for": now, "due_at": now,
            "claimed_by": "worker-a", "claimed_at": now,
            "error_code": None, "error_message": None,
            "created_at": now, "updated_at": now, "completed_at": None,
            "topology": "two_tank", "intent_source": None, "intent_trigger": None,
            "intent_id": None, "intent_meta": {},
            "current_stage": "startup", "workflow_phase": "idle",
            "stage_deadline_at": None, "stage_retry_count": 0, "stage_entered_at": None,
            "clean_fill_cycle": 0, "corr_step": None,
        })

        plan = planner.build(task=task, snapshot=snapshot)

        assert plan.workflow == "cycle_start"
        assert plan.topology == "two_tank_drip_substrate_trays"
        assert plan.steps == ()
        assert plan.named_plans["clean_fill_start"][0].node_uid == node_uid
        assert plan.named_plans["clean_fill_start"][0].channel == "valve_clean_fill"
        assert plan.named_plans["solution_fill_start"][-1].channel == "pump_main"
        assert plan.named_plans["irr_state_probe"][0].channel == "storage_state"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_zone_snapshot_read_model_fails_closed_without_active_grow_cycle() -> None:
    prefix = f"ae3-snapshot-missing-cycle-{uuid4().hex}"
    read_model = PgZoneSnapshotReadModel()

    try:
        greenhouse_id = await _insert_greenhouse(prefix)
        zone_id = await _insert_zone(f"{prefix}-zone", greenhouse_id=greenhouse_id)

        with pytest.raises(SnapshotBuildError):
            await read_model.load(zone_id=zone_id)
    finally:
        await _cleanup(prefix)

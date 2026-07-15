"""Интеграционный тест greenhouse climate tick: intent → run_tick → HL publish → commands=DONE → state.

HTTP-ingress `POST /greenhouses/{id}/start-climate-tick` только ставит BackgroundTask и вызывает тот же
`run_greenhouse_climate_tick`; здесь проверяем полный DB-пайплайн исполнителя и ожидание терминального
статуса в `commands` (как делает runtime через `_wait_command_terminal`).

Реальный history-logger и MQTT в этом тесте не поднимаются: клиент подменяется фейком, который
вставляет строку `commands` со статусом `DONE` и тем же `cmd_id`, что возвращает HL-контракт.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import pytest

from ae3lite.greenhouse_climate.run_tick import run_greenhouse_climate_tick
from common.db import execute, fetch


class _FakeHistoryLoggerClient:
    """Имитирует HL: фиксирует вызовы и сразу создаёт `commands` со статусом DONE (как после node response)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def publish(
        self,
        *,
        greenhouse_uid: str,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        params: Mapping[str, Any],
        cmd_id: str | None = None,
    ) -> str:
        cid = (cmd_id or str(uuid.uuid4())).strip()
        self.calls.append(
            {
                "greenhouse_uid": greenhouse_uid,
                "zone_id": zone_id,
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
                "params": dict(params),
                "cmd_id": cid,
            }
        )
        await execute(
            """
            INSERT INTO commands (
                zone_id,
                channel,
                cmd,
                params,
                status,
                cmd_id,
                source,
                created_at,
                updated_at
            )
            VALUES ($1, $2, $3, $4::jsonb, 'DONE', $5, 'automation-engine', NOW(), NOW())
            """,
            zone_id,
            channel,
            cmd,
            json.dumps(dict(params)),
            cid,
        )
        return cid


class _FakeAlertPublisher:
    def __init__(self) -> None:
        self.active: list[dict[str, Any]] = []
        self.resolved: list[dict[str, Any]] = []

    async def raise_active(self, **kwargs: Any) -> bool:
        self.active.append(dict(kwargs))
        return True

    async def resolve(self, **kwargs: Any) -> bool:
        self.resolved.append(dict(kwargs))
        return True


def _bundle_config() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "greenhouse": {
            "logic_profile": {
                "active_mode": "working",
                "profiles": {
                    "working": {
                        "subsystems": {
                            "climate": {
                                "enabled": True,
                                "control_mode": "auto",
                                "execution": {
                                    "decision_interval_sec": 60,
                                    "min_command_interval_sec": 0,
                                    "max_step_pct": 25,
                                    "position_deadband_pct": 0,
                                    "sensor_freshness_sec": 7200,
                                    "day_schedule": {
                                        "start_local": "00:00",
                                        "end_local": "23:59",
                                    },
                                    "command_terminal_timeout_sec": 5,
                                    "command_poll_sec": 0.15,
                                    "greenhouse_targets": {
                                        "temp_max_c": 28,
                                        "temp_min_c": 18,
                                        "humidity_min_pct": 40,
                                        "humidity_max_pct": 95,
                                    },
                                    "temp_full_open_delta_c": 2,
                                    "day_min_open_pct": 0,
                                    "day_max_open_pct": 100,
                                    "night_min_open_pct": 0,
                                    "night_max_open_pct": 100,
                                },
                            }
                        }
                    }
                },
            }
        },
    }


def _disabled_bundle_config_without_targets() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "greenhouse": {
            "logic_profile": {
                "active_mode": "working",
                "profiles": {
                    "working": {
                        "subsystems": {
                            "climate": {
                                "enabled": False,
                                "control_mode": "auto",
                                "execution": {
                                    "decision_interval_sec": 60,
                                },
                            }
                        }
                    }
                },
            }
        },
    }


async def _cleanup_greenhouse(*, greenhouse_id: int, zone_id: int, sensor_ids: list[int]) -> None:
    await execute("DELETE FROM greenhouse_automation_intents WHERE greenhouse_id = $1", greenhouse_id)
    await execute("DELETE FROM greenhouse_automation_leases WHERE greenhouse_id = $1", greenhouse_id)
    await execute("DELETE FROM greenhouse_automation_state WHERE greenhouse_id = $1", greenhouse_id)
    await execute("DELETE FROM greenhouse_automation_tasks WHERE greenhouse_id = $1", greenhouse_id)
    await execute("DELETE FROM greenhouse_manual_overrides WHERE greenhouse_id = $1", greenhouse_id)
    await execute("DELETE FROM automation_effective_bundles WHERE scope_type = 'greenhouse' AND scope_id = $1", greenhouse_id)
    for sid in sensor_ids:
        await execute("DELETE FROM telemetry_last WHERE sensor_id = $1", sid)
        await execute("DELETE FROM sensors WHERE id = $1", sid)
    await execute("DELETE FROM commands WHERE zone_id = $1", zone_id)
    await execute(
        """
        DELETE FROM channel_bindings
        WHERE infrastructure_instance_id IN (
            SELECT id FROM infrastructure_instances
            WHERE owner_type = 'greenhouse' AND owner_id = $1
        )
        """,
        greenhouse_id,
    )
    await execute("DELETE FROM infrastructure_instances WHERE owner_type = 'greenhouse' AND owner_id = $1", greenhouse_id)
    await execute("DELETE FROM node_channels WHERE node_id IN (SELECT id FROM nodes WHERE zone_id = $1)", zone_id)
    await execute("DELETE FROM nodes WHERE zone_id = $1", zone_id)
    await execute("DELETE FROM zones WHERE id = $1", zone_id)
    await execute("DELETE FROM greenhouses WHERE id = $1", greenhouse_id)


@pytest.mark.asyncio
async def test_disabled_greenhouse_climate_tick_does_not_require_targets() -> None:
    prefix = f"gh-disabled-{uuid.uuid4().hex[:12]}"
    gh_uid = f"gh-{uuid.uuid4().hex[:20]}"
    fake_hl = _FakeHistoryLoggerClient()
    fake_alerts = _FakeAlertPublisher()

    gh_rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        gh_uid,
        prefix,
        f"pt-{uuid.uuid4().hex[:24]}",
    )
    greenhouse_id = int(gh_rows[0]["id"])
    rev = uuid.uuid4().hex
    await execute(
        """
        INSERT INTO automation_effective_bundles (
            scope_type, scope_id, bundle_revision, schema_revision, config, violations, status, compiled_at, inputs_checksum, created_at, updated_at
        )
        VALUES ('greenhouse', $1, $2, '1', $3::jsonb, '[]'::jsonb, 'valid', NOW(), $4, NOW(), NOW())
        """,
        greenhouse_id,
        rev,
        _disabled_bundle_config_without_targets(),
        rev,
    )
    await execute(
        """
        INSERT INTO greenhouse_automation_state (
            greenhouse_id, climate_enabled, control_mode, left_position_pct, right_position_pct,
            recommended_left_position_pct, recommended_right_position_pct,
            created_at, updated_at
        )
        VALUES ($1, false, 'auto', 10, 20, 10, 20, NOW(), NOW())
        """,
        greenhouse_id,
    )
    idem = f"idem-{uuid.uuid4().hex}"
    await execute(
        """
        INSERT INTO greenhouse_automation_intents (
            greenhouse_id, intent_type, task_type, intent_source, idempotency_key, status, created_at, updated_at
        )
        VALUES ($1, 'GREENHOUSE_CLIMATE_TICK', 'greenhouse_climate_tick', 'pytest', $2, 'pending', NOW(), NOW())
        """,
        greenhouse_id,
        idem,
    )

    try:
        result = await run_greenhouse_climate_tick(
            greenhouse_id=greenhouse_id,
            idempotency_key=idem,
            history_logger_client=fake_hl,
            alert_publisher=fake_alerts,
        )
        assert result.get("status") == "completed", result
        assert result.get("reason") == "climate_disabled", result
        assert fake_hl.calls == []

        intents = await fetch(
            "SELECT status, error_code FROM greenhouse_automation_intents WHERE greenhouse_id = $1 AND idempotency_key = $2",
            greenhouse_id,
            idem,
        )
        assert intents and str(intents[0]["status"]).lower() == "completed"

        st = await fetch(
            "SELECT climate_enabled, decision_reason, active_alerts_summary FROM greenhouse_automation_state WHERE greenhouse_id = $1",
            greenhouse_id,
        )
        assert st
        assert bool(st[0]["climate_enabled"]) is False
        assert st[0]["decision_reason"] == "climate_disabled"
        assert st[0]["active_alerts_summary"] == []
        assert fake_alerts.active == []
        assert {item["code"] for item in fake_alerts.resolved} >= {
            "GREENHOUSE_WEATHER_STATION_STALE",
            "GREENHOUSE_VENT_COMMAND_FAILED",
        }
    finally:
        await _cleanup_greenhouse(greenhouse_id=greenhouse_id, zone_id=-1, sensor_ids=[])


@pytest.mark.asyncio
async def test_greenhouse_climate_tick_intent_to_done_updates_state() -> None:
    prefix = f"gh-tick-{uuid.uuid4().hex[:12]}"
    gh_uid = f"gh-{uuid.uuid4().hex[:20]}"
    z_uid = f"zn-{uuid.uuid4().hex[:20]}"
    fake_hl = _FakeHistoryLoggerClient()
    fake_alerts = _FakeAlertPublisher()
    sensor_ids: list[int] = []

    gh_rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        gh_uid,
        prefix,
        f"pt-{uuid.uuid4().hex[:24]}",
    )
    greenhouse_id = int(gh_rows[0]["id"])

    z_rows = await fetch(
        """
        INSERT INTO zones (greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at)
        VALUES ($1, $2, $3, 'online', 'ae3', NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        f"{prefix}-zone",
        z_uid,
    )
    zone_id = int(z_rows[0]["id"])

    node_left_uid = f"nd-{uuid.uuid4().hex[:16]}"
    node_right_uid = f"nd-{uuid.uuid4().hex[:16]}"
    n_left = await fetch(
        """
        INSERT INTO nodes (zone_id, uid, name, type, status, lifecycle_state, created_at, updated_at)
        VALUES ($1, $2, $3, 'relay', 'online', 'ACTIVE', NOW(), NOW())
        RETURNING id
        """,
        zone_id,
        node_left_uid,
        f"{prefix}-vent-l",
    )
    n_right = await fetch(
        """
        INSERT INTO nodes (zone_id, uid, name, type, status, lifecycle_state, created_at, updated_at)
        VALUES ($1, $2, $3, 'relay', 'online', 'ACTIVE', NOW(), NOW())
        RETURNING id
        """,
        zone_id,
        node_right_uid,
        f"{prefix}-vent-r",
    )
    left_node_id = int(n_left[0]["id"])
    right_node_id = int(n_right[0]["id"])

    nc_left = await fetch(
        """
        INSERT INTO node_channels (node_id, channel, type, is_active, created_at, updated_at)
        VALUES ($1, 'roof_vent_left', 'ACTUATOR', true, NOW(), NOW())
        RETURNING id
        """,
        left_node_id,
    )
    nc_right = await fetch(
        """
        INSERT INTO node_channels (node_id, channel, type, is_active, created_at, updated_at)
        VALUES ($1, 'roof_vent_right', 'ACTUATOR', true, NOW(), NOW())
        RETURNING id
        """,
        right_node_id,
    )

    inst = await fetch(
        """
        INSERT INTO infrastructure_instances (owner_type, owner_id, asset_type, label, required, created_at, updated_at)
        VALUES ('greenhouse', $1, 'VENT', $2, false, NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        f"{prefix}-vent-inst",
    )
    infra_id = int(inst[0]["id"])

    await execute(
        """
        INSERT INTO channel_bindings (infrastructure_instance_id, node_channel_id, direction, role, created_at, updated_at)
        VALUES ($1, $2, 'actuator', 'vent_actuator', NOW(), NOW()),
               ($1, $3, 'actuator', 'vent_actuator', NOW(), NOW())
        """,
        infra_id,
        int(nc_left[0]["id"]),
        int(nc_right[0]["id"]),
    )

    cfg = _bundle_config()
    rev = uuid.uuid4().hex
    await execute(
        """
        INSERT INTO automation_effective_bundles (
            scope_type, scope_id, bundle_revision, schema_revision, config, violations, status, compiled_at, inputs_checksum, created_at, updated_at
        )
        VALUES ('greenhouse', $1, $2, '1', $3::jsonb, '[]'::jsonb, 'valid', NOW(), $4, NOW(), NOW())
        """,
        greenhouse_id,
        rev,
        cfg,
        rev,
    )

    s_rows = await fetch(
        """
        INSERT INTO sensors (greenhouse_id, zone_id, node_id, scope, type, label, is_active, created_at, updated_at)
        VALUES ($1, $2, NULL, 'inside', 'TEMPERATURE', 'temp_air', true, NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        zone_id,
    )
    sensor_id = int(s_rows[0]["id"])
    sensor_ids.append(sensor_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await execute(
        """
        INSERT INTO telemetry_last (sensor_id, last_value, last_ts, last_quality, updated_at)
        VALUES ($1, 32.0, $2, 'GOOD', NOW())
        """,
        sensor_id,
        now,
    )

    await execute(
        """
        INSERT INTO greenhouse_automation_state (
            greenhouse_id, climate_enabled, control_mode, left_position_pct, right_position_pct,
            recommended_left_position_pct, recommended_right_position_pct,
            created_at, updated_at
        )
        VALUES ($1, false, 'auto', 0, 0, 0, 0, NOW(), NOW())
        """,
        greenhouse_id,
    )

    idem = f"idem-{uuid.uuid4().hex}"
    await execute(
        """
        INSERT INTO greenhouse_automation_intents (
            greenhouse_id, intent_type, task_type, intent_source, idempotency_key, status, created_at, updated_at
        )
        VALUES ($1, 'GREENHOUSE_CLIMATE_TICK', 'greenhouse_climate_tick', 'pytest', $2, 'pending', NOW(), NOW())
        """,
        greenhouse_id,
        idem,
    )

    try:
        result = await run_greenhouse_climate_tick(
            greenhouse_id=greenhouse_id,
            idempotency_key=idem,
            history_logger_client=fake_hl,
            alert_publisher=fake_alerts,
        )
        assert result.get("status") == "ok", result

        assert len(fake_hl.calls) >= 1
        for c in fake_hl.calls:
            assert c["cmd"] == "set_position"
            assert c["greenhouse_uid"] == gh_uid
            assert int(c["zone_id"]) == zone_id

        intents = await fetch(
            "SELECT status, error_code FROM greenhouse_automation_intents WHERE greenhouse_id = $1 AND idempotency_key = $2",
            greenhouse_id,
            idem,
        )
        assert intents and str(intents[0]["status"]).lower() == "completed"
        assert {item["code"] for item in fake_alerts.active} >= {
            "GREENHOUSE_WEATHER_STATION_STALE",
        }

        st = await fetch("SELECT left_position_pct, right_position_pct, climate_enabled FROM greenhouse_automation_state WHERE greenhouse_id = $1", greenhouse_id)
        assert st
        assert bool(st[0]["climate_enabled"]) is True
        assert int(st[0]["left_position_pct"]) > 0 or int(st[0]["right_position_pct"]) > 0

        for c in fake_hl.calls:
            rows = await fetch("SELECT status FROM commands WHERE cmd_id = $1 LIMIT 1", c["cmd_id"])
            assert rows and str(rows[0]["status"]).upper() == "DONE"
    finally:
        await _cleanup_greenhouse(greenhouse_id=greenhouse_id, zone_id=zone_id, sensor_ids=sensor_ids)


@pytest.mark.asyncio
async def test_greenhouse_climate_busy_lease_returns_intent_to_pending() -> None:
    from ae3lite.greenhouse_climate.run_tick import resolve_greenhouse_lease_owner, run_greenhouse_climate_tick

    prefix = f"gh-busy-{uuid.uuid4().hex[:12]}"
    gh_uid = f"gh-{uuid.uuid4().hex[:20]}"
    fake_hl = _FakeHistoryLoggerClient()
    idem = f"busy-{uuid.uuid4().hex}"
    owner_a = resolve_greenhouse_lease_owner(worker_owner="worker-a")
    gh_rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        gh_uid,
        prefix,
        f"pt-{uuid.uuid4().hex[:24]}",
    )
    greenhouse_id = int(gh_rows[0]["id"])
    zone_id = 0
    sensor_ids: list[int] = []
    try:
        await execute(
            """
            INSERT INTO greenhouse_automation_intents (
                greenhouse_id, intent_type, task_type, intent_source, idempotency_key, status, created_at, updated_at
            )
            VALUES ($1, 'GREENHOUSE_CLIMATE_TICK', 'greenhouse_climate_tick', 'pytest', $2, 'pending', NOW(), NOW())
            """,
            greenhouse_id,
            idem,
        )
        await execute(
            """
            INSERT INTO greenhouse_automation_leases (greenhouse_id, owner, leased_until, updated_at)
            VALUES ($1, $2, NOW() + INTERVAL '5 minutes', NOW())
            """,
            greenhouse_id,
            owner_a,
        )

        result = await run_greenhouse_climate_tick(
            greenhouse_id=greenhouse_id,
            idempotency_key=idem,
            history_logger_client=fake_hl,
            worker_owner="worker-b",
        )
        assert result["reason"] == "greenhouse_climate_busy"
        rows = await fetch(
            "SELECT status FROM greenhouse_automation_intents WHERE greenhouse_id = $1 AND idempotency_key = $2",
            greenhouse_id,
            idem,
        )
        assert rows and rows[0]["status"] == "pending"
    finally:
        await _cleanup_greenhouse(greenhouse_id=greenhouse_id, zone_id=zone_id, sensor_ids=sensor_ids)


@pytest.mark.asyncio
async def test_recover_stale_greenhouse_running_intent_requeues_pending() -> None:
    from ae3lite.greenhouse_climate.recovery import recover_stale_greenhouse_automation

    prefix = f"gh-stale-{uuid.uuid4().hex[:12]}"
    gh_uid = f"gh-{uuid.uuid4().hex[:20]}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_at = now - timedelta(minutes=30)
    idem = f"stale-{uuid.uuid4().hex}"
    gh_rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        gh_uid,
        prefix,
        f"pt-{uuid.uuid4().hex[:24]}",
    )
    greenhouse_id = int(gh_rows[0]["id"])
    zone_id = 0
    sensor_ids: list[int] = []
    try:
        intent_rows = await fetch(
            """
            INSERT INTO greenhouse_automation_intents (
                greenhouse_id, intent_type, task_type, intent_source, idempotency_key,
                status, claimed_at, created_at, updated_at
            )
            VALUES ($1, 'GREENHOUSE_CLIMATE_TICK', 'greenhouse_climate_tick', 'pytest', $2,
                    'running', $3, $3, $3)
            RETURNING id
            """,
            greenhouse_id,
            idem,
            stale_at,
        )
        intent_id = int(intent_rows[0]["id"])
        await execute(
            """
            INSERT INTO greenhouse_automation_tasks (
                greenhouse_id, intent_id, task_type, status, idempotency_key, workflow_stage, created_at, updated_at
            )
            VALUES ($1, $2, 'greenhouse_climate_tick', 'running', $3, 'decision', $4, $4)
            """,
            greenhouse_id,
            intent_id,
            idem,
            stale_at,
        )

        result = await recover_stale_greenhouse_automation(now=now, stale_running_ttl_sec=600)
        assert result["requeued_intents"] == 1

        rows = await fetch(
            "SELECT status FROM greenhouse_automation_intents WHERE id = $1",
            intent_id,
        )
        assert rows and rows[0]["status"] == "pending"
    finally:
        await _cleanup_greenhouse(greenhouse_id=greenhouse_id, zone_id=zone_id, sensor_ids=sensor_ids)

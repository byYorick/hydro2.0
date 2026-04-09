from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from ae3lite.application.adapters import LegacyIntentMapper
from ae3lite.application.use_cases import CreateTaskFromIntentUseCase
from ae3lite.domain.errors import TaskCreateError
from ae3lite.infrastructure.repositories import PgAutomationTaskRepository, PgZoneAlertRepository, PgZoneLeaseRepository
from common.db import execute, fetch


async def _insert_zone(prefix: str) -> int:
    greenhouse_name = prefix[:40]
    greenhouse_uid = f"gh-{uuid4().hex[:20]}"
    provisioning_token = f"gh_{uuid4().hex[:24]}"
    greenhouse_rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, $2, 'UTC', $3, NOW(), NOW())
        RETURNING id
        """,
        greenhouse_uid,
        greenhouse_name,
        provisioning_token,
    )
    greenhouse_id = int(greenhouse_rows[0]["id"])
    zone_name = prefix[:48]
    zone_uid = f"zn-{uuid4().hex[:20]}"
    rows = await fetch(
        """
        INSERT INTO zones (greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at)
        VALUES ($1, $2, $3, 'online', 'ae3', NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        zone_name,
        zone_uid,
    )
    return int(rows[0]["id"])


async def _insert_recipe_revision(prefix: str) -> int:
    recipe_rows = await fetch(
        """
        INSERT INTO recipes (name, metadata, created_at, updated_at)
        VALUES ($1, '{}'::jsonb, NOW(), NOW())
        RETURNING id
        """,
        f"{prefix[:40]}-recipe",
    )
    recipe_id = int(recipe_rows[0]["id"])
    revision_rows = await fetch(
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
    return int(revision_rows[0]["id"])


async def _cleanup(prefix: str) -> None:
    await execute(
        """
        DELETE FROM alerts
        WHERE zone_id IN (
            SELECT id
            FROM zones
            WHERE name LIKE $1
        )
        """,
        f"{prefix}%",
    )
    await execute("DELETE FROM zones WHERE name LIKE $1", f"{prefix}%")
    await execute("DELETE FROM greenhouses WHERE name LIKE $1", f"{prefix}%")
    await execute("DELETE FROM recipes WHERE name LIKE $1", f"{prefix[:40]}%")


async def _insert_active_grow_cycle(zone_id: int, prefix: str) -> int:
    recipe_revision_id = await _insert_recipe_revision(prefix)
    cycle_rows = await fetch(
        """
        INSERT INTO grow_cycles (
            greenhouse_id,
            zone_id,
            recipe_revision_id,
            status,
            created_at,
            updated_at
        )
        VALUES (
            (SELECT greenhouse_id FROM zones WHERE id = $1),
            $1,
            $2,
            'RUNNING',
            NOW(),
            NOW()
        )
        RETURNING id
        """,
        zone_id,
        recipe_revision_id,
    )
    grow_cycle_id = int(cycle_rows[0]["id"])
    phase_rows = await fetch(
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
            created_at,
            updated_at
        )
        VALUES (
            $1,
            0,
            'VEG',
            5.5,
            5.2,
            5.8,
            2.0,
            1.8,
            2.2,
            'SUBSTRATE',
            600,
            45,
            NOW(),
            NOW()
        )
        RETURNING id
        """,
        grow_cycle_id,
    )
    phase_id = int(phase_rows[0]["id"])
    await execute(
        """
        UPDATE grow_cycles
        SET current_phase_id = $2,
            started_at = NOW(),
            recipe_started_at = NOW(),
            updated_at = NOW()
        WHERE id = $1
        """,
        grow_cycle_id,
        phase_id,
    )
    return grow_cycle_id


def _intent_row(zone_id: int, prefix: str) -> dict[str, object]:
    return {
        "id": 801,
        "zone_id": zone_id,
        "intent_type": "diagnostics_tick",
        "retry_count": 0,
        "payload": {
            "workflow": "cycle_start",
            "task_type": "diagnostics",
            "source": "laravel_scheduler",
            "topology": "two_tank",
        },
        "idempotency_key": f"{prefix}-idem",
    }


def _irrigation_intent_row(zone_id: int, prefix: str) -> dict[str, object]:
    return {
        "id": 901,
        "zone_id": zone_id,
        "intent_type": "irrigation",
        "retry_count": 0,
        "payload": {
            "workflow": "cycle_start",
            "task_type": "irrigation_start",
            "source": "zone_ui",
            "topology": "two_tank",
            "mode": "normal",
            "requested_duration_sec": 180,
        },
        "idempotency_key": f"{prefix}-irrigation-idem",
    }


@pytest.mark.asyncio
async def test_create_task_from_intent_creates_canonical_pending_task() -> None:
    prefix = f"ae3-create-task-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    use_case = CreateTaskFromIntentUseCase(
        task_repository=PgAutomationTaskRepository(),
        zone_lease_repository=PgZoneLeaseRepository(),
        legacy_intent_mapper=LegacyIntentMapper(),
    )

    try:
        zone_id = await _insert_zone(prefix)
        await _insert_active_grow_cycle(zone_id, prefix)
        result = await use_case.run(
            zone_id=zone_id,
            source="laravel_scheduler",
            idempotency_key=f"{prefix}-idem",
            intent_row=_intent_row(zone_id, prefix),
            now=now,
        )

        assert result.created is True
        assert result.task.zone_id == zone_id
        assert result.task.status == "pending"
        assert result.task.intent_id == 801
        assert result.task.topology == "two_tank"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_create_task_from_intent_persists_irrigation_runtime_columns() -> None:
    prefix = f"ae3-create-task-irrigation-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    use_case = CreateTaskFromIntentUseCase(
        task_repository=PgAutomationTaskRepository(),
        zone_lease_repository=PgZoneLeaseRepository(),
        legacy_intent_mapper=LegacyIntentMapper(),
    )

    try:
        zone_id = await _insert_zone(prefix)
        await _insert_active_grow_cycle(zone_id, prefix)
        result = await use_case.run(
            zone_id=zone_id,
            source="zone_ui",
            idempotency_key=f"{prefix}-irrigation-idem",
            intent_row=_irrigation_intent_row(zone_id, prefix),
            now=now,
        )

        assert result.created is True
        assert result.task.task_type == "irrigation_start"
        assert result.task.current_stage == "await_ready"
        assert result.task.workflow_phase == "ready"
        assert result.task.irrigation_mode == "normal"
        assert result.task.irrigation_requested_duration_sec == 180

        rows = await fetch(
            """
            SELECT
                task_type,
                current_stage,
                workflow_phase,
                irrigation_mode,
                irrigation_requested_duration_sec,
                irrigation_decision_strategy,
                irrigation_decision_outcome,
                irrigation_replay_count
            FROM ae_tasks
            WHERE id = $1
            """,
            int(result.task.id),
        )

        assert len(rows) == 1
        row = rows[0]
        assert row["task_type"] == "irrigation_start"
        assert row["current_stage"] == "await_ready"
        assert row["workflow_phase"] == "ready"
        assert row["irrigation_mode"] == "normal"
        assert int(row["irrigation_requested_duration_sec"]) == 180
        assert row["irrigation_decision_strategy"] is None
        assert row["irrigation_decision_outcome"] is None
        assert int(row["irrigation_replay_count"] or 0) == 0
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_create_task_from_intent_deduplicates_same_idempotency_key() -> None:
    prefix = f"ae3-create-task-dedupe-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    use_case = CreateTaskFromIntentUseCase(
        task_repository=PgAutomationTaskRepository(),
        zone_lease_repository=PgZoneLeaseRepository(),
        legacy_intent_mapper=LegacyIntentMapper(),
    )

    try:
        zone_id = await _insert_zone(prefix)
        await _insert_active_grow_cycle(zone_id, prefix)
        first = await use_case.run(
            zone_id=zone_id,
            source="laravel_scheduler",
            idempotency_key=f"{prefix}-idem",
            intent_row=_intent_row(zone_id, prefix),
            now=now,
        )
        second = await use_case.run(
            zone_id=zone_id,
            source="laravel_scheduler",
            idempotency_key=f"{prefix}-idem",
            intent_row=_intent_row(zone_id, prefix),
            now=now + timedelta(seconds=1),
        )

        assert first.created is True
        assert second.created is False
        assert second.task.id == first.task.id
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_create_task_from_intent_allows_same_idempotency_key_in_other_zone() -> None:
    prefix = f"ae3-xzone-{uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    use_case = CreateTaskFromIntentUseCase(
        task_repository=PgAutomationTaskRepository(),
        zone_lease_repository=PgZoneLeaseRepository(),
        legacy_intent_mapper=LegacyIntentMapper(),
    )

    try:
        first_zone_id = await _insert_zone(f"{prefix}-a")
        second_zone_id = await _insert_zone(f"{prefix}-b")
        await _insert_active_grow_cycle(first_zone_id, f"{prefix}-a")
        await _insert_active_grow_cycle(second_zone_id, f"{prefix}-b")

        first = await use_case.run(
            zone_id=first_zone_id,
            source="laravel_scheduler",
            idempotency_key="shared-idem-key",
            intent_row=_intent_row(first_zone_id, prefix),
            now=now,
        )
        second = await use_case.run(
            zone_id=second_zone_id,
            source="laravel_scheduler",
            idempotency_key="shared-idem-key",
            intent_row=_intent_row(second_zone_id, prefix),
            now=now + timedelta(seconds=1),
        )

        assert first.created is True
        assert second.created is True
        assert first.task.zone_id == first_zone_id
        assert second.task.zone_id == second_zone_id
        assert first.task.id != second.task.id
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_create_task_from_intent_rejects_active_zone_lease() -> None:
    prefix = f"ae3-create-task-lease-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    use_case = CreateTaskFromIntentUseCase(
        task_repository=PgAutomationTaskRepository(),
        zone_lease_repository=PgZoneLeaseRepository(),
        legacy_intent_mapper=LegacyIntentMapper(),
    )

    try:
        zone_id = await _insert_zone(prefix)
        await _insert_active_grow_cycle(zone_id, prefix)
        await execute(
            """
            INSERT INTO ae_zone_leases (zone_id, owner, leased_until, updated_at)
            VALUES ($1, 'busy-worker', $2, $3)
            """,
            zone_id,
            now + timedelta(minutes=5),
            now,
        )

        with pytest.raises(TaskCreateError) as exc:
            await use_case.run(
                zone_id=zone_id,
                source="laravel_scheduler",
                idempotency_key=f"{prefix}-idem",
                intent_row=_intent_row(zone_id, prefix),
                now=now,
            )

        assert exc.value.code == "start_cycle_zone_busy"
        assert exc.value.details["active_lease_owner"] == "busy-worker"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_create_task_from_intent_rejects_zone_with_active_blocking_alert() -> None:
    prefix = f"ae3-create-task-alert-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    use_case = CreateTaskFromIntentUseCase(
        task_repository=PgAutomationTaskRepository(),
        zone_lease_repository=PgZoneLeaseRepository(),
        legacy_intent_mapper=LegacyIntentMapper(),
        zone_alert_repository=PgZoneAlertRepository(),
    )

    try:
        zone_id = await _insert_zone(prefix)
        await _insert_active_grow_cycle(zone_id, prefix)
        await execute(
            """
            INSERT INTO alerts (
                zone_id, source, code, type, details, status, category, severity, error_count, created_at, first_seen_at, last_seen_at
            )
            VALUES (
                $1, 'biz', 'biz_zone_dosing_calibration_missing', 'zone', '{}'::jsonb, 'ACTIVE', 'operations', 'critical', 1, $2, $2, $2
            )
            """,
            zone_id,
            now,
        )

        with pytest.raises(TaskCreateError) as exc:
            await use_case.run(
                zone_id=zone_id,
                source="laravel_scheduler",
                idempotency_key=f"{prefix}-idem",
                intent_row=_intent_row(zone_id, prefix),
                now=now,
            )

        assert exc.value.code == "start_cycle_zone_busy"
        assert exc.value.details["blocking_alert_code"] == "biz_zone_dosing_calibration_missing"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_create_task_from_intent_terminal_mode_fails_closed_when_task_missing() -> None:
    prefix = f"ae3-create-task-terminal-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    use_case = CreateTaskFromIntentUseCase(
        task_repository=PgAutomationTaskRepository(),
        zone_lease_repository=PgZoneLeaseRepository(),
        legacy_intent_mapper=LegacyIntentMapper(),
    )

    try:
        zone_id = await _insert_zone(prefix)
        await _insert_active_grow_cycle(zone_id, prefix)

        with pytest.raises(TaskCreateError) as exc:
            await use_case.run(
                zone_id=zone_id,
                source="laravel_scheduler",
                idempotency_key=f"{prefix}-idem",
                intent_row=_intent_row(zone_id, prefix),
                now=now,
                allow_create=False,
            )

        assert exc.value.code == "start_cycle_intent_terminal"
        assert exc.value.details["idempotency_key"] == f"{prefix}-idem"
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_create_task_from_intent_rejects_missing_topology() -> None:
    prefix = f"ae3-create-task-topology-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    use_case = CreateTaskFromIntentUseCase(
        task_repository=PgAutomationTaskRepository(),
        zone_lease_repository=PgZoneLeaseRepository(),
        legacy_intent_mapper=LegacyIntentMapper(),
    )

    try:
        zone_id = await _insert_zone(prefix)
        await _insert_active_grow_cycle(zone_id, prefix)

        with pytest.raises(TaskCreateError) as exc:
            await use_case.run(
                zone_id=zone_id,
                source="laravel_scheduler",
                idempotency_key=f"{prefix}-idem",
                intent_row={
                    "id": 991,
                    "zone_id": zone_id,
                    "intent_type": "diagnostics_tick",
                    "retry_count": 0,
                    "payload": {
                        "workflow": "cycle_start",
                        "task_type": "diagnostics",
                        "source": "laravel_scheduler",
                    },
                    "idempotency_key": f"{prefix}-idem",
                },
                now=now,
            )

        assert exc.value.code == "start_cycle_intent_topology_missing"
        assert exc.value.details["intent_id"] == 991
    finally:
        await _cleanup(prefix)


@pytest.mark.asyncio
async def test_create_task_from_intent_rejects_zone_without_active_grow_cycle() -> None:
    prefix = f"ae3-create-task-no-cycle-{uuid4().hex}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    use_case = CreateTaskFromIntentUseCase(
        task_repository=PgAutomationTaskRepository(),
        zone_lease_repository=PgZoneLeaseRepository(),
        legacy_intent_mapper=LegacyIntentMapper(),
    )

    try:
        zone_id = await _insert_zone(prefix)

        with pytest.raises(TaskCreateError) as exc:
            await use_case.run(
                zone_id=zone_id,
                source="laravel_scheduler",
                idempotency_key=f"{prefix}-idem",
                intent_row=_intent_row(zone_id, prefix),
                now=now,
            )

        assert exc.value.code == "ae3_snapshot_no_active_grow_cycle"
    finally:
        await _cleanup(prefix)

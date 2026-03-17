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
    rows = await fetch(
        """
        INSERT INTO zones (name, uid, status, automation_runtime, created_at, updated_at)
        VALUES ($1, $2, 'online', 'ae3', NOW(), NOW())
        RETURNING id
        """,
        prefix,
        f"{prefix}-uid",
    )
    return int(rows[0]["id"])


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
        },
        "idempotency_key": f"{prefix}-idem",
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

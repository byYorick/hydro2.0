from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ae3lite.application.adapters import LegacyIntentMapper
from ae3lite.application.use_cases import CreateTaskFromIntentUseCase
from ae3lite.api.contracts import StartCycleRequest
from ae3lite.domain.errors import TaskCreateError
from ae3lite.domain.entities import AutomationTask


NOW = datetime(2026, 3, 14, 12, 0, 0, tzinfo=timezone.utc).replace(tzinfo=None)


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakeConn:
    def __init__(self) -> None:
        self.fetchval_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_results: list[object] = []

    async def fetchval(self, query: str, *args):
        self.fetchval_calls.append((query, args))
        return True

    async def fetchrow(self, query: str, *args):
        self.fetchrow_calls.append((query, args))
        if self.fetchrow_results:
            return self.fetchrow_results.pop(0)
        return None

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction()


class _FakeAcquire:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakePool:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self._conn)


def _task(zone_id: int) -> AutomationTask:
    return AutomationTask.from_row(
        {
            "id": 901,
            "zone_id": zone_id,
            "task_type": "cycle_start",
            "status": "pending",
            "idempotency_key": "idem-1",
            "scheduled_for": NOW,
            "due_at": NOW,
            "claimed_by": None,
            "claimed_at": None,
            "error_code": None,
            "error_message": None,
            "created_at": NOW,
            "updated_at": NOW,
            "completed_at": None,
            "topology": "two_tank",
            "intent_source": "laravel_scheduler",
            "intent_trigger": "schedule",
            "intent_id": 12,
            "intent_meta": {},
            "current_stage": "startup",
            "workflow_phase": "idle",
            "stage_deadline_at": None,
            "stage_retry_count": 0,
            "stage_entered_at": NOW,
            "clean_fill_cycle": 0,
            "corr_step": None,
        }
    )


class _TaskRepo:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn
        self.calls: list[tuple[str, object]] = []

    async def get_by_idempotency_key(self, *, zone_id: int, idempotency_key: str):
        self.calls.append(("get_by_idempotency_key", zone_id, idempotency_key))
        return None

    async def get_active_for_zone_with_conn(self, *, zone_id: int, conn):
        self.calls.append(("get_active_for_zone_with_conn", conn))
        assert conn is self._conn
        return None

    async def create_pending(
        self,
        *,
        zone_id: int,
        idempotency_key: str,
        task_type: str,
        topology: str,
        current_stage: str,
        workflow_phase: str,
        intent_source,
        intent_trigger,
        intent_id,
        intent_meta,
        scheduled_for,
        due_at,
        now,
        irrigation_mode=None,
        irrigation_requested_duration_sec=None,
        irrigation_decision_strategy=None,
        irrigation_decision_config=None,
        irrigation_bundle_revision=None,
        conn,
    ):
        self.calls.append((
            "create_pending",
            conn,
            irrigation_decision_strategy,
            irrigation_decision_config,
            irrigation_bundle_revision,
        ))
        assert conn is self._conn
        return _task(zone_id)


class _LeaseRepo:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn
        self.calls: list[object] = []

    async def get(self, *, zone_id: int, conn):
        self.calls.append(conn)
        assert conn is self._conn
        return None


class _AlertRepo:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn
        self.calls: list[object] = []

    async def find_first_active_by_codes(self, *, zone_id: int, codes, conn):
        self.calls.append(conn)
        assert conn is self._conn
        return None


@pytest.mark.asyncio
async def test_create_task_from_intent_uses_shared_locked_connection_for_checks_and_insert() -> None:
    conn = _FakeConn()
    conn.fetchrow_results = [
        {
            "grow_cycle_id": 55,
            "current_phase_id": 77,
        },
    ]
    use_case = CreateTaskFromIntentUseCase(
        task_repository=_TaskRepo(conn),
        zone_lease_repository=_LeaseRepo(conn),
        legacy_intent_mapper=LegacyIntentMapper(),
        zone_alert_repository=_AlertRepo(conn),
    )

    with patch(
        "ae3lite.application.use_cases.create_task_from_intent.get_pool",
        return_value=_FakePool(conn),
    ):
        result = await use_case.run(
            zone_id=7,
            source="laravel_scheduler",
            idempotency_key="idem-1",
            intent_row={
                "id": 12,
                "zone_id": 7,
                "intent_type": "diagnostics_tick",
                "retry_count": 0,
                "payload": {
                    "workflow": "cycle_start",
                    "task_type": "diagnostics",
                    "source": "laravel_scheduler",
                    "topology": "two_tank",
                },
                "idempotency_key": "idem-1",
            },
            now=NOW,
        )

    assert result.created is True
    assert result.task.zone_id == 7


@pytest.mark.asyncio
async def test_create_task_from_intent_locks_irrigation_decision_snapshot_before_worker_claim() -> None:
    conn = _FakeConn()
    conn.fetchrow_results = [
        {
            "grow_cycle_id": 55,
            "current_phase_id": 70,
        },
        {
            "grow_cycle_id": 55,
            "cycle_settings": {"bundle_revision": "bundle-1"},
        },
        {
            "bundle_revision": "bundle-1",
            "config": {
                "zone": {
                    "logic_profile": {
                        "active_profile": {
                            "subsystems": {
                                "irrigation": {
                                    "decision": {
                                        "strategy": "smart_soil_v1",
                                        "config": {
                                            "lookback_sec": 1800,
                                            "min_samples": 3,
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    ]
    task_repo = _TaskRepo(conn)
    use_case = CreateTaskFromIntentUseCase(
        task_repository=task_repo,
        zone_lease_repository=_LeaseRepo(conn),
        legacy_intent_mapper=LegacyIntentMapper(),
        zone_alert_repository=_AlertRepo(conn),
    )

    with patch(
        "ae3lite.application.use_cases.create_task_from_intent.get_pool",
        return_value=_FakePool(conn),
    ):
        result = await use_case.run(
            zone_id=7,
            source="zone_ui",
            idempotency_key="idem-irrigation",
            intent_row={
                "id": 18,
                "zone_id": 7,
                "intent_type": "irrigation",
                "retry_count": 0,
                "payload": {
                    "workflow": "cycle_start",
                    "task_type": "irrigation_start",
                    "source": "zone_ui",
                    "topology": "two_tank",
                    "mode": "normal",
                    "requested_duration_sec": 120,
                },
                "idempotency_key": "idem-irrigation",
            },
            now=NOW,
        )

    assert result.created is True
    create_pending_call = next(call for call in task_repo.calls if call[0] == "create_pending")
    assert create_pending_call[2] == "smart_soil_v1"
    assert create_pending_call[3] == {"lookback_sec": 1800, "min_samples": 3}
    assert create_pending_call[4] == "bundle-1"


@pytest.mark.asyncio
async def test_create_task_from_intent_fails_closed_without_active_grow_cycle() -> None:
    conn = _FakeConn()
    use_case = CreateTaskFromIntentUseCase(
        task_repository=_TaskRepo(conn),
        zone_lease_repository=_LeaseRepo(conn),
        legacy_intent_mapper=LegacyIntentMapper(),
        zone_alert_repository=_AlertRepo(conn),
    )

    with patch(
        "ae3lite.application.use_cases.create_task_from_intent.get_pool",
        return_value=_FakePool(conn),
    ):
        with pytest.raises(TaskCreateError) as exc:
            await use_case.run(
                zone_id=7,
                source="laravel_scheduler",
                idempotency_key="idem-missing-cycle",
                intent_row={
                    "id": 12,
                    "zone_id": 7,
                    "intent_type": "diagnostics_tick",
                    "retry_count": 0,
                    "payload": {
                        "workflow": "cycle_start",
                        "task_type": "diagnostics",
                        "source": "laravel_scheduler",
                        "topology": "two_tank",
                    },
                    "idempotency_key": "idem-missing-cycle",
                },
                now=NOW,
            )

    assert exc.value.code == "ae3_snapshot_no_active_grow_cycle"

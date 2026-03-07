"""Integration tests for ae_stage_transitions audit trail.

Tests that PgAutomationTaskRepository.record_transition() correctly:
 1. Inserts a row into ae_stage_transitions
 2. Is append-only (multiple calls → multiple rows, no updates)
 3. Stores metadata JSONB correctly
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ae3lite.infrastructure.repositories.automation_task_repository import PgAutomationTaskRepository
from common.db import execute, fetch


NOW = datetime(2026, 3, 7, 12, 0, 0, tzinfo=timezone.utc)


async def _insert_greenhouse() -> int:
    rows = await fetch(
        """
        INSERT INTO greenhouses (uid, name, timezone, provisioning_token, created_at, updated_at)
        VALUES ($1, 'st-gh', 'UTC', $2, NOW(), NOW())
        RETURNING id
        """,
        f"gh-st-{uuid4().hex[:20]}",
        f"pt-st-{uuid4().hex[:20]}",
    )
    return int(rows[0]["id"])


async def _insert_zone(greenhouse_id: int) -> int:
    rows = await fetch(
        """
        INSERT INTO zones (greenhouse_id, name, uid, status, automation_runtime, created_at, updated_at)
        VALUES ($1, 'st-zone', $2, 'online', 'ae3', NOW(), NOW())
        RETURNING id
        """,
        greenhouse_id,
        f"zn-st-{uuid4().hex[:20]}",
    )
    return int(rows[0]["id"])


async def _insert_task(zone_id: int) -> int:
    ikey = f"st-{uuid4().hex[:20]}"
    rows = await fetch(
        """
        INSERT INTO ae_tasks (
            zone_id, task_type, status, idempotency_key,
            scheduled_for, due_at, claimed_by, claimed_at,
            created_at, updated_at,
            topology, current_stage, workflow_phase
        )
        VALUES ($1, 'cycle_start', 'running', $2,
                $3, $3, 'worker-test', $3,
                $3, $3,
                'two_tank', 'startup', 'idle')
        RETURNING id
        """,
        zone_id,
        ikey,
        NOW,
    )
    return int(rows[0]["id"])


async def _cleanup(zone_id: int) -> None:
    await execute("DELETE FROM ae_tasks WHERE zone_id = $1", zone_id)
    await execute("DELETE FROM zones WHERE id = $1", zone_id)


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.integration
async def test_record_transition_inserts_row():
    """record_transition() → one row in ae_stage_transitions."""
    gh_id = await _insert_greenhouse()
    zone_id = await _insert_zone(gh_id)
    task_id = await _insert_task(zone_id)
    try:
        repo = PgAutomationTaskRepository()
        await repo.record_transition(
            task_id=task_id,
            from_stage="startup",
            to_stage="clean_fill_start",
            workflow_phase="tank_filling",
            now=NOW,
        )

        rows = await fetch(
            "SELECT * FROM ae_stage_transitions WHERE task_id = $1",
            task_id,
        )
        assert len(rows) == 1
        assert rows[0]["from_stage"] == "startup"
        assert rows[0]["to_stage"] == "clean_fill_start"
        assert rows[0]["workflow_phase"] == "tank_filling"
    finally:
        await execute("DELETE FROM ae_stage_transitions WHERE task_id = $1", task_id)
        await _cleanup(zone_id)
        await execute("DELETE FROM greenhouses WHERE id = $1", gh_id)


@pytest.mark.integration
async def test_record_transition_is_append_only():
    """Multiple record_transition() calls → multiple rows (no UPDATE/UPSERT)."""
    gh_id = await _insert_greenhouse()
    zone_id = await _insert_zone(gh_id)
    task_id = await _insert_task(zone_id)
    try:
        repo = PgAutomationTaskRepository()
        transitions = [
            ("startup", "clean_fill_start", "tank_filling"),
            ("clean_fill_start", "clean_fill_check", "tank_filling"),
            ("clean_fill_check", "clean_fill_stop_to_solution", "tank_filling"),
        ]
        for from_s, to_s, phase in transitions:
            await repo.record_transition(
                task_id=task_id,
                from_stage=from_s,
                to_stage=to_s,
                workflow_phase=phase,
                now=NOW,
            )

        rows = await fetch(
            "SELECT * FROM ae_stage_transitions WHERE task_id = $1 ORDER BY id ASC",
            task_id,
        )
        assert len(rows) == 3
        assert rows[0]["from_stage"] == "startup"
        assert rows[1]["from_stage"] == "clean_fill_start"
        assert rows[2]["from_stage"] == "clean_fill_check"
    finally:
        await execute("DELETE FROM ae_stage_transitions WHERE task_id = $1", task_id)
        await _cleanup(zone_id)
        await execute("DELETE FROM greenhouses WHERE id = $1", gh_id)


@pytest.mark.integration
async def test_record_transition_metadata_stored():
    """metadata dict → stored as JSONB in the metadata column."""
    gh_id = await _insert_greenhouse()
    zone_id = await _insert_zone(gh_id)
    task_id = await _insert_task(zone_id)
    try:
        repo = PgAutomationTaskRepository()
        meta = {"recovery": True, "corr_attempt": 3, "error_code": "timeout"}
        await repo.record_transition(
            task_id=task_id,
            from_stage="clean_fill_check",
            to_stage="clean_fill_timeout_stop",
            workflow_phase="tank_filling",
            metadata=meta,
            now=NOW,
        )

        rows = await fetch(
            "SELECT metadata FROM ae_stage_transitions WHERE task_id = $1",
            task_id,
        )
        assert len(rows) == 1
        stored = dict(rows[0]["metadata"])
        assert stored["recovery"] is True
        assert stored["corr_attempt"] == 3
        assert stored["error_code"] == "timeout"
    finally:
        await execute("DELETE FROM ae_stage_transitions WHERE task_id = $1", task_id)
        await _cleanup(zone_id)
        await execute("DELETE FROM greenhouses WHERE id = $1", gh_id)

"""Shared helpers for AE3 preflight / zone node diagnostics in unit tests."""

from __future__ import annotations

import asyncio
from typing import Any, Sequence

import pytest

from ae3lite.domain.services.zone_node_availability import classify_zone_nodes

DEFAULT_TWO_TANK_NODE_TYPES = ("irrig", "ph", "ec")
TERMINAL_TASK_STATUSES = frozenset({"completed", "failed", "cancelled"})

# Legacy/per-test node_uid values used across handler/gateway unit tests.
COMMON_TEST_NODE_ALIASES: tuple[tuple[str, str], ...] = (
    ("nd-1", "irrig"),
    ("nd-irr-1", "irrig"),
    ("nd-test-irrig-1", "irrig"),
    ("n1", "irrig"),
    ("n2", "ec"),
)


def make_zone_nodes_diag_rows(
    *,
    node_types: Sequence[str] = DEFAULT_TWO_TANK_NODE_TYPES,
    status: str = "online",
    last_seen_age_sec: int = 5,
    active_actuator_count: int = 2,
    uid_prefix: str = "nd",
    extra_aliases: Sequence[tuple[str, str]] = COMMON_TEST_NODE_ALIASES,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_uids: set[str] = set()

    def _append_row(*, node_uid: str, node_type: str) -> None:
        if node_uid in seen_uids:
            return
        seen_uids.add(node_uid)
        rows.append(
            {
                "node_uid": node_uid,
                "node_type": node_type,
                "status": status,
                "last_seen_age_sec": last_seen_age_sec,
                "active_actuator_count": active_actuator_count,
            }
        )

    for node_type in node_types:
        _append_row(node_uid=f"{uid_prefix}-{node_type}-1", node_type=node_type)
    for alias_uid, alias_type in extra_aliases:
        _append_row(node_uid=alias_uid, node_type=alias_type)
    return rows


def make_zone_nodes_diagnostics(
    zone_id: int,
    *,
    node_types: Sequence[str] = DEFAULT_TWO_TANK_NODE_TYPES,
    status: str = "online",
    last_seen_age_sec: int = 5,
    active_actuator_count: int = 2,
    uid_prefix: str = "nd",
    extra_aliases: Sequence[tuple[str, str]] = COMMON_TEST_NODE_ALIASES,
) -> dict[str, Any]:
    return classify_zone_nodes(
        zone_id=zone_id,
        diag_rows=make_zone_nodes_diag_rows(
            node_types=node_types,
            status=status,
            last_seen_age_sec=last_seen_age_sec,
            active_actuator_count=active_actuator_count,
            uid_prefix=uid_prefix,
            extra_aliases=extra_aliases,
        ),
    )


async def stub_fetch_zone_nodes_diagnostics(
    *,
    zone_id: int,
    conn: Any | None = None,  # noqa: ARG001
    node_types: Sequence[str] | None = None,
    status: str = "online",
    last_seen_age_sec: int = 5,
    active_actuator_count: int = 2,
    uid_prefix: str = "nd",
    extra_aliases: Sequence[tuple[str, str]] = COMMON_TEST_NODE_ALIASES,
) -> dict[str, Any]:
    return make_zone_nodes_diagnostics(
        zone_id,
        node_types=node_types or DEFAULT_TWO_TANK_NODE_TYPES,
        status=status,
        last_seen_age_sec=last_seen_age_sec,
        active_actuator_count=active_actuator_count,
        uid_prefix=uid_prefix,
        extra_aliases=extra_aliases,
    )


def patch_fetch_zone_nodes_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    *,
    node_types: Sequence[str] | None = None,
    status: str = "online",
    last_seen_age_sec: int = 5,
    active_actuator_count: int = 2,
    uid_prefix: str = "nd",
) -> None:
    types = node_types

    async def _fetch(**kwargs: Any) -> dict[str, Any]:
        zone_id = int(kwargs.get("zone_id", 99) or 99)
        return await stub_fetch_zone_nodes_diagnostics(
            zone_id=zone_id,
            conn=kwargs.get("conn"),
            node_types=types,
            status=status,
            last_seen_age_sec=last_seen_age_sec,
            active_actuator_count=active_actuator_count,
            uid_prefix=uid_prefix,
        )

    monkeypatch.setattr(
        "ae3lite.domain.services.zone_node_availability.fetch_zone_nodes_diagnostics",
        _fetch,
    )


async def drain_until_idle(
    worker: Any,
    *,
    task_id: int,
    max_rounds: int = 300,
    poll_sec: float = 0.02,
    expect_status: str | None = None,
    expect_stage: str | None = None,
) -> dict[str, Any]:
    """Крутит drain до terminal status или ожидаемого (stage, status).

    После PR2 ``_drain_pending_tasks`` может выйти в ``sleeping`` на poll-stage;
    helper форсирует ``due_at`` и повторяет drain.
    """
    from common.db import execute, fetch

    expected_status = str(expect_status or "").strip().lower() or None
    expected_stage = str(expect_stage or "").strip() or None

    for _ in range(max_rounds):
        rows = await fetch(
            """
            SELECT status::text AS status, current_stage
            FROM ae_tasks
            WHERE id = $1
            """,
            task_id,
        )
        if not rows:
            raise AssertionError(f"ae_tasks id={task_id} not found")
        row = dict(rows[0])
        status = str(row.get("status") or "").lower()
        stage = str(row.get("current_stage") or "")

        if expected_status is not None and expected_stage is not None:
            if status == expected_status and stage == expected_stage:
                return row
        elif status in TERMINAL_TASK_STATUSES:
            return row

        await execute(
            """
            UPDATE ae_tasks
            SET due_at = NOW() - INTERVAL '1 millisecond'
            WHERE id = $1
              AND status IN ('pending', 'claimed', 'running', 'waiting_command')
            """,
            task_id,
        )
        kick = getattr(worker, "kick", None)
        if callable(kick):
            kick()
        await worker._drain_pending_tasks()
        await asyncio.sleep(poll_sec)

    raise AssertionError(
        f"drain_until_idle timeout task_id={task_id} "
        f"last_status={row.get('status')} last_stage={row.get('current_stage')}"
    )

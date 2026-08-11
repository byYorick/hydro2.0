"""Unit-тесты диагностики `no_online_actuator_channels` в `PgZoneSnapshotReadModel`.

Покрывают логику :py:meth:`PgZoneSnapshotReadModel._build_no_actuators_diagnostics`
без обращения к БД — проверяется построение payload для ``SnapshotBuildError.details``.
"""

from __future__ import annotations

import pytest

from ae3lite.infrastructure.read_models.zone_snapshot_read_model import (
    PgZoneSnapshotReadModel,
)


def _row(
    *,
    uid: str,
    node_type: str,
    status: str,
    last_seen_age_sec: int | None,
    active_actuator_count: int = 0,
) -> dict:
    return {
        "node_uid": uid,
        "node_type": node_type,
        "status": status,
        "last_seen_age_sec": last_seen_age_sec,
        "active_actuator_count": active_actuator_count,
    }


def test_build_no_actuators_diagnostics_returns_full_breakdown() -> None:
    rows = [
        _row(uid="nd-irrig-1", node_type="irrig", status="online", last_seen_age_sec=5, active_actuator_count=6),
        _row(uid="nd-ph-1", node_type="ph", status="offline", last_seen_age_sec=120, active_actuator_count=2),
        _row(uid="nd-ec-1", node_type="ec", status="offline", last_seen_age_sec=900, active_actuator_count=2),
    ]

    diag = PgZoneSnapshotReadModel._build_no_actuators_diagnostics(zone_id=42, diag_rows=rows)

    assert diag["zone_id"] == 42
    assert len(diag["zone_nodes"]) == 3
    assert diag["zone_nodes"][0]["uid"] == "nd-irrig-1"
    assert diag["zone_nodes"][0]["status"] == "online"
    assert diag["transiently_offline_uids"] == ["nd-ph-1"]
    assert diag["persistently_offline_uids"] == ["nd-ec-1"]
    assert diag["persistent_dead_threshold_sec"] >= 60


def test_build_no_actuators_diagnostics_classifies_at_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """Узел с last_seen_age_sec ровно на пороге считается persistently dead."""
    monkeypatch.setenv("AE3_NODE_PERSISTENT_DEAD_SEC", "300")

    rows = [
        _row(uid="nd-a", node_type="ph", status="offline", last_seen_age_sec=300),
        _row(uid="nd-b", node_type="ph", status="offline", last_seen_age_sec=299),
    ]

    diag = PgZoneSnapshotReadModel._build_no_actuators_diagnostics(zone_id=1, diag_rows=rows)

    assert diag["persistently_offline_uids"] == ["nd-a"]
    assert diag["transiently_offline_uids"] == ["nd-b"]
    assert diag["persistent_dead_threshold_sec"] == 300


def test_build_no_actuators_diagnostics_handles_empty_zone() -> None:
    diag = PgZoneSnapshotReadModel._build_no_actuators_diagnostics(zone_id=7, diag_rows=[])

    assert diag["zone_id"] == 7
    assert diag["zone_nodes"] == []
    assert diag["persistently_offline_uids"] == []
    assert diag["transiently_offline_uids"] == []


def test_build_no_actuators_diagnostics_skips_rows_without_uid() -> None:
    rows = [
        {"node_uid": "", "node_type": "ph", "status": "offline", "last_seen_age_sec": 60},
        _row(uid="nd-1", node_type="irrig", status="offline", last_seen_age_sec=60),
    ]

    diag = PgZoneSnapshotReadModel._build_no_actuators_diagnostics(zone_id=1, diag_rows=rows)

    assert len(diag["zone_nodes"]) == 1
    assert diag["zone_nodes"][0]["uid"] == "nd-1"


def test_build_no_actuators_diagnostics_handles_null_last_seen() -> None:
    """Если ``last_seen_at`` пуст (NULL → None), узел считается transiently offline."""
    rows = [
        _row(uid="nd-x", node_type="ph", status="offline", last_seen_age_sec=None),
    ]

    diag = PgZoneSnapshotReadModel._build_no_actuators_diagnostics(zone_id=1, diag_rows=rows)

    assert diag["transiently_offline_uids"] == ["nd-x"]
    assert diag["persistently_offline_uids"] == []
    assert diag["zone_nodes"][0]["last_seen_age_sec"] is None


def test_build_no_actuators_diagnostics_online_node_never_marked_offline() -> None:
    """Online-узел не попадает ни в transient, ни в persistent списки, даже при больших last_seen_age."""
    rows = [
        _row(uid="nd-1", node_type="irrig", status="online", last_seen_age_sec=10000),
    ]

    diag = PgZoneSnapshotReadModel._build_no_actuators_diagnostics(zone_id=1, diag_rows=rows)

    assert diag["transiently_offline_uids"] == []
    assert diag["persistently_offline_uids"] == []
    assert diag["zone_nodes"][0]["status"] == "online"

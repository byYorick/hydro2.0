"""Unit-тесты диагностики доступности нод зоны."""

from __future__ import annotations

import pytest

from ae3lite.domain.errors import ErrorCodes
from ae3lite.domain.services.zone_node_availability import (
    classify_zone_nodes,
    liveness_is_unreachable,
    offline_failure_from_liveness,
    offline_failure_for_node_uid,
    resolve_required_nodes_offline_failure,
    resolve_task_error_with_node_offline,
    should_remap_error_for_node_check,
)


def test_resolve_required_nodes_offline_returns_transient_code() -> None:
    diagnostics = classify_zone_nodes(
        zone_id=1,
        diag_rows=[
            {
                "node_uid": "nd-irrig-1",
                "node_type": "irrig",
                "status": "offline",
                "last_seen_age_sec": 90,
                "active_actuator_count": 4,
            },
            {
                "node_uid": "nd-ph-1",
                "node_type": "ph",
                "status": "online",
                "last_seen_age_sec": 5,
                "active_actuator_count": 2,
            },
            {
                "node_uid": "nd-ec-1",
                "node_type": "ec",
                "status": "online",
                "last_seen_age_sec": 5,
                "active_actuator_count": 2,
            },
        ],
    )

    failure = resolve_required_nodes_offline_failure(
        zone_id=1,
        topology="two_tank_drip_substrate_trays",
        diagnostics=diagnostics,
    )

    assert failure is not None
    assert failure.code == ErrorCodes.AE3_REQUIRED_NODE_OFFLINE
    assert "nd-irrig-1" in failure.message


def test_resolve_required_nodes_offline_returns_persistent_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AE3_NODE_PERSISTENT_DEAD_SEC", "120")

    diagnostics = classify_zone_nodes(
        zone_id=2,
        diag_rows=[
            {
                "node_uid": "nd-irrig-1",
                "node_type": "irrig",
                "status": "offline",
                "last_seen_age_sec": 500,
                "active_actuator_count": 4,
            },
            {
                "node_uid": "nd-ph-1",
                "node_type": "ph",
                "status": "online",
                "last_seen_age_sec": 5,
                "active_actuator_count": 2,
            },
            {
                "node_uid": "nd-ec-1",
                "node_type": "ec",
                "status": "online",
                "last_seen_age_sec": 5,
                "active_actuator_count": 2,
            },
        ],
    )

    failure = resolve_required_nodes_offline_failure(
        zone_id=2,
        topology="two_tank",
        diagnostics=diagnostics,
    )

    assert failure is not None
    assert failure.code == ErrorCodes.AE3_SNAPSHOT_REQUIRED_NODE_PERSISTENTLY_OFFLINE


def test_liveness_is_unreachable_for_offline_status() -> None:
    assert liveness_is_unreachable({"found": True, "status": "offline"}) is True
    assert liveness_is_unreachable({"found": True, "status": "online", "heartbeat_age_sec": 5}) is False
    assert liveness_is_unreachable({"found": True, "status": "online", "heartbeat_age_sec": 45}) is True


def test_should_remap_error_for_node_check() -> None:
    assert should_remap_error_for_node_check("ae3_zone_lease_lost") is True
    assert should_remap_error_for_node_check("two_tank_clean_level_unavailable") is True
    assert should_remap_error_for_node_check("corr_dose_ec_bad_sequence") is False


@pytest.mark.asyncio
async def test_resolve_task_error_with_node_offline_by_diagnostics() -> None:
    diagnostics = classify_zone_nodes(
        zone_id=5,
        diag_rows=[
            {
                "node_uid": "nd-irrig-1",
                "node_type": "irrig",
                "status": "offline",
                "last_seen_age_sec": 90,
                "active_actuator_count": 4,
            },
            {
                "node_uid": "nd-ph-1",
                "node_type": "ph",
                "status": "online",
                "last_seen_age_sec": 5,
                "active_actuator_count": 2,
            },
            {
                "node_uid": "nd-ec-1",
                "node_type": "ec",
                "status": "online",
                "last_seen_age_sec": 5,
                "active_actuator_count": 2,
            },
        ],
    )

    failure = await resolve_task_error_with_node_offline(
        zone_id=5,
        topology="two_tank",
        error_code="ae3_zone_lease_lost",
        error_message="lease lost",
        diagnostics=diagnostics,
    )

    assert failure is not None
    assert failure.code == ErrorCodes.AE3_REQUIRED_NODE_OFFLINE


def test_offline_failure_for_node_uid() -> None:
    diagnostics = classify_zone_nodes(
        zone_id=6,
        diag_rows=[
            {
                "node_uid": "nd-ph-1",
                "node_type": "ph",
                "status": "offline",
                "last_seen_age_sec": 40,
                "active_actuator_count": 2,
            },
        ],
    )
    failure = offline_failure_for_node_uid(
        zone_id=6,
        node_uid="nd-ph-1",
        diagnostics=diagnostics,
    )
    assert failure is not None
    assert failure.code == ErrorCodes.AE3_REQUIRED_NODE_OFFLINE


def test_offline_failure_from_liveness_message() -> None:
    failure = offline_failure_from_liveness(
        zone_id=3,
        node_uid="nd-test-irrig",
        liveness={"status": "offline", "last_seen_age_sec": 30},
    )

    assert failure.code == ErrorCodes.AE3_REQUIRED_NODE_OFFLINE
    assert "nd-test-irrig" in failure.message

"""Unit-тесты диагностики доступности нод зоны."""

from __future__ import annotations

import pytest

from ae3lite.domain.errors import ErrorCodes
from ae3lite.domain.services.zone_node_availability import (
    classify_zone_nodes,
    liveness_is_unreachable,
    offline_failure_for_command_transport,
    offline_failure_from_liveness,
    offline_failure_for_node_uid,
    required_node_types_for_task,
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


def test_required_node_types_for_irrigation_start_only_needs_irrig() -> None:
    required = required_node_types_for_task(
        topology="two_tank",
        task_type="irrigation_start",
        current_stage="irrigation_run",
    )
    assert required == frozenset({"irrig"})


def test_resolve_required_nodes_offline_ignores_ph_for_irrigation_start() -> None:
    diagnostics = classify_zone_nodes(
        zone_id=3,
        diag_rows=[
            {
                "node_uid": "nd-irrig-1",
                "node_type": "irrig",
                "status": "online",
                "last_seen_age_sec": 5,
                "active_actuator_count": 4,
            },
            {
                "node_uid": "nd-ph-1",
                "node_type": "ph",
                "status": "offline",
                "last_seen_age_sec": 90,
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
        zone_id=3,
        topology="two_tank",
        diagnostics=diagnostics,
        task_type="irrigation_start",
        current_stage="irrigation_run",
    )

    assert failure is None


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


def test_offline_failure_for_command_transport_skipped_when_node_fresh_online() -> None:
    diagnostics = classify_zone_nodes(
        zone_id=7,
        diag_rows=[
            {
                "node_uid": "nd-irrig-1",
                "node_type": "irrig",
                "status": "online",
                "last_seen_age_sec": 4,
                "active_actuator_count": 4,
            },
        ],
    )
    for error_code in (
        "irr_state_unavailable",
        "irr_state_stale",
        "ae3_command_poll_deadline_exceeded",
    ):
        failure = offline_failure_for_command_transport(
            zone_id=7,
            node_uid="nd-irrig-1",
            error_code=error_code,
            diagnostics=diagnostics,
        )
        assert failure is None, error_code


def test_offline_failure_for_command_transport_when_node_stale_online() -> None:
    diagnostics = classify_zone_nodes(
        zone_id=7,
        diag_rows=[
            {
                "node_uid": "nd-irrig-1",
                "node_type": "irrig",
                "status": "online",
                "last_seen_age_sec": 120,
                "active_actuator_count": 4,
            },
        ],
    )
    for error_code in (
        "irr_state_unavailable",
        "ae3_command_poll_deadline_exceeded",
    ):
        failure = offline_failure_for_command_transport(
            zone_id=7,
            node_uid="nd-irrig-1",
            error_code=error_code,
            diagnostics=diagnostics,
        )
        assert failure is not None, error_code
        assert failure.code == ErrorCodes.AE3_REQUIRED_NODE_OFFLINE


def test_offline_failure_for_command_send_failed_when_node_still_online() -> None:
    diagnostics = classify_zone_nodes(
        zone_id=7,
        diag_rows=[
            {
                "node_uid": "nd-irrig-1",
                "node_type": "irrig",
                "status": "online",
                "last_seen_age_sec": 4,
                "active_actuator_count": 4,
            },
        ],
    )
    failure = offline_failure_for_command_transport(
        zone_id=7,
        node_uid="nd-irrig-1",
        error_code="command_send_failed",
        diagnostics=diagnostics,
    )
    assert failure is not None
    assert failure.code == ErrorCodes.AE3_REQUIRED_NODE_OFFLINE
    assert "не отвечает на команды" in failure.message


@pytest.mark.asyncio
async def test_resolve_task_error_with_node_offline_skips_fresh_irr_state() -> None:
    diagnostics = classify_zone_nodes(
        zone_id=8,
        diag_rows=[
            {
                "node_uid": "nd-irrig-1",
                "node_type": "irrig",
                "status": "online",
                "last_seen_age_sec": 3,
                "active_actuator_count": 4,
            },
            {
                "node_uid": "nd-ph-1",
                "node_type": "ph",
                "status": "online",
                "last_seen_age_sec": 2,
                "active_actuator_count": 2,
            },
            {
                "node_uid": "nd-ec-1",
                "node_type": "ec",
                "status": "online",
                "last_seen_age_sec": 2,
                "active_actuator_count": 2,
            },
        ],
    )
    failure = await resolve_task_error_with_node_offline(
        zone_id=8,
        topology="two_tank",
        error_code="irr_state_unavailable",
        error_message="snapshot missing",
        node_uid="nd-irrig-1",
        diagnostics=diagnostics,
    )
    assert failure is None


@pytest.mark.asyncio
async def test_resolve_task_error_with_node_offline_by_command_transport() -> None:
    diagnostics = classify_zone_nodes(
        zone_id=8,
        diag_rows=[
            {
                "node_uid": "nd-irrig-1",
                "node_type": "irrig",
                "status": "online",
                "last_seen_age_sec": 3,
                "active_actuator_count": 4,
            },
            {
                "node_uid": "nd-ph-1",
                "node_type": "ph",
                "status": "online",
                "last_seen_age_sec": 2,
                "active_actuator_count": 2,
            },
            {
                "node_uid": "nd-ec-1",
                "node_type": "ec",
                "status": "online",
                "last_seen_age_sec": 2,
                "active_actuator_count": 2,
            },
        ],
    )
    failure = await resolve_task_error_with_node_offline(
        zone_id=8,
        topology="two_tank",
        error_code="command_send_failed",
        error_message="hl publish failed",
        node_uid="nd-irrig-1",
        diagnostics=diagnostics,
    )
    assert failure is not None
    assert failure.code == ErrorCodes.AE3_REQUIRED_NODE_OFFLINE

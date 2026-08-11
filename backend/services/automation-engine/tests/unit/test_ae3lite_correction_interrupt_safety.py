"""Unit-тесты deferred hardware verify после correction interrupt."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.application.services.correction_interrupt_safety import (
    DOSE_ACTUATORS_UNVERIFIABLE_REASON,
    CorrectionInterruptPendingCheck,
    assess_dose_path_risk,
    build_pending_check_from_task,
    evaluate_correction_interrupt_safety,
    flow_snapshot_is_safe,
    is_dose_correction_step,
)

NOW = datetime(2026, 7, 22, 5, 20, tzinfo=timezone.utc)

_OFF_SNAPSHOT = {
    "valve_solution_supply": False,
    "valve_irrigation": False,
    "pump_main": False,
}


def _base_check(**overrides) -> CorrectionInterruptPendingCheck:
    data = dict(
        zone_id=1,
        task_id=2,
        task_type="irrigation_start",
        topology="two_tank_drip_substrate_trays",
        stage="irrigation_check",
        corr_step="corr_dose_ec",
        workflow_phase="irrigating",
        recovery_source="startup_recovery",
        deadline_at=NOW + timedelta(seconds=60),
    )
    data.update(overrides)
    return CorrectionInterruptPendingCheck(**data)


def _patch_common(monkeypatch, *, phase: str = "irrigating") -> None:
    async def _no_active(*, zone_id: int) -> bool:
        return False

    async def _nodes_ok(*, zone_id: int, required_types=()):
        return True, ()

    async def _phase(*, zone_id: int):
        return phase

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.zone_has_active_ae_task",
        _no_active,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.required_nodes_online",
        _nodes_ok,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.read_workflow_phase",
        _phase,
    )


def test_is_dose_correction_step() -> None:
    assert is_dose_correction_step("corr_dose_ec") is True
    assert is_dose_correction_step("corr_wait_ph") is True
    assert is_dose_correction_step("corr_check") is False


def test_assess_dose_path_risk_fail_closed_for_dose_wait() -> None:
    assert assess_dose_path_risk(corr_step="corr_dose_ec") == DOSE_ACTUATORS_UNVERIFIABLE_REASON
    assert assess_dose_path_risk(corr_step="corr_wait_ph") == DOSE_ACTUATORS_UNVERIFIABLE_REASON
    assert assess_dose_path_risk(corr_step="corr_check") is None


def test_flow_snapshot_is_safe_for_irrigation_check() -> None:
    assert flow_snapshot_is_safe(
        stage="irrigation_check",
        snapshot=_OFF_SNAPSHOT,
    )
    assert not flow_snapshot_is_safe(
        stage="irrigation_check",
        snapshot={
            "valve_solution_supply": False,
            "valve_irrigation": True,
            "pump_main": False,
        },
    )


def test_build_pending_check_from_task() -> None:
    task = SimpleNamespace(
        id=2,
        zone_id=1,
        task_type="irrigation_start",
        topology="two_tank_drip_substrate_trays",
        current_stage="irrigation_check",
        workflow_phase="irrigating",
        irrigation_mode="normal",
        irrigation_requested_duration_sec=300,
        intent_id=8,
        correction=SimpleNamespace(corr_step="corr_dose_ec"),
    )
    check = build_pending_check_from_task(task=task, now=NOW, verify_grace_sec=60)
    assert check is not None
    assert check.task_id == 2
    assert check.deadline_at == NOW + timedelta(seconds=60)
    assert check.corr_step == "corr_dose_ec"


@pytest.mark.asyncio
async def test_evaluate_dose_step_not_safe_even_with_off_snapshot(monkeypatch) -> None:
    """Irrig OFF недостаточен: dose actuators через irr_state не probe'ятся → не safe."""
    check = _base_check()
    runtime_monitor = SimpleNamespace(
        read_latest_irr_state=AsyncMock(
            return_value={
                "has_snapshot": True,
                "is_stale": False,
                "snapshot": _OFF_SNAPSHOT,
            }
        )
    )
    _patch_common(monkeypatch, phase="irrigating")

    verdict = await evaluate_correction_interrupt_safety(
        check=check,
        now=NOW,
        runtime_monitor=runtime_monitor,
    )
    assert verdict.status == "pending"
    assert verdict.reason == DOSE_ACTUATORS_UNVERIFIABLE_REASON
    assert verdict.dose_risk == DOSE_ACTUATORS_UNVERIFIABLE_REASON


@pytest.mark.asyncio
async def test_evaluate_dose_step_unsafe_after_grace_even_with_off_snapshot(
    monkeypatch,
) -> None:
    check = _base_check(deadline_at=NOW - timedelta(seconds=1))
    runtime_monitor = SimpleNamespace(
        read_latest_irr_state=AsyncMock(
            return_value={
                "has_snapshot": True,
                "is_stale": False,
                "snapshot": _OFF_SNAPSHOT,
            }
        )
    )
    _patch_common(monkeypatch, phase="irrigating")

    verdict = await evaluate_correction_interrupt_safety(
        check=check,
        now=NOW,
        runtime_monitor=runtime_monitor,
    )
    assert verdict.status == "unsafe"
    assert verdict.reason == f"{DOSE_ACTUATORS_UNVERIFIABLE_REASON}_after_grace"
    assert verdict.dose_risk == DOSE_ACTUATORS_UNVERIFIABLE_REASON


@pytest.mark.asyncio
async def test_evaluate_safe_when_non_dose_step_and_off_snapshot(monkeypatch) -> None:
    """Без dose-risk irrig OFF → safe (будущий/не-dose путь)."""
    check = _base_check(corr_step="corr_check")
    runtime_monitor = SimpleNamespace(
        read_latest_irr_state=AsyncMock(
            return_value={
                "has_snapshot": True,
                "is_stale": False,
                "snapshot": _OFF_SNAPSHOT,
            }
        )
    )
    _patch_common(monkeypatch, phase="irrigating")

    verdict = await evaluate_correction_interrupt_safety(
        check=check,
        now=NOW,
        runtime_monitor=runtime_monitor,
    )
    assert verdict.status == "safe"
    assert verdict.reason == "irr_state_off_confirmed"
    assert verdict.dose_risk is None


@pytest.mark.asyncio
async def test_evaluate_pending_while_waiting_nodes(monkeypatch) -> None:
    check = _base_check()
    runtime_monitor = SimpleNamespace(read_latest_irr_state=AsyncMock())

    async def _no_active(*, zone_id: int) -> bool:
        return False

    async def _nodes_offline(*, zone_id: int, required_types=()):
        return False, ("irrig",)

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.zone_has_active_ae_task",
        _no_active,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.required_nodes_online",
        _nodes_offline,
    )

    verdict = await evaluate_correction_interrupt_safety(
        check=check,
        now=NOW,
        runtime_monitor=runtime_monitor,
    )
    assert verdict.status == "pending"
    assert "waiting_nodes" in verdict.reason
    assert verdict.dose_risk == DOSE_ACTUATORS_UNVERIFIABLE_REASON


@pytest.mark.asyncio
async def test_evaluate_ready_stale_snapshot_not_safe(monkeypatch) -> None:
    """CRITICAL: ready + stale/missing snapshot — НЕ auto-safe (fail-closed)."""
    check = _base_check()
    runtime_monitor = SimpleNamespace(
        read_latest_irr_state=AsyncMock(
            return_value={
                "has_snapshot": True,
                "is_stale": True,
                "snapshot": {"pump_main": True, "valve_irrigation": True},
            }
        )
    )
    _patch_common(monkeypatch, phase="ready")

    verdict = await evaluate_correction_interrupt_safety(
        check=check,
        now=NOW,
        runtime_monitor=runtime_monitor,
    )
    assert verdict.status == "pending"
    assert verdict.status != "safe"
    assert "waiting_fresh_irr_state" in verdict.reason
    assert "ready" in verdict.reason
    assert verdict.dose_risk == DOSE_ACTUATORS_UNVERIFIABLE_REASON


@pytest.mark.asyncio
async def test_evaluate_ready_stale_snapshot_unsafe_after_grace(monkeypatch) -> None:
    check = _base_check(deadline_at=NOW - timedelta(seconds=1))
    runtime_monitor = SimpleNamespace(
        read_latest_irr_state=AsyncMock(
            return_value={
                "has_snapshot": False,
                "is_stale": True,
                "snapshot": None,
            }
        )
    )
    _patch_common(monkeypatch, phase="ready")

    verdict = await evaluate_correction_interrupt_safety(
        check=check,
        now=NOW,
        runtime_monitor=runtime_monitor,
    )
    assert verdict.status == "unsafe"
    assert "irr_state_unavailable_after_grace" in verdict.reason
    assert "ready" in verdict.reason


@pytest.mark.asyncio
async def test_evaluate_idle_missing_snapshot_not_safe(monkeypatch) -> None:
    check = _base_check()
    runtime_monitor = SimpleNamespace(
        read_latest_irr_state=AsyncMock(
            return_value={
                "has_snapshot": False,
                "is_stale": False,
                "snapshot": None,
            }
        )
    )
    _patch_common(monkeypatch, phase="idle")

    verdict = await evaluate_correction_interrupt_safety(
        check=check,
        now=NOW,
        runtime_monitor=runtime_monitor,
    )
    assert verdict.status == "pending"
    assert "waiting_fresh_irr_state" in verdict.reason
    assert "idle" in verdict.reason


@pytest.mark.asyncio
async def test_evaluate_unsafe_after_grace_when_actuators_on(monkeypatch) -> None:
    check = _base_check(deadline_at=NOW - timedelta(seconds=1))
    runtime_monitor = SimpleNamespace(
        read_latest_irr_state=AsyncMock(
            return_value={
                "has_snapshot": True,
                "is_stale": False,
                "snapshot": {
                    "valve_solution_supply": False,
                    "valve_irrigation": True,
                    "pump_main": True,
                },
            }
        )
    )
    _patch_common(monkeypatch, phase="irrigating")

    verdict = await evaluate_correction_interrupt_safety(
        check=check,
        now=NOW,
        runtime_monitor=runtime_monitor,
    )
    assert verdict.status == "unsafe"
    assert verdict.reason == "irr_state_actuators_active_after_grace"
    assert verdict.dose_risk == DOSE_ACTUATORS_UNVERIFIABLE_REASON


def test_pending_check_event_payload_roundtrip() -> None:
    from ae3lite.application.services.correction_interrupt_safety import (
        pending_check_from_event_payload,
        pending_check_to_event_payload,
    )

    check = _base_check(
        irrigation_mode="normal",
        irrigation_requested_duration_sec=300,
        intent_id=8,
    )
    payload = pending_check_to_event_payload(check)
    restored = pending_check_from_event_payload(zone_id=1, payload=payload, fallback_now=NOW)
    assert restored is not None
    assert restored.task_id == check.task_id
    assert restored.corr_step == check.corr_step
    assert restored.deadline_at == check.deadline_at
    assert restored.irrigation_mode == "normal"
    assert restored.irrigation_requested_duration_sec == 300
    assert restored.intent_id == 8
    assert "irrigation_mode" in payload
    assert "intent_id" in payload


@pytest.mark.asyncio
async def test_load_open_pending_skips_closed_and_restores_open(monkeypatch) -> None:
    from ae3lite.application.services.correction_interrupt_safety import (
        HARDWARE_SAFE_EVENT,
        PENDING_VERIFY_EVENT,
        load_open_pending_correction_interrupt_checks,
        pending_check_to_event_payload,
    )

    open_check = _base_check(task_id=11)
    closed_check = _base_check(task_id=12)

    async def _fetch(sql: str, *args):
        assert args[0] == PENDING_VERIFY_EVENT
        # $1=type, $2=closed event types, $3=lookback hours
        assert HARDWARE_SAFE_EVENT in args[1]
        return [
            {"zone_id": 1, "payload": pending_check_to_event_payload(open_check)},
            {"zone_id": 1, "payload": pending_check_to_event_payload(closed_check)},
            # duplicate task_id — last wins
            {
                "zone_id": 1,
                "payload": pending_check_to_event_payload(
                    _base_check(task_id=11, corr_step="corr_wait_ph")
                ),
            },
        ]

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.fetch",
        _fetch,
    )
    loaded = await load_open_pending_correction_interrupt_checks(now=NOW)
    by_task = {c.task_id: c for c in loaded}
    assert set(by_task) == {11, 12}
    assert by_task[11].corr_step == "corr_wait_ph"


def test_build_fail_safe_shutdown_commands_orders_pump_first() -> None:
    from ae3lite.application.services.correction_interrupt_safety import (
        build_fail_safe_shutdown_commands,
    )

    commands = build_fail_safe_shutdown_commands(
        actuators=(
            {"node_uid": "irrig-1", "node_type": "irrig", "channel": "valve_irrigation"},
            {"node_uid": "irrig-1", "node_type": "irrig", "channel": "pump_main"},
            {"node_uid": "ph-1", "node_type": "ph", "channel": "pump_a"},
        )
    )
    assert [c.channel for c in commands] == ["pump_main", "valve_irrigation"]
    assert all(c.payload.get("_ae3_fail_safe") is True for c in commands)
    assert all(c.payload.get("params", {}).get("state") is False for c in commands)


@pytest.mark.asyncio
async def test_attempt_fail_safe_stop_publishes_via_gateway(monkeypatch) -> None:
    from ae3lite.application.services.correction_interrupt_safety import (
        attempt_correction_interrupt_fail_safe_stop,
    )

    async def _actuators(*, zone_id: int):
        return (
            {"node_uid": "irrig-1", "node_type": "irrig", "channel": "pump_main"},
            {"node_uid": "irrig-1", "node_type": "irrig", "channel": "valve_irrigation"},
        )

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.load_irrig_fail_safe_actuators",
        _actuators,
    )
    gateway = SimpleNamespace(run_publish_only_batch=AsyncMock(return_value={"success": True}))
    result = await attempt_correction_interrupt_fail_safe_stop(
        check=_base_check(),
        now=NOW,
        command_gateway=gateway,
    )
    assert result.attempted is True
    assert result.success is True
    assert result.commands_total == 2
    gateway.run_publish_only_batch.assert_awaited_once()
    call = gateway.run_publish_only_batch.await_args
    assert call.kwargs["task"].id == 2
    assert call.kwargs["task"].zone_id == 1


@pytest.mark.asyncio
async def test_attempt_fail_safe_stop_skips_without_gateway() -> None:
    from ae3lite.application.services.correction_interrupt_safety import (
        attempt_correction_interrupt_fail_safe_stop,
    )

    result = await attempt_correction_interrupt_fail_safe_stop(
        check=_base_check(),
        now=NOW,
        command_gateway=None,
    )
    assert result.attempted is False
    assert result.success is False
    assert result.reason == "no_command_gateway"


@pytest.mark.asyncio
async def test_worker_unsafe_attempts_fail_safe_before_escalate(monkeypatch) -> None:
    from ae3lite.runtime.worker import Ae3RuntimeWorker

    check = _base_check(deadline_at=NOW - timedelta(seconds=1))
    stop_mock = AsyncMock(
        return_value=SimpleNamespace(attempted=True, success=True, reason="ok", commands_total=2)
    )
    escalate_mock = AsyncMock()
    evaluate_mock = AsyncMock(
        return_value=SimpleNamespace(status="unsafe", reason="irr_state_actuators_active_after_grace")
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.evaluate_correction_interrupt_safety",
        evaluate_mock,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.attempt_correction_interrupt_fail_safe_stop",
        stop_mock,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.escalate_correction_interrupt_hardware_risk",
        escalate_mock,
    )

    worker = Ae3RuntimeWorker(
        owner="test",
        claim_next_task_use_case=SimpleNamespace(),
        idle_poll_interval_sec=0.5,
        execute_task_use_case=SimpleNamespace(),
        startup_recovery_use_case=SimpleNamespace(),
        zone_lease_repository=SimpleNamespace(),
        zone_intent_repository=SimpleNamespace(),
        runtime_monitor=SimpleNamespace(),
        command_gateway=SimpleNamespace(),
        spawn_background_task_fn=lambda *a, **k: None,
        now_fn=lambda: NOW,
        logger=SimpleNamespace(
            info=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            debug=lambda *a, **k: None,
            error=lambda *a, **k: None,
        ),
    )
    worker._pending_correction_safety_checks = [check]
    await worker._maybe_run_correction_interrupt_safety_once()
    stop_mock.assert_awaited_once()
    escalate_mock.assert_awaited_once()
    assert stop_mock.await_args.kwargs["check"].task_id == 2
    assert escalate_mock.await_args.kwargs["reason"] == "irr_state_actuators_active_after_grace"
    assert worker._pending_correction_safety_checks == []

# ── required_nodes_online / worker replay hardening ─────────────────


@pytest.mark.asyncio
async def test_required_nodes_online_requires_all_assigned_of_type(monkeypatch) -> None:
    """Нельзя брать только первую ноду типа: offline sibling → missing."""

    async def _fetch(sql: str, *args):
        return [
            {"node_type": "irrig", "status": "online", "last_seen_age_sec": 5},
            {"node_type": "irrig", "status": "offline", "last_seen_age_sec": 5},
            {"node_type": "ph", "status": "online", "last_seen_age_sec": 5},
            {"node_type": "ec", "status": "online", "last_seen_age_sec": 5},
        ]

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.fetch",
        _fetch,
    )
    from ae3lite.application.services.correction_interrupt_safety import required_nodes_online

    ok, missing = await required_nodes_online(zone_id=1)
    assert ok is False
    assert "irrig" in missing


@pytest.mark.asyncio
async def test_required_nodes_online_rejects_stale_last_seen(monkeypatch) -> None:
    async def _fetch(sql: str, *args):
        return [
            {"node_type": "irrig", "status": "online", "last_seen_age_sec": 500},
            {"node_type": "ph", "status": "online", "last_seen_age_sec": 5},
            {"node_type": "ec", "status": "online", "last_seen_age_sec": 5},
        ]

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.fetch",
        _fetch,
    )
    from ae3lite.application.services.correction_interrupt_safety import required_nodes_online

    ok, missing = await required_nodes_online(zone_id=1, max_age_sec=120)
    assert ok is False
    assert missing == ("irrig",)


@pytest.mark.asyncio
async def test_required_nodes_online_missing_type_is_fail_closed(monkeypatch) -> None:
    async def _fetch(sql: str, *args):
        return [
            {"node_type": "irrig", "status": "online", "last_seen_age_sec": 5},
            {"node_type": "ph", "status": "online", "last_seen_age_sec": 5},
        ]

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.fetch",
        _fetch,
    )
    from ae3lite.application.services.correction_interrupt_safety import required_nodes_online

    ok, missing = await required_nodes_online(zone_id=1)
    assert ok is False
    assert "ec" in missing


@pytest.mark.asyncio
async def test_required_nodes_online_all_fresh(monkeypatch) -> None:
    async def _fetch(sql: str, *args):
        return [
            {"node_type": "irrig", "status": "online", "last_seen_age_sec": 5},
            {"node_type": "ph", "status": "online", "last_seen_age_sec": 10},
            {"node_type": "ec", "status": "online", "last_seen_age_sec": 15},
        ]

    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.fetch",
        _fetch,
    )
    from ae3lite.application.services.correction_interrupt_safety import required_nodes_online

    ok, missing = await required_nodes_online(zone_id=1)
    assert ok is True
    assert missing == ()


def _build_interrupt_worker(
    *,
    zone_intent_repository: object,
    create_task_from_intent_use_case: object | None = None,
    runtime_monitor: object | None = None,
    correction_interrupt_replay_irrigation: bool = True,
    now: datetime = NOW,
):
    import asyncio
    import logging
    from ae3lite.runtime import Ae3RuntimeWorker

    logger = logging.getLogger("test_correction_interrupt_worker")
    return Ae3RuntimeWorker(
        owner="interrupt-test-worker",
        claim_next_task_use_case=SimpleNamespace(run=AsyncMock(return_value=None)),
        idle_poll_interval_sec=0.01,
        execute_task_use_case=SimpleNamespace(run=AsyncMock(return_value=None)),
        startup_recovery_use_case=SimpleNamespace(run=AsyncMock(return_value=None)),
        task_repository=SimpleNamespace(get_active_for_zone=AsyncMock(return_value=None)),
        zone_lease_repository=SimpleNamespace(release=AsyncMock(return_value=True)),
        zone_intent_repository=zone_intent_repository,
        create_task_from_intent_use_case=create_task_from_intent_use_case,
        runtime_monitor=runtime_monitor or SimpleNamespace(),
        correction_interrupt_replay_irrigation=correction_interrupt_replay_irrigation,
        spawn_background_task_fn=lambda coro, **kwargs: asyncio.create_task(
            coro,
            name=str(kwargs.get("task_name") or "ae3-interrupt-test"),
        ),
        now_fn=lambda: now,
        logger=logger,
        lease_ttl_sec=120,
        max_task_execution_sec=900,
        max_parallel_tasks=1,
    )


@pytest.mark.asyncio
async def test_replay_returns_false_and_marks_terminal_when_created_false() -> None:
    intent_repo = SimpleNamespace(
        upsert_irrigation_replay_intent=AsyncMock(return_value=99),
        claim_pending_intent_by_id=AsyncMock(
            return_value={"decision": "claimed", "intent": {"id": 99, "zone_id": 1}}
        ),
        mark_terminal=AsyncMock(return_value=None),
    )
    create_uc = SimpleNamespace(
        run=AsyncMock(return_value=SimpleNamespace(created=False, task=None)),
    )
    worker = _build_interrupt_worker(
        zone_intent_repository=intent_repo,
        create_task_from_intent_use_case=create_uc,
    )
    ok = await worker._replay_irrigation_after_correction_interrupt(
        check=_base_check(),
        now=NOW,
    )
    assert ok is False
    intent_repo.mark_terminal.assert_awaited()
    assert intent_repo.mark_terminal.await_args.kwargs["success"] is False


@pytest.mark.asyncio
async def test_replay_marks_terminal_on_create_exception() -> None:
    intent_repo = SimpleNamespace(
        upsert_irrigation_replay_intent=AsyncMock(return_value=77),
        claim_pending_intent_by_id=AsyncMock(
            return_value={"decision": "claimed", "intent": {"id": 77, "zone_id": 1}}
        ),
        mark_terminal=AsyncMock(return_value=None),
    )
    create_uc = SimpleNamespace(run=AsyncMock(side_effect=RuntimeError("boom")))
    worker = _build_interrupt_worker(
        zone_intent_repository=intent_repo,
        create_task_from_intent_use_case=create_uc,
    )
    ok = await worker._replay_irrigation_after_correction_interrupt(
        check=_base_check(),
        now=NOW,
    )
    assert ok is False
    intent_repo.mark_terminal.assert_awaited_once()
    kwargs = intent_repo.mark_terminal.await_args.kwargs
    assert kwargs["intent_id"] == 77
    assert kwargs["success"] is False
    assert kwargs["error_code"] == "ae3_irrigation_replay_create_failed"


@pytest.mark.asyncio
async def test_replay_returns_true_only_when_created() -> None:
    intent_repo = SimpleNamespace(
        upsert_irrigation_replay_intent=AsyncMock(return_value=55),
        claim_pending_intent_by_id=AsyncMock(
            return_value={"decision": "claimed", "intent": {"id": 55, "zone_id": 1}}
        ),
        mark_terminal=AsyncMock(return_value=None),
    )
    create_uc = SimpleNamespace(
        run=AsyncMock(
            return_value=SimpleNamespace(
                created=True,
                task=SimpleNamespace(id=500, intent_id=55),
            )
        ),
    )
    worker = _build_interrupt_worker(
        zone_intent_repository=intent_repo,
        create_task_from_intent_use_case=create_uc,
    )
    ok = await worker._replay_irrigation_after_correction_interrupt(
        check=_base_check(),
        now=NOW,
    )
    assert ok is True
    intent_repo.mark_terminal.assert_not_awaited()


@pytest.mark.asyncio
async def test_evaluate_exception_after_deadline_escalates(monkeypatch) -> None:
    check = _base_check(deadline_at=NOW - timedelta(seconds=1))
    escalate = AsyncMock()
    fail_safe = AsyncMock(
        return_value=SimpleNamespace(success=False, reason="no_command_gateway", attempted=False)
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.evaluate_correction_interrupt_safety",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.attempt_correction_interrupt_fail_safe_stop",
        fail_safe,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.escalate_correction_interrupt_hardware_risk",
        escalate,
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.emit_correction_interrupt_hardware_safe",
        AsyncMock(),
    )

    worker = _build_interrupt_worker(
        zone_intent_repository=SimpleNamespace(mark_terminal=AsyncMock()),
        runtime_monitor=SimpleNamespace(),
        now=NOW,
    )
    worker._pending_correction_safety_checks = [check]
    await worker._maybe_run_correction_interrupt_safety_once()
    assert worker._pending_correction_safety_checks == []
    fail_safe.assert_awaited_once()
    escalate.assert_awaited_once()
    assert escalate.await_args.kwargs["reason"] == "evaluate_exception_after_grace"


@pytest.mark.asyncio
async def test_evaluate_exception_before_deadline_keeps_pending(monkeypatch) -> None:
    check = _base_check(deadline_at=NOW + timedelta(seconds=60))
    escalate = AsyncMock()
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.evaluate_correction_interrupt_safety",
        AsyncMock(side_effect=RuntimeError("transient")),
    )
    monkeypatch.setattr(
        "ae3lite.application.services.correction_interrupt_safety.escalate_correction_interrupt_hardware_risk",
        escalate,
    )

    worker = _build_interrupt_worker(
        zone_intent_repository=SimpleNamespace(mark_terminal=AsyncMock()),
        runtime_monitor=SimpleNamespace(),
        now=NOW,
    )
    worker._pending_correction_safety_checks = [check]
    await worker._maybe_run_correction_interrupt_safety_once()
    assert worker._pending_correction_safety_checks == [check]
    escalate.assert_not_awaited()


def test_env_replay_irrigation_defaults_off(monkeypatch) -> None:
    from ae3lite.runtime.env import Ae3RuntimeConfig

    monkeypatch.delenv("AE_CORRECTION_INTERRUPT_REPLAY_IRRIGATION", raising=False)
    monkeypatch.setenv("AE_DB_DSN", "postgresql://hydro:hydro@localhost:5432/hydro_test")
    monkeypatch.setenv("HISTORY_LOGGER_API_TOKEN", "test-token")
    monkeypatch.setenv("AE_API_TOKEN", "test-token")
    monkeypatch.setenv("APP_ENV", "test")
    cfg = Ae3RuntimeConfig.from_env()
    assert cfg.correction_interrupt_replay_irrigation is False


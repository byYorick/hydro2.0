"""Unit tests for PrepareRecircCheckHandler.

Outcomes:
1. Deadline exceeded → prepare_recirculation_window_exhausted (stage_retry_count++)
2. Targets reached → prepare_recirculation_stop_to_ready
3. Targets not reached → enter_correction (sensors_already_active=True)
4. IRR state probe mismatch → TaskExecutionError (irr_state_mismatch)
5. IRR state stale on first read → waits and retries → ok
6. IRR state stale after wait → fail-closed → TaskExecutionError (irr_state_stale)
7. PH/EC telemetry unavailable → TaskExecutionError
8. stage_def on_corr_success/fail overrides used in correction state
9. correction state caps total attempts by per-PID retry limits
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from unittest.mock import AsyncMock

from ae3lite.application.handlers.prepare_recirc import PrepareRecircCheckHandler
from ae3lite.domain.entities.automation_task import AutomationTask
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.topology_registry import StageDef


NOW = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(hours=1)
FUTURE = NOW + timedelta(hours=1)

RUNTIME = {
    "solution_max_sensor_labels": ["sol_max"],
    "solution_min_sensor_labels": ["sol_min"],
    "level_switch_on_threshold": 0.5,
    "telemetry_max_age_sec": 300,
    "irr_state_max_age_sec": 60,
    "irr_state_wait_timeout_sec": 0.02,
    "irr_state_wait_poll_interval_sec": 0.005,
    "target_ph": 5.8,
    "target_ec": 1.4,
    "prepare_tolerance": {"ph_pct": 15, "ec_pct": 25},
    "correction": {
        "max_ec_correction_attempts": 3,
        "max_ph_correction_attempts": 3,
        "prepare_recirculation_max_correction_attempts": 20,
        "prepare_recirculation_max_attempts": 3,
        "stabilization_sec": 60,
    },
    "process_calibrations": {
        "tank_recirc": {
            "transport_delay_sec": 4,
            "settle_sec": 4,
        },
    },
    "fail_safe_guards": {
        "recirculation_stop_on_solution_min": True,
    },
}


def _make_task(
    *,
    deadline=FUTURE,
    retry_count=0,
    control_mode: str = "auto",
    pending_manual_step: str | None = None,
) -> AutomationTask:
    return AutomationTask.from_row({
        "id": 5, "zone_id": 50, "task_type": "cycle_start", "status": "running",
        "idempotency_key": "k5", "scheduled_for": NOW, "due_at": NOW,
        "claimed_by": "w1", "claimed_at": NOW,
        "error_code": None, "error_message": None,
        "created_at": NOW, "updated_at": NOW, "completed_at": None,
        "topology": "two_tank", "intent_source": None, "intent_trigger": None,
        "intent_id": None, "intent_meta": {},
        "current_stage": "prepare_recirculation_check",
        "workflow_phase": "tank_recirc",
        "stage_deadline_at": deadline, "stage_retry_count": retry_count,
        "stage_entered_at": NOW, "clean_fill_cycle": 1,
        "control_mode_snapshot": control_mode,
        "pending_manual_step": pending_manual_step,
        "corr_step": None,
    })


_IRR_MATCH = {
    "has_snapshot": True, "is_stale": False,
    "snapshot": {"valve_solution_supply": True, "valve_solution_fill": True, "pump_main": True},
}
_IRR_MISMATCH = {
    "has_snapshot": True, "is_stale": False,
    "snapshot": {"valve_solution_supply": True, "valve_solution_fill": True, "pump_main": False},
}


class _Monitor:
    """Configurable mock for PrepareRecircCheckHandler dependencies."""

    def __init__(
        self,
        *,
        ph: float = 5.8,
        ec: float = 1.4,
        ph_samples: list[float] | None = None,
        ec_samples: list[float] | None = None,
        has_ph: bool = True,
        has_ec: bool = True,
        ph_stale: bool = False,
        ec_stale: bool = False,
        irr_state: dict | None = None,
        irr_states: list[dict] | None = None,
        recent_storage_event: dict[str, Any] | None = None,
    ) -> None:
        self._ph = {"has_value": has_ph, "is_stale": False, "value": ph}
        self._ec = {"has_value": has_ec, "is_stale": False, "value": ec}
        self._ph_window = self._build_window(values=ph_samples if ph_samples is not None else [ph] * 3)
        self._ec_window = self._build_window(values=ec_samples if ec_samples is not None else [ec] * 3)
        self._ph_window_state = {"has_sensor": has_ph, "is_stale": ph_stale, "samples": self._ph_window}
        self._ec_window_state = {"has_sensor": has_ec, "is_stale": ec_stale, "samples": self._ec_window}
        # irr_states list is consumed sequentially; falls back to irr_state after exhausted
        self._irr_states: list[dict] = list(irr_states) if irr_states else []
        self._irr_state = irr_state if irr_state is not None else dict(_IRR_MATCH)
        self.irr_reads = 0
        self._recent_storage_event = recent_storage_event

    @staticmethod
    def _build_window(*, values: list[float]) -> tuple[dict[str, Any], ...]:
        sample_count = len(values)
        return tuple(
            {
                "ts": NOW - timedelta(seconds=(sample_count - index)),
                "value": value,
            }
            for index, value in enumerate(values, start=1)
        )

    async def read_metric(self, *, zone_id: int, sensor_type: str, telemetry_max_age_sec: int) -> dict:
        return self._ph if sensor_type == "PH" else self._ec

    async def read_metric_window(
        self,
        *,
        zone_id: int,
        sensor_type: str,
        since_ts: datetime,
        telemetry_max_age_sec: int,
    ) -> dict:
        state = self._ph_window_state if sensor_type == "PH" else self._ec_window_state
        return {
            "has_sensor": state["has_sensor"],
            "has_samples": bool(state["samples"]),
            "is_stale": state["is_stale"],
            "samples": state["samples"],
            "latest_sample_ts": state["samples"][-1]["ts"] if state["samples"] else None,
        }

    async def read_latest_irr_state(self, **_kw: Any) -> dict:
        self.irr_reads += 1
        if self._irr_states:
            return self._irr_states.pop(0)
        return self._irr_state

    async def read_level_switch(self, **_kw: Any) -> dict:
        return {"has_level": True, "is_stale": False, "is_triggered": True}

    async def read_latest_zone_event(self, **_kw: Any) -> dict[str, Any] | None:
        return dict(self._recent_storage_event) if self._recent_storage_event is not None else None


class _MockGateway:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def run_batch(self, *, task: Any, commands: Any, now: Any, track_task_state: bool = True) -> dict:
        self.calls.append({"task": task, "commands": commands, "now": now, "track_task_state": track_task_state})
        return {"success": True, "error_code": None, "error_message": None}


class _ProbeGateway(_MockGateway):
    def __init__(self, *, probe_cmd_id: str) -> None:
        super().__init__()
        self._probe_cmd_id = probe_cmd_id

    async def run_batch(self, *, task: Any, commands: Any, now: Any, track_task_state: bool = True) -> dict:
        self.calls.append({"task": task, "commands": commands, "now": now, "track_task_state": track_task_state})
        return {
            "success": True,
            "error_code": None,
            "error_message": None,
            "command_statuses": [{"legacy_cmd_id": self._probe_cmd_id}],
        }


class _MockPlan:
    def __init__(self, runtime: dict | None = None) -> None:
        self.runtime = runtime or RUNTIME
        self.named_plans = {"irr_state_probe": ("probe_cmd",)}


class _StageDef:
    on_corr_success = "prepare_recirculation_stop_to_ready"
    on_corr_fail = "prepare_recirculation_window_exhausted"


def _make_handler(monitor: _Monitor | None = None, gateway: _MockGateway | None = None) -> PrepareRecircCheckHandler:
    return PrepareRecircCheckHandler(
        runtime_monitor=monitor or _Monitor(),
        command_gateway=gateway or _MockGateway(),
    )


# ── 1. Deadline exceeded ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deadline_exceeded_returns_window_exhausted() -> None:
    """Deadline passed → prepare_recirculation_window_exhausted with retry_count+1."""
    monitor = _Monitor()
    handler = _make_handler(monitor=monitor)
    task = _make_task(deadline=PAST, retry_count=2)
    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 3
    assert monitor.irr_reads == 0


@pytest.mark.asyncio
async def test_deadline_exceeded_increments_retry_count() -> None:
    """Retry count increments correctly for any initial value."""
    handler = _make_handler()
    for initial_retry in (0, 1, 5):
        task = _make_task(deadline=PAST, retry_count=initial_retry)
        outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
        assert outcome.stage_retry_count == initial_retry + 1


@pytest.mark.asyncio
async def test_deadline_too_close_for_probe_exhausts_window_without_probe() -> None:
    monitor = _Monitor()
    handler = _make_handler(monitor=monitor)
    task = _make_task(deadline=NOW + timedelta(seconds=4), retry_count=1)

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=_StageDef(), now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 2
    assert monitor.irr_reads == 0


@pytest.mark.asyncio
async def test_deadline_six_seconds_away_still_skips_probe_on_realhw_budget() -> None:
    monitor = _Monitor()
    handler = _make_handler(monitor=monitor)
    task = _make_task(deadline=NOW + timedelta(seconds=6), retry_count=2)

    outcome = await handler.run(task=task, plan=_MockPlan(), stage_def=_StageDef(), now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_window_exhausted"
    assert outcome.stage_retry_count == 3
    assert monitor.irr_reads == 0


# ── 2. Targets reached ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_targets_reached_transitions_to_stop_ready() -> None:
    """PH/EC exactly at target → within tolerance → prepare_recirculation_stop_to_ready."""
    handler = _make_handler(monitor=_Monitor(ph=5.8, ec=1.4))
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"


@pytest.mark.asyncio
async def test_targets_reached_within_tolerance() -> None:
    """target_ph=5.8 tol=15% → [4.93, 6.67]; ph=6.0 ec=1.2 → within bounds."""
    handler = _make_handler(monitor=_Monitor(ph=6.0, ec=1.2))
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"


@pytest.mark.asyncio
async def test_targets_soft_tolerance_without_explicit_ready_band_enters_correction() -> None:
    runtime = dict(RUNTIME)
    runtime["target_ph_min"] = 5.6
    runtime["target_ph_max"] = 6.0
    runtime["target_ec_min"] = 1.2
    runtime["target_ec_max"] = 1.45
    handler = _make_handler(monitor=_Monitor(ph=5.8, ec=1.5))

    outcome = await handler.run(task=_make_task(), plan=_MockPlan(runtime=runtime), stage_def=_StageDef(), now=NOW)

    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None


@pytest.mark.asyncio
async def test_targets_reached_uses_explicit_ready_band_when_present() -> None:
    runtime = dict(RUNTIME)
    runtime["prepare_tolerance"] = {"ph_pct": 1, "ec_pct": 1}
    runtime["target_ec_min"] = 1.9
    runtime["target_ec_max"] = 2.1
    handler = _make_handler(monitor=_Monitor(ph=5.8, ec=1.91))

    outcome = await handler.run(task=_make_task(), plan=_MockPlan(runtime=runtime), stage_def=_StageDef(), now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"


@pytest.mark.asyncio
async def test_targets_use_window_median_not_single_latest_sample() -> None:
    handler = _make_handler(
        monitor=_Monitor(
            ph=5.8,
            ec=1.4,
            ph_samples=[4.0, 4.1, 5.8],
            ec_samples=[1.4, 1.4, 1.4],
        )
    )
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "enter_correction"


@pytest.mark.asyncio
async def test_targets_reached_uses_window_grace_for_late_sample() -> None:
    late_samples = [
        {"ts": NOW - timedelta(seconds=7), "value": 5.8},
        {"ts": NOW - timedelta(seconds=5), "value": 5.8},
        {"ts": NOW - timedelta(seconds=3), "value": 5.8},
    ]
    handler = _make_handler(
        monitor=_Monitor(
            ph=5.8,
            ec=1.4,
            ph_samples=[sample["value"] for sample in late_samples],
            ec_samples=[1.4, 1.4, 1.4],
        )
    )
    handler._runtime_monitor._ph_window_state["samples"] = tuple(late_samples)
    handler._runtime_monitor._ec_window_state["samples"] = tuple(
        {"ts": NOW - timedelta(seconds=offset), "value": 1.4}
        for offset in (7, 5, 3)
    )
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"


# ── 3. Targets not reached → enter_correction ─────────────────────────────────

@pytest.mark.asyncio
async def test_targets_not_reached_enters_correction() -> None:
    """PH way below target → enter_correction with sensors_already_active=True."""
    handler = _make_handler(monitor=_Monitor(ph=4.0, ec=1.4))
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "enter_correction"
    assert outcome.correction is not None
    assert outcome.correction.corr_step == "corr_check"
    assert outcome.correction.attempt == 0
    assert outcome.correction.ec_attempt == 0
    assert outcome.correction.ph_attempt == 0
    assert outcome.correction.activated_here is False
    assert outcome.correction.return_stage_success == "prepare_recirculation_stop_to_ready"
    assert outcome.correction.return_stage_fail == "prepare_recirculation_window_exhausted"


@pytest.mark.asyncio
async def test_manual_prepare_recirculation_without_pending_step_polls() -> None:
    handler = _make_handler(monitor=_Monitor(ph=4.0, ec=1.4))
    outcome = await handler.run(
        task=_make_task(control_mode="manual"),
        plan=_MockPlan(),
        stage_def=_StageDef(),
        now=NOW,
    )
    assert outcome.kind == "poll"
    assert outcome.due_delay_sec == 10


@pytest.mark.asyncio
async def test_manual_prepare_recirculation_stop_transitions_to_ready() -> None:
    handler = _make_handler(monitor=_Monitor(ph=4.0, ec=1.4))
    outcome = await handler.run(
        task=_make_task(control_mode="manual", pending_manual_step="prepare_recirculation_stop"),
        plan=_MockPlan(),
        stage_def=_StageDef(),
        now=NOW,
    )
    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"


@pytest.mark.asyncio
async def test_correction_state_caps_total_attempts_by_pid_limits() -> None:
    """prepare_recirculation should not exceed per-PID retry limits."""
    handler = _make_handler(monitor=_Monitor(ph=4.0))
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.correction.max_attempts == 3
    assert outcome.correction.ec_max_attempts == 3
    assert outcome.correction.ph_max_attempts == 3


# ── 4. IRR state probe mismatch ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_irr_state_mismatch_raises() -> None:
    """IRR state does not match expected → TaskExecutionError(irr_state_mismatch)."""
    monitor = _Monitor(ph=6.0, ec=2.0, irr_state=dict(_IRR_MISMATCH))
    handler = _make_handler(monitor=monitor)
    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert exc_info.value.code == "irr_state_mismatch"


# ── 5. IRR state stale → waits → succeeds ────────────────────────────────────

@pytest.mark.asyncio
async def test_irr_state_stale_waits_for_fresh_snapshot() -> None:
    """First read stale → polls → gets fresh → proceeds normally."""
    stale = {
        "has_snapshot": True, "is_stale": True,
        "snapshot": {"valve_solution_supply": True, "valve_solution_fill": True, "pump_main": True},
    }
    fresh = {
        "has_snapshot": True, "is_stale": False,
        "snapshot": {"valve_solution_supply": True, "valve_solution_fill": True, "pump_main": True},
    }
    monitor = _Monitor(ph=5.8, ec=1.4, irr_states=[stale, fresh])
    handler = _make_handler(monitor=monitor)
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"
    assert monitor.irr_reads >= 2


@pytest.mark.asyncio
async def test_irr_state_waits_for_matching_probe_cmd_id() -> None:
    """Old snapshot from another probe must not satisfy current probe."""
    runtime = {**RUNTIME, "irr_state_wait_timeout_sec": 0.02, "irr_state_wait_poll_interval_sec": 0.005}

    class _CausalMonitor(_Monitor):
        async def read_latest_irr_state(self, *, expected_cmd_id: str | None = None, **_kw: Any) -> dict:
            self.irr_reads += 1
            if expected_cmd_id == "probe-cmd-99" and self.irr_reads >= 2:
                return {**dict(_IRR_MATCH), "cmd_id": "probe-cmd-99"}
            return {**dict(_IRR_MATCH), "cmd_id": "older-probe"}

    monitor = _CausalMonitor(ph=5.8, ec=1.4)
    handler = _make_handler(monitor=monitor, gateway=_ProbeGateway(probe_cmd_id="probe-cmd-99"))
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(runtime), stage_def=_StageDef(), now=NOW)
    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"
    assert monitor.irr_reads >= 2
    assert handler._command_gateway.calls[0]["track_task_state"] is False


@pytest.mark.asyncio
async def test_irr_state_republishes_probe_after_transient_loss() -> None:
    runtime = {**RUNTIME, "irr_state_wait_timeout_sec": 0.01, "irr_state_wait_poll_interval_sec": 0.005}

    class _RepublishMonitor(_Monitor):
        async def read_latest_irr_state(self, *, expected_cmd_id: str | None = None, **_kw: Any) -> dict:
            self.irr_reads += 1
            if expected_cmd_id == "probe-cmd-02":
                return {**dict(_IRR_MATCH), "cmd_id": "probe-cmd-02"}
            return {"has_snapshot": False, "is_stale": False, "snapshot": None, "cmd_id": "older-probe"}

    class _MultiProbeGateway(_MockGateway):
        def __init__(self) -> None:
            super().__init__()
            self._cmd_ids = iter(("probe-cmd-01", "probe-cmd-02"))

        async def run_batch(self, *, task: Any, commands: Any, now: Any, track_task_state: bool = True) -> dict:
            self.calls.append({"task": task, "commands": commands, "now": now, "track_task_state": track_task_state})
            return {
                "success": True,
                "error_code": None,
                "error_message": None,
                "command_statuses": [{"legacy_cmd_id": next(self._cmd_ids)}],
            }

    gateway = _MultiProbeGateway()
    monitor = _RepublishMonitor(ph=5.8, ec=1.4)
    handler = _make_handler(monitor=monitor, gateway=gateway)

    outcome = await handler.run(task=_make_task(), plan=_MockPlan(runtime), stage_def=_StageDef(), now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"
    assert len(gateway.calls) == 2
    assert all(call["track_task_state"] is False for call in gateway.calls)


@pytest.mark.asyncio
async def test_irr_state_cmd_id_mismatch_after_republish_fails_closed() -> None:
    runtime = {**RUNTIME, "irr_state_wait_timeout_sec": 0.01, "irr_state_wait_poll_interval_sec": 0.005}

    class _MismatchMonitor(_Monitor):
        async def read_latest_irr_state(self, *, expected_cmd_id: str | None = None, **_kw: Any) -> dict:
            self.irr_reads += 1
            return {**dict(_IRR_MATCH), "cmd_id": "older-probe"}

    gateway = _ProbeGateway(probe_cmd_id="probe-cmd-99")
    handler = _make_handler(monitor=_MismatchMonitor(), gateway=gateway)

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=_make_task(), plan=_MockPlan(runtime), stage_def=_StageDef(), now=NOW)

    assert exc_info.value.code == "irr_state_unavailable"
    assert len(gateway.calls) == 2


# ── 6. IRR state stale after wait → fail-closed ───────────────────────────────

@pytest.mark.asyncio
async def test_irr_state_still_stale_after_wait_fails_closed() -> None:
    """Both reads stale → fail-closed → TaskExecutionError(irr_state_stale)."""
    stale = {
        "has_snapshot": True, "is_stale": True,
        "snapshot": {"valve_solution_supply": True, "valve_solution_fill": True, "pump_main": True},
    }
    monitor = _Monitor(irr_states=[stale, stale], irr_state=stale)
    handler = _make_handler(monitor=monitor)
    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)
    assert exc_info.value.code == "irr_state_stale"
    assert monitor.irr_reads >= 2


# ── 7. Telemetry unavailable ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ph_unavailable_raises() -> None:
    """PH telemetry has_value=False → TaskExecutionError."""
    handler = _make_handler(monitor=_Monitor(has_ph=False))
    with pytest.raises(TaskExecutionError, match="недоступна"):
        await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)


@pytest.mark.asyncio
async def test_ec_unavailable_raises() -> None:
    """EC telemetry has_value=False → TaskExecutionError."""
    handler = _make_handler(monitor=_Monitor(has_ec=False))
    with pytest.raises(TaskExecutionError, match="недоступна"):
        await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)


# ── 8. stage_def on_corr_success/fail overrides ───────────────────────────────

@pytest.mark.asyncio
async def test_correction_uses_stage_def_on_corr_fail() -> None:
    """Custom on_corr_success/fail from stage_def are propagated to correction state."""
    class _CustomStageDef:
        on_corr_success = "custom_success"
        on_corr_fail = "custom_fail"

    handler = _make_handler(monitor=_Monitor(ph=4.0))
    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_CustomStageDef(), now=NOW)
    assert outcome.correction.return_stage_success == "custom_success"
    assert outcome.correction.return_stage_fail == "custom_fail"


@pytest.mark.asyncio
async def test_prepare_recirculation_recent_solution_low_event_transitions_to_terminal_stop() -> None:
    handler = _make_handler(
        monitor=_Monitor(
            recent_storage_event={
                "event_type": "RECIRCULATION_SOLUTION_LOW",
                "event_id": 31,
                "created_at": NOW,
                "payload": {"channel": "storage_state"},
            }
        )
    )

    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_solution_low_stop"


@pytest.mark.asyncio
async def test_prepare_recirculation_ignores_solution_low_event_when_guard_disabled() -> None:
    handler = _make_handler(
        monitor=_Monitor(
            recent_storage_event={
                "event_type": "RECIRCULATION_SOLUTION_LOW",
                "event_id": 33,
                "created_at": NOW,
                "payload": {"channel": "storage_state"},
            }
        )
    )
    runtime = {
        **RUNTIME,
        "fail_safe_guards": {
            "recirculation_stop_on_solution_min": False,
        },
    }

    outcome = await handler.run(task=_make_task(), plan=_MockPlan(runtime), stage_def=_StageDef(), now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_stop_to_ready"


@pytest.mark.asyncio
async def test_prepare_recirculation_solution_min_sensor_fallback_transitions_to_terminal_stop() -> None:
    class _LowLevelMonitor(_Monitor):
        async def read_level_switch(self, **_kw: Any) -> dict:
            return {
                "has_level": True,
                "is_stale": False,
                "is_triggered": False,
                "sample_ts": NOW,
                "sample_age_sec": 0.0,
            }

    handler = _make_handler(monitor=_LowLevelMonitor())

    outcome = await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)

    assert outcome.kind == "transition"
    assert outcome.next_stage == "prepare_recirculation_solution_low_stop"


@pytest.mark.asyncio
async def test_prepare_recirculation_recent_estop_reconcile_failure_raises_emergency_stop() -> None:
    handler = _make_handler(
        monitor=_Monitor(
            recent_storage_event={
                "event_type": "EMERGENCY_STOP_ACTIVATED",
                "event_id": 32,
                "created_at": NOW,
                "payload": {"channel": "storage_state"},
            }
        )
    )
    handler._probe_irr_state = AsyncMock(side_effect=TaskExecutionError("irr_state_mismatch", "pump off"))

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=_make_task(), plan=_MockPlan(), stage_def=_StageDef(), now=NOW)

    assert exc_info.value.code == "emergency_stop_activated"

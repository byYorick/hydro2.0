"""Integration-style tests for multi-dose EC correction (CORRECTION_CYCLE_SPEC §6.2 MVP).

Goes above the ``_run_dose_ec`` unit stubs in
``test_ae3lite_correction_handler_multi_dose.py`` by driving
``CorrectionHandler.run()`` with ``CorrectionEventLogger`` enrichment and a
gateway that returns per-command ``command_statuses``.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Mapping

import pytest
from prometheus_client import REGISTRY

from ae3lite.application.handlers.correction import CorrectionHandler
from ae3lite.application.services.correction_event_logger import CorrectionEventLogger
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.errors import TaskExecutionError
from test_ae3lite_correction_handler import (
    NOW,
    RUNTIME,
    _MockPlan,
    _MockRuntimeMonitor,
    _base_corr,
    _make_task,
)


class _FakeEventSink:
    """Recording stand-in for ``common.db.create_zone_event``."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, str, dict]] = []

    async def __call__(
        self, zone_id: int, event_type: str, payload: Mapping[str, Any]
    ) -> None:
        self.calls.append((zone_id, event_type, dict(payload)))


class _DoseGateway:
    """Gateway stub with per-call outcomes and realistic command_statuses."""

    def __init__(
        self,
        *,
        dose_outcomes: list[dict[str, Any]] | None = None,
        default_success: bool = True,
    ) -> None:
        self._dose_outcomes = list(dose_outcomes or [])
        self._default_success = default_success
        self.calls: list[dict[str, Any]] = []

    @staticmethod
    def _is_dose_batch(commands: tuple[Any, ...]) -> bool:
        for cmd in commands:
            payload = cmd.payload if hasattr(cmd, "payload") else {}
            if isinstance(payload, dict) and payload.get("cmd") == "dose":
                return True
        return False

    async def run_batch(self, *, task, commands, now, track_task_state: bool = True):
        self.calls.append(
            {
                "task": task,
                "commands": tuple(commands),
                "now": now,
                "track_task_state": track_task_state,
            }
        )
        is_dose = self._is_dose_batch(tuple(commands))
        if is_dose and self._dose_outcomes:
            outcome = self._dose_outcomes.pop(0)
        else:
            outcome = {
                "success": self._default_success,
                "error_code": None if self._default_success else "hw_error",
                "error_message": None if self._default_success else "device offline",
                "command_statuses": [],
            }
        if outcome.get("success") and not outcome.get("command_statuses"):
            outcome = {
                **outcome,
                "command_statuses": [
                    {
                        "terminal_status": "DONE",
                        "success": True,
                        "legacy_cmd_id": f"dose-{len(self.calls)}",
                    }
                    for _ in commands
                ],
            }
        return {**outcome, "task": task}


def _runtime_plan(**overrides: Any) -> _MockPlan:
    runtime = deepcopy(RUNTIME)
    runtime.update(overrides)
    return _MockPlan(runtime=runtime)


def _dose_commands(gateway: _DoseGateway) -> list[PlannedCommand]:
    commands: list[PlannedCommand] = []
    for call in gateway.calls:
        for cmd in call["commands"]:
            payload = cmd.payload if hasattr(cmd, "payload") else {}
            if isinstance(payload, dict) and payload.get("cmd") == "dose":
                commands.append(cmd)
    return commands


def _three_component_seq() -> list[dict[str, Any]]:
    return [
        {"component": "calcium", "node_uid": "nd-ca", "channel": "pump_b", "amount_ml": 1.0, "duration_ms": 100},
        {"component": "magnesium", "node_uid": "nd-mg", "channel": "pump_c", "amount_ml": 2.0, "duration_ms": 200},
        {"component": "micro", "node_uid": "nd-mi", "channel": "pump_d", "amount_ml": 3.0, "duration_ms": 300},
    ]


def _seq_corr(*, seq: list[dict], seq_index: int = 0):
    return _base_corr(
        corr_step="corr_dose_ec",
        needs_ec=True,
        ec_node_uid="nd-ca",
        ec_channel="pump_b",
        ec_amount_ml=6.0,
        ec_duration_ms=600,
        activated_here=False,
        stabilization_sec=1,
        return_stage_success="irrigation_check",
        return_stage_fail="irrigation_check",
        ec_component="multi_sequential",
        ec_dose_sequence_json=json.dumps(seq),
        ec_current_seq_index=seq_index,
    )


def _parallel_corr(*, seq: list[dict]):
    return _base_corr(
        corr_step="corr_dose_ec",
        needs_ec=True,
        ec_node_uid="nd-ca",
        ec_channel="pump_b",
        ec_amount_ml=6.0,
        ec_duration_ms=600,
        activated_here=False,
        stabilization_sec=1,
        return_stage_success="irrigation_check",
        return_stage_fail="irrigation_check",
        ec_component="multi_parallel",
        ec_dose_sequence_json=json.dumps(seq),
        ec_current_seq_index=0,
    )


def _irrigation_task(corr):
    return _make_task(
        corr=corr,
        current_stage="irrigation_check",
        workflow_phase="irrigating",
    )


def _make_integration_handler(
    *,
    gateway: _DoseGateway,
    event_sink: _FakeEventSink,
    monitor: _MockRuntimeMonitor | None = None,
    pid_repo=None,
) -> CorrectionHandler:
    event_logger = CorrectionEventLogger(
        create_event_fn=event_sink,
        probe_snapshot_context_fn=lambda *, task: None,
    )
    return CorrectionHandler(
        runtime_monitor=monitor or _MockRuntimeMonitor(),
        command_gateway=gateway,
        pid_state_repository=pid_repo,
        event_logger=event_logger,
    )


@pytest.mark.asyncio
async def test_integration_multi_sequential_happy_path_via_handler_run(monkeypatch) -> None:
    """Ca→Mg→Micro through handler.run() with event logger + command_statuses."""
    zone_events: list[tuple[int, str, dict]] = []

    async def _capture_zone_event(zone_id: int, event_type: str, payload: Mapping[str, Any]) -> None:
        zone_events.append((zone_id, event_type, dict(payload)))

    monkeypatch.setattr(
        "ae3lite.application.handlers.correction.create_zone_event",
        _capture_zone_event,
    )

    seq = _three_component_seq()
    gateway = _DoseGateway()
    sink = _FakeEventSink()
    handler = _make_integration_handler(gateway=gateway, event_sink=sink)

    corr = _seq_corr(seq=seq)
    task = _irrigation_task(corr)
    plan = _runtime_plan(target_ec=1.5)

    out1 = await handler.run(task=task, plan=plan, stage_def=None, now=NOW)
    assert out1.kind == "enter_correction"
    assert out1.correction.ec_current_seq_index == 1
    assert _dose_commands(gateway)[-1].node_uid == "nd-ca"

    task2 = _make_task(
        corr=out1.correction,
        current_stage="irrigation_check",
        workflow_phase="irrigating",
    )
    out2 = await handler.run(task=task2, plan=plan, stage_def=None, now=NOW)
    assert out2.kind == "enter_correction"
    assert out2.correction.ec_current_seq_index == 2
    assert _dose_commands(gateway)[-1].node_uid == "nd-mg"

    task3 = _make_task(
        corr=out2.correction,
        current_stage="irrigation_check",
        workflow_phase="irrigating",
    )
    out3 = await handler.run(task=task3, plan=plan, stage_def=None, now=NOW)
    assert out3.kind == "enter_correction"
    assert out3.correction.corr_step == "corr_wait_ec"
    assert out3.correction.ec_current_seq_index == 3
    assert _dose_commands(gateway)[-1].node_uid == "nd-mi"
    assert len(_dose_commands(gateway)) == 3

    reactivate_events = [c for c in sink.calls if c[1] == "CORRECTION_SENSOR_MODE_REACTIVATED"]
    assert len(reactivate_events) == 3

    ec_dosing_events = [c for c in sink.calls if c[1] == "EC_DOSING"]
    assert len(ec_dosing_events) == 1
    _zone_id, _etype, payload = ec_dosing_events[0]
    assert payload["event_schema_version"] == 2
    assert payload["task_id"] == 6
    assert payload["stage"] == "irrigation_check"
    assert payload["workflow_phase"] == "irrigating"
    assert payload["seq_index"] == 3
    assert len(payload["dose_sequence"]) == 3

    multi_dose_events = [c for c in zone_events if c[1] == "IRRIGATION_EC_MULTI_DOSE"]
    assert len(multi_dose_events) == 1
    assert multi_dose_events[0][2]["dose_sequence"] == seq


class _PidRepoStub:
    def __init__(self, *, current_ec: float = 1.42) -> None:
        self._current_ec = current_ec

    async def read_measured_value(self, *, zone_id: int, pid_type: str):
        if pid_type == "ec":
            return self._current_ec
        return None

    async def upsert_states(self, **_kwargs):
        return None

    async def clear_feedforward_bias(self, **_kwargs):
        return None

    async def reset_no_effect_counts(self, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_integration_partial_failure_event_logger_and_metric() -> None:
    """Component 0 DONE, component 1 FAIL → enriched event + metric, no recovery."""
    seq = _three_component_seq()
    gateway = _DoseGateway(
        dose_outcomes=[
            {"success": True},
            {
                "success": False,
                "error_code": "hw_error",
                "error_message": "device offline",
                "command_statuses": [
                    {"terminal_status": "ERROR", "success": False, "legacy_cmd_id": "dose-fail"},
                ],
            },
        ]
    )
    sink = _FakeEventSink()
    handler = _make_integration_handler(
        gateway=gateway,
        event_sink=sink,
        pid_repo=_PidRepoStub(current_ec=1.42),
    )
    metric_labels = {"mode": "multi_sequential"}
    before_metric = (
        REGISTRY.get_sample_value("ae3_correction_ec_batch_partial_failure_total", metric_labels)
        or 0.0
    )

    corr = _seq_corr(seq=seq)
    task = _irrigation_task(corr)
    plan = _runtime_plan(target_ec=1.5)

    out1 = await handler.run(task=task, plan=plan, stage_def=None, now=NOW)
    assert out1.correction.ec_current_seq_index == 1

    task2 = _make_task(
        corr=out1.correction,
        current_stage="irrigation_check",
        workflow_phase="irrigating",
    )
    out2 = await handler.run(task=task2, plan=plan, stage_def=None, now=NOW)

    assert out2.kind == "exit_correction"
    assert out2.next_stage == "irrigation_check"
    assert out2.next_stage != "irrigation_recovery_start"
    assert out2.correction is not None
    assert out2.correction.outcome_success is False
    assert out2.correction.ec_current_seq_index == 1
    assert len(_dose_commands(gateway)) == 2

    partial_calls = [c for c in sink.calls if c[1] == "EC_BATCH_PARTIAL_FAILURE"]
    assert len(partial_calls) == 1
    zone_id, event_type, payload = partial_calls[0]
    assert zone_id == 60
    assert event_type == "EC_BATCH_PARTIAL_FAILURE"
    assert payload["status"] == "degraded"
    assert payload["mode"] == "multi_sequential"
    assert payload["failed_component"] == "magnesium"
    assert payload["successful_components"] == ["calcium"]
    assert payload["remaining_components"] == ["micro"]
    assert payload["error_code"] == "hw_error"
    assert payload["error_message"] == "device offline"
    assert payload["failed_index"] == 1
    assert payload["target_ec"] == 1.5
    assert payload["current_ec"] == 1.42
    assert payload["node_uid"] == "nd-mg"
    assert payload["channel"] == "pump_c"
    assert payload["task_id"] == 6
    assert payload["stage"] == "irrigation_check"
    assert payload["workflow_phase"] == "irrigating"
    assert payload["event_schema_version"] == 2

    after_metric = (
        REGISTRY.get_sample_value("ae3_correction_ec_batch_partial_failure_total", metric_labels)
        or 0.0
    )
    assert after_metric == before_metric + 1.0


@pytest.mark.asyncio
async def test_integration_first_component_failure_no_partial_event() -> None:
    """First-step failure → TaskExecutionError, no EC_BATCH_PARTIAL_FAILURE."""
    seq = _three_component_seq()[:2]
    gateway = _DoseGateway(
        dose_outcomes=[
            {
                "success": False,
                "error_code": "hw_error",
                "error_message": "pump offline",
                "command_statuses": [],
            },
        ]
    )
    sink = _FakeEventSink()
    handler = _make_integration_handler(gateway=gateway, event_sink=sink)

    corr = _seq_corr(seq=seq)
    task = _irrigation_task(corr)

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_runtime_plan(), stage_def=None, now=NOW)
    assert exc_info.value.code == "hw_error"
    assert not any(c[1] == "EC_BATCH_PARTIAL_FAILURE" for c in sink.calls)


@pytest.mark.asyncio
async def test_integration_multi_parallel_partial_failure_with_command_statuses() -> None:
    """Parallel batch: Ca DONE, Mg ERROR → partial failure event (mode=multi_parallel)."""
    seq = _three_component_seq()
    gateway = _DoseGateway(
        dose_outcomes=[
            {
                "success": False,
                "error_code": "ec_batch_command_failed",
                "error_message": "magnesium pump busy",
                "command_statuses": [
                    {"terminal_status": "DONE", "success": True, "legacy_cmd_id": "ca-1"},
                    {"terminal_status": "BUSY", "success": False, "legacy_cmd_id": "mg-1"},
                ],
            },
        ]
    )
    sink = _FakeEventSink()
    handler = _make_integration_handler(
        gateway=gateway,
        event_sink=sink,
        pid_repo=_PidRepoStub(current_ec=1.55),
    )
    metric_labels = {"mode": "multi_parallel"}
    before_metric = (
        REGISTRY.get_sample_value("ae3_correction_ec_batch_partial_failure_total", metric_labels)
        or 0.0
    )

    corr = _parallel_corr(seq=seq)
    task = _irrigation_task(corr)

    out = await handler.run(task=task, plan=_runtime_plan(target_ec=1.8), stage_def=None, now=NOW)

    assert out.kind == "exit_correction"
    assert out.correction is not None
    assert out.correction.outcome_success is False
    assert out.correction.ec_current_seq_index == 1
    assert out.next_stage == "irrigation_check"
    assert out.next_stage != "irrigation_recovery_start"

    # sensor activate + one parallel dose batch
    assert len(gateway.calls) >= 2
    dose_batches = [c for c in gateway.calls if _DoseGateway._is_dose_batch(c["commands"])]
    assert len(dose_batches) == 1
    assert len(dose_batches[0]["commands"]) == 3
    assert len(_dose_commands(gateway)) == 3

    partial_calls = [c for c in sink.calls if c[1] == "EC_BATCH_PARTIAL_FAILURE"]
    assert len(partial_calls) == 1
    payload = partial_calls[0][2]
    assert payload["status"] == "degraded"
    assert payload["mode"] == "multi_parallel"
    assert payload["successful_components"] == ["calcium"]
    assert payload["failed_component"] == "magnesium"
    assert payload["remaining_components"] == ["micro"]
    assert payload["failed_index"] == 1
    assert payload["error_code"] == "ec_batch_command_failed"
    assert payload["error_message"] == "magnesium pump busy"
    assert payload["target_ec"] == 1.8
    assert payload["current_ec"] == 1.55
    assert payload["node_uid"] == "nd-mg"
    assert payload["channel"] == "pump_c"
    assert payload["event_schema_version"] == 2
    assert payload["task_id"] == 6
    assert payload["stage"] == "irrigation_check"
    assert payload["workflow_phase"] == "irrigating"

    after_metric = (
        REGISTRY.get_sample_value("ae3_correction_ec_batch_partial_failure_total", metric_labels)
        or 0.0
    )
    assert after_metric == before_metric + 1.0


@pytest.mark.asyncio
async def test_integration_multi_parallel_first_component_failure_no_partial_event() -> None:
    """Parallel first-component fail (no prior DONE) → TaskExecutionError, no partial event."""
    seq = _three_component_seq()
    gateway = _DoseGateway(
        dose_outcomes=[
            {
                "success": False,
                "error_code": "hw_error",
                "error_message": "calcium offline",
                "command_statuses": [],
            },
        ]
    )
    sink = _FakeEventSink()
    handler = _make_integration_handler(gateway=gateway, event_sink=sink)

    corr = _parallel_corr(seq=seq)
    task = _irrigation_task(corr)

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler.run(task=task, plan=_runtime_plan(target_ec=1.8), stage_def=None, now=NOW)
    assert exc_info.value.code == "hw_error"
    assert not any(c[1] == "EC_BATCH_PARTIAL_FAILURE" for c in sink.calls)

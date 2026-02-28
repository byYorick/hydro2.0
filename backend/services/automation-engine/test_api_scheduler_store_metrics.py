from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import ae2lite.api_scheduler_store as scheduler_store


class _LabeledMetricHandle:
    def __init__(self, sink, labels):
        self._sink = sink
        self._labels = labels

    def inc(self, amount: float = 1.0):
        self._sink.append(("inc", self._labels, amount))

    def observe(self, value: float):
        self._sink.append(("observe", self._labels, value))


class _LabeledMetricSpy:
    def __init__(self):
        self.calls = []

    def labels(self, **labels):
        return _LabeledMetricHandle(self.calls, labels)


class _GaugeSpy:
    def __init__(self):
        self.values = []

    def set(self, value: float):
        self.values.append(float(value))


@pytest.mark.asyncio
async def test_create_scheduler_task_updates_accept_metrics(monkeypatch):
    status_counter = _LabeledMetricSpy()
    accept_latency = _LabeledMetricSpy()
    active_tasks = _GaugeSpy()

    monkeypatch.setattr(scheduler_store, "SCHEDULER_TASK_STATUS_TOTAL", status_counter)
    monkeypatch.setattr(scheduler_store, "SCHEDULER_TASK_ACCEPT_LATENCY_SEC", accept_latency)
    monkeypatch.setattr(scheduler_store, "SCHEDULER_ACTIVE_TASKS", active_tasks)

    req = SimpleNamespace(
        zone_id=7,
        task_type="diagnostics",
        payload={"workflow": "cycle_start"},
        scheduled_for="2026-02-28T10:00:00",
        due_at="2026-02-28T10:00:05",
        expires_at="2026-02-28T10:05:00",
        correlation_id="corr-7",
    )
    scheduler_tasks = {}
    lock = asyncio.Lock()

    async def _noop_cleanup(_now):
        return None

    async def _load_existing(_correlation_id):
        return None

    async def _persist(_snapshot):
        return None

    task, is_duplicate = await scheduler_store.create_scheduler_task(
        req,
        scheduler_tasks=scheduler_tasks,
        scheduler_tasks_lock=lock,
        cleanup_scheduler_tasks_locked_fn=_noop_cleanup,
        load_scheduler_task_by_correlation_id_fn=_load_existing,
        task_payload_fingerprint_fn=lambda _req: "fp-1",
        task_payload_matches_fn=lambda _req, _existing, _fp: True,
        new_scheduler_task_id_fn=lambda: "st-7",
        persist_scheduler_task_snapshot_fn=_persist,
    )

    assert is_duplicate is False
    assert task["task_id"] == "st-7"
    assert ("inc", {"task_type": "diagnostics", "status": "accepted"}, 1.0) in status_counter.calls
    assert len([call for call in accept_latency.calls if call[0] == "observe"]) == 1
    assert active_tasks.values[-1] == 1.0


@pytest.mark.asyncio
async def test_update_scheduler_task_updates_terminal_metrics(monkeypatch):
    status_counter = _LabeledMetricSpy()
    completion_latency = _LabeledMetricSpy()
    active_tasks = _GaugeSpy()

    monkeypatch.setattr(scheduler_store, "SCHEDULER_TASK_STATUS_TOTAL", status_counter)
    monkeypatch.setattr(scheduler_store, "SCHEDULER_TASK_COMPLETION_LATENCY_SEC", completion_latency)
    monkeypatch.setattr(scheduler_store, "SCHEDULER_ACTIVE_TASKS", active_tasks)

    created_at = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5)).isoformat()
    scheduler_tasks = {
        "st-9": {
            "task_id": "st-9",
            "zone_id": 9,
            "task_type": "diagnostics",
            "status": "accepted",
            "created_at": created_at,
            "updated_at": created_at,
        }
    }
    lock = asyncio.Lock()

    async def _persist(_snapshot):
        return None

    await scheduler_store.update_scheduler_task(
        task_id="st-9",
        status="failed",
        scheduler_tasks=scheduler_tasks,
        scheduler_tasks_lock=lock,
        persist_scheduler_task_snapshot_fn=_persist,
        error="execution_failed",
        error_code="SCHEDULER_ERR_EXECUTION_EXCEPTION",
    )

    assert ("inc", {"task_type": "diagnostics", "status": "failed"}, 1.0) in status_counter.calls
    completion_calls = [call for call in completion_latency.calls if call[0] == "observe"]
    assert len(completion_calls) == 1
    _, labels, observed = completion_calls[0]
    assert labels == {"task_type": "diagnostics", "status": "failed"}
    assert observed >= 0.0
    assert active_tasks.values[-1] == 1.0

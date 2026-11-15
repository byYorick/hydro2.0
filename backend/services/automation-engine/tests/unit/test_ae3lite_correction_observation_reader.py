"""Post-dose reads preserve validation order and isolate concurrent zone context."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from ae3lite.application.services.correction_observation_reader import (
    CorrectionObservationReader,
    ObservationRetry,
    ObservationWindow,
)
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.telemetry_window_summary import summarize_window

NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)


def samples(value=2.0, offsets=(-8, -4, 0)):
    return [{'ts': NOW + timedelta(seconds=offset), 'value': value} for offset in offsets]


def setup_reader(rows=None, **window_overrides):
    window = dict(has_sensor=True, is_stale=False, samples=samples() if rows is None else rows)
    window.update(window_overrides)
    monitor = SimpleNamespace(read_metric_window=AsyncMock(return_value=window))
    log_event = AsyncMock()
    reader = CorrectionObservationReader(
        runtime_monitor=monitor,
        summarize_window_fn=summarize_window,
        log_event_fn=log_event,
        logger=logging.getLogger('observation-test'),
    )
    return reader, monitor, log_event


def read_args(zone_id=7):
    return dict(
        task=SimpleNamespace(id=zone_id + 100, zone_id=zone_id),
        corr=None,
        now=NOW,
        pid_type='ec',
        sensor_type='EC',
        telemetry_max_age_sec=10,
        pid_entry={'last_dose_at': NOW - timedelta(seconds=20), 'last_measured_value': 0.0},
        observe_cfg={
            'transport_delay_sec': 6,
            'window_min_samples': 3,
            'stability_max_slope': 0.2,
            'decision_window_sec': 8,
            'telemetry_period_sec': 2,
            'observe_poll_sec': 2,
        },
        process_cfg={'ec_gain_per_ml': 0.1},
        stale_retry_delay_fn=Mock(return_value=30),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('missing', ['last_dose_at', 'last_measured_value'])
async def test_missing_baseline_fails_before_telemetry_read(missing):
    reader, monitor, event = setup_reader()
    args = read_args()
    args['pid_entry'].pop(missing)
    with pytest.raises(TaskExecutionError, match='baseline'):
        await reader.read(**args)
    monitor.read_metric_window.assert_not_awaited()
    event.assert_not_awaited()
    args['stale_retry_delay_fn'].assert_not_called()


@pytest.mark.asyncio
async def test_ready_window_preserves_zero_baseline_and_transport_delay():
    reader, monitor, event = setup_reader()
    args = read_args()
    result = await reader.read(**args)
    assert isinstance(result, ObservationWindow)
    assert result.baseline_value == 0.0
    assert result.summary_value == 2.0
    assert result.pid_entry == args['pid_entry']
    assert result.process_cfg == args['process_cfg']
    assert monitor.read_metric_window.await_args.kwargs == dict(
        zone_id=7,
        sensor_type='EC',
        since_ts=NOW - timedelta(seconds=14),
        telemetry_max_age_sec=10,
    )
    event.assert_not_awaited()
    args['stale_retry_delay_fn'].assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', [{'is_stale': True}, {'has_sensor': False}])
async def test_unavailable_window_uses_stale_delay_without_summary(condition):
    reader, _monitor, event = setup_reader(**condition)
    reader._summarize_window = Mock(side_effect=AssertionError('stale data cannot be summarized'))
    args = read_args()
    assert await reader.read(**args) == ObservationRetry(due_delay_sec=30)
    args['stale_retry_delay_fn'].assert_called_once_with()
    assert event.await_args.kwargs['event_type'] == 'CORRECTION_SKIPPED_FRESHNESS'
    assert event.await_args.kwargs['payload']['retry_after_sec'] == 30


@pytest.mark.asyncio
@pytest.mark.parametrize('rows', [samples(offsets=(-2,)), samples(offsets=(-2, -1, 0))])
async def test_normal_window_accumulation_retries_without_event_spam(rows):
    reader, _monitor, event = setup_reader(rows)
    assert await reader.read(**read_args()) == ObservationRetry(due_delay_sec=2)
    event.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('rows', 'reason'),
    [
        (samples(value=999), 'sensor_out_of_bounds'),
        (samples(offsets=(-8, 0, 30)), 'sample_in_future'),
    ],
)
async def test_unsafe_window_retries_with_diagnostic_reason(rows, reason):
    reader, _monitor, event = setup_reader(rows)
    assert await reader.read(**read_args()) == ObservationRetry(due_delay_sec=2)
    payload = event.await_args.kwargs['payload']
    assert payload['reason'] == reason
    assert payload['sensor_scope'] == 'observe_window'


@pytest.mark.asyncio
async def test_cancelled_read_does_not_turn_into_retry_or_event():
    reader, monitor, event = setup_reader()
    monitor.read_metric_window.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await reader.read(**read_args())
    event.assert_not_awaited()


@pytest.mark.asyncio
async def test_shared_reader_keeps_concurrent_zone_windows_separate():
    reader, monitor, event = setup_reader()
    entered = asyncio.Event()
    seen = []

    async def read_window(**kwargs):
        seen.append(kwargs['zone_id'])
        if len(seen) == 2:
            entered.set()
        await entered.wait()
        return dict(has_sensor=True, is_stale=False, samples=samples(value=kwargs['zone_id']))

    monitor.read_metric_window.side_effect = read_window
    first, second = read_args(1), read_args(2)
    second['pid_entry']['last_measured_value'] = 1.5
    results = await asyncio.wait_for(asyncio.gather(reader.read(**first), reader.read(**second)), timeout=1)
    assert [(r.summary_value, r.baseline_value) for r in results] == [(1.0, 0.0), (2.0, 1.5)]
    event.assert_not_awaited()

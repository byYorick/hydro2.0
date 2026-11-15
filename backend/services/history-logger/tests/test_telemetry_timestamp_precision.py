"""A successful timestamp(0) INSERT must not be requeued as a missing JOIN."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from telemetry_processing import TelemetryBatchResult, _handle_samples_join_mismatch


@pytest.mark.parametrize(
    ('source', 'stored'),
    [
        ('2026-11-14T12:00:00.000001+00:00', '2026-11-14T12:00:00'),
        ('2026-11-14T12:00:00.499999+00:00', '2026-11-14T12:00:00'),
        ('2026-11-14T12:00:00.500000+00:00', '2026-11-14T12:00:01'),
        ('2026-11-14T23:59:59.999999+00:00', '2026-11-15T00:00:00'),
        ('2026-12-31T23:59:59.500000+00:00', '2027-01-01T00:00:00'),
        ('2026-11-14T15:00:00.500000+03:00', '2026-11-14T12:00:01'),
        ('1999-12-31T23:59:59.500000+00:00', '1999-12-31T23:59:59'),
        ('1999-12-31T23:59:59.500001+00:00', '2000-01-01T00:00:00'),
        ('1999-12-31T23:59:59.499999+00:00', '1999-12-31T23:59:59'),
    ],
)
def test_committed_fractional_timestamp_is_not_requeued(source, stored):
    sample_ts = datetime.fromisoformat(source)
    entry = object()
    item = {'sensor_id': 7, 'zone_id': 3, 'entry': entry, 'sample': SimpleNamespace(metric_type='PH')}
    result = TelemetryBatchResult()
    written = _handle_samples_join_mismatch(
        [item], [7], [sample_ts], [{'sensor_id': 7, 'ts': datetime.fromisoformat(stored)}], result
    )
    assert written == [item]
    assert not result.entries_to_requeue


def test_genuinely_missing_sample_still_requeues():
    entry = object()
    item = {'sensor_id': 7, 'zone_id': 3, 'entry': entry, 'sample': SimpleNamespace(metric_type='PH')}
    result = TelemetryBatchResult()
    written = _handle_samples_join_mismatch([item], [7], [datetime(2026, 11, 14, tzinfo=timezone.utc)], [], result)
    assert not written
    assert result.entries_to_requeue == [entry]

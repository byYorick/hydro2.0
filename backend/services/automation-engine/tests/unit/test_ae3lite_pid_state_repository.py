from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ae3lite.infrastructure.repositories.pid_state_repository import (
    PgPidStateRepository,
    _SQL_UPSERT,
)


def test_pid_state_upsert_params_match_sql_placeholders() -> None:
    repo = PgPidStateRepository()
    now = datetime(2026, 3, 25, 12, 0, tzinfo=timezone.utc)

    params = repo._normalize_params(
        zone_id=7,
        pid_type="ec",
        now=now,
        integral=1.5,
        prev_error=0.2,
        prev_derivative=0.1,
        last_output_ms=1200,
        last_dose_at=now,
        hold_until=now,
        last_measurement_at=now,
        last_measured_value=1.23,
        feedforward_bias=0.05,
        no_effect_count=1,
        last_correction_kind="dose",
        stats={"adaptive": {"gain": 0.8}},
        current_zone="far",
    )

    assert len(params) == 17
    assert "$17" in _SQL_UPSERT
    assert _SQL_UPSERT.count("$16") == 1
    assert _SQL_UPSERT.count("$17") == 1


@pytest.mark.asyncio
async def test_partial_pid_update_preserves_unspecified_fields_and_allows_explicit_zero():
    from test_ae3lite_workflow_router_atomic_postgres import _insert_greenhouse, _insert_zone, _cleanup
    from common.db import fetch

    prefix = f"ae3-pid-partial-{uuid4().hex}"
    now = datetime.now(timezone.utc)
    repo = PgPidStateRepository()
    try:
        gh = await _insert_greenhouse(prefix)
        zone = await _insert_zone(prefix, greenhouse_id=gh)
        initial = dict(integral=1.25, prev_derivative=0.125, last_output_ms=1500,
                       feedforward_bias=0.25, no_effect_count=2)
        await repo.upsert_state(zone_id=zone, pid_type="ph", now=now, **initial)
        await repo.upsert_state(zone_id=zone, pid_type="ph", now=now,
                                last_measurement_at=now, last_measured_value=6.0)
        row = (await fetch("SELECT * FROM pid_state WHERE zone_id=$1 AND pid_type='ph'", zone))[0]
        for field, value in initial.items():
            assert float(row[field]) == pytest.approx(value), field
        await repo.upsert_state(zone_id=zone, pid_type="ph", now=now, **{key: 0 for key in initial})
        row = (await fetch("SELECT * FROM pid_state WHERE zone_id=$1 AND pid_type='ph'", zone))[0]
        assert all(float(row[field]) == 0 for field in initial)
    finally:
        await _cleanup(prefix)

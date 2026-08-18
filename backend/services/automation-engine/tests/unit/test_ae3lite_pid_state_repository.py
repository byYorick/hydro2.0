from datetime import datetime, timezone

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

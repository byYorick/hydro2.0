from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.zone_correction_gating import build_correction_gating_state


class _Logger:
    def __init__(self) -> None:
        self.entries = []

    def info(self, message: str, extra=None):
        self.entries.append((message, extra))


def test_gating_fail_closed_for_stale_flags():
    now = datetime.now(timezone.utc)
    logger = _Logger()
    state = build_correction_gating_state(
        telemetry={},
        telemetry_timestamps={},
        correction_flags={
            "flow_active": True,
            "stable": True,
            "corrections_allowed": True,
            "flow_active_ts": (now - timedelta(seconds=180)).isoformat(),
            "stable_ts": (now - timedelta(seconds=5)).isoformat(),
            "corrections_allowed_ts": (now - timedelta(seconds=5)).isoformat(),
        },
        workflow_phase="ready",
        normalize_workflow_phase_fn=lambda v: str(v).strip().lower(),
        utcnow_fn=lambda: now,
        correction_open_phases={"tank_filling", "tank_recirc"},
        required_flag_names=("flow_active", "stable", "corrections_allowed"),
        flags_max_age_seconds=60,
        flags_require_timestamps=True,
        logger=logger,
    )

    assert state["can_run"] is False
    assert state["reason_code"] == "stale_flags"
    assert "flow_active" in state["stale_flags"]


def test_gating_allows_workflow_open_phase_with_stale_flags():
    now = datetime.now(timezone.utc)
    logger = _Logger()
    state = build_correction_gating_state(
        telemetry={},
        telemetry_timestamps={},
        correction_flags={
            "flow_active": True,
            "stable": True,
            "corrections_allowed": True,
            "flow_active_ts": (now - timedelta(seconds=5)).isoformat(),
            "stable_ts": (now - timedelta(seconds=5)).isoformat(),
            "corrections_allowed_ts": (now - timedelta(seconds=5)).isoformat(),
        },
        workflow_phase="tank_recirc",
        normalize_workflow_phase_fn=lambda v: str(v).strip().lower(),
        utcnow_fn=lambda: now,
        correction_open_phases={"tank_filling", "tank_recirc"},
        required_flag_names=("flow_active", "stable", "corrections_allowed"),
        flags_max_age_seconds=60,
        flags_require_timestamps=True,
        logger=logger,
    )

    assert state["can_run"] is True
    assert state["reason_code"] == "workflow_phase_open"

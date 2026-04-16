from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ae3lite.application.handlers.base import BaseStageHandler
from ae3lite.domain.services.cycle_start_planner import CycleStartPlanner
from ae3lite.infrastructure.read_models import PgZoneSnapshotReadModel
from common.db import execute, fetch
from test_ae3lite_two_tank_cycle_start_integration import _insert_two_tank_runtime_zone
from test_ae3lite_zone_snapshot_read_model_integration import _cleanup, _upsert_zone_bundle


async def _set_zone_live_mode(zone_id: int, *, config_revision: int) -> None:
    await execute(
        """
        UPDATE zones
        SET control_mode = 'manual',
            config_mode = 'live',
            live_started_at = NOW(),
            live_until = NOW() + INTERVAL '1 hour',
            config_revision = $2,
            updated_at = NOW()
        WHERE id = $1
        """,
        zone_id,
        config_revision,
    )


async def _latest_hot_reload_event(zone_id: int) -> dict | None:
    rows = await fetch(
        """
        SELECT payload_json
        FROM zone_events
        WHERE zone_id = $1
          AND type = 'CONFIG_HOT_RELOADED'
        ORDER BY id DESC
        LIMIT 1
        """,
        zone_id,
    )
    if not rows:
        return None
    payload = rows[0]["payload_json"]
    return dict(payload) if isinstance(payload, dict) else None


@pytest.mark.asyncio
async def test_checkpoint_hot_swap_reloads_nested_correction_and_process_calibration() -> None:
    prefix = f"ae3-checkpoint-live-{uuid4().hex}"
    try:
        _greenhouse_id, zone_id = await _insert_two_tank_runtime_zone(
            prefix,
            clean_full=True,
            solution_full=True,
        )
        await _set_zone_live_mode(zone_id, config_revision=1)

        snapshot = await PgZoneSnapshotReadModel().load(zone_id=zone_id)
        plan = CycleStartPlanner().build(
            task=SimpleNamespace(task_type="cycle_start", zone_id=zone_id),
            snapshot=snapshot,
        )

        assert plan.runtime.config_revision == 1
        assert plan.runtime.correction.stabilization_sec == 60
        assert plan.runtime.correction.controllers.ec.observe.decision_window_sec == 6
        assert plan.runtime.process_calibrations["solution_fill"].transport_delay_sec == 6
        assert plan.runtime.process_calibrations["solution_fill"].settle_sec == 4

        await _upsert_zone_bundle(
            zone_id,
            {
                "correction": {
                    "resolved_config": {
                        "phases": {
                            "solution_fill": {
                                "timing": {
                                    "stabilization_sec": 77,
                                },
                                "controllers": {
                                    "ec": {
                                        "observe": {
                                            "decision_window_sec": 19,
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
                "process_calibration": {
                    "solution_fill": {
                        "transport_delay_sec": 17,
                        "settle_sec": 11,
                        "confidence": 0.66,
                    },
                },
            },
        )
        await execute(
            """
            UPDATE zones
            SET config_revision = 2,
                live_until = NOW() + INTERVAL '1 hour',
                updated_at = NOW()
            WHERE id = $1
            """,
            zone_id,
        )

        handler = BaseStageHandler(
            runtime_monitor=object(),
            command_gateway=object(),
            live_reload_enabled=True,
        )
        task = SimpleNamespace(
            zone_id=zone_id,
            id=501,
            current_stage="clean_fill_check",
        )

        refreshed_runtime = await handler._checkpoint(
            task=task,
            plan=plan,
            now=datetime.now(timezone.utc),
        )

        assert refreshed_runtime is not plan.runtime
        assert refreshed_runtime.config_revision == 2
        assert refreshed_runtime.correction.stabilization_sec == 77
        assert refreshed_runtime.correction.controllers.ec.observe.decision_window_sec == 19
        assert refreshed_runtime.correction_by_phase["solution_fill"].stabilization_sec == 77
        assert (
            refreshed_runtime.correction_by_phase["solution_fill"]
            .controllers.ec.observe.decision_window_sec
            == 19
        )
        assert refreshed_runtime.process_calibrations["solution_fill"].transport_delay_sec == 17
        assert refreshed_runtime.process_calibrations["solution_fill"].settle_sec == 11
        assert refreshed_runtime.process_calibrations["solution_fill"].confidence == pytest.approx(0.66)

        event_payload = await _latest_hot_reload_event(zone_id)
        assert event_payload is not None
        assert int(event_payload["revision"]) == 2
        assert int(event_payload["previous_revision"]) == 1
        assert int(event_payload["task_id"]) == 501
        assert str(event_payload["stage"]) == "clean_fill_check"
    finally:
        await _cleanup(prefix)

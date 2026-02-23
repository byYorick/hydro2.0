from datetime import datetime

import pytest
from pydantic import ValidationError

from application.api_contracts import StartCycleRequest
from application.api_start_cycle import (
    DEFAULT_START_CYCLE_WORKFLOW,
    build_start_cycle_response,
    build_start_cycle_scheduler_task_request,
)


def test_start_cycle_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        StartCycleRequest(
            source="laravel_scheduler",
            idempotency_key="sch:z12:irrigation:2026-02-21T10:00:00Z",
            steps=[{"cmd": "pump_on"}],
        )


def test_build_scheduler_request_uses_minimal_canonical_payload():
    now = datetime(2026, 2, 21, 10, 0, 0)
    req = StartCycleRequest(
        source="laravel_scheduler",
        idempotency_key="sch:z12:irrigation:2026-02-21T10:00:00Z",
    )

    scheduler_req = build_start_cycle_scheduler_task_request(
        zone_id=12,
        req=req,
        now=now,
        due_in_sec=60,
        expires_in_sec=900,
        default_topology="two_tank_drip_substrate_trays",
    )

    assert scheduler_req.zone_id == 12
    assert scheduler_req.task_type == "diagnostics"
    assert scheduler_req.payload["workflow"] == DEFAULT_START_CYCLE_WORKFLOW
    assert scheduler_req.payload["topology"] == "two_tank_drip_substrate_trays"
    assert scheduler_req.payload["config"]["execution"]["workflow"] == DEFAULT_START_CYCLE_WORKFLOW
    assert scheduler_req.payload["config"]["execution"]["topology"] == "two_tank_drip_substrate_trays"
    assert scheduler_req.payload["source"] == "laravel_scheduler"
    assert scheduler_req.correlation_id == "start-cycle:12:sch:z12:irrigation:2026-02-21T10:00:00Z"


def test_build_start_cycle_response_matches_contract_shape():
    req = StartCycleRequest(
        source="laravel_scheduler",
        idempotency_key="sch:z2:test:2026-02-21T10:00:00Z",
    )

    payload = build_start_cycle_response(
        zone_id=2,
        req=req,
        is_duplicate=True,
        task_id="tsk-001",
    )

    assert payload == {
        "status": "ok",
        "data": {
            "zone_id": 2,
            "accepted": True,
            "runner_state": "active",
            "deduplicated": True,
            "task_id": "tsk-001",
            "idempotency_key": "sch:z2:test:2026-02-21T10:00:00Z",
        },
    }

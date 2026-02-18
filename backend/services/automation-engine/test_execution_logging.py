"""Unit tests for application.execution_logging helpers."""

from datetime import datetime
from unittest.mock import Mock

from domain.models.decision_models import DecisionOutcome
from application.execution_logging import log_execution_finished, log_execution_started


def test_log_execution_started_forwards_structured_fields():
    log_structured_fn = Mock()
    logger_obj = Mock()
    log_execution_started(
        log_structured_fn=log_structured_fn,
        logger_obj=logger_obj,
        zone_id=3,
        task_type="diagnostics",
        payload={"workflow": "startup"},
        context={"task_id": "st-3", "correlation_id": "corr-3"},
    )
    assert log_structured_fn.called
    assert log_structured_fn.call_args.kwargs["task_id"] == "st-3"


def test_log_execution_finished_forwards_result():
    log_structured_fn = Mock()
    logger_obj = Mock()
    decision = DecisionOutcome(
        action_required=True,
        decision="run",
        reason_code="ok",
        reason="ok",
    )
    log_execution_finished(
        log_structured_fn=log_structured_fn,
        logger_obj=logger_obj,
        zone_id=3,
        task_type="diagnostics",
        payload={},
        context={"task_id": "st-3", "correlation_id": "corr-3"},
        result={"success": True, "commands_total": 2, "decision": "run", "reason_code": "ok"},
        decision=decision,
        execute_started_at=datetime(2026, 2, 16, 0, 0, 0),
    )
    assert log_structured_fn.called
    assert log_structured_fn.call_args.kwargs["command_count"] == 2

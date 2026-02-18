"""Unit tests for application.diagnostics_execution helpers."""

import asyncio
from unittest.mock import AsyncMock, Mock

from domain.models.decision_models import DecisionOutcome
from application.diagnostics_execution import execute_diagnostics


def _decision() -> DecisionOutcome:
    return DecisionOutcome(action_required=True, decision="run", reason_code="ok", reason="ok")


def test_execute_diagnostics_returns_unavailable_when_zone_service_missing():
    emit_task_event = AsyncMock(return_value=None)
    send_alert = AsyncMock(return_value=True)

    result = asyncio.run(
        execute_diagnostics(
            zone_id=1,
            payload={"workflow": "diagnostics"},
            context={"task_id": "st-1"},
            decision=_decision(),
            zone_service=None,
            logger_obj=Mock(),
            reason_diagnostics_service_unavailable="diagnostics_service_unavailable",
            err_diagnostics_service_unavailable="diagnostics_service_unavailable",
            emit_task_event_fn=emit_task_event,
            send_infra_alert_fn=send_alert,
        )
    )

    assert result["success"] is False
    assert result["mode"] == "diagnostics_unavailable"
    emit_task_event.assert_awaited_once()
    send_alert.assert_awaited_once()


def test_execute_diagnostics_returns_success_when_process_zone_ok():
    zone_service = Mock()
    zone_service.process_zone = AsyncMock(return_value=None)

    result = asyncio.run(
        execute_diagnostics(
            zone_id=2,
            payload={},
            context={},
            decision=_decision(),
            zone_service=zone_service,
            logger_obj=Mock(),
            reason_diagnostics_service_unavailable="diagnostics_service_unavailable",
            err_diagnostics_service_unavailable="diagnostics_service_unavailable",
            emit_task_event_fn=AsyncMock(),
            send_infra_alert_fn=AsyncMock(),
        )
    )

    assert result["success"] is True
    assert result["mode"] == "zone_service"
    zone_service.process_zone.assert_awaited_once_with(2)


def test_execute_diagnostics_returns_failed_when_process_zone_raises():
    zone_service = Mock()
    zone_service.process_zone = AsyncMock(side_effect=RuntimeError("boom"))
    emit_task_event = AsyncMock(return_value=None)
    send_alert = AsyncMock(return_value=True)

    result = asyncio.run(
        execute_diagnostics(
            zone_id=3,
            payload={"x": 1},
            context={"task_id": "st-3"},
            decision=_decision(),
            zone_service=zone_service,
            logger_obj=Mock(),
            reason_diagnostics_service_unavailable="diagnostics_service_unavailable",
            err_diagnostics_service_unavailable="diagnostics_service_unavailable",
            emit_task_event_fn=emit_task_event,
            send_infra_alert_fn=send_alert,
        )
    )

    assert result["success"] is False
    assert result["mode"] == "diagnostics_failed"
    emit_task_event.assert_awaited_once()
    send_alert.assert_awaited_once()

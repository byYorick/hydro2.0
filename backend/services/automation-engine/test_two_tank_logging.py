"""Unit tests for application.two_tank_logging helpers."""

import logging
from unittest.mock import Mock

from application.two_tank_logging import log_two_tank_safety_guard


def test_log_two_tank_safety_guard_forwards_structured_extra():
    logger_obj = Mock()
    log_two_tank_safety_guard(
        logger_obj=logger_obj,
        zone_id=7,
        context={"task_id": "st-7", "correlation_id": "corr-7"},
        phase="clean_fill",
        stop_result={"success": True},
        feature_flag_state=True,
        level=logging.INFO,
    )
    logger_obj.log.assert_called_once()
    kwargs = logger_obj.log.call_args.kwargs
    assert kwargs["extra"]["zone_id"] == 7
    assert kwargs["extra"]["feature_flag_state"] is True

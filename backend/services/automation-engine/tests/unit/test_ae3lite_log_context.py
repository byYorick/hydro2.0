"""Unit tests for AE3 log-context helpers."""

from __future__ import annotations

import logging

from ae3lite.infrastructure.log_context import (
    Ae3LogContextFilter,
    attach_ae3_log_context_filter,
    get_log_context,
    log_context_scope,
)
from common.trace_context import clear_trace_id, set_trace_id


def test_log_context_filter_adds_bound_fields():
    attach_ae3_log_context_filter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    with log_context_scope(task_id=42, zone_id=7, stage="startup", trace_id="trace-abc"):
        assert Ae3LogContextFilter().filter(record) is True
        assert record.task_id == 42
        assert record.zone_id == 7
        assert record.stage == "startup"
        assert record.trace_id == "trace-abc"
    clear_trace_id()
    assert get_log_context() == {}

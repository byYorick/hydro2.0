"""Structured logging helpers for scheduler task execution lifecycle."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict

from domain.models.decision_models import DecisionOutcome

LogStructuredFn = Callable[..., Any]


def log_execution_started(
    *,
    log_structured_fn: LogStructuredFn,
    logger_obj: logging.Logger,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    context: Dict[str, Any],
) -> None:
    log_structured_fn(
        logger_obj,
        logging.INFO,
        "Scheduler task execution started",
        component="scheduler_task_executor",
        zone_id=zone_id,
        task_id=context.get("task_id") or None,
        task_type=task_type,
        workflow=str(payload.get("workflow") or "") or None,
        workflow_phase=str(payload.get("workflow_phase") or "") or None,
        decision=None,
        reason_code=None,
        result_status="success",
        correlation_id=context.get("correlation_id") or None,
    )


def log_execution_finished(
    *,
    log_structured_fn: LogStructuredFn,
    logger_obj: logging.Logger,
    zone_id: int,
    task_type: str,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    result: Dict[str, Any],
    decision: DecisionOutcome,
    execute_started_at: datetime,
) -> None:
    log_structured_fn(
        logger_obj,
        logging.INFO if result.get("success") else logging.ERROR,
        "Scheduler task execution finished",
        component="scheduler_task_executor",
        zone_id=zone_id,
        task_id=context.get("task_id") or None,
        task_type=task_type,
        workflow=str(result.get("workflow") or payload.get("workflow") or "") or None,
        workflow_phase=str(result.get("workflow_phase") or payload.get("workflow_phase") or "") or None,
        decision=str(result.get("decision") or decision.decision or "") or None,
        reason_code=str(result.get("reason_code") or decision.reason_code or "") or None,
        command_count=int(result.get("commands_total") or 0),
        result_status="success" if result.get("success") else "failed",
        correlation_id=context.get("correlation_id") or None,
        started_at=execute_started_at,
    )


__all__ = ["log_execution_finished", "log_execution_started"]

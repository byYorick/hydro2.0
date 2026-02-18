"""Pydantic request contracts for automation-engine API."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class SchedulerTaskRequest(BaseModel):
    """Абстрактная задача расписания от scheduler."""

    zone_id: int = Field(..., ge=1, description="Zone ID")
    task_type: Literal[
        "irrigation",
        "lighting",
        "ventilation",
        "solution_change",
        "mist",
        "diagnostics",
    ] = Field(..., description="Abstract task type")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Task payload")
    scheduled_for: Optional[str] = Field(default=None, description="ISO datetime when task was scheduled")
    due_at: str = Field(..., description="ISO datetime when task must be started")
    expires_at: str = Field(..., description="ISO datetime when task should be rejected")
    correlation_id: str = Field(..., min_length=8, max_length=128, description="Mandatory idempotency correlation ID")


class SchedulerBootstrapRequest(BaseModel):
    scheduler_id: str = Field(..., min_length=1, max_length=64)
    scheduler_version: Optional[str] = Field(default=None, max_length=64)
    protocol_version: Optional[str] = Field(default="2.0", max_length=16)
    started_at: Optional[str] = Field(default=None)
    capabilities: Dict[str, Any] = Field(default_factory=dict)


class SchedulerBootstrapHeartbeatRequest(BaseModel):
    scheduler_id: str = Field(..., min_length=1, max_length=64)
    lease_id: str = Field(..., min_length=8, max_length=128)


class SchedulerInternalEnqueueRequest(BaseModel):
    zone_id: int = Field(..., ge=1, description="Zone ID")
    task_type: Literal[
        "irrigation",
        "lighting",
        "ventilation",
        "solution_change",
        "mist",
        "diagnostics",
    ] = Field(..., description="Abstract task type")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Task payload")
    scheduled_for: Optional[str] = Field(default=None, description="ISO datetime when task should be dispatched")
    expires_at: Optional[str] = Field(default=None, description="ISO datetime when enqueued task expires")
    correlation_id: Optional[str] = Field(default=None, max_length=128, description="Optional custom correlation_id")
    source: str = Field(default="automation-engine", max_length=64)


__all__ = [
    "SchedulerBootstrapHeartbeatRequest",
    "SchedulerBootstrapRequest",
    "SchedulerInternalEnqueueRequest",
    "SchedulerTaskRequest",
]

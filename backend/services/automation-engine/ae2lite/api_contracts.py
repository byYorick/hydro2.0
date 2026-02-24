"""Pydantic request contracts for automation-engine API."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

    @staticmethod
    def _extract_execution_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
        execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
        return execution

    @model_validator(mode="after")
    def _validate_diagnostics_payload_contract(self) -> "SchedulerTaskRequest":
        if self.task_type != "diagnostics":
            return self

        payload = self.payload if isinstance(self.payload, dict) else {}
        execution = self._extract_execution_payload(payload)
        topology = str(payload.get("topology") or execution.get("topology") or "").strip().lower()
        workflow = str(
            payload.get("workflow")
            or payload.get("diagnostics_workflow")
            or execution.get("workflow")
            or ""
        ).strip().lower()

        if not topology:
            raise ValueError("missing_topology")
        if not workflow:
            raise ValueError("missing_workflow")
        return self


class StartCycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="laravel_scheduler", min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=160)


__all__ = [
    "SchedulerTaskRequest",
    "StartCycleRequest",
]

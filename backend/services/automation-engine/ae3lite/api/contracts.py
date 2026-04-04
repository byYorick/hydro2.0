"""Pydantic request contracts for AE3-Lite API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StartCycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="laravel_scheduler", min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=160)


class StartIrrigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="laravel_scheduler", min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=160)
    mode: str = Field(default="normal", min_length=4, max_length=16, pattern="^(normal|force)$")
    requested_duration_sec: int | None = Field(default=None, ge=1, le=3600)


class StartLightingTickRequest(BaseModel):
    """Scheduler/API compat: one-shot lighting dispatch (C1, AE3-only path)."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="laravel_scheduler", min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=160)


__all__ = ["StartCycleRequest", "StartIrrigationRequest", "StartLightingTickRequest"]

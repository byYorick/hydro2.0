"""Pydantic-контракты запросов для API AE3-Lite."""

from __future__ import annotations

from typing import Literal

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
    """Совместимый с scheduler/API one-shot lighting dispatch (C1, только путь AE3)."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="laravel_scheduler", min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=160)
    desired_state: Literal["on", "off"] = "on"
    brightness_pct: int | None = Field(default=None, ge=0, le=100)


class StartSolutionTopupRequest(BaseModel):
    """Совместимый с scheduler/API one-shot solution topup dispatch (этап B)."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="laravel_scheduler", min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=160)
    mode: str = Field(default="normal", min_length=4, max_length=16, pattern="^(normal|force)$")
    trigger: str | None = Field(default=None, min_length=3, max_length=32)


class StartSolutionChangeRequest(BaseModel):
    """Совместимый с scheduler/API semi-auto solution change dispatch (этап D.1)."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="laravel_scheduler", min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=160)
    trigger: str | None = Field(default=None, min_length=3, max_length=32)


__all__ = [
    "StartCycleRequest",
    "StartIrrigationRequest",
    "StartLightingTickRequest",
    "StartSolutionTopupRequest",
    "StartSolutionChangeRequest",
]

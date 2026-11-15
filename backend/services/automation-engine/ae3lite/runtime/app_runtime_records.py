"""Typed records shared by the component boundaries."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ControlModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_mode: str = Field(..., min_length=1, max_length=16, pattern="^(auto|semi|manual)$")
    source: str = Field(default="laravel_api", min_length=1, max_length=64)
    user_id: Optional[int] = Field(default=None, ge=0)
    user_role: Optional[str] = Field(default=None, min_length=1, max_length=32)
    reason: Optional[str] = Field(default=None, max_length=500)


class OperatorUnblockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="laravel_api", min_length=1, max_length=64)
    reason: Optional[str] = Field(default=None, max_length=500)
    user_id: Optional[int] = Field(default=None, ge=0)
    user_role: Optional[str] = Field(default=None, min_length=1, max_length=32)


class ManualStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manual_step: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern="^(clean_fill_start|clean_fill_stop|solution_fill_start|force_solution_fill_start|solution_fill_stop|prepare_recirculation_start|prepare_recirculation_stop|irrigation_stop|solution_drain_confirm|solution_refill_confirm|solution_change_abort)$",
    )
    source: str = Field(default="laravel_manual_step", min_length=1, max_length=64)


class BackgroundTaskLimitError(RuntimeError):
    """Выбрасывается, когда AE3 отказывается создавать новые отслеживаемые фоновые задачи."""

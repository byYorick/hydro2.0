"""Ingress `POST /greenhouses/{id}/start-climate-tick` для greenhouse climate tick."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from fastapi import BackgroundTasks, Body, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ae3lite.greenhouse_climate.run_tick import run_greenhouse_climate_tick
from common.db import fetch

logger = logging.getLogger(__name__)


class StartClimateTickRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="laravel_scheduler", min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=191)


def bind_greenhouse_climate_tick_route(
    app: FastAPI,
    *,
    validate_scheduler_security_baseline_fn: Callable[[Request], Awaitable[None]],
    history_logger_client: Any,
    logger: Any = logger,
) -> None:
    async def _validate_greenhouse(greenhouse_id: int) -> None:
        rows = await fetch(
            "SELECT id FROM greenhouses WHERE id = $1 LIMIT 1",
            greenhouse_id,
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"Теплица '{greenhouse_id}' не найдена")

    @app.post("/greenhouses/{greenhouse_id}/start-climate-tick")
    async def greenhouse_start_climate_tick(
        greenhouse_id: int,
        request: Request,
        background_tasks: BackgroundTasks,
        req: StartClimateTickRequest = Body(...),
    ) -> dict[str, Any]:
        await validate_scheduler_security_baseline_fn(request)
        await _validate_greenhouse(greenhouse_id)
        background_tasks.add_task(
            run_greenhouse_climate_tick,
            greenhouse_id=greenhouse_id,
            idempotency_key=req.idempotency_key.strip(),
            history_logger_client=history_logger_client,
        )
        return {
            "status": "accepted",
            "data": {
                "greenhouse_id": greenhouse_id,
                "idempotency_key": req.idempotency_key.strip(),
            },
        }


__all__ = ["StartClimateTickRequest", "bind_greenhouse_climate_tick_route"]

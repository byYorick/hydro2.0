"""Ingress `POST /greenhouses/{id}/start-climate-tick` для greenhouse climate tick."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Awaitable, Callable

from fastapi import Body, FastAPI, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field

from ae3lite.api.http_errors import api_error_detail
from ae3lite.greenhouse_climate.run_tick import run_greenhouse_climate_tick
from common.db import fetch

logger = logging.getLogger(__name__)

SpawnBackgroundTaskFn = Callable[..., Any]


class StartClimateTickRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = Field(default="laravel_scheduler", min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=160)


def bind_greenhouse_climate_tick_route(
    app: FastAPI,
    *,
    validate_scheduler_security_baseline_fn: Callable[[Request], Awaitable[None]],
    is_climate_tick_rate_limit_enabled_fn: Callable[[], bool],
    climate_tick_rate_limit_check_fn: Callable[[int], bool],
    climate_tick_rate_limit_window_sec_fn: Callable[[], int],
    climate_tick_rate_limit_max_requests_fn: Callable[[], int],
    history_logger_client: Any,
    spawn_background_task_fn: SpawnBackgroundTaskFn,
    worker_owner: str | None = None,
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
        greenhouse_id: Annotated[int, Path(..., gt=0)],
        request: Request,
        req: StartClimateTickRequest = Body(...),
    ) -> dict[str, Any]:
        await validate_scheduler_security_baseline_fn(request)
        await _validate_greenhouse(greenhouse_id)
        if is_climate_tick_rate_limit_enabled_fn() and not climate_tick_rate_limit_check_fn(
            greenhouse_id
        ):
            raise api_error_detail(
                "start_cycle_rate_limited",
                status_code=429,
                greenhouse_id=greenhouse_id,
                window_sec=climate_tick_rate_limit_window_sec_fn(),
                max_requests=climate_tick_rate_limit_max_requests_fn(),
            )
        try:
            spawn_background_task_fn(
                run_greenhouse_climate_tick(
                    greenhouse_id=greenhouse_id,
                    idempotency_key=req.idempotency_key.strip(),
                    history_logger_client=history_logger_client,
                    worker_owner=worker_owner,
                ),
                task_name="greenhouse_climate_tick",
            )
        except RuntimeError as exc:
            if "ae3_background_task_limit_exceeded" in str(exc):
                raise api_error_detail(
                    "ae3_background_task_limit_exceeded",
                    status_code=503,
                    greenhouse_id=greenhouse_id,
                ) from exc
            raise
        return {
            "status": "accepted",
            "data": {
                "greenhouse_id": greenhouse_id,
                "idempotency_key": req.idempotency_key.strip(),
            },
        }


__all__ = ["StartClimateTickRequest", "bind_greenhouse_climate_tick_route"]

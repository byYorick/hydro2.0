"""HTTP API для калибровки и drift-мониторинга (Phase D)."""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from calibrators import (
    calibrate_zone,
    calibrate_zone_with_persist,
    compute_drift_for_zone,
    list_active_params,
    list_versions,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# --- Calibrate ----------------------------------------------------------


@router.post("/v1/calibrate/zone/{zone_id}")
async def calibrate_zone_endpoint(
    zone_id: int,
    days: int = Query(7, ge=1, le=30),
    persist: bool = Query(False),
):
    """Запустить полную калибровку зоны.

    `persist=true` — записать новые версии в `zone_dt_params` (вытесняя
    активные). `persist=false` — только вернуть рассчитанные параметры.
    """
    try:
        if persist:
            result = await calibrate_zone_with_persist(zone_id, days=days)
        else:
            result = await calibrate_zone(zone_id, days=days)
        return JSONResponse(content={"status": "ok", "data": result})
    except Exception as exc:
        logger.exception("Calibration failed for zone %s", zone_id)
        raise HTTPException(status_code=500, detail=f"Calibration failed: {exc}")


# --- Drift --------------------------------------------------------------


class DriftRequest(BaseModel):
    from_ts: datetime
    to_ts: datetime
    step_minutes: int = Field(15, ge=1, le=60)
    thresholds: Optional[Dict[str, float]] = None


@router.post("/v1/drift/zone/{zone_id}")
async def drift_zone_endpoint(zone_id: int, request: DriftRequest):
    """Подсчитать sim2real drift зоны через replay."""
    if request.to_ts <= request.from_ts:
        raise HTTPException(status_code=400, detail="to_ts must be > from_ts")
    try:
        result = await compute_drift_for_zone(
            zone_id=zone_id,
            from_ts=request.from_ts,
            to_ts=request.to_ts,
            step_minutes=request.step_minutes,
            thresholds=request.thresholds,
        )
        return JSONResponse(content={"status": "ok", "data": result})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Drift computation failed for zone %s", zone_id)
        raise HTTPException(status_code=500, detail=f"Drift failed: {exc}")


# --- DT params readers --------------------------------------------------


@router.get("/v1/zone-dt-params/{zone_id}")
async def get_zone_dt_params_endpoint(zone_id: int):
    """Вернуть все активные группы параметров зоны (с MAE и version)."""
    try:
        params = await list_active_params(zone_id)
        return JSONResponse(content={"status": "ok", "data": params})
    except Exception as exc:
        logger.exception("Failed to list dt_params for zone %s", zone_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/v1/zone-dt-params/{zone_id}/{param_group}/versions")
async def list_versions_endpoint(zone_id: int, param_group: str):
    """История версий конкретной группы параметров зоны."""
    try:
        versions = await list_versions(zone_id, param_group)
        return JSONResponse(content={"status": "ok", "data": versions})
    except Exception as exc:
        logger.exception(
            "Failed to list versions zone=%s group=%s", zone_id, param_group
        )
        raise HTTPException(status_code=500, detail=str(exc))

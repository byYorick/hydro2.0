"""
Digital Twin Engine - симуляция зон для тестирования рецептов и сценариев.
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from fastapi import Query
from decimal import Decimal
from datetime import datetime, timedelta
from common.utils.time import utcnow
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from common.env import get_settings
from common.db import fetch, execute
from common.schemas import SimulationRequest, SimulationScenario
from common.service_logs import send_service_log
from prometheus_client import Counter, Histogram, start_http_server

# Настройка логирования (должна быть до импорта других модулей)
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Явно указываем stdout для Docker
)

logger = logging.getLogger(__name__)

SIMULATIONS_RUN = Counter("simulations_run_total", "Total simulations executed")
SIMULATION_DURATION = Histogram("simulation_duration_seconds", "Simulation execution time")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Digital twin service started")
    send_service_log(
        service="digital-twin",
        level="info",
        message="Digital twin service started",
        context={"port": 8003},
    )
    yield


app = FastAPI(title="Digital Twin Engine", lifespan=lifespan)

# Модели для симуляции
from models import PHModel, ECModel, ClimateModel


class SimulationResponse(BaseModel):
    status: str
    data: Dict[str, Any]


async def get_recipe_revision_phases(recipe_id: int) -> List[Dict[str, Any]]:
    """
    Получить фазы рецепта из ревизии (новая модель).
    Для симуляции используем последнюю опубликованную ревизию рецепта.
    """
    # Получаем последнюю опубликованную ревизию рецепта
    revision_rows = await fetch(
        """
        SELECT id
        FROM recipe_revisions
        WHERE recipe_id = $1 AND status = 'PUBLISHED'
        ORDER BY revision_number DESC
        LIMIT 1
        """,
        recipe_id,
    )
    
    if not revision_rows:
        logger.warning(f'No published revision found for recipe {recipe_id}')
        return []
    
    revision_id = revision_rows[0]["id"]
    
    # Получаем фазы ревизии
    phase_rows = await fetch(
        """
        SELECT 
            phase_index,
            name,
            duration_hours,
            duration_days,
            ph_target, ph_min, ph_max,
            ec_target, ec_min, ec_max,
            temp_air_target,
            humidity_target,
            co2_target,
            irrigation_mode,
            irrigation_interval_sec,
            irrigation_duration_sec,
            lighting_photoperiod_hours,
            lighting_start_time,
            mist_interval_sec,
            mist_duration_sec,
            mist_mode,
            extensions
        FROM recipe_revision_phases
        WHERE recipe_revision_id = $1
        ORDER BY phase_index ASC
        """,
        revision_id,
    )
    
    if not phase_rows:
        return []
    
    # Преобразуем фазы в формат, совместимый со старым кодом
    phases = []
    def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
        if value is None:
            return default
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def sanitize_numeric(value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, dict):
            return {k: sanitize_numeric(v) for k, v in value.items()}
        if isinstance(value, list):
            return [sanitize_numeric(v) for v in value]
        return value

    for row in phase_rows:
        # Преобразуем колонки в формат targets для совместимости
        targets = {}
        
        if row.get("ph_target") is not None:
            targets["ph"] = to_float(row["ph_target"], None)
        if row.get("ec_target") is not None:
            targets["ec"] = to_float(row["ec_target"], None)
        if row.get("temp_air_target") is not None:
            targets["temp_air"] = to_float(row["temp_air_target"], None)
        if row.get("humidity_target") is not None:
            targets["humidity_air"] = to_float(row["humidity_target"], None)
        if row.get("co2_target") is not None:
            targets["co2"] = to_float(row["co2_target"], None)
        
        # Добавляем расширения если есть
        if row.get("extensions"):
            targets.update(row["extensions"])

        targets = sanitize_numeric(targets)

        duration_hours = to_float(row.get("duration_hours"), None)
        if not duration_hours and row.get("duration_days"):
            duration_hours = to_float(row["duration_days"], 0) * 24
        
        phases.append({
            "phase_index": row["phase_index"],
            "name": row["name"],
            "duration_hours": duration_hours or 0,
            "targets": targets,
        })
    
    return phases


async def simulate_zone(request: SimulationRequest) -> Dict[str, Any]:
    """
    Симуляция зоны на заданный период времени.
    """
    with SIMULATION_DURATION.time():
        SIMULATIONS_RUN.inc()

        # Получаем фазы рецепта
        recipe_id = request.scenario.recipe_id
        logger.info(
            "Digital twin simulation requested",
            extra={
                "zone_id": request.zone_id,
                "recipe_id": recipe_id,
                "duration_hours": request.duration_hours,
                "step_minutes": request.step_minutes,
            },
        )
        if not recipe_id:
            raise HTTPException(status_code=400, detail="recipe_id required in scenario")

        phases = await get_recipe_revision_phases(recipe_id)
        if not phases:
            raise HTTPException(status_code=404, detail=f"Recipe {recipe_id} not found or has no phases")

        def to_float(value: Any, default: float) -> float:
            if value is None:
                return default
            if isinstance(value, Decimal):
                return float(value)
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def sanitize_numeric(value: Any) -> Any:
            if isinstance(value, Decimal):
                return float(value)
            if isinstance(value, dict):
                return {k: sanitize_numeric(v) for k, v in value.items()}
            if isinstance(value, list):
                return [sanitize_numeric(v) for v in value]
            return value

        # Начальное состояние
        initial_state = sanitize_numeric(request.scenario.initial_state or {})
        ph = to_float(initial_state.get("ph"), 6.0)
        ec = to_float(initial_state.get("ec"), 1.2)
        temp_air = to_float(initial_state.get("temp_air"), 22.0)
        temp_water = to_float(initial_state.get("temp_water"), 20.0)
        humidity_air = to_float(initial_state.get("humidity_air"), 60.0)

        # Получаем калиброванные параметры для зоны (опционально, можно кэшировать)
        # Для MVP используем дефолтные параметры, калибровку можно вызывать отдельно
        calibrated_params = None
        
        # Инициализация моделей с калиброванными параметрами (если есть)
        ph_params = calibrated_params.get("ph") if calibrated_params and isinstance(calibrated_params, dict) else None
        ec_params = calibrated_params.get("ec") if calibrated_params and isinstance(calibrated_params, dict) else None
        climate_params = calibrated_params.get("climate") if calibrated_params and isinstance(calibrated_params, dict) else None
        
        ph_model = PHModel(ph_params)
        ec_model = ECModel(ec_params)
        climate_model = ClimateModel(climate_params)

        # Результаты симуляции
        points = []
        start_time = utcnow()
        current_time = start_time
        end_time = current_time + timedelta(hours=request.duration_hours)
        step_delta = timedelta(minutes=request.step_minutes)
        step_hours = step_delta.total_seconds() / 3600

        # Определяем текущую фазу
        current_phase_index = 0
        phase_start_time = current_time
        cumulative_hours = 0.0

        while current_time < end_time:
            # Проверяем переход на следующую фазу
            if current_phase_index < len(phases):
                phase = phases[current_phase_index]
                phase_duration = phase.get("duration_hours", 0)
                
                if (current_time - phase_start_time).total_seconds() / 3600 >= phase_duration:
                    current_phase_index += 1
                    if current_phase_index < len(phases):
                        phase_start_time = current_time
                    else:
                        # Все фазы завершены, используем последнюю
                        current_phase_index = len(phases) - 1

            # Получаем targets текущей фазы
            if current_phase_index < len(phases):
                phase = phases[current_phase_index]
                targets = sanitize_numeric(phase.get("targets", {}))
                target_ph = to_float(targets.get("ph", ph), ph)
                target_ec = to_float(targets.get("ec", ec), ec)
                target_temp_air = to_float(targets.get("temp_air", temp_air), temp_air)
                target_humidity_air = to_float(targets.get("humidity_air", humidity_air), humidity_air)
            else:
                # Используем последние значения как targets
                target_ph = ph
                target_ec = ec
                target_temp_air = temp_air
                target_humidity_air = humidity_air

            # Симулируем один шаг (используем длительность шага, а не накопленное время)
            ph = to_float(ph, 6.0)
            ec = to_float(ec, 1.2)
            temp_air = to_float(temp_air, 22.0)
            humidity_air = to_float(humidity_air, 60.0)
            
            # pH модель
            ph = ph_model.step(ph, target_ph, step_hours)
            
            # EC модель
            ec = ec_model.step(ec, target_ec, step_hours)
            
            # Климат модель
            temp_air, humidity_air = climate_model.step(
                temp_air, humidity_air, target_temp_air, target_humidity_air, step_hours
            )

            # Сохраняем точку
            elapsed_hours_total = (current_time - start_time).total_seconds() / 3600
            points.append({
                "t": elapsed_hours_total,  # часы от начала
                "ph": round(ph, 2),
                "ec": round(ec, 2),
                "temp_air": round(temp_air, 1),
                "temp_water": round(temp_water, 1),
                "humidity_air": round(humidity_air, 1),
                "phase_index": current_phase_index,
            })

            current_time += step_delta

        return {
            "status": "ok",
            "data": {
                "points": points,
                "duration_hours": request.duration_hours,
                "step_minutes": request.step_minutes,
            },
        }


@app.post("/simulate/zone", response_model=SimulationResponse)
async def simulate_zone_endpoint(request: SimulationRequest):
    """Запустить симуляцию зоны."""
    try:
        result = await simulate_zone(request)
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Digital Twin simulation failed", exc_info=e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calibrate/zone/{zone_id}")
async def calibrate_zone(zone_id: int, days: int = Query(7, ge=1, le=30)):
    """
    Калибровка параметров модели по историческим данным.
    
    Args:
        zone_id: ID зоны для калибровки
        days: Количество дней исторических данных для анализа (по умолчанию 7)
    
    Returns:
        Калиброванные параметры моделей
    """
    from calibration import calibrate_zone_models
    
    try:
        result = await calibrate_zone_models(zone_id, days)
        
        # Сохраняем калиброванные параметры в БД (опционально)
        # Можно создать таблицу zone_model_params для хранения
        
        return JSONResponse(content={
            "status": "ok",
            "data": result,
        })
    except Exception as e:
        import logging
        logging.error(f"Calibration failed for zone {zone_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Calibration failed: {str(e)}")


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    start_http_server(9403)  # Prometheus metrics
    uvicorn.run(app, host="0.0.0.0", port=8003)

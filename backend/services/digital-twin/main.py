"""
Digital Twin Engine - симуляция зон для тестирования рецептов и сценариев.
"""
import asyncio
import json
import logging
import os
from typing import Dict, Any, List, Optional
from fastapi import Query
from datetime import datetime, timedelta
from common.utils.time import utcnow
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from common.env import get_settings
from common.db import fetch, execute
from common.schemas import SimulationRequest, SimulationScenario
from prometheus_client import Counter, Histogram, start_http_server

# Настройка логирования (должна быть до импорта других модулей)
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Явно указываем stdout для Docker
)

SIMULATIONS_RUN = Counter("simulations_run_total", "Total simulations executed")
SIMULATION_DURATION = Histogram("simulation_duration_seconds", "Simulation execution time")

app = FastAPI(title="Digital Twin Engine")

# Модели для симуляции
from models import PHModel, ECModel, ClimateModel


class SimulationResponse(BaseModel):
    status: str
    data: Dict[str, Any]


async def get_recipe_phases(recipe_id: int) -> List[Dict[str, Any]]:
    """Получить фазы рецепта."""
    rows = await fetch(
        """
        SELECT phase_index, name, duration_hours, targets
        FROM recipe_phases
        WHERE recipe_id = $1
        ORDER BY phase_index ASC
        """,
        recipe_id,
    )
    return rows or []


async def simulate_zone(request: SimulationRequest) -> Dict[str, Any]:
    """
    Симуляция зоны на заданный период времени.
    """
    with SIMULATION_DURATION.time():
        SIMULATIONS_RUN.inc()

        # Получаем фазы рецепта
        recipe_id = request.scenario.recipe_id
        if not recipe_id:
            raise HTTPException(status_code=400, detail="recipe_id required in scenario")

        phases = await get_recipe_phases(recipe_id)
        if not phases:
            raise HTTPException(status_code=404, detail=f"Recipe {recipe_id} not found or has no phases")

        # Начальное состояние
        initial_state = request.scenario.initial_state or {}
        ph = initial_state.get("ph", 6.0)
        ec = initial_state.get("ec", 1.2)
        temp_air = initial_state.get("temp_air", 22.0)
        temp_water = initial_state.get("temp_water", 20.0)
        humidity_air = initial_state.get("humidity_air", 60.0)

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
                targets = phase.get("targets", {})
                target_ph = targets.get("ph", ph)
                target_ec = targets.get("ec", ec)
                target_temp_air = targets.get("temp_air", temp_air)
                target_humidity_air = targets.get("humidity_air", humidity_air)
            else:
                # Используем последние значения как targets
                target_ph = ph
                target_ec = ec
                target_temp_air = temp_air
                target_humidity_air = humidity_air

            # Симулируем один шаг
            elapsed_hours = (current_time - phase_start_time).total_seconds() / 3600
            
            # pH модель
            ph = ph_model.step(ph, target_ph, elapsed_hours)
            
            # EC модель
            ec = ec_model.step(ec, target_ec, elapsed_hours)
            
            # Климат модель
            temp_air, humidity_air = climate_model.step(
                temp_air, humidity_air, target_temp_air, target_humidity_air, elapsed_hours
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


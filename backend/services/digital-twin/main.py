"""
Digital Twin Engine - симуляция зон для тестирования рецептов и сценариев.
"""
import asyncio
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from common.env import get_settings
from common.db import fetch, execute
from prometheus_client import Counter, Histogram, start_http_server

SIMULATIONS_RUN = Counter("simulations_run_total", "Total simulations executed")
SIMULATION_DURATION = Histogram("simulation_duration_seconds", "Simulation execution time")

app = FastAPI(title="Digital Twin Engine")

# Модели для симуляции
from models import PHModel, ECModel, ClimateModel


class SimulationRequest(BaseModel):
    zone_id: int
    duration_hours: int = 72
    step_minutes: int = 10
    scenario: Dict[str, Any]  # {recipe_id, initial_state: {ph, ec, temp_air, temp_water}}


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
        recipe_id = request.scenario.get("recipe_id")
        if not recipe_id:
            raise HTTPException(status_code=400, detail="recipe_id required in scenario")

        phases = await get_recipe_phases(recipe_id)
        if not phases:
            raise HTTPException(status_code=404, detail=f"Recipe {recipe_id} not found or has no phases")

        # Начальное состояние
        initial_state = request.scenario.get("initial_state", {})
        ph = initial_state.get("ph", 6.0)
        ec = initial_state.get("ec", 1.2)
        temp_air = initial_state.get("temp_air", 22.0)
        temp_water = initial_state.get("temp_water", 20.0)
        humidity_air = initial_state.get("humidity_air", 60.0)

        # Инициализация моделей
        ph_model = PHModel()
        ec_model = ECModel()
        climate_model = ClimateModel()

        # Результаты симуляции
        points = []
        start_time = datetime.utcnow()
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
async def calibrate_zone(zone_id: int):
    """
    Калибровка параметров модели по историческим данным.
    Пока заглушка - в будущем можно реализовать ML-калибровку.
    """
    # TODO: Реализовать калибровку по историческим данным
    # Пока возвращаем дефолтные параметры
    return JSONResponse(content={
        "status": "ok",
        "data": {
            "zone_id": zone_id,
            "models": {
                "ph": {
                    "buffer_capacity": 0.1,
                    "natural_drift": 0.01,
                    "correction_rate": 0.05,
                },
                "ec": {
                    "evaporation_rate": 0.02,
                    "dilution_rate": 0.01,
                    "nutrient_addition_rate": 0.03,
                },
                "climate": {
                    "heat_loss_rate": 0.5,
                    "humidity_decay_rate": 0.02,
                    "ventilation_cooling": 1.0,
                },
            },
        },
    })


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    start_http_server(9403)  # Prometheus metrics
    uvicorn.run(app, host="0.0.0.0", port=8003)


"""
Digital Twin Engine - симуляция зон для тестирования рецептов и сценариев.
"""
import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional, Tuple
from fastapi import Query
from decimal import Decimal
from datetime import datetime, timedelta
from common.utils.time import utcnow
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from common.env import get_settings
from common.db import fetch, execute
from common.node_types import normalize_node_type as normalize_canonical_node_type
from common.schemas import SimulationRequest, SimulationScenario
from common.service_logs import send_service_log
from common.infra_alerts import send_infra_exception_alert
from prometheus_client import Counter, Histogram, start_http_server
import httpx
from common.logging_setup import setup_standard_logging, install_exception_handlers
from common.trace_context import clear_trace_id, inject_trace_id_header, set_trace_id_from_headers

# Настройка логирования (до запуска приложения)
setup_standard_logging("digital-twin")
install_exception_handlers("digital-twin")

logger = logging.getLogger(__name__)

SIMULATIONS_RUN = Counter("simulations_run_total", "Total simulations executed")
SIMULATION_DURATION = Histogram("simulation_duration_seconds", "Simulation execution time")

LIVE_SIM_TASKS: Dict[int, asyncio.Task] = {}

NODE_SIM_MANAGER_URL = os.getenv("NODE_SIM_MANAGER_URL", "http://node-sim-manager:9100")
NODE_SIM_MANAGER_TOKEN = os.getenv("NODE_SIM_MANAGER_TOKEN")

DEFAULT_MQTT_CONFIG = {
    "host": os.getenv("NODE_SIM_MQTT_HOST", os.getenv("MQTT_HOST", "mqtt")),
    "port": int(os.getenv("NODE_SIM_MQTT_PORT", os.getenv("MQTT_PORT", 1883))),
    "username": os.getenv("NODE_SIM_MQTT_USERNAME", os.getenv("MQTT_USERNAME")),
    "password": os.getenv("NODE_SIM_MQTT_PASSWORD", os.getenv("MQTT_PASSWORD")),
    "tls": bool(os.getenv("NODE_SIM_MQTT_TLS", "false").lower() == "true"),
    "ca_certs": os.getenv("NODE_SIM_MQTT_CA_CERTS"),
    "keepalive": int(os.getenv("NODE_SIM_MQTT_KEEPALIVE", os.getenv("MQTT_KEEPALIVE", 60))),
}

DEFAULT_TELEMETRY_CONFIG = {
    "interval_seconds": float(os.getenv("NODE_SIM_TELEMETRY_INTERVAL", 5.0)),
    "heartbeat_interval_seconds": float(os.getenv("NODE_SIM_HEARTBEAT_INTERVAL", 30.0)),
    "status_interval_seconds": float(os.getenv("NODE_SIM_STATUS_INTERVAL", 60.0)),
}


def _scale_telemetry_config(
    telemetry: Dict[str, Any],
    time_scale: float,
    min_interval_seconds: float = 0.5,
) -> Dict[str, Any]:
    if not time_scale or time_scale <= 0:
        return telemetry

    scaled = dict(telemetry)
    for key in ("interval_seconds", "heartbeat_interval_seconds", "status_interval_seconds"):
        value = scaled.get(key)
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        scaled_value = numeric / time_scale
        scaled[key] = max(min_interval_seconds, scaled_value)
    return scaled


def _apply_initial_state_to_nodes(
    nodes: List[Dict[str, Any]],
    scenario: Dict[str, Any],
) -> None:
    initial_state = scenario.get("initial_state") or {}
    if not isinstance(initial_state, dict) or not initial_state:
        return

    def to_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    key_map = {
        "ph": ["ph_sensor", "ph"],
        "ec": ["ec_sensor", "ec"],
        "temp_air": ["air_temp_c", "temp_air", "temperature"],
        "temp_water": ["solution_temp_c", "temp_water", "water_temp_c"],
        "humidity_air": ["air_rh", "humidity", "rh", "humidity_air"],
    }

    for node in nodes:
        sensors = node.get("sensors") or []
        sensor_map = {
            str(sensor).lower(): sensor
            for sensor in sensors
            if isinstance(sensor, str)
        }
        if not sensor_map:
            continue

        initial_sensors: Dict[str, float] = {}
        for state_key, candidates in key_map.items():
            if state_key not in initial_state:
                continue
            value = to_float(initial_state.get(state_key))
            if value is None:
                continue
            for candidate in candidates:
                actual = sensor_map.get(candidate.lower())
                if actual:
                    initial_sensors[actual] = value
                    break

        if initial_sensors:
            node["initial_sensors"] = initial_sensors


def _apply_drift_to_nodes(
    nodes: List[Dict[str, Any]],
    scenario: Dict[str, Any],
) -> None:
    node_sim = scenario.get("node_sim") or {}
    if not isinstance(node_sim, dict):
        return

    drift = node_sim.get("drift_per_minute") or {}
    if not isinstance(drift, dict):
        drift = {}
    drift_noise = node_sim.get("drift_noise_per_minute")

    def to_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    key_map = {
        "ph": ["ph_sensor", "ph"],
        "ec": ["ec_sensor", "ec"],
        "temp_air": ["air_temp_c", "temp_air", "temperature"],
        "temp_water": ["solution_temp_c", "temp_water", "water_temp_c"],
        "humidity_air": ["air_rh", "humidity", "rh", "humidity_air"],
    }

    noise_value = to_float(drift_noise)

    for node in nodes:
        sensors = node.get("sensors") or []
        sensor_map = {
            str(sensor).lower(): sensor
            for sensor in sensors
            if isinstance(sensor, str)
        }
        if not sensor_map:
            continue

        drift_map: Dict[str, float] = {}
        for drift_key, raw_value in drift.items():
            value = to_float(raw_value)
            if value is None:
                continue
            if drift_key in key_map:
                for candidate in key_map[drift_key]:
                    actual = sensor_map.get(candidate.lower())
                    if actual:
                        drift_map[actual] = value
                        break
                continue
            actual = sensor_map.get(str(drift_key).lower())
            if actual:
                drift_map[actual] = value

        if drift_map:
            node["drift_per_minute"] = drift_map
        if noise_value is not None:
            node["drift_noise_per_minute"] = noise_value


_LIVE_ORCHESTRATOR = None  # type: Optional["LiveOrchestrator"]


def get_live_orchestrator():
    """Singleton LiveOrchestrator (Phase C)."""
    global _LIVE_ORCHESTRATOR
    if _LIVE_ORCHESTRATOR is None:
        from live import LiveOrchestrator
        _LIVE_ORCHESTRATOR = LiveOrchestrator(
            mqtt_host=DEFAULT_MQTT_CONFIG["host"],
            mqtt_port=DEFAULT_MQTT_CONFIG["port"],
            mqtt_username=DEFAULT_MQTT_CONFIG.get("username"),
            mqtt_password=DEFAULT_MQTT_CONFIG.get("password"),
        )
    return _LIVE_ORCHESTRATOR


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Digital twin service started")
    send_service_log(
        service="digital-twin",
        level="info",
        message="Digital twin service started",
        context={"port": 8003},
    )
    try:
        yield
    finally:
        # Phase C: остановить активные SimWorld и MQTT-bridge.
        global _LIVE_ORCHESTRATOR
        if _LIVE_ORCHESTRATOR is not None:
            try:
                await _LIVE_ORCHESTRATOR.stop()
            except Exception as exc:
                logger.warning("LiveOrchestrator stop failed: %s", exc)
            _LIVE_ORCHESTRATOR = None


app = FastAPI(title="Digital Twin Engine", lifespan=lifespan)

from replay import router as replay_router  # noqa: E402  (fastapi requires app first)
from calibration_api import router as calibration_router  # noqa: E402
app.include_router(replay_router)
app.include_router(calibration_router)


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = set_trace_id_from_headers(request.headers, fallback_generate=True)
    try:
        response = await call_next(request)
    finally:
        clear_trace_id()
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    return response

# Модели для симуляции
# `models.py` сохранён как legacy-контракт для test_models.py.
# Новый код использует модульные solvers через ZoneWorld.
from models import PHModel, ECModel, ClimateModel  # noqa: F401  (legacy regression)
from world import CommandRouter, ZoneWorld


class SimulationResponse(BaseModel):
    status: str
    data: Dict[str, Any]


class LiveSimulationStartRequest(BaseModel):
    zone_id: int = Field(..., ge=1)
    duration_hours: int = Field(..., ge=1)
    step_minutes: int = Field(10, ge=1)
    sim_duration_minutes: int = Field(..., ge=1)
    scenario: Dict[str, Any]
    mqtt: Optional[Dict[str, Any]] = None
    telemetry: Optional[Dict[str, Any]] = None
    failure_mode: Optional[Dict[str, Any]] = None
    # Phase C: физический backend для symлируемой зоны.
    # 'drift' (default, legacy) — node-sim генерит drift-телеметрию сам.
    # 'dt'                       — DT публикует physics-based телеметрию,
    #                              а node-sim используется только для
    #                              status/heartbeat/lwt (sensors=[] override).
    physics_mode: str = Field("drift", pattern="^(drift|dt)$")
    tick_seconds: float = Field(1.0, gt=0.0, le=10.0)


class LiveSimulationStopRequest(BaseModel):
    simulation_id: int = Field(..., ge=1)
    status: str = Field("completed", pattern="^(completed|failed|stopped)$")
    reason: Optional[str] = None


class LiveSimulationStartResponse(BaseModel):
    status: str
    simulation_id: int
    node_sim_session_id: str
    time_scale: float


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


def _sanitize_numeric(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _sanitize_numeric(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_numeric(v) for v in value]
    return value


# Чтение `zone_dt_params` вынесено в `dt_params.py` чтобы избежать конфликта
# `Duplicated timeseries` prometheus_client при повторном импорте `main`.
from dt_params import get_zone_dt_params  # noqa: E402, F401


async def simulate_zone(request: SimulationRequest) -> Dict[str, Any]:
    """Симуляция зоны на заданный период времени через ZoneWorld."""
    with SIMULATION_DURATION.time():
        SIMULATIONS_RUN.inc()

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
            raise HTTPException(
                status_code=404,
                detail=f"Recipe {recipe_id} not found or has no phases",
            )

        initial_state = _sanitize_numeric(request.scenario.initial_state or {})
        params_by_group = await get_zone_dt_params(request.zone_id)

        world = ZoneWorld(params_by_group=params_by_group)
        state = world.initial_state(initial_state)

        # Phase B: если задан inputs_schedule — используем command-driven шаги.
        inputs_schedule = list(request.inputs_schedule or [])
        command_router: Optional[CommandRouter] = None
        if inputs_schedule:
            command_router = CommandRouter(world.actuator_solver, inputs_schedule)

        start_time = utcnow()
        current_time = start_time
        end_time = current_time + timedelta(hours=request.duration_hours)
        step_delta = timedelta(minutes=request.step_minutes)
        step_hours = step_delta.total_seconds() / 3600

        current_phase_index = 0
        phase_start_time = current_time
        points: List[Dict[str, Any]] = []

        while current_time < end_time:
            if current_phase_index < len(phases):
                phase_duration = float(phases[current_phase_index].get("duration_hours", 0) or 0)
                elapsed_in_phase = (current_time - phase_start_time).total_seconds() / 3600
                if elapsed_in_phase >= phase_duration:
                    current_phase_index += 1
                    if current_phase_index < len(phases):
                        phase_start_time = current_time
                    else:
                        # Все фазы завершены — оставляем последнюю как hold targets.
                        current_phase_index = len(phases) - 1

            if current_phase_index < len(phases):
                targets = _sanitize_numeric(phases[current_phase_index].get("targets", {}) or {})
            else:
                targets = {}

            elapsed_minutes_total = (current_time - start_time).total_seconds() / 60.0
            if command_router is not None:
                # Применить cmd-события до конца этого шага (incl).
                command_router.advance_to(elapsed_minutes_total + request.step_minutes)
                state = world.step_with_commands(state, targets, step_hours)
            else:
                state = world.step(state, targets, step_hours)

            elapsed_hours_total = elapsed_minutes_total / 60.0
            point: Dict[str, Any] = {
                "t": elapsed_hours_total,
                "ph": round(state.chem.ph, 2),
                "ec": round(state.chem.ec, 2),
                "temp_air": round(state.climate.temp_air_c, 1),
                "temp_water": round(state.tank.water_temp_c, 1),
                "humidity_air": round(state.climate.humidity_air_pct, 1),
                "phase_index": current_phase_index,
            }
            if command_router is not None:
                point["solution_volume_l"] = round(state.tank.solution_volume_l, 2)
                point["clean_volume_l"] = round(state.tank.clean_volume_l, 2)
                point["level_clean_max"] = state.tank.level_clean_max
                point["level_solution_max"] = state.tank.level_solution_max
                point["level_solution_min"] = state.tank.level_solution_min
                point["water_content"] = round(state.substrate.water_content_pct, 1)
            points.append(point)

            current_time += step_delta

        return {
            "status": "ok",
            "data": {
                "points": points,
                "duration_hours": request.duration_hours,
                "step_minutes": request.step_minutes,
            },
        }


async def _node_sim_request(path: str, payload: Dict[str, Any]) -> None:
    headers = inject_trace_id_header()
    if NODE_SIM_MANAGER_TOKEN:
        headers["Authorization"] = f"Bearer {NODE_SIM_MANAGER_TOKEN}"
    url = NODE_SIM_MANAGER_URL.rstrip("/") + path
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload, headers=headers)
    if response.status_code >= 300:
        raise HTTPException(status_code=502, detail=f"node-sim-manager error: {response.text}")


def _normalize_node_type(value: Optional[str]) -> str:
    return normalize_canonical_node_type(value)


async def _load_node_configs(zone_id: int) -> Tuple[str, str, List[Dict[str, Any]]]:
    zone_rows = await fetch(
        """
        SELECT z.uid as zone_uid, g.uid as gh_uid
        FROM zones z
        JOIN greenhouses g ON g.id = z.greenhouse_id
        WHERE z.id = $1
        """,
        zone_id,
    )
    if not zone_rows:
        raise HTTPException(status_code=404, detail="zone not found")
    zone_uid = zone_rows[0]["zone_uid"] or f"zn-{zone_id}"
    gh_uid = zone_rows[0]["gh_uid"] or "gh-1"

    node_rows = await fetch(
        """
        SELECT id, uid, hardware_id, type
        FROM nodes
        WHERE zone_id = $1
        """,
        zone_id,
    )
    if not node_rows:
        raise HTTPException(status_code=400, detail="zone has no nodes for simulation")

    node_ids = [row["id"] for row in node_rows]
    channel_rows = await fetch(
        """
        SELECT node_id, channel, type
        FROM node_channels
        WHERE node_id = ANY($1::int[])
        """,
        node_ids,
    )
    channels_by_node: Dict[int, Dict[str, List[str]]] = {}
    for row in channel_rows:
        entry = channels_by_node.setdefault(row["node_id"], {"sensors": [], "actuators": []})
        channel_type = (row["type"] or "").upper()
        if channel_type == "ACTUATOR":
            entry["actuators"].append(row["channel"])
        else:
            entry["sensors"].append(row["channel"])

    nodes: List[Dict[str, Any]] = []
    for row in node_rows:
        if not row["uid"] or not row["hardware_id"]:
            continue
        node_channels = channels_by_node.get(row["id"], {"sensors": [], "actuators": []})
        nodes.append({
            "node_uid": row["uid"],
            "hardware_id": row["hardware_id"],
            "gh_uid": gh_uid,
            "zone_uid": zone_uid,
            "node_type": _normalize_node_type(row["type"]),
            "mode": "configured",
            "config_report_on_start": True,
            "sensors": node_channels["sensors"],
            "actuators": node_channels["actuators"],
        })

    if not nodes:
        raise HTTPException(status_code=400, detail="zone nodes missing uid/hardware_id")
    return gh_uid, zone_uid, nodes


async def _create_live_simulation(
    request: LiveSimulationStartRequest,
) -> Tuple[int, str, float, Dict[str, Any]]:
    if request.sim_duration_minutes <= 0:
        raise HTTPException(status_code=400, detail="sim_duration_minutes must be > 0")

    now_iso = utcnow().isoformat()
    time_scale = (request.duration_hours * 60.0) / float(request.sim_duration_minutes)
    session_id = f"sim-{request.zone_id}-{int(utcnow().timestamp())}"

    scenario_payload = dict(request.scenario or {})
    if not scenario_payload.get("recipe_id"):
        raise HTTPException(status_code=400, detail="recipe_id required for live simulation")
    sim_meta = {
        "real_started_at": now_iso,
        "sim_started_at": now_iso,
        "engine": "pipeline",
        "mode": "live",
        "orchestrator": "digital-twin",
        "time_scale": time_scale,
        "real_duration_minutes": int(request.sim_duration_minutes),
        "node_sim_session_id": session_id,
    }
    existing_meta = scenario_payload.get("simulation") or {}
    scenario_payload["simulation"] = {**existing_meta, **sim_meta}

    rows = await fetch(
        """
        INSERT INTO zone_simulations (zone_id, scenario, duration_hours, step_minutes, status, created_at, updated_at)
        VALUES ($1, $2, $3, $4, 'running', NOW(), NOW())
        RETURNING id
        """,
        request.zone_id,
        scenario_payload,
        request.duration_hours,
        request.step_minutes,
    )
    simulation_id = rows[0]["id"]

    await _record_simulation_event(
        simulation_id,
        request.zone_id,
        service="digital-twin",
        stage="live_init",
        status="running",
        message="Live-симуляция зарегистрирована",
        payload={
            "node_sim_session_id": session_id,
            "time_scale": time_scale,
        },
    )

    return simulation_id, session_id, time_scale, scenario_payload


async def _update_simulation_status(
    simulation_id: int,
    status: str,
    scenario: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> None:
    await execute(
        """
        UPDATE zone_simulations
        SET status = $1,
            scenario = COALESCE($2, scenario),
            error_message = $3,
            updated_at = NOW()
        WHERE id = $4
        """,
        status,
        scenario,
        error_message,
        simulation_id,
    )


async def _record_simulation_event(
    simulation_id: int,
    zone_id: int,
    service: str,
    stage: str,
    status: str,
    message: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    level: str = "info",
) -> None:
    await execute(
        """
        INSERT INTO simulation_events (
            simulation_id,
            zone_id,
            service,
            stage,
            status,
            level,
            message,
            payload,
            occurred_at,
            created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
        """,
        simulation_id,
        zone_id,
        service,
        stage,
        status,
        level,
        message,
        json.dumps(payload) if payload else None,
    )


async def _complete_live_simulation(
    simulation_id: int,
    session_id: str,
    duration_minutes: int,
):
    scenario: Dict[str, Any] = {}
    zone_id: int = 0
    try:
        await asyncio.sleep(duration_minutes * 60)
        rows = await fetch(
            "SELECT scenario, zone_id FROM zone_simulations WHERE id = $1",
            simulation_id,
        )
        if not rows:
            return
        scenario = rows[0]["scenario"] or {}
        zone_id = rows[0].get("zone_id") or 0
        sim_meta = scenario.get("simulation") or {}
        sim_meta["real_ended_at"] = utcnow().isoformat()
        sim_started = sim_meta.get("sim_started_at")
        time_scale = sim_meta.get("time_scale")
        if sim_started and time_scale:
            try:
                sim_start_dt = datetime.fromisoformat(sim_started)
                sim_end_dt = sim_start_dt + timedelta(seconds=duration_minutes * 60 * float(time_scale))
                sim_meta["sim_ended_at"] = sim_end_dt.isoformat()
            except ValueError:
                pass
        scenario["simulation"] = sim_meta
        await _node_sim_request("/sessions/stop", {"session_id": session_id})
        await _update_simulation_status(simulation_id, "completed", scenario=scenario)
        await _record_simulation_event(
            simulation_id,
            zone_id,
            service="digital-twin",
            stage="live_complete",
            status="completed",
            message="Live-симуляция завершена",
            payload={
                "node_sim_session_id": session_id,
                "duration_minutes": duration_minutes,
            },
        )
    except Exception as exc:
        await _update_simulation_status(simulation_id, "failed", error_message=str(exc))
        await _record_simulation_event(
            simulation_id,
            zone_id,
            service="digital-twin",
            stage="live_complete",
            status="failed",
            message="Live-симуляция завершилась ошибкой",
            payload={
                "node_sim_session_id": session_id,
                "error": str(exc),
            },
            level="error",
        )
        await send_infra_exception_alert(
            error=exc,
            code="infra_unknown_error",
            alert_type="Digital Twin Live Completion Failed",
            severity="error",
            zone_id=zone_id or None,
            service="digital-twin",
            component="live_simulation_completion",
            details={
                "simulation_id": simulation_id,
                "node_sim_session_id": session_id,
            },
        )
    finally:
        LIVE_SIM_TASKS.pop(simulation_id, None)
        # Phase C: cleanup SimWorld если был зарегистрирован.
        try:
            orch = get_live_orchestrator()
            await orch.unregister_simulation(simulation_id)
        except Exception as exc:
            logger.debug("DT SimWorld unregister no-op: %s", exc)


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
        await send_infra_exception_alert(
            error=e,
            code="infra_unknown_error",
            alert_type="Digital Twin Simulation Failed",
            severity="error",
            zone_id=request.zone_id,
            service="digital-twin",
            component="simulate_zone_endpoint",
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/simulations/live/start", response_model=LiveSimulationStartResponse)
async def start_live_simulation(request: LiveSimulationStartRequest):
    try:
        simulation_id, session_id, time_scale, scenario_payload = await _create_live_simulation(request)
        gh_uid, zone_uid, nodes = await _load_node_configs(request.zone_id)

        mqtt_config = dict(DEFAULT_MQTT_CONFIG)
        telemetry_config = dict(DEFAULT_TELEMETRY_CONFIG)
        if request.mqtt:
            mqtt_config.update(request.mqtt)
        if request.telemetry:
            telemetry_config.update(request.telemetry)
        telemetry_config = _scale_telemetry_config(telemetry_config, time_scale)
        _apply_initial_state_to_nodes(nodes, scenario_payload)
        _apply_drift_to_nodes(nodes, scenario_payload)

        # Phase C: при physics_mode='dt' DT берёт на себя sensors-телеметрию.
        # Чтобы node-sim не публиковал свою drift-телеметрию параллельно с DT,
        # обнуляем sensors. status/heartbeat/lwt останутся на node-sim.
        if request.physics_mode == "dt":
            for node in nodes:
                node["sensors"] = []
                node.pop("initial_sensors", None)
                node.pop("drift_per_minute", None)
                node.pop("drift_noise_per_minute", None)

        payload = {
            "session_id": session_id,
            "mqtt": mqtt_config,
            "telemetry": telemetry_config,
            "nodes": nodes,
            "failure_mode": request.failure_mode,
        }
        await _record_simulation_event(
            simulation_id,
            request.zone_id,
            service="node-sim-manager",
            stage="session_start",
            status="requested",
            message="Запрос на запуск node-sim сессии",
            payload={"node_sim_session_id": session_id},
        )
        try:
            await _node_sim_request("/sessions/start", payload)
        except Exception as exc:
            await _record_simulation_event(
                simulation_id,
                request.zone_id,
                service="node-sim-manager",
                stage="session_start",
                status="failed",
                message="Ошибка запуска node-sim сессии",
                payload={"node_sim_session_id": session_id, "error": str(exc)},
                level="error",
            )
            raise

        await _record_simulation_event(
            simulation_id,
            request.zone_id,
            service="node-sim-manager",
            stage="session_start",
            status="completed",
            message="Node-sim сессия запущена",
            payload={"node_sim_session_id": session_id},
        )

        # Phase C: регистрируем SimWorld в DT (если physics_mode='dt').
        if request.physics_mode == "dt":
            try:
                params_by_group = await get_zone_dt_params(request.zone_id)
                initial_state = scenario_payload.get("initial_state") or {}
                orch = get_live_orchestrator()
                await orch.register_simulation(
                    simulation_id=simulation_id,
                    zone_id=request.zone_id,
                    gh_uid=gh_uid,
                    zone_uid=zone_uid,
                    params_by_group=params_by_group,
                    initial_state=initial_state if isinstance(initial_state, dict) else {},
                    time_scale=time_scale,
                    tick_seconds=request.tick_seconds,
                )
                await _record_simulation_event(
                    simulation_id,
                    request.zone_id,
                    service="digital-twin",
                    stage="dt_world_registered",
                    status="completed",
                    message="DT physics-backend поднят для зоны",
                    payload={"tick_seconds": request.tick_seconds},
                )
            except Exception as exc:
                logger.exception("Failed to register DT SimWorld", exc_info=exc)
                await _record_simulation_event(
                    simulation_id,
                    request.zone_id,
                    service="digital-twin",
                    stage="dt_world_registered",
                    status="failed",
                    message="Не удалось поднять DT physics-backend",
                    payload={"error": str(exc)},
                    level="error",
                )

        task = asyncio.create_task(
            _complete_live_simulation(simulation_id, session_id, request.sim_duration_minutes)
        )
        LIVE_SIM_TASKS[simulation_id] = task

        return LiveSimulationStartResponse(
            status="started",
            simulation_id=simulation_id,
            node_sim_session_id=session_id,
            time_scale=time_scale,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Live simulation start failed", exc_info=e)
        await send_infra_exception_alert(
            error=e,
            code="infra_unknown_error",
            alert_type="Live Simulation Start Failed",
            severity="error",
            zone_id=request.zone_id,
            service="digital-twin",
            component="start_live_simulation",
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/simulations/live/stop")
async def stop_live_simulation(request: LiveSimulationStopRequest):
    try:
        rows = await fetch(
            "SELECT scenario, zone_id FROM zone_simulations WHERE id = $1",
            request.simulation_id,
        )
        if not rows:
            raise HTTPException(status_code=404, detail="simulation not found")
        scenario = rows[0]["scenario"] or {}
        zone_id = rows[0].get("zone_id") or 0
        sim_meta = scenario.get("simulation") or {}
        session_id = sim_meta.get("node_sim_session_id")
        if session_id:
            await _record_simulation_event(
                request.simulation_id,
                zone_id,
                service="node-sim-manager",
                stage="session_stop",
                status="requested",
                message="Запрос на остановку node-sim сессии",
                payload={"node_sim_session_id": session_id},
            )
            await _node_sim_request("/sessions/stop", {"session_id": session_id})
            await _record_simulation_event(
                request.simulation_id,
                zone_id,
                service="node-sim-manager",
                stage="session_stop",
                status="completed",
                message="Node-sim сессия остановлена",
                payload={"node_sim_session_id": session_id},
            )

        if request.status in ("completed", "failed", "stopped"):
            sim_meta["real_ended_at"] = utcnow().isoformat()
            scenario["simulation"] = sim_meta
            await _update_simulation_status(
                request.simulation_id,
                request.status,
                scenario=scenario,
                error_message=request.reason,
            )

        task = LIVE_SIM_TASKS.pop(request.simulation_id, None)
        if task:
            task.cancel()

        # Phase C: cleanup SimWorld для этой симуляции (если был зарегистрирован).
        try:
            orch = get_live_orchestrator()
            await orch.unregister_simulation(request.simulation_id)
        except Exception as exc:
            logger.debug("DT SimWorld unregister on stop no-op: %s", exc)

        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Live simulation stop failed", exc_info=e)
        await send_infra_exception_alert(
            error=e,
            code="infra_unknown_error",
            alert_type="Live Simulation Stop Failed",
            severity="error",
            zone_id=None,
            service="digital-twin",
            component="stop_live_simulation",
            details={"simulation_id": request.simulation_id},
        )
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
        await send_infra_exception_alert(
            error=e,
            code="infra_unknown_error",
            alert_type="Digital Twin Calibration Failed",
            severity="error",
            zone_id=zone_id,
            service="digital-twin",
            component="calibrate_zone",
        )
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

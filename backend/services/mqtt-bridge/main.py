from fastapi import FastAPI, Path
from fastapi import HTTPException, Request
from fastapi import Body, Response
from pydantic import BaseModel, Field
from typing import Optional
import logging
import os
from common.schemas import CommandRequest
from common.commands import new_command_id, mark_command_sent
from publisher import Publisher
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from common.env import get_settings
from common.mqtt import MqttClient
from common.db import fetch
from common.water_flow import execute_fill_mode, execute_drain_mode, calibrate_flow

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

REQ_COUNTER = Counter("bridge_requests_total", "Bridge HTTP requests", ["path"])

app = FastAPI(title="MQTT Bridge", version="0.1.2")

# Создаем Publisher при старте приложения
try:
    publisher = Publisher()
    logger.info("Publisher initialized successfully, MQTT connected: %s", publisher._mqtt.is_connected())
except Exception as e:
    logger.error(f"Failed to initialize Publisher: {e}", exc_info=True)
    publisher = None


def _auth(request: Request):
    """
    Проверка токена аутентификации.
    В production токен обязателен всегда, без исключений для внутренних IP.
    В dev окружении разрешаем внутренние запросы без токена только если токен не настроен.
    """
    s = get_settings()
    
    # Проверяем окружение
    app_env = os.getenv("APP_ENV", "").lower().strip()
    is_prod = app_env in ("production", "prod") and app_env != ""
    
    # В production токен обязателен всегда
    if is_prod:
        if not s.bridge_api_token:
            logger.error("PY_API_TOKEN must be set in production environment")
            raise HTTPException(
                status_code=500,
                detail="Server configuration error: API token not configured"
            )
        
        token = request.headers.get("Authorization", "")
        if token != f"Bearer {s.bridge_api_token}":
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(
                f"Invalid or missing token in production: token_present={bool(token)}, "
                f"client_ip={client_ip}"
            )
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: token required in production"
            )
        return
    
    # В dev окружении: если токен настроен, он обязателен
    # Если токен не настроен, разрешаем только localhost (не все внутренние IP)
    if s.bridge_api_token:
        token = request.headers.get("Authorization", "")
        if token != f"Bearer {s.bridge_api_token}":
            logger.warning(f"Invalid or missing token: token_present={bool(token)}")
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: invalid or missing token"
            )
        return
    
    # Dev окружение без токена: разрешаем только localhost
    client_ip = request.client.host if request.client else ""
    is_localhost = client_ip in ["127.0.0.1", "::1", "localhost"]
    
    if not is_localhost:
        logger.warning(
            f"Rejecting non-localhost request without token in dev: client_ip={client_ip}. "
            f"Set PY_API_TOKEN for production or use localhost in dev."
        )
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: token required for non-localhost requests. Set PY_API_TOKEN or use localhost."
        )
    
    logger.debug(f"Allowing localhost request without token (dev mode): client_ip={client_ip}")


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/bridge/zones/{zone_id}/commands")
async def send_zone_command(
    request: Request,
    zone_id: int = Path(..., ge=1),
    req: CommandRequest = Body(...),
):
    _auth(request)
    REQ_COUNTER.labels(path="/bridge/zones/{zone_id}/commands").inc()
    if not (req.greenhouse_uid and req.node_uid and req.channel):
        raise HTTPException(status_code=400, detail="greenhouse_uid, node_uid and channel are required")
    # Use cmd_id from Laravel if provided, otherwise generate new one
    cmd_id = req.cmd_id or new_command_id()
    payload = {"cmd": req.type, "cmd_id": cmd_id, **({"params": req.params} if req.params else {})}
    # Получаем hardware_id из запроса для временного топика
    hardware_id = req.hardware_id
    
    # Получаем zone_uid из БД, если mqtt_zone_format="uid"
    zone_uid = None
    s = get_settings()
    if s.mqtt_zone_format == "uid":
        rows = await fetch(
            """
            SELECT uid
            FROM zones
            WHERE id = $1
            """,
            zone_id,
        )
        if rows and len(rows) > 0:
            zone_uid = rows[0].get("uid")
            if not zone_uid:
                logger.warning(f"Zone {zone_id} has no uid, using zn-{zone_id} as fallback")
        else:
            logger.warning(f"Zone {zone_id} not found, using zn-{zone_id} as fallback")
    
    publisher.publish_command(req.greenhouse_uid, zone_id, req.node_uid, req.channel, payload, hardware_id=hardware_id, zone_uid=zone_uid)
    await mark_command_sent(cmd_id)
    return {"status": "ok", "data": {"command_id": cmd_id}}


@app.post("/bridge/nodes/{node_uid}/commands")
async def send_node_command(
    request: Request,
    node_uid: str = Path(..., min_length=1),
    req: CommandRequest = Body(...),
):
    _auth(request)
    REQ_COUNTER.labels(path="/bridge/nodes/{node_uid}/commands").inc()
    if not (req.greenhouse_uid and req.zone_id and req.channel):
        raise HTTPException(status_code=400, detail="greenhouse_uid, zone_id and channel are required")
    # Use cmd_id from Laravel if provided, otherwise generate new one
    cmd_id = req.cmd_id or new_command_id()
    payload = {"cmd": req.type, "cmd_id": cmd_id, **({"params": req.params} if req.params else {})}
    # Получаем hardware_id из запроса для временного топика
    hardware_id = req.hardware_id
    
    # Получаем zone_uid из БД, если mqtt_zone_format="uid"
    zone_uid = None
    s = get_settings()
    if s.mqtt_zone_format == "uid" and req.zone_id:
        rows = await fetch(
            """
            SELECT uid
            FROM zones
            WHERE id = $1
            """,
            req.zone_id,
        )
        if rows and len(rows) > 0:
            zone_uid = rows[0].get("uid")
            if not zone_uid:
                logger.warning(f"Zone {req.zone_id} has no uid, using zn-{req.zone_id} as fallback")
        else:
            logger.warning(f"Zone {req.zone_id} not found, using zn-{req.zone_id} as fallback")
    
    publisher.publish_command(req.greenhouse_uid, req.zone_id, node_uid, req.channel, payload, hardware_id=hardware_id, zone_uid=zone_uid)
    await mark_command_sent(cmd_id)
    return {"status": "ok", "data": {"command_id": cmd_id}}


class FillDrainRequest(BaseModel):
    target_level: float
    max_duration_sec: Optional[int] = 300


class CalibrateFlowRequest(BaseModel):
    node_id: int
    channel: str
    pump_duration_sec: Optional[int] = 10


async def get_gh_uid_for_zone(zone_id: int) -> Optional[str]:
    """Get greenhouse uid for zone."""
    rows = await fetch(
        """
        SELECT g.uid
        FROM zones z
        JOIN greenhouses g ON g.id = z.greenhouse_id
        WHERE z.id = $1
        """,
        zone_id,
    )
    if rows and len(rows) > 0:
        return rows[0]["uid"]
    return None


@app.post("/bridge/zones/{zone_id}/fill")
async def zone_fill(
    request: Request,
    zone_id: int = Path(..., ge=1),
    req: FillDrainRequest = Body(...),
):
    """Execute fill mode for zone."""
    _auth(request)
    REQ_COUNTER.labels(path="/bridge/zones/{zone_id}/fill").inc()
    
    # Validate target_level
    if not (0.1 <= req.target_level <= 1.0):
        raise HTTPException(status_code=400, detail="target_level must be between 0.1 and 1.0")
    
    # Get greenhouse uid
    gh_uid = await get_gh_uid_for_zone(zone_id)
    if not gh_uid:
        raise HTTPException(status_code=404, detail="Zone not found or has no greenhouse")
    
    # Create MQTT client
    mqtt = MqttClient(client_id_suffix="-fill")
    mqtt.start()
    
    try:
        # Execute fill mode (async, but we wait for it)
        result = await execute_fill_mode(
            zone_id,
            req.target_level,
            mqtt,
            gh_uid,
            req.max_duration_sec
        )
        return {"status": "ok", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Закрываем соединение MQTT для предотвращения утечек
        mqtt.stop()


@app.post("/bridge/zones/{zone_id}/drain")
async def zone_drain(
    request: Request,
    zone_id: int = Path(..., ge=1),
    req: FillDrainRequest = Body(...),
):
    """Execute drain mode for zone."""
    _auth(request)
    REQ_COUNTER.labels(path="/bridge/zones/{zone_id}/drain").inc()
    
    # Validate target_level
    if not (0.0 <= req.target_level <= 0.9):
        raise HTTPException(status_code=400, detail="target_level must be between 0.0 and 0.9")
    
    # Get greenhouse uid
    gh_uid = await get_gh_uid_for_zone(zone_id)
    if not gh_uid:
        raise HTTPException(status_code=404, detail="Zone not found or has no greenhouse")
    
    # Create MQTT client
    mqtt = MqttClient(client_id_suffix="-drain")
    mqtt.start()
    
    try:
        # Execute drain mode (async, but we wait for it)
        result = await execute_drain_mode(
            zone_id,
            req.target_level,
            mqtt,
            gh_uid,
            req.max_duration_sec
        )
        return {"status": "ok", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Закрываем соединение MQTT для предотвращения утечек
        mqtt.stop()


from common.schemas import NodeConfigModel

class NodeConfigRequest(BaseModel):
    node_uid: str = Field(..., min_length=1, max_length=128)
    hardware_id: Optional[str] = Field(None, max_length=128)  # Для временного топика
    zone_id: Optional[int] = Field(None, ge=1)
    greenhouse_uid: Optional[str] = Field(None, max_length=128)
    config: NodeConfigModel


@app.post("/bridge/nodes/{node_uid}/config")
async def publish_node_config(
    request: Request,
    node_uid: str = Path(..., min_length=1),
    req: NodeConfigRequest = Body(...),
):
    """Публиковать NodeConfig в MQTT."""
    _auth(request)
    REQ_COUNTER.labels(path="/bridge/nodes/{node_uid}/config").inc()
    
    # Получаем zone_id и gh_uid из запроса или из БД
    zone_id = req.zone_id
    gh_uid = req.greenhouse_uid
    
    # Если не указаны, пытаемся получить из БД
    if not zone_id or not gh_uid:
        rows = await fetch(
            """
            SELECT n.zone_id, g.uid as gh_uid
            FROM nodes n
            LEFT JOIN zones z ON n.zone_id = z.id
            LEFT JOIN greenhouses g ON z.greenhouse_id = g.id
            WHERE n.uid = $1
            """,
            node_uid,
        )
        if rows and len(rows) > 0:
            if not zone_id:
                zone_id = rows[0].get("zone_id")
            if not gh_uid:
                gh_uid = rows[0].get("gh_uid")
    
    if not zone_id:
        raise HTTPException(status_code=400, detail="zone_id is required (node must be assigned to a zone)")
    if not gh_uid:
        raise HTTPException(status_code=400, detail="greenhouse_uid is required (zone must have a greenhouse)")
    
    # Публикуем конфиг
    if not publisher:
        raise HTTPException(status_code=500, detail="Publisher not initialized")
    
    try:
        logger.info(f"Publishing config for node {node_uid}, zone_id: {zone_id}, gh_uid: {gh_uid}, hardware_id: {req.hardware_id}")
        # Преобразуем Pydantic модель в dict для публикации
        config_dict = req.config.dict() if hasattr(req.config, 'dict') else req.config.model_dump() if hasattr(req.config, 'model_dump') else dict(req.config)
        publisher.publish_config(gh_uid, zone_id, node_uid, config_dict, hardware_id=req.hardware_id)
        logger.info(f"Config published successfully for node {node_uid}")
        return {"status": "ok", "data": {"published": True, "topic": f"hydro/{gh_uid}/zn-{zone_id}/{node_uid}/config"}}
    except Exception as e:
        logger.error(f"Failed to publish config for node {node_uid}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to publish config: {str(e)}")


@app.post("/bridge/zones/{zone_id}/calibrate-flow")
async def zone_calibrate_flow(
    request: Request,
    zone_id: int = Path(..., ge=1),
    req: CalibrateFlowRequest = Body(...),
):
    """Execute flow calibration for zone."""
    _auth(request)
    REQ_COUNTER.labels(path="/bridge/zones/{zone_id}/calibrate-flow").inc()
    
    # Validate pump_duration_sec
    if not (5 <= req.pump_duration_sec <= 60):
        raise HTTPException(status_code=400, detail="pump_duration_sec must be between 5 and 60")
    
    # Get greenhouse uid
    gh_uid = await get_gh_uid_for_zone(zone_id)
    if not gh_uid:
        raise HTTPException(status_code=404, detail="Zone not found or has no greenhouse")
    
    # Create MQTT client
    mqtt = MqttClient(client_id_suffix="-calibrate")
    mqtt.start()
    
    try:
        # Execute flow calibration (async, but we wait for it)
        result = await calibrate_flow(
            zone_id,
            req.node_id,
            req.channel,
            mqtt,
            gh_uid,
            req.pump_duration_sec
        )
        return {"status": "ok", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Закрываем соединение MQTT для предотвращения утечек
        mqtt.stop()



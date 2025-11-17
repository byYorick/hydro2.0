from fastapi import FastAPI, Path
from fastapi import HTTPException, Request
from fastapi import Body, Response
from pydantic import BaseModel
from typing import Optional
from common.schemas import CommandRequest
from common.commands import new_command_id, mark_command_sent
from publisher import Publisher
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from common.env import get_settings
from common.mqtt import MqttClient
from common.db import fetch
from common.water_flow import execute_fill_mode, execute_drain_mode, calibrate_flow

REQ_COUNTER = Counter("bridge_requests_total", "Bridge HTTP requests", ["path"])

app = FastAPI(title="MQTT Bridge", version="0.1.2")
publisher = Publisher()


def _auth(request: Request):
    s = get_settings()
    token = request.headers.get("Authorization", "")
    if s.bridge_api_token and token != f"Bearer {s.bridge_api_token}":
        raise HTTPException(status_code=401, detail="Unauthorized")


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
    publisher.publish_command(req.greenhouse_uid, zone_id, req.node_uid, req.channel, payload)
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
    publisher.publish_command(req.greenhouse_uid, req.zone_id, node_uid, req.channel, payload)
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


class NodeConfigRequest(BaseModel):
    node_uid: str
    zone_id: Optional[int] = None
    greenhouse_uid: Optional[str] = None
    config: dict


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
    publisher.publish_config(gh_uid, zone_id, node_uid, req.config)
    
    return {"status": "ok", "data": {"published": True, "topic": f"hydro/{gh_uid}/zn-{zone_id}/{node_uid}/config"}}


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



from fastapi import FastAPI, Path
from fastapi import HTTPException, Request
from fastapi import Body, Response
from common.schemas import CommandRequest
from common.commands import new_command_id, mark_command_sent
from publisher import Publisher
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
from common.env import get_settings

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
    cmd_id = new_command_id()
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
    cmd_id = new_command_id()
    payload = {"cmd": req.type, "cmd_id": cmd_id, **({"params": req.params} if req.params else {})}
    publisher.publish_command(req.greenhouse_uid, req.zone_id, node_uid, req.channel, payload)
    await mark_command_sent(cmd_id)
    return {"status": "ok", "data": {"command_id": cmd_id}}



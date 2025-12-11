"""
FastAPI endpoints для automation-engine.
Предоставляет REST API для scheduler и других сервисов.
"""
from fastapi import FastAPI, HTTPException, Body, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
from infrastructure import CommandBus

logger = logging.getLogger(__name__)

app = FastAPI(title="Automation Engine API")

# Глобальные переменные для доступа к CommandBus
_command_bus: Optional[CommandBus] = None
_gh_uid: str = ""


def set_command_bus(command_bus: CommandBus, gh_uid: str):
    """Установить CommandBus для использования в endpoints."""
    global _command_bus, _gh_uid
    _command_bus = command_bus
    _gh_uid = gh_uid


class SchedulerCommandRequest(BaseModel):
    """Request model для команд от scheduler."""
    zone_id: int = Field(..., ge=1, description="Zone ID")
    node_uid: str = Field(..., min_length=1, max_length=128, description="Node UID")
    channel: str = Field(..., min_length=1, max_length=64, description="Channel name")
    cmd: str = Field(..., min_length=1, max_length=64, description="Command name")
    params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Command parameters")


@app.post("/scheduler/command")
async def scheduler_command(request: Request, req: SchedulerCommandRequest = Body(...)):
    """
    Endpoint для scheduler для отправки команд через automation-engine.
    Scheduler не должен общаться с нодами напрямую, только через automation-engine.
    """
    if not _command_bus:
        raise HTTPException(status_code=503, detail="CommandBus not initialized")
    
    try:
        logger.info(
            f"Scheduler command request: zone_id={req.zone_id}, node_uid={req.node_uid}, "
            f"channel={req.channel}, cmd={req.cmd}",
            extra={"zone_id": req.zone_id, "node_uid": req.node_uid}
        )
        
        # Отправляем команду через CommandBus (который использует history-logger)
        success = await _command_bus.publish_command(
            zone_id=req.zone_id,
            node_uid=req.node_uid,
            channel=req.channel,
            cmd=req.cmd,
            params=req.params
        )
        
        if success:
            return {
                "status": "ok",
                "data": {
                    "zone_id": req.zone_id,
                    "node_uid": req.node_uid,
                    "channel": req.channel,
                    "cmd": req.cmd
                }
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to publish command")
            
    except Exception as e:
        logger.error(
            f"Error processing scheduler command: {e}",
            exc_info=True,
            extra={"zone_id": req.zone_id, "node_uid": req.node_uid}
        )
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "automation-engine"}


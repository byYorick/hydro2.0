from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class TelemetryPayload(BaseModel):
    node_id: str
    channel: str
    metric_type: str
    value: Optional[float] = None
    raw: Optional[Any] = None
    timestamp: Optional[int] = None


class CommandRequest(BaseModel):
    type: str = Field(..., max_length=64)
    params: Dict[str, Any] = {}
    node_uid: Optional[str] = None
    channel: Optional[str] = None
    greenhouse_uid: Optional[str] = None
    zone_id: Optional[int] = None
    cmd_id: Optional[str] = None  # Command ID from Laravel, if provided


class CommandResponse(BaseModel):
    cmd_id: str
    status: str
    ts: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None



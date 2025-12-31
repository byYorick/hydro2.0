from datetime import datetime
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field


class TelemetryPayloadModel(BaseModel):
    """Model for validating telemetry payload from MQTT."""

    model_config = {"extra": "allow"}

    metric_type: str = Field(..., min_length=1, max_length=50, description="Type of metric")
    value: float = Field(..., description="Metric value")
    ts: Optional[Union[int, float, str]] = Field(
        None, description="Timestamp in seconds (Unix timestamp) from firmware"
    )
    channel: Optional[str] = Field(None, max_length=100, description="Channel identifier")
    node_id: Optional[str] = Field(None, max_length=100, description="Node ID (from firmware)")
    raw: Optional[Union[int, float]] = Field(None, description="Raw sensor value (from firmware)")
    stub: Optional[bool] = Field(
        None, description="Stub flag indicating if value is simulated (from firmware)"
    )
    stable: Optional[bool] = Field(
        None, description="Stability flag for sensor readings (from firmware)"
    )
    tds: Optional[Union[int, float]] = Field(None, description="TDS value (from ec_node)")
    error_code: Optional[Union[int, str]] = Field(None, description="Error code (from firmware)")
    temperature: Optional[float] = Field(None, description="Temperature value (from firmware)")
    state: Optional[str] = Field(None, max_length=50, description="State (from firmware)")
    event: Optional[str] = Field(None, max_length=100, description="Event (from firmware)")
    health: Optional[dict] = Field(None, description="Health metrics (from pump_node)")
    zone_uid: Optional[str] = Field(None, max_length=100, description="Zone UID (fallback from payload)")
    zone_id: Optional[int] = Field(None, ge=1, description="Zone ID (numeric)")
    node_uid: Optional[str] = Field(None, max_length=100, description="Node UID (fallback from payload)")
    gh_uid: Optional[str] = Field(
        None, max_length=100, description="Greenhouse UID (for multi-greenhouse zone resolution)"
    )


class TelemetrySampleModel(BaseModel):
    """Model for telemetry sample."""

    node_uid: str
    zone_uid: Optional[str] = None
    zone_id: Optional[int] = None
    gh_uid: Optional[str] = None
    metric_type: str
    value: float
    ts: Optional[datetime] = None
    raw: Optional[dict] = None
    channel: Optional[str] = None


class CommandRequest(BaseModel):
    """Request model for publishing commands."""

    type: Optional[str] = Field(None, max_length=64, description="Command type (legacy)")
    cmd: Optional[str] = Field(None, max_length=64, description="Command name (new format)")
    params: Dict[str, Any] = Field(default_factory=dict, description="Command parameters")
    source: Optional[str] = Field(None, max_length=64, description="Command source (automation/api/device)")
    node_uid: Optional[str] = Field(None, max_length=128, description="Node UID")
    channel: Optional[str] = Field(None, max_length=64, description="Channel name")
    greenhouse_uid: Optional[str] = Field(None, max_length=128, description="Greenhouse UID")
    zone_id: Optional[int] = Field(None, ge=1, description="Zone ID")
    zone_uid: Optional[str] = Field(None, max_length=128, description="Zone UID")
    cmd_id: Optional[str] = Field(None, max_length=64, description="Command ID from Laravel")
    ts: Optional[int] = Field(None, description="Command timestamp (seconds)")
    sig: Optional[str] = Field(None, max_length=128, description="Command HMAC signature (hex)")
    trace_id: Optional[str] = Field(None, max_length=64, description="Trace ID for logging")

    def get_command_name(self) -> str:
        """Get command name from either 'cmd' or 'type' field."""
        return self.cmd or self.type or ""


class FillDrainRequest(BaseModel):
    """Request model for fill/drain operations."""

    target_level: float = Field(..., ge=0.0, le=1.0, description="Target water level (0.0-1.0)")
    max_duration_sec: Optional[int] = Field(300, ge=1, le=600, description="Maximum operation duration in seconds")


class CalibrateFlowRequest(BaseModel):
    """Request model for flow calibration."""

    node_id: int = Field(..., ge=1, description="Node ID with flow sensor")
    channel: str = Field(..., min_length=1, max_length=64, description="Flow sensor channel name")
    pump_duration_sec: Optional[int] = Field(10, ge=1, le=60, description="Pump duration for calibration")

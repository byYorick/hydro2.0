from datetime import datetime
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator


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
    flow_active: Optional[bool] = Field(
        None, description="Flow activity flag for correction gating (from firmware)"
    )
    corrections_allowed: Optional[bool] = Field(
        None, description="Correction permission flag for correction gating (from firmware)"
    )
    tds: Optional[Union[int, float]] = Field(None, description="TDS value (from node type ec)")
    error_code: Optional[Union[int, str]] = Field(None, description="Error code (from firmware)")
    temperature: Optional[float] = Field(None, description="Temperature value (from firmware)")
    state: Optional[str] = Field(None, max_length=50, description="State (from firmware)")
    event: Optional[str] = Field(None, max_length=100, description="Event (from firmware)")
    health: Optional[dict] = Field(None, description="Health metrics (from node type irrig)")
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

    cmd: Optional[str] = Field(None, max_length=64, description="Command name")
    legacy_type: Optional[str] = Field(
        None,
        alias="type",
        max_length=64,
        description="Legacy command alias (deprecated, rejected)",
    )
    params: Dict[str, Any] = Field(default_factory=dict, description="Command parameters")
    source: Optional[str] = Field(None, max_length=64, description="Command source (automation/api/device)")
    node_uid: Optional[str] = Field(None, max_length=128, description="Node UID")
    channel: Optional[str] = Field(None, max_length=64, description="Channel name")
    greenhouse_uid: Optional[str] = Field(None, max_length=128, description="Greenhouse UID")
    zone_id: Optional[int] = Field(None, ge=1, description="Zone ID")
    zone_uid: Optional[str] = Field(None, max_length=128, description="Zone UID")
    cmd_id: Optional[str] = Field(None, max_length=128, description="Command ID from Laravel")
    ts: Optional[int] = Field(None, description="Command timestamp (seconds)")
    sig: Optional[str] = Field(None, max_length=128, description="Command HMAC signature (hex)")
    trace_id: Optional[str] = Field(None, max_length=64, description="Trace ID for logging")

    def get_command_name(self) -> str:
        """Get command name."""
        return self.cmd or ""


class NodeConfigPublishRequest(BaseModel):
    """Request model for publishing node config to MQTT."""

    model_config = {"extra": "forbid"}

    greenhouse_uid: str = Field(..., max_length=128, description="Greenhouse UID")
    zone_id: Optional[int] = Field(None, ge=1, description="Zone ID")
    zone_uid: Optional[str] = Field(None, max_length=128, description="Zone UID")
    config: Dict[str, Any] = Field(..., description="Node config payload")


class FillDrainRequest(BaseModel):
    """Request model for fill/drain operations."""

    target_level: float = Field(..., ge=0.0, le=1.0, description="Target water level (0.0-1.0)")
    max_duration_sec: Optional[int] = Field(300, ge=1, le=600, description="Maximum operation duration in seconds")


class CalibrateFlowRequest(BaseModel):
    """Request model for flow calibration."""

    node_id: int = Field(..., ge=1, description="Node ID with flow sensor")
    channel: str = Field(..., min_length=1, max_length=64, description="Flow sensor channel name")
    pump_duration_sec: Optional[int] = Field(10, ge=1, le=60, description="Pump duration for calibration")


class CalibratePumpRequest(BaseModel):
    """Request model for dosing pump calibration."""

    node_channel_id: int = Field(..., ge=1, description="Actuator node_channel ID for pump")
    duration_sec: int = Field(..., ge=1, le=120, description="Pump run duration (seconds)")
    actual_ml: Optional[float] = Field(None, gt=0.0, description="Measured real volume in ml")
    skip_run: bool = Field(False, description="Skip physical run and only persist calibration")
    component: Optional[str] = Field(None, max_length=16, description="npk|calcium|magnesium|micro|ph_up|ph_down")
    test_volume_l: Optional[float] = Field(None, gt=0.0, description="Calibration test volume in liters")
    ec_before_ms: Optional[float] = Field(None, ge=0.0, le=20.0, description="EC before dosing, mS/cm")
    ec_after_ms: Optional[float] = Field(None, ge=0.0, le=20.0, description="EC after dosing, mS/cm")
    temperature_c: Optional[float] = Field(None, ge=0.0, le=50.0, description="Water temperature in Celsius")

    @field_validator("component")
    @classmethod
    def validate_component(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "phup": "ph_up",
            "phdown": "ph_down",
            "ph_base": "ph_up",
            "ph_acid": "ph_down",
            "base": "ph_up",
            "acid": "ph_down",
        }
        normalized = aliases.get(normalized, normalized)
        allowed = {"npk", "calcium", "magnesium", "micro", "ph_up", "ph_down"}
        if normalized not in allowed:
            raise ValueError("component must be one of npk|calcium|magnesium|micro|ph_up|ph_down")
        return normalized

    @model_validator(mode="after")
    def validate_ec_range(self) -> "CalibratePumpRequest":
        if self.ec_before_ms is not None and self.ec_after_ms is not None and self.ec_after_ms <= self.ec_before_ms:
            raise ValueError("ec_after_ms must be greater than ec_before_ms")
        return self

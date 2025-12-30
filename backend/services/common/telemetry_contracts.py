from datetime import datetime
from typing import Any, Dict, Optional, Literal

from pydantic import BaseModel, ConfigDict


class TelemetrySensorIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    greenhouse_id: int
    zone_id: Optional[int] = None
    node_id: Optional[int] = None
    scope: Literal["inside", "outside"]
    type: str
    label: str
    specs: Optional[Dict[str, Any]] = None


class TelemetrySample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensor_id: int
    ts: datetime
    value: float
    quality: Optional[Literal["GOOD", "BAD", "UNCERTAIN"]] = None
    metadata: Optional[Dict[str, Any]] = None
    zone_id: Optional[int] = None
    cycle_id: Optional[int] = None

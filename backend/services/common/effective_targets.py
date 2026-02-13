"""
Pydantic models for Effective Targets API responses.
Provides validation and type normalization for automation-engine consumers.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _empty_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


class PhaseInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    code: str
    name: str
    started_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    progress_model: Optional[str] = None


class PhTarget(BaseModel):
    model_config = ConfigDict(extra="allow")

    target: float
    min: Optional[float] = None
    max: Optional[float] = None

    _normalize_min = field_validator("min", mode="before")(_empty_to_none)
    _normalize_max = field_validator("max", mode="before")(_empty_to_none)


class EcTarget(BaseModel):
    model_config = ConfigDict(extra="allow")

    target: float
    min: Optional[float] = None
    max: Optional[float] = None

    _normalize_min = field_validator("min", mode="before")(_empty_to_none)
    _normalize_max = field_validator("max", mode="before")(_empty_to_none)


class IrrigationTarget(BaseModel):
    model_config = ConfigDict(extra="allow")

    mode: Optional[str] = None
    interval_sec: Optional[int] = None
    duration_sec: Optional[int] = None

    @field_validator("interval_sec", "duration_sec", mode="before")
    @classmethod
    def _normalize_int(cls, value: Any) -> Any:
        value = _empty_to_none(value)
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid integer value: {value}") from exc


class LightingTarget(BaseModel):
    model_config = ConfigDict(extra="allow")

    photoperiod_hours: Optional[float] = None
    start_time: Optional[str] = None

    _normalize_photoperiod = field_validator("photoperiod_hours", mode="before")(_empty_to_none)
    _normalize_start_time = field_validator("start_time", mode="before")(_empty_to_none)


class ClimateRequestTarget(BaseModel):
    model_config = ConfigDict(extra="allow")

    temp_air_target: Optional[float] = None
    humidity_target: Optional[float] = None
    co2_target: Optional[float] = None

    _normalize_temp = field_validator("temp_air_target", mode="before")(_empty_to_none)
    _normalize_humidity = field_validator("humidity_target", mode="before")(_empty_to_none)
    _normalize_co2 = field_validator("co2_target", mode="before")(_empty_to_none)


class NutritionComponentTarget(BaseModel):
    model_config = ConfigDict(extra="allow")

    ratio_pct: Optional[float] = None
    dose_ml_per_l: Optional[float] = None

    _normalize_ratio = field_validator("ratio_pct", mode="before")(_empty_to_none)
    _normalize_dose = field_validator("dose_ml_per_l", mode="before")(_empty_to_none)


class NutritionTarget(BaseModel):
    model_config = ConfigDict(extra="allow")

    program_code: Optional[str] = None
    components: Optional[Dict[str, NutritionComponentTarget]] = None


class EffectiveTargets(BaseModel):
    model_config = ConfigDict(extra="allow")

    ph: Optional[PhTarget] = None
    ec: Optional[EcTarget] = None
    irrigation: Optional[IrrigationTarget] = None
    lighting: Optional[LightingTarget] = None
    climate_request: Optional[ClimateRequestTarget] = None
    nutrition: Optional[NutritionTarget] = None
    mist: Optional[Dict[str, Any]] = None
    extensions: Optional[Dict[str, Any]] = None


class EffectiveTargetsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    cycle_id: int
    zone_id: int
    phase: PhaseInfo
    targets: EffectiveTargets = Field(default_factory=EffectiveTargets)


def parse_effective_targets(data: Dict[str, Any]) -> EffectiveTargetsResponse:
    """
    Validate and normalize Effective Targets API payloads.

    Raises:
        ValidationError: if the payload does not match the schema.
    """
    return EffectiveTargetsResponse.model_validate(data)

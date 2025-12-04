from typing import Any, Dict, Optional, Literal
from pydantic import BaseModel, Field, validator


class TelemetryPayload(BaseModel):
    node_id: str
    channel: str
    metric_type: str
    value: Optional[float] = None
    raw: Optional[Any] = None
    timestamp: Optional[int] = None


class CommandRequest(BaseModel):
    type: str = Field(..., max_length=64, description="Command type")
    params: Dict[str, Any] = Field(default_factory=dict, description="Command parameters")
    node_uid: Optional[str] = Field(None, max_length=128, description="Node UID")
    channel: Optional[str] = Field(None, max_length=64, description="Channel name")
    greenhouse_uid: Optional[str] = Field(None, max_length=128, description="Greenhouse UID")
    zone_id: Optional[int] = Field(None, ge=1, description="Zone ID")
    cmd_id: Optional[str] = Field(None, max_length=64, description="Command ID from Laravel")
    hardware_id: Optional[str] = Field(None, max_length=128, description="Hardware ID for temporary topic")
    
    @validator('type')
    def validate_command_type(cls, v):
        """Валидация типа команды."""
        allowed_types = [
            'run_pump', 'calibrate_ph', 'calibrate_ec', 'manual_dose',
            'adjust_ph', 'adjust_ec', 'fill', 'drain', 'calibrate_flow',
            'set_light', 'set_fan', 'set_heater', 'reboot', 'update_config'
        ]
        if v not in allowed_types:
            # Предупреждение, но не блокируем (для расширяемости)
            pass
        return v


class CommandResponse(BaseModel):
    cmd_id: str = Field(..., max_length=64)
    status: str = Field(..., description="Command status")
    ts: Optional[int] = Field(None, description="Timestamp")
    error_code: Optional[str] = Field(None, max_length=64)
    error_message: Optional[str] = Field(None, max_length=512)
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")
    
    @validator('status')
    def validate_status(cls, v):
        """Валидация статуса команды."""
        allowed_statuses = ['accepted', 'completed', 'failed', 'rejected', 'timeout']
        if v not in allowed_statuses:
            raise ValueError(f"Invalid status: {v}. Allowed: {allowed_statuses}")
        return v


class NodeConfigModel(BaseModel):
    """Модель для конфигурации узла."""
    node_id: Optional[str] = Field(None, max_length=128, description="Node UID")
    version: Optional[int] = Field(None, ge=1, description="Config version")
    type: Optional[str] = Field(None, max_length=32, description="Node type")
    node_type: Optional[str] = Field(None, max_length=32, description="Node type (legacy)")
    zone_id: Optional[int] = Field(None, ge=1, description="Zone ID")
    zone_uid: Optional[str] = Field(None, max_length=128, description="Zone UID")
    gh_uid: Optional[str] = Field(None, max_length=128, description="Greenhouse UID")
    channel: Optional[str] = Field(None, max_length=64, description="Channel name (legacy)")
    channels: Optional[list] = Field(None, description="List of node channels")
    wifi: Optional[Dict[str, Any]] = Field(None, description="WiFi configuration")
    mqtt: Optional[Dict[str, Any]] = Field(None, description="MQTT configuration")
    calibration: Optional[Dict[str, Any]] = None
    thresholds: Optional[Dict[str, float]] = None
    schedule: Optional[Dict[str, Any]] = None
    
    class Config:
        extra = "allow"  # Разрешаем дополнительные поля для обратной совместимости
    
    @validator('node_type', 'type')
    def validate_node_type(cls, v):
        """Валидация типа узла."""
        if v:
            allowed_types = ['ph', 'ec', 'climate', 'pump', 'irrig', 'light', 'unknown']
            if v not in allowed_types:
                # Предупреждение, но не блокируем (для расширяемости)
                pass
        return v


class SimulationScenario(BaseModel):
    """Модель для сценария симуляции."""
    recipe_id: Optional[int] = Field(None, ge=1, description="Recipe ID")
    initial_state: Optional[Dict[str, float]] = Field(None, description="Initial state")
    
    @validator('initial_state')
    def validate_initial_state(cls, v):
        """Валидация начального состояния."""
        if v:
            allowed_keys = {'ph', 'ec', 'temp_air', 'temp_water', 'humidity_air'}
            for key in v.keys():
                if key not in allowed_keys:
                    raise ValueError(f"Unknown initial_state key: {key}. Allowed: {allowed_keys}")
            # Валидация диапазонов значений
            if 'ph' in v:
                if not (0 <= v['ph'] <= 14):
                    raise ValueError("ph must be between 0 and 14")
            if 'ec' in v:
                if v['ec'] < 0:
                    raise ValueError("ec must be >= 0")
            if 'humidity_air' in v:
                if not (0 <= v['humidity_air'] <= 100):
                    raise ValueError("humidity_air must be between 0 and 100")
        return v


class SimulationRequest(BaseModel):
    """Модель для запроса симуляции."""
    zone_id: int = Field(..., ge=1, description="Zone ID")
    duration_hours: int = Field(72, ge=1, le=720, description="Simulation duration in hours")
    step_minutes: int = Field(5, ge=1, le=60, description="Simulation step in minutes")
    scenario: SimulationScenario = Field(default_factory=SimulationScenario, description="Simulation scenario")

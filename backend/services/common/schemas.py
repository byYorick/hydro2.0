from typing import Any, Dict, Optional, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
import time

from common.node_types import CANONICAL_NODE_TYPES, normalize_node_type


class TelemetryPayload(BaseModel):
    node_id: str
    channel: str
    metric_type: str
    value: Optional[float] = None
    raw: Optional[Any] = None
    timestamp: Optional[int] = None


# ============================================================================
# Единый контракт команд (Protocol/Contracts Agent)
# ============================================================================

class Command(BaseModel):
    """
    Единый контракт команды для всех сервисов.
    Соответствует JSON схеме: schemas/command.json
    """
    cmd_id: str = Field(..., max_length=128, description="Уникальный идентификатор команды")
    cmd: str = Field(..., max_length=64, description="Тип команды")
    params: Dict[str, Any] = Field(default_factory=dict, description="Параметры команды")
    ts: int = Field(..., description="Unix timestamp создания команды в секундах")
    sig: str = Field(..., max_length=128, description="HMAC подпись команды (hex)")
    
    @field_validator('cmd_id', 'sig')
    @classmethod
    def validate_id_format(cls, v):
        """Валидация формата идентификатора/подписи."""
        if v and not all(c.isalnum() or c in '_-' for c in v):
            raise ValueError(f"Invalid format: {v}. Only alphanumeric, underscore and dash allowed")
        return v
    
    @classmethod
    def create(
        cls,
        cmd: str,
        params: Optional[Dict[str, Any]] = None,
        cmd_id: Optional[str] = None,
        sig: Optional[str] = None
    ) -> 'Command':
        """Создает команду с автоматической генерацией cmd_id и ts."""
        import uuid
        return cls(
            cmd_id=cmd_id or str(uuid.uuid4()),
            cmd=cmd,
            params=params or {},
            ts=int(time.time()),
            sig=sig or "dev-signature"
        )


class CommandResponse(BaseModel):
    """
    Единый контракт ответа на команду для всех сервисов.
    Соответствует JSON схеме: schemas/command_response.json
    """
    cmd_id: str = Field(..., max_length=128, description="Идентификатор команды")
    status: Literal["ACK", "DONE", "ERROR", "INVALID", "BUSY", "NO_EFFECT"] = Field(
        ..., description="Статус выполнения команды"
    )
    ts: int = Field(..., description="Unix timestamp ответа в миллисекундах")
    details: Optional[Dict[str, Any]] = Field(None, description="Дополнительные детали ответа")
    
    @classmethod
    def ack(cls, cmd_id: str, ts: Optional[int] = None) -> 'CommandResponse':
        """Создает ответ со статусом ACK."""
        return cls(
            cmd_id=cmd_id,
            status="ACK",
            ts=ts or int(time.time() * 1000)
        )
    
    @classmethod
    def done(cls, cmd_id: str, details: Optional[Dict[str, Any]] = None, ts: Optional[int] = None) -> 'CommandResponse':
        """Создает ответ со статусом DONE."""
        return cls(
            cmd_id=cmd_id,
            status="DONE",
            ts=ts or int(time.time() * 1000),
            details=details
        )
    
    @classmethod
    def error(cls, cmd_id: str, details: Optional[Dict[str, Any]] = None, ts: Optional[int] = None) -> 'CommandResponse':
        """Создает ответ со статусом ERROR."""
        return cls(
            cmd_id=cmd_id,
            status="ERROR",
            ts=ts or int(time.time() * 1000),
            details=details
        )


class CommandRequest(BaseModel):
    """HTTP модель для команд (strict format)."""
    cmd: str = Field(..., max_length=64, description="Command name")
    params: Dict[str, Any] = Field(default_factory=dict, description="Command parameters")
    node_uid: Optional[str] = Field(None, max_length=128, description="Node UID")
    channel: Optional[str] = Field(None, max_length=64, description="Channel name")
    greenhouse_uid: Optional[str] = Field(None, max_length=128, description="Greenhouse UID")
    zone_id: Optional[int] = Field(None, ge=1, description="Zone ID")
    cmd_id: Optional[str] = Field(None, max_length=64, description="Command ID from Laravel")
    hardware_id: Optional[str] = Field(None, max_length=128, description="Hardware ID for temporary topic")
    ts: Optional[int] = Field(None, description="Command timestamp (seconds)")
    sig: Optional[str] = Field(None, max_length=128, description="Command HMAC signature (hex)")
    
    def to_command(self) -> Command:
        """Конвертирует CommandRequest в единый контракт Command."""
        return Command.create(
            cmd=self.cmd,
            params=self.params,
            cmd_id=self.cmd_id,
            sig=self.sig
        )
    
    @field_validator('cmd')
    @classmethod
    def validate_command_type(cls, v):
        """Валидация типа команды."""
        allowed_types = [
            'dose', 'run_pump', 'set_relay', 'set_pwm', 'test_sensor', 'restart'
        ]
        if v not in allowed_types:
            # Предупреждение, но не блокируем (для расширяемости)
            pass
        return v



class NodeConfigModel(BaseModel):
    """Модель для конфигурации узла."""
    model_config = ConfigDict(extra="allow")

    node_id: Optional[str] = Field(None, max_length=128, description="Node UID")
    version: Optional[int] = Field(None, ge=1, description="Config version")
    type: Optional[str] = Field(None, max_length=32, description="Node type")
    zone_id: Optional[int] = Field(None, ge=1, description="Zone ID")
    zone_uid: Optional[str] = Field(None, max_length=128, description="Zone UID")
    gh_uid: Optional[str] = Field(None, max_length=128, description="Greenhouse UID")
    channels: Optional[list] = Field(None, description="List of node channels")
    wifi: Optional[Dict[str, Any]] = Field(None, description="WiFi configuration")
    mqtt: Optional[Dict[str, Any]] = Field(None, description="MQTT configuration")
    calibration: Optional[Dict[str, Any]] = None
    thresholds: Optional[Dict[str, float]] = None
    schedule: Optional[Dict[str, Any]] = None
    
    @field_validator('type')
    @classmethod
    def validate_node_type(cls, v):
        """Валидация типа узла."""
        if v is None:
            return v

        normalized = normalize_node_type(v)
        if normalized == "unknown" and str(v).strip().lower() != "unknown":
            allowed_types = ", ".join(sorted(CANONICAL_NODE_TYPES))
            raise ValueError(f"type must be one of canonical node types: {allowed_types}")
        return normalized


class SimulationScenario(BaseModel):
    """Модель для сценария симуляции."""
    recipe_id: Optional[int] = Field(None, ge=1, description="Recipe ID")
    initial_state: Optional[Dict[str, float]] = Field(None, description="Initial state")
    
    @field_validator('initial_state')
    @classmethod
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

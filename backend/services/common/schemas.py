from typing import Any, Dict, Optional, Literal
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
import time


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
    ts: int = Field(..., description="Unix timestamp создания команды в миллисекундах")
    params: Dict[str, Any] = Field(default_factory=dict, description="Параметры команды")
    deadline_ms: Optional[int] = Field(None, ge=0, description="Дедлайн выполнения команды в миллисекундах")
    attempt: int = Field(1, ge=1, description="Номер попытки выполнения команды")
    correlation_id: Optional[str] = Field(None, max_length=128, description="Альтернативное поле для cmd_id (обратная совместимость)")
    
    @field_validator('cmd_id', 'correlation_id')
    @classmethod
    def validate_id_format(cls, v):
        """Валидация формата идентификатора."""
        if v and not all(c.isalnum() or c in '_-' for c in v):
            raise ValueError(f"Invalid ID format: {v}. Only alphanumeric, underscore and dash allowed")
        return v
    
    @classmethod
    def create(cls, cmd: str, params: Optional[Dict[str, Any]] = None, cmd_id: Optional[str] = None, 
               deadline_ms: Optional[int] = None, attempt: int = 1) -> 'Command':
        """Создает команду с автоматической генерацией cmd_id и ts."""
        import uuid
        return cls(
            cmd_id=cmd_id or str(uuid.uuid4()),
            cmd=cmd,
            params=params or {},
            ts=int(time.time() * 1000),
            deadline_ms=deadline_ms,
            attempt=attempt
        )


class CommandResponse(BaseModel):
    """
    Единый контракт ответа на команду для всех сервисов.
    Соответствует JSON схеме: schemas/command_response.json
    """
    cmd_id: str = Field(..., max_length=128, description="Идентификатор команды")
    status: Literal["ACCEPTED", "DONE", "FAILED"] = Field(..., description="Статус выполнения команды")
    ts: int = Field(..., description="Unix timestamp ответа в миллисекундах")
    result_code: int = Field(0, ge=0, description="Код результата выполнения (0 = успех)")
    error_code: Optional[str] = Field(None, max_length=64, description="Символический код ошибки")
    error_message: Optional[str] = Field(None, max_length=512, description="Человекочитаемое сообщение об ошибке")
    duration_ms: Optional[int] = Field(None, ge=0, description="Длительность выполнения команды в миллисекундах")
    
    @classmethod
    def accepted(cls, cmd_id: str, ts: Optional[int] = None) -> 'CommandResponse':
        """Создает ответ со статусом ACCEPTED."""
        return cls(
            cmd_id=cmd_id,
            status="ACCEPTED",
            ts=ts or int(time.time() * 1000),
            result_code=0
        )
    
    @classmethod
    def done(cls, cmd_id: str, duration_ms: Optional[int] = None, ts: Optional[int] = None) -> 'CommandResponse':
        """Создает ответ со статусом DONE."""
        return cls(
            cmd_id=cmd_id,
            status="DONE",
            ts=ts or int(time.time() * 1000),
            result_code=0,
            duration_ms=duration_ms
        )
    
    @classmethod
    def failed(cls, cmd_id: str, error_code: Optional[str] = None, error_message: Optional[str] = None,
               result_code: int = 1, ts: Optional[int] = None) -> 'CommandResponse':
        """Создает ответ со статусом FAILED."""
        return cls(
            cmd_id=cmd_id,
            status="FAILED",
            ts=ts or int(time.time() * 1000),
            result_code=result_code,
            error_code=error_code,
            error_message=error_message
        )


# ============================================================================
# Legacy модели (для обратной совместимости)
# ============================================================================

class CommandRequest(BaseModel):
    """
    Legacy модель для HTTP запросов команд.
    Используется для совместимости с существующими API endpoints.
    """
    type: str = Field(..., max_length=64, description="Command type")
    params: Dict[str, Any] = Field(default_factory=dict, description="Command parameters")
    node_uid: Optional[str] = Field(None, max_length=128, description="Node UID")
    channel: Optional[str] = Field(None, max_length=64, description="Channel name")
    greenhouse_uid: Optional[str] = Field(None, max_length=128, description="Greenhouse UID")
    zone_id: Optional[int] = Field(None, ge=1, description="Zone ID")
    cmd_id: Optional[str] = Field(None, max_length=64, description="Command ID from Laravel")
    hardware_id: Optional[str] = Field(None, max_length=128, description="Hardware ID for temporary topic")
    
    def to_command(self) -> Command:
        """Конвертирует CommandRequest в единый контракт Command."""
        return Command.create(
            cmd=self.type,
            params=self.params,
            cmd_id=self.cmd_id
        )
    
    @field_validator('type')
    @classmethod
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


# Legacy CommandResponse для обратной совместимости
# Используется в старых частях кода, которые еще не переведены на единый контракт
class LegacyCommandResponse(BaseModel):
    """Legacy модель ответа для обратной совместимости."""
    cmd_id: str = Field(..., max_length=64)
    status: str = Field(..., description="Command status")
    ts: Optional[int] = Field(None, description="Timestamp")
    error_code: Optional[str] = Field(None, max_length=64)
    error_message: Optional[str] = Field(None, max_length=512)
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")
    
    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        """Валидация статуса команды."""
        allowed_statuses = ['accepted', 'completed', 'failed', 'rejected', 'timeout']
        if v not in allowed_statuses:
            raise ValueError(f"Invalid status: {v}. Allowed: {allowed_statuses}")
        return v
    
    def to_command_response(self) -> CommandResponse:
        """Конвертирует LegacyCommandResponse в единый контракт CommandResponse."""
        status_map = {
            'accepted': 'ACCEPTED',
            'completed': 'DONE',
            'failed': 'FAILED',
            'rejected': 'FAILED',
            'timeout': 'FAILED'
        }
        return CommandResponse(
            cmd_id=self.cmd_id,
            status=status_map.get(self.status.lower(), 'FAILED'),
            ts=self.ts or int(time.time() * 1000),
            error_code=self.error_code,
            error_message=self.error_message
        )


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
    
    @field_validator('node_type', 'type')
    @classmethod
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

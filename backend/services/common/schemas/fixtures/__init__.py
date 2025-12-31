"""
Тестовые fixtures для единого контракта команд.

Используются для тестирования и примеров использования.
"""
import time
from typing import Dict, Any, Optional


def create_command_fixture(
    cmd: str = "dose",
    params: Optional[Dict[str, Any]] = None,
    cmd_id: Optional[str] = None,
    deadline_ms: Optional[int] = None,
    attempt: int = 1
) -> Dict[str, Any]:
    """
    Создает fixture команды в формате JSON.
    
    Args:
        cmd: Тип команды
        params: Параметры команды
        cmd_id: Идентификатор команды (генерируется автоматически если не указан)
        deadline_ms: Дедлайн выполнения
        attempt: Номер попытки
    
    Returns:
        Словарь с данными команды
    """
    if params is None:
        params = {}
    
    if cmd_id is None:
        import uuid
        cmd_id = str(uuid.uuid4())
    
    ts = int(time.time() * 1000)
    
    return {
        "cmd_id": cmd_id,
        "cmd": cmd,
        "params": params,
        "ts": ts,
        "deadline_ms": deadline_ms,
        "attempt": attempt
    }


def create_command_response_fixture(
    cmd_id: str,
    status: str = "DONE",
    result_code: int = 0,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None
) -> Dict[str, Any]:
    """
    Создает fixture ответа на команду в формате JSON.
    
    Args:
        cmd_id: Идентификатор команды
        status: Статус (ACCEPTED|DONE|FAILED)
        result_code: Код результата (0 = успех)
        error_code: Символический код ошибки
        error_message: Сообщение об ошибке
        duration_ms: Длительность выполнения
    
    Returns:
        Словарь с данными ответа
    """
    ts = int(time.time() * 1000)
    
    response = {
        "cmd_id": cmd_id,
        "status": status,
        "ts": ts,
        "result_code": result_code
    }
    
    if duration_ms is not None:
        response["duration_ms"] = duration_ms
    
    if error_code:
        response["error_code"] = error_code
    
    if error_message:
        response["error_message"] = error_message
    
    return response


FIXTURE_COMMAND_DOSE = create_command_fixture(
    cmd="dose",
    params={"ml": 1.2, "channel": "pump_nutrient"}
)

FIXTURE_COMMAND_RUN_PUMP = create_command_fixture(
    cmd="run_pump",
    params={"duration_sec": 30, "channel": "pump_irrigation"}
)

FIXTURE_COMMAND_CALIBRATE_PH = create_command_fixture(
    cmd="calibrate_ph",
    params={"value": 7.0, "channel": "ph_sensor"}
)

FIXTURE_RESPONSE_ACCEPTED = create_command_response_fixture(
    cmd_id="cmd-abc123",
    status="ACCEPTED"
)

FIXTURE_RESPONSE_DONE = create_command_response_fixture(
    cmd_id="cmd-abc123",
    status="DONE",
    duration_ms=1000
)

FIXTURE_RESPONSE_FAILED = create_command_response_fixture(
    cmd_id="cmd-abc123",
    status="FAILED",
    result_code=1,
    error_code="TIMEOUT",
    error_message="Command execution timeout"
)

FIXTURE_RESPONSE_FAILED_INVALID_PARAMS = create_command_response_fixture(
    cmd_id="cmd-abc123",
    status="FAILED",
    result_code=2,
    error_code="INVALID_PARAMS",
    error_message="Invalid parameter value: ml must be positive"
)

FIXTURE_RESPONSE_FAILED_DEVICE_ERROR = create_command_response_fixture(
    cmd_id="cmd-abc123",
    status="FAILED",
    result_code=3,
    error_code="DEVICE_ERROR",
    error_message="Device not responding"
)


def get_all_command_fixtures() -> Dict[str, Dict[str, Any]]:
    """Возвращает все fixtures команд."""
    return {
        "dose": FIXTURE_COMMAND_DOSE,
        "run_pump": FIXTURE_COMMAND_RUN_PUMP,
        "calibrate_ph": FIXTURE_COMMAND_CALIBRATE_PH,
    }


def get_all_response_fixtures() -> Dict[str, Dict[str, Any]]:
    """Возвращает все fixtures ответов."""
    return {
        "accepted": FIXTURE_RESPONSE_ACCEPTED,
        "done": FIXTURE_RESPONSE_DONE,
        "failed": FIXTURE_RESPONSE_FAILED,
        "failed_invalid_params": FIXTURE_RESPONSE_FAILED_INVALID_PARAMS,
        "failed_device_error": FIXTURE_RESPONSE_FAILED_DEVICE_ERROR,
    }


__all__ = [
    "create_command_fixture",
    "create_command_response_fixture",
    "get_all_command_fixtures",
    "get_all_response_fixtures",
]

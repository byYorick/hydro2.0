"""
Тестовые fixtures для единого контракта команд.

Используются для тестирования и примеров использования.
"""
import time
from typing import Dict, Any, Optional
import sys
from pathlib import Path

# Импорты для использования в тестах
# В реальном использовании импортируйте напрямую: from common.schemas import Command, CommandResponse
try:
    from common.schemas import Command, CommandResponse
except ImportError:
    # Fallback для случаев, когда модуль используется напрямую
    import sys
    parent_dir = Path(__file__).parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))
    from schemas import Command, CommandResponse


def create_command_fixture(
    cmd: str = "dose",
    params: Optional[Dict[str, Any]] = None,
    cmd_id: Optional[str] = None,
    sig: Optional[str] = None
) -> Dict[str, Any]:
    """
    Создает fixture команды в формате JSON.
    
    Args:
        cmd: Тип команды
        params: Параметры команды
        cmd_id: Идентификатор команды (генерируется автоматически если не указан)
        sig: HMAC подпись команды
    
    Returns:
        Словарь с данными команды
    """
    if params is None:
        params = {}
    
    if cmd_id is None:
        import uuid
        cmd_id = str(uuid.uuid4())
    
    ts = int(time.time())
    
    return {
        "cmd_id": cmd_id,
        "cmd": cmd,
        "params": params,
        "ts": ts,
        "sig": sig or "test-signature"
    }


def create_command_response_fixture(
    cmd_id: str,
    status: str = "DONE",
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Создает fixture ответа на команду в формате JSON.
    
    Args:
        cmd_id: Идентификатор команды
        status: Статус (ACK|DONE|ERROR|INVALID|BUSY|NO_EFFECT)
        details: Дополнительные детали
    
    Returns:
        Словарь с данными ответа
    """
    ts = int(time.time() * 1000)
    
    response = {
        "cmd_id": cmd_id,
        "status": status,
        "ts": ts
    }

    if details:
        response["details"] = details
    
    return response


# Примеры fixtures для различных сценариев

FIXTURE_COMMAND_DOSE = create_command_fixture(
    cmd="dose",
    params={"ml": 1.2}
)

FIXTURE_COMMAND_RUN_PUMP = create_command_fixture(
    cmd="run_pump",
    params={"duration_ms": 30000}
)

FIXTURE_COMMAND_SET_RELAY = create_command_fixture(
    cmd="set_relay",
    params={"state": True}
)

FIXTURE_RESPONSE_ACK = create_command_response_fixture(
    cmd_id="cmd-abc123",
    status="ACK"
)

FIXTURE_RESPONSE_DONE = create_command_response_fixture(
    cmd_id="cmd-abc123",
    status="DONE",
    details={"duration_ms": 1000}
)

FIXTURE_RESPONSE_ERROR = create_command_response_fixture(
    cmd_id="cmd-abc123",
    status="ERROR",
    details={"error_code": "TIMEOUT", "error_message": "Command execution timeout"}
)

FIXTURE_RESPONSE_INVALID = create_command_response_fixture(
    cmd_id="cmd-abc123",
    status="INVALID",
    details={"error_code": "INVALID_PARAMS", "error_message": "Invalid parameter value: ml must be positive"}
)

FIXTURE_RESPONSE_BUSY = create_command_response_fixture(
    cmd_id="cmd-abc123",
    status="BUSY",
    details={"retry_after_ms": 2000}
)


def get_all_command_fixtures() -> Dict[str, Dict[str, Any]]:
    """Возвращает все fixtures команд."""
    return {
        "dose": FIXTURE_COMMAND_DOSE,
        "run_pump": FIXTURE_COMMAND_RUN_PUMP,
        "set_relay": FIXTURE_COMMAND_SET_RELAY,
    }


def get_all_response_fixtures() -> Dict[str, Dict[str, Any]]:
    """Возвращает все fixtures ответов."""
    return {
        "ack": FIXTURE_RESPONSE_ACK,
        "done": FIXTURE_RESPONSE_DONE,
        "error": FIXTURE_RESPONSE_ERROR,
        "invalid": FIXTURE_RESPONSE_INVALID,
        "busy": FIXTURE_RESPONSE_BUSY,
    }

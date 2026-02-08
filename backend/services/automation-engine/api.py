"""
FastAPI endpoints для automation-engine.
Предоставляет REST API для scheduler и других сервисов.
"""
from fastapi import FastAPI, HTTPException, Body, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import logging
import os
from datetime import datetime
from infrastructure import CommandBus
from common.infra_alerts import send_infra_exception_alert
from common.trace_context import extract_trace_id_from_headers
from utils.logging_context import set_trace_id

logger = logging.getLogger(__name__)

app = FastAPI(title="Automation Engine API")


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = extract_trace_id_from_headers(request.headers)
    if trace_id:
        set_trace_id(trace_id)
    else:
        trace_id = set_trace_id()
    response = await call_next(request)
    if trace_id:
        response.headers["X-Trace-Id"] = trace_id
    return response

# Глобальные переменные для доступа к CommandBus
_command_bus: Optional[CommandBus] = None
_gh_uid: str = ""

# Test hooks для детерминированных ошибок (только в test mode)
_test_mode = os.getenv("AE_TEST_MODE", "0") == "1"
_test_hooks: Dict[str, Dict[str, Any]] = {}  # zone_id -> {controller: error_type, ...}
_zone_states_override: Dict[int, Dict[str, Any]] = {}  # zone_id -> {error_streak: int, next_allowed_run_at: datetime}


def set_command_bus(command_bus: CommandBus, gh_uid: str):
    """Установить CommandBus для использования в endpoints."""
    global _command_bus, _gh_uid
    _command_bus = command_bus
    _gh_uid = gh_uid


class SchedulerCommandRequest(BaseModel):
    """Request model для команд от scheduler."""
    zone_id: int = Field(..., ge=1, description="Zone ID")
    node_uid: str = Field(..., min_length=1, max_length=128, description="Node UID")
    channel: str = Field(..., min_length=1, max_length=64, description="Channel name")
    cmd: str = Field(..., min_length=1, max_length=64, description="Command name")
    params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Command parameters")


@app.post("/scheduler/command")
async def scheduler_command(request: Request, req: SchedulerCommandRequest = Body(...)):
    """
    Endpoint для scheduler для отправки команд через automation-engine.
    Scheduler не должен общаться с нодами напрямую, только через automation-engine.
    """
    if not _command_bus:
        raise HTTPException(status_code=503, detail="CommandBus not initialized")
    
    try:
        logger.info(
            f"Scheduler command request: zone_id={req.zone_id}, node_uid={req.node_uid}, "
            f"channel={req.channel}, cmd={req.cmd}",
            extra={"zone_id": req.zone_id, "node_uid": req.node_uid}
        )
        
        # Отправляем команду через CommandBus (который использует history-logger)
        success = await _command_bus.publish_command(
            zone_id=req.zone_id,
            node_uid=req.node_uid,
            channel=req.channel,
            cmd=req.cmd,
            params=req.params
        )
        
        if success:
            return {
                "status": "ok",
                "data": {
                    "zone_id": req.zone_id,
                    "node_uid": req.node_uid,
                    "channel": req.channel,
                    "cmd": req.cmd
                }
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to publish command")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error processing scheduler command: {e}",
            exc_info=True,
            extra={"zone_id": req.zone_id, "node_uid": req.node_uid}
        )
        await send_infra_exception_alert(
            error=e,
            code="infra_unknown_error",
            alert_type="Automation API Unexpected Error",
            severity="error",
            zone_id=req.zone_id,
            service="automation-engine",
            component="api:/scheduler/command",
            node_uid=req.node_uid,
            channel=req.channel,
            cmd=req.cmd,
        )
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "automation-engine"}


# Test hooks (только в test mode)
class TestHookRequest(BaseModel):
    """Request model для test hooks."""
    zone_id: int = Field(..., ge=1, description="Zone ID")
    controller: Optional[str] = Field(None, description="Controller name (climate, ph, ec, irrigation, etc.)")
    action: str = Field(..., description="Action: inject_error, clear_error, reset_backoff, set_state")
    error_type: Optional[str] = Field(None, description="Error type for inject_error")
    state: Optional[Dict[str, Any]] = Field(None, description="State override for set_state")


def _parse_optional_datetime(value: Any, field_name: str) -> Optional[datetime]:
    """Нормализовать datetime-поле override из JSON (None|ISO string|datetime)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return None
        # Поддержка ISO вида 2099-01-01T00:00:00Z
        if raw.endswith("Z"):
            raw = f"{raw[:-1]}+00:00"
        try:
            return datetime.fromisoformat(raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid datetime format for '{field_name}': {value}",
            ) from exc
    raise HTTPException(
        status_code=400,
        detail=f"Field '{field_name}' must be null or ISO datetime string",
    )


def _normalize_state_override(state: Dict[str, Any]) -> Dict[str, Any]:
    """Привести override состояния зоны к безопасному внутреннему формату."""
    error_streak_raw = state.get("error_streak", 0)
    try:
        error_streak = int(error_streak_raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Field 'error_streak' must be integer, got: {error_streak_raw}",
        ) from exc
    if error_streak < 0:
        raise HTTPException(status_code=400, detail="Field 'error_streak' must be >= 0")

    return {
        "error_streak": error_streak,
        "next_allowed_run_at": _parse_optional_datetime(state.get("next_allowed_run_at"), "next_allowed_run_at"),
        "last_backoff_reported_until": _parse_optional_datetime(state.get("last_backoff_reported_until"), "last_backoff_reported_until"),
        "degraded_alert_active": bool(state.get("degraded_alert_active", False)),
        "last_missing_targets_report_at": _parse_optional_datetime(state.get("last_missing_targets_report_at"), "last_missing_targets_report_at"),
    }


@app.post("/test/hook")
async def test_hook(req: TestHookRequest = Body(...)):
    """
    Test hook для детерминированных ошибок и управления состоянием.
    Доступен только если AE_TEST_MODE=1.
    """
    if not _test_mode:
        raise HTTPException(status_code=403, detail="Test mode is not enabled (AE_TEST_MODE=0)")
    
    zone_id = req.zone_id
    controller = req.controller
    action = req.action
    
    if action == "inject_error":
        if not controller or not req.error_type:
            raise HTTPException(status_code=400, detail="inject_error requires controller and error_type")
        
        if zone_id not in _test_hooks:
            _test_hooks[zone_id] = {}
        _test_hooks[zone_id][controller] = {"error_type": req.error_type, "active": True}
        
        logger.info(f"[TEST_HOOK] Injected error for zone {zone_id}, controller {controller}: {req.error_type}")
        return {"status": "ok", "message": f"Error injected for zone {zone_id}, controller {controller}"}
    
    elif action == "clear_error":
        if controller:
            if zone_id in _test_hooks and controller in _test_hooks[zone_id]:
                del _test_hooks[zone_id][controller]
                if not _test_hooks[zone_id]:
                    del _test_hooks[zone_id]
        else:
            # Очистить все ошибки для зоны
            if zone_id in _test_hooks:
                del _test_hooks[zone_id]
        
        logger.info(f"[TEST_HOOK] Cleared errors for zone {zone_id}, controller {controller or 'all'}")
        return {"status": "ok", "message": f"Errors cleared for zone {zone_id}"}
    
    elif action == "reset_backoff":
        # Сброс backoff состояния для зоны
        _zone_states_override[zone_id] = _normalize_state_override({"error_streak": 0})
        
        logger.info(f"[TEST_HOOK] Reset backoff for zone {zone_id}")
        return {"status": "ok", "message": f"Backoff reset for zone {zone_id}"}
    
    elif action == "set_state":
        if not req.state:
            raise HTTPException(status_code=400, detail="set_state requires state")
        
        normalized_state = _normalize_state_override(req.state)
        _zone_states_override[zone_id] = normalized_state
        logger.info(f"[TEST_HOOK] Set state for zone {zone_id}: {normalized_state}")
        return {"status": "ok", "message": f"State set for zone {zone_id}"}
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action}")


@app.get("/test/hook/{zone_id}")
async def get_test_hook(zone_id: int):
    """Получить текущее состояние test hooks для зоны."""
    if not _test_mode:
        raise HTTPException(status_code=403, detail="Test mode is not enabled")
    
    hooks = _test_hooks.get(zone_id, {})
    state = _zone_states_override.get(zone_id, {})
    
    return {
        "status": "ok",
        "data": {
            "zone_id": zone_id,
            "hooks": hooks,
            "state_override": state
        }
    }


def get_test_hook_for_zone(zone_id: int, controller: str) -> Optional[Dict[str, Any]]:
    """Получить test hook для зоны и контроллера (используется в ZoneAutomationService)."""
    if not _test_mode:
        return None
    if zone_id in _test_hooks and controller in _test_hooks[zone_id]:
        return _test_hooks[zone_id][controller]
    return None


def get_zone_state_override(zone_id: int) -> Optional[Dict[str, Any]]:
    """Получить override состояния для зоны (используется в ZoneAutomationService)."""
    if not _test_mode:
        return None
    return _zone_states_override.get(zone_id)
